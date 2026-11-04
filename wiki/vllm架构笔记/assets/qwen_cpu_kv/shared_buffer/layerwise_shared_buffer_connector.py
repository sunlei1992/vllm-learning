"""Single-engine layerwise shared-buffer connector for vLLM CPU.

All shared layers alias one KV tensor.  Before a layer runs, its historical
KV is restored from the connector store; after it runs, the updated tensor is
saved.  This is the missing fence between physical slot reuse and decode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        del request, num_computed_tokens
        return 0, False

    def update_state_after_alloc(self, request, blocks, num_external_tokens):
        del blocks, num_external_tokens
        self._pending[request.request_id] = request.request_id

    def build_connector_meta(self, scheduler_output):
        del scheduler_output
        return Metadata(tuple(RequestMeta(request_id) for request_id in self._pending))

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

    def wait_for_layer_load(self, layer_name):
        if self._current_key is None:
            return
        tensor = self._kv_caches.get(layer_name)
        if tensor is None:
            return
        saved = self._store.get((self._current_key, layer_name))
        print("CONN_LOAD", layer_name, "hit" if saved is not None else "zero", flush=True)
        if saved is None:
            tensor.zero_()
        else:
            tensor.copy_(saved.to(tensor.device))

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
        del attn_metadata, kwargs
        if self._current_key is None:
            return
        self._store[(self._current_key, layer_name)] = kv_layer.detach().cpu().clone()
        print("CONN_SAVE", layer_name, flush=True)

    def wait_for_save(self):
        return None

    def get_finished(self, finished_req_ids):
        del finished_req_ids
        return set(), set()

    def shutdown(self):
        self._store.clear()
        self._kv_caches.clear()
