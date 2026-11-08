# SPDX-License-Identifier: Apache-2.0
"""In-memory stand-in for AscendStoreConnector, for simulated execution.

The real connector queries a Mooncake store through a ZMQ pool worker and
registers real KV tensors. Simulated forward has neither tensors nor a store,
so this connector keeps the scheduler-side behaviour (prefix lookup over block
hashes, capacity-limited LRU, eviction) and makes the worker side a no-op.

Storage backend and latency are configurable (see ``store_backends.py``):

  store_backend = memory | mooncake
  store_latency = zero | modeled | real

``memory`` + ``zero``    pure scheduling sweep, no IO and no transfer time.
``memory`` + ``modeled`` logical store, transfer time booked by GB/s.
``mooncake`` + ``real``  real store memory/RPC, real latency on the path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from store_backends import make_store, resolve_latency
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


class SimulatedAscendStoreConnector(KVConnectorBase_V1):
    """AscendStoreConnector with a pluggable store and a no-op worker."""

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
        self.block_bytes = max(
            1, group.kv_cache_spec.page_size_bytes * max(1, len(group.layer_names))
        )
        store_gb = float(extra.get("store_gb", 8.0))
        capacity_blocks = int(store_gb * 1024**3 // self.block_bytes)
        backend_name = str(extra.get("store_backend", "memory")).lower()
        self.store = make_store(extra, capacity_blocks=capacity_blocks)
        prefix = extra.get("key_prefix", os.environ.get("MC_KEY_PREFIX", ""))
        self._key_prefix = prefix.encode() if isinstance(prefix, str) else prefix
        self.store_latency = resolve_latency(extra, backend_name)
        self.bytes_per_token = self.block_bytes / max(1, self.block_size)

        # Set by vllm's simulated_kv_connector: books transfer time.
        self.simulated_transfers = None
        self._pending: dict[str, int] = {}
        self._loading: set[str] = set()
        self._scheduler = None
        print(
            f"[MC] backend={self.store.name} latency={self.store_latency} "
            f"store={type(self.store).__name__} capacity={self.store.capacity} "
            f"payload={getattr(self.store, 'payload_bytes', None)} "
            f"block_bytes={self.block_bytes} block_size={self.block_size}",
            flush=True,
        )
        logger.info(
            "Simulated AscendStore (backend=%s latency=%s): block_size=%d block_bytes=%d",
            self.store.name,
            self.store_latency,
            self.block_size,
            self.block_bytes,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _key(self, block_hash: bytes) -> bytes:
        return self._key_prefix + block_hash

    def _book_transfers(self) -> bool:
        """Whether this connector books transfer time on the simulated clock."""
        return self.simulated_transfers is not None and self.store_latency == "modeled"

    def _log_stats(self) -> None:
        stats = self.store.stats()
        print(
            f"[MC] backend={self.store.name} puts={stats['puts']} "
            f"hit={stats['hits']} miss={stats['misses']} "
            f"evicted={stats['evictions']} avg_put={stats['avg_put_ms']:.2f}ms",
            flush=True,
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
            if not self.store.has(self._key(block_hash)):
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
        # Only "modeled" latency books an async load on the simulated clock.
        # zero/real modes apply the hit synchronously: there is no transfer
        # event that would ever complete them.
        async_load = self.store_latency == "modeled" and os.environ.get(
            "MC_SYNC", "0"
        ) != "1"
        return need, async_load

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
            self.store.put(self._key(block_hash), block_id)
        if hashes and self.store.stats()["puts"] % 64 == 0:
            self._log_stats()
        if hashes and self._book_transfers():
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
        if metadata is None or not self._book_transfers():
            return
        for request_id, num_bytes in (metadata.loads or {}).items():
            if request_id in self._loading:
                continue
            self._loading.add(request_id)
            self.simulated_transfers.submit_load(request_id, num_bytes)

    def wait_for_layer_load(self, layer_name):
        return None

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
        return None

    def wait_for_save(self):
        return None

    def get_finished(self, finished_req_ids):
        if self.simulated_transfers is None or self.store_latency != "modeled":
            return None, None
        sending, recving = self.simulated_transfers.get_finished()
        for rid in recving:
            self._loading.discard(rid)
        # A load submitted for a request that was later preempted completes after
        # it left WAITING_FOR_REMOTE_KVS; only report loads still pending.
        scheduler = self._scheduler
        if scheduler is not None and recving:
            from vllm.v1.request import RequestStatus

            recving = {
                rid
                for rid in recving
                if rid in scheduler.requests
                and scheduler.requests[rid].status == RequestStatus.WAITING_FOR_REMOTE_KVS
            }
        return (sending or None), (recving or None)
