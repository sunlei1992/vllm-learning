"""Single-engine layerwise shared-buffer connector for vLLM CPU.

All shared layers alias one KV tensor.  Before a layer runs, its historical
KV is restored from the connector store; after it runs, the updated tensor is
saved.  This is the missing fence between physical slot reuse and decode.
"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass, field
from typing import Any

import torch

from vllm.distributed.kv_transfer.kv_connector.v1.base import (
    KVConnectorBase_V1,
    KVConnectorMetadata,
    KVConnectorRole,
)
from vllm.logger import init_logger

logger = init_logger(__name__)


@dataclass(frozen=True)
class RequestMeta:
    request_id: str


@dataclass
class Metadata(KVConnectorMetadata):
    requests: tuple[RequestMeta, ...] = ()


@dataclass
class LayerwiseSharedBufferConnector(KVConnectorBase_V1):
    _pending: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _store: dict[tuple[str, str], Any] = field(default_factory=dict, init=False, repr=False)
    _kv_caches: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _current_key: str | None = field(default=None, init=False, repr=False)

    def __init__(self, vllm_config, role, kv_cache_config):
        super().__init__(vllm_config, role, kv_cache_config)
        self._pending = {}
        self._store = {}
        self._kv_caches = {}
        self._current_key = None
        extra = self._kv_transfer_config.kv_connector_extra_config
        self._mooncake = None
        self._versions: dict[tuple[str, str], int] = {}
        self._latest: dict[tuple[str, str], str] = {}
        self._checksums: dict[str, str] = {}
        self._saved_ptrs: dict[str, int] = {}
        self._saved_shapes: dict[str, tuple[int, ...]] = {}
        master = extra.get("mooncake_master")
        if master:
            from mooncake_tcp_transport import connect_mooncake_tcp_session
            self._mooncake = connect_mooncake_tcp_session(
                master_server_addr=master,
                num_shards=1,
                key_prefix=extra.get("mooncake_key_prefix", "shared"),
                global_segment_size=extra.get("mooncake_segment_size", 2 * 1024**3),
                local_buffer_size=extra.get("mooncake_local_buffer", 256 * 1024**2),
            )

    def _sum(self, tensor):
        return hashlib.sha256(
            tensor.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()
        ).hexdigest()

    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        del request, num_computed_tokens
        return 0, False

    def update_state_after_alloc(self, request, blocks, num_external_tokens):
        del blocks, num_external_tokens
        self._pending[request.request_id] = request.request_id

    def build_connector_meta(self, scheduler_output):
        ids = set(self._pending)
        for req in getattr(scheduler_output, "scheduled_new_reqs", ()):
            ids.add(req.req_id)
        cached = getattr(scheduler_output, "scheduled_cached_reqs", None)
        if cached is not None:
            ids.update(cached.req_ids)
        print("CONN_META", sorted(ids), flush=True)
        return Metadata(tuple(RequestMeta(request_id) for request_id in sorted(ids)))

    def request_finished(self, request, block_ids):
        del block_ids
        self._pending.pop(request.request_id, None)
        return False, None

    def register_kv_caches(self, kv_caches):
        self._kv_caches = dict(kv_caches)

    def start_load_kv(self, forward_context, **kwargs):
        del forward_context, kwargs
        if not self.has_connector_metadata():
            return
        metadata = self._get_connector_metadata()
        if isinstance(metadata, Metadata) and metadata.requests:
            self._current_key = metadata.requests[0].request_id
            print("CONN_START", self._current_key, len(metadata.requests), flush=True)

    def wait_for_layer_load(self, layer_name):
        if self._current_key is None:
            return
        from vllm.forward_context import get_forward_context
        ctx = get_forward_context()
        tensor = getattr(ctx.no_compile_layers[layer_name], "kv_cache", None)
        if tensor is None:
            tensor = self._kv_caches.get(layer_name)
        if tensor is None:
            return
        base_key = (self._current_key, layer_name)
        object_key = self._latest.get(base_key)
        if self._mooncake is not None and object_key is not None:
            try:
                payload = self._mooncake.get_layer(object_key, 0)
                self._mooncake.wait_get(object_key)
            except KeyError:
                payload = None
        else:
            payload = self._store.get(object_key) if object_key is not None else None
        print("CONN_LOAD", layer_name, "hit" if payload is not None else "zero", flush=True)
        if payload is None:
            tensor.zero_()
        else:
            if self._mooncake is not None:
                saved = torch.load(__import__("io").BytesIO(payload), weights_only=True)["tensor"]
            else:
                saved = payload
            tensor.copy_(saved.to(tensor.device))
            actual = self._sum(tensor)
            expected = self._checksums.get(object_key)
            print("CONN_CHECK", layer_name, "ok" if actual == expected else "BAD", flush=True)

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
        if self._current_key is None:
            print("CONN_SAVE_SKIP", layer_name, "no_key", flush=True)
            return
        print(
            "CONN_SAVE_PHASE", layer_name,
            type(attn_metadata).__name__,
            "prefill", getattr(attn_metadata, "num_prefill_tokens", None),
            "decode", getattr(attn_metadata, "num_decode_tokens", None),
            flush=True,
        )
        del attn_metadata, kwargs
        base_key = (self._current_key, layer_name)
        version = self._versions.get(base_key, 0) + 1
        self._versions[base_key] = version
        object_key = f"{self._current_key}:{layer_name}:v{version}"
        if self._mooncake is not None:
            import io
            buffer = io.BytesIO()
            torch.save({"tensor": kv_layer.detach().cpu().clone()}, buffer)
            self._mooncake.put_layer(object_key, 0, 0, buffer.getvalue())
            self._mooncake.wait_put(object_key)
        else:
            self._store[object_key] = kv_layer.detach().cpu().clone()
        self._latest[base_key] = object_key
        self._checksums[object_key] = self._sum(kv_layer)
        self._saved_ptrs[layer_name] = kv_layer.data_ptr()
        self._saved_shapes[layer_name] = tuple(kv_layer.shape)
        print("CONN_SAVE", layer_name, flush=True)

    def wait_for_save(self):
        return None

    def get_finished(self, finished_req_ids):
        del finished_req_ids
        return set(), set()

    def shutdown(self):
        self._store.clear()
        self._kv_caches.clear()
