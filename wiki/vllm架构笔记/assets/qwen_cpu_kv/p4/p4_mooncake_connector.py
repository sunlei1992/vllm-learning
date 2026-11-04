"""ExampleConnector variant that moves per-layer KV through Mooncake TCP."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import torch
from vllm.distributed.kv_transfer.kv_connector.v1.example_connector import (
    ExampleConnector,
    ExampleConnectorMetadata,
)
from vllm.logger import init_logger
from vllm.model_executor.layers.attention.mla_attention import MLACommonMetadata
from vllm.utils.gpu_sync_debug import gpu_sync_allowed

from mooncake_tcp_transport import connect_mooncake_tcp_session

logger = init_logger(__name__)


class MooncakeExampleConnector(ExampleConnector):
    def __init__(self, vllm_config, role, kv_cache_config):
        super().__init__(vllm_config, role, kv_cache_config)
        extra = self._kv_transfer_config.kv_connector_extra_config
        master = extra.get("mooncake_master")
        if not master:
            raise ValueError("mooncake_master is required")
        self._transport = connect_mooncake_tcp_session(
            master_server_addr=master,
            num_shards=1,
            key_prefix=extra.get("mooncake_key_prefix", "p4"),
            global_segment_size=extra.get("mooncake_segment_size", 2 * 1024**3),
            local_buffer_size=extra.get("mooncake_local_buffer", 256 * 1024**2),
        )

    def _key(self, layer_name: str, token_ids, mm_hashes) -> str:
        folder = self._generate_foldername_debug(token_ids, mm_hashes, create_folder=False)
        return f"{Path(folder).name}:{layer_name}"

    def start_load_kv(self, forward_context, **kwargs: Any) -> None:
        from vllm.v1.attention.backend import AttentionMetadata

        def inject(dst, src, slot_mapping, attn_metadata):
            with gpu_sync_allowed():
                slot_mapping = slot_mapping.to(dst.device, non_blocking=True)
            if isinstance(attn_metadata, MLACommonMetadata):
                dst = dst.reshape(-1, dst.shape[-1])
                dst[slot_mapping, ...] = src
            else:
                block_idxs = slot_mapping // self._block_size
                offsets = slot_mapping % self._block_size
                dst[block_idxs, :, offsets] = src

        metadata = self._get_connector_metadata()
        assert isinstance(metadata, ExampleConnectorMetadata)
        attn_metadata = forward_context.attn_metadata
        if attn_metadata is None:
            return
        for request in metadata.requests:
            if request.is_store:
                continue
            for layer_name in forward_context.no_compile_layers:
                layer = forward_context.no_compile_layers[layer_name]
                kv_cache_layer = getattr(layer, "kv_cache", None)
                if kv_cache_layer is None:
                    continue
                key = self._key(layer_name, request.token_ids, request.mm_hashes)
                payload = self._transport.get_layer(key, 0)
                self._transport.wait_get(key)
                kv_cache = torch.load(io.BytesIO(payload), weights_only=True)["kv_cache"]
                if isinstance(attn_metadata, dict):
                    inject(
                        kv_cache_layer,
                        kv_cache.to(kv_cache_layer.device),
                        request.slot_mapping,
                        attn_metadata[layer_name],
                    )

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs: Any) -> None:
        def extract(layer, slot_mapping):
            with gpu_sync_allowed():
                slot_mapping = slot_mapping.to(layer.device, non_blocking=True)
            if isinstance(attn_metadata, MLACommonMetadata):
                return layer.reshape(-1, layer.shape[-1])[slot_mapping, ...]
            block_idxs = slot_mapping // self._block_size
            offsets = slot_mapping % self._block_size
            return layer[block_idxs, :, offsets]

        metadata = self._get_connector_metadata()
        assert isinstance(metadata, ExampleConnectorMetadata)
        for request in metadata.requests:
            if not request.is_store:
                continue
            key = self._key(layer_name, request.token_ids, request.mm_hashes)
            kv_cache = extract(kv_layer, request.slot_mapping).detach().cpu()
            buffer = io.BytesIO()
            torch.save({"kv_cache": kv_cache}, buffer)
            self._transport.put_layer(key, 0, 0, buffer.getvalue())
            self._transport.wait_put(key)
            self._generate_foldername_debug(
                request.token_ids, request.mm_hashes, create_folder=True
            )
