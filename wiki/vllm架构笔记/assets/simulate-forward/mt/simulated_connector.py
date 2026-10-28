# SPDX-License-Identifier: Apache-2.0
"""In-memory stand-in for AscendStoreConnector, for simulated execution.

The real connector queries a Mooncake store through a ZMQ pool worker and
registers real KV tensors. Simulated forward has neither tensors nor a store,
so this connector keeps the scheduler-side behaviour (prefix lookup over block
hashes, capacity-limited LRU, eviction) and makes the worker side a no-op.

It is a LOCAL EXPERIMENT shim: it measures hit rate and eviction behaviour,
not transfer performance.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from vllm.distributed.kv_transfer.kv_connector.v1.base import (
    KVConnectorBase_V1,
    KVConnectorMetadata,
    KVConnectorRole,
)
from vllm.logger import init_logger

if TYPE_CHECKING:
    from vllm.config import VllmConfig
    from vllm.v1.kv_cache_interface import KVCacheConfig
    from vllm.v1.request import Request

logger = init_logger(__name__)


@dataclass
class SimulatedStoreMetadata(KVConnectorMetadata):
    """Bytes to load per request, booked on the simulated clock."""

    loads: dict[str, int] | None = None


class _LRUStore:
    """Block-hash keyed store with a capacity measured in blocks."""

    def __init__(self, capacity_blocks: int) -> None:
        self.capacity = max(1, capacity_blocks)
        self.blocks: OrderedDict[str, int] = OrderedDict()
        self.hit_lookups = 0
        self.miss_lookups = 0

    def has(self, key: str) -> bool:
        if key in self.blocks:
            self.blocks.move_to_end(key)
            self.hit_lookups += 1
            return True
        self.miss_lookups += 1
        return False

    def put(self, key: str, block_id: int) -> None:
        self.blocks[key] = block_id
        self.blocks.move_to_end(key)
        while len(self.blocks) > self.capacity:
            self.blocks.popitem(last=False)


class SimulatedAscendStoreConnector(KVConnectorBase_V1):
    """AscendStoreConnector with an in-memory store and a no-op worker."""

    def __init__(
        self,
        vllm_config: "VllmConfig",
        role: KVConnectorRole,
        kv_cache_config: "KVCacheConfig",
    ):
        super().__init__(
            vllm_config=vllm_config, role=role, kv_cache_config=kv_cache_config
        )
        extra = (vllm_config.kv_transfer_config or {}).get(
            "kv_connector_extra_config", {}
        ) if not hasattr(vllm_config.kv_transfer_config, "kv_connector_extra_config") else (
            vllm_config.kv_transfer_config.kv_connector_extra_config or {}
        )
        group = kv_cache_config.kv_cache_groups[0]
        self.block_size = group.kv_cache_spec.block_size
        self.block_bytes = max(1, group.kv_cache_spec.page_size_bytes * max(1, len(group.layer_names)))
        store_gb = float(extra.get("store_gb", 8.0))
        self.store = _LRUStore(int(store_gb * 1024**3) // self.block_bytes)
        self.bytes_per_token = self.block_bytes / max(1, self.block_size)
        # Set by vllm's simulated_kv_connector: books transfer time.
        self.simulated_transfers = None
        self._pending: dict[str, int] = {}
        logger.info(
            "Simulated AscendStore: %d blocks x %d bytes (%.2f GiB), block_size=%d",
            self.store.capacity,
            self.block_bytes,
            self.store.capacity * self.block_bytes / 1024**3,
            self.block_size,
        )

    # ------------------------------------------------------------------ #
    # Scheduler side
    # ------------------------------------------------------------------ #
    def get_num_new_matched_tokens(
        self, request: "Request", num_computed_tokens: int
    ) -> tuple[int, bool]:
        hashes = getattr(request, "block_hashes", None) or []
        hit_blocks = 0
        for block_hash in hashes:
            if not self.store.has(block_hash):
                break
            hit_blocks += 1
        hit_tokens = hit_blocks * self.block_size
        if hit_tokens == 0:
            return 0, False
        if hit_tokens >= request.num_tokens:
            hit_tokens = request.num_tokens - 1
        if hit_tokens <= num_computed_tokens:
            return 0, False
        need = hit_tokens - num_computed_tokens
        self._pending[request.request_id] = need
        # Async: the scheduler waits for get_finished() to report the load.
        return need, True

    def update_state_after_alloc(self, request, blocks, num_external_tokens):
        return None

    def build_connector_meta(self, scheduler_output):
        loads = {
            request_id: int(tokens * self.bytes_per_token)
            for request_id, tokens in self._pending.items()
        }
        self._pending.clear()
        return SimulatedStoreMetadata(loads=loads)

    def request_finished(self, request, block_ids):
        hashes = getattr(request, "block_hashes", None) or []
        for block_hash, block_id in zip(hashes, block_ids):
            self.store.put(block_hash, block_id)
        if self.simulated_transfers is not None and hashes:
            self.simulated_transfers.submit_store(
                request.request_id, int(len(hashes) * self.block_bytes)
            )
        return False, None

    # ------------------------------------------------------------------ #
    # Worker side: no data movement
    # ------------------------------------------------------------------ #
    def register_kv_caches(self, kv_caches):
        return None

    def start_load_kv(self, forward_context, **kwargs):
        metadata = self._connector_metadata
        if self.simulated_transfers is None or metadata is None:
            return
        for request_id, num_bytes in (metadata.loads or {}).items():
            self.simulated_transfers.submit_load(request_id, num_bytes)

    def wait_for_layer_load(self, layer_name):
        return None

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
        return None

    def wait_for_save(self):
        return None

    def get_finished(self, finished_req_ids):
        if self.simulated_transfers is None:
            return None, None
        sending, recving = self.simulated_transfers.get_finished()
        return (sending or None), (recving or None)
