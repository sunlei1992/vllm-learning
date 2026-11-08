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

import socket
import time
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



class _MooncakeStore:
    """Block-hash keyed store backed by a real Mooncake master.

    Writes a small placeholder payload per block: the goal is to exercise the
    real store path (key lookup, capacity, eviction, network round-trip) without
    pushing tens of MB per request through a laptop's memory.
    """

    def __init__(
        self,
        master: str,
        payload_bytes: int = 4096,
        segment_mb: int = 512,
        buffer_mb: int = 128,
        capacity_blocks: int = 0,
    ) -> None:
        from mooncake.store import MooncakeDistributedStore

        self._store = MooncakeDistributedStore()
        rc = self._store.setup(
            socket.gethostname(),
            "P2PHANDSHAKE",
            segment_mb * 1024**2,
            buffer_mb * 1024**2,
            "tcp",
            "",
            master,
        )
        if rc != 0:
            raise RuntimeError(f"Mooncake setup failed rc={rc} master={master}")
        self._payload = b"\0" * payload_bytes
        self.payload_bytes = payload_bytes
        self.capacity = max(1, capacity_blocks)
        self._order: OrderedDict[str, None] = OrderedDict()
        self.evicted_keys = 0
        self.hit_lookups = 0
        self.miss_lookups = 0
        self.put_count = 0
        self.put_ms_total = 0.0

    def has(self, key: str) -> bool:
        exists = self._store.is_exist(key) > 0
        if exists:
            self.hit_lookups += 1
        else:
            self.miss_lookups += 1
        return exists

    def put(self, key: str, block_id: int) -> None:  # noqa: ARG002
        started = time.perf_counter()
        rc = self._store.put(key, self._payload)
        self.put_ms_total += (time.perf_counter() - started) * 1000
        self.put_count += 1
        if rc != 0:
            raise RuntimeError(f"Mooncake put failed rc={rc} key={key}")
        self._order[key] = None
        self._order.move_to_end(key)
        while len(self._order) > self.capacity:
            old_key, _ = self._order.popitem(last=False)
            if old_key != key:
                self._store.remove(old_key)
                self.evicted_keys += 1
        if self.put_count % 64 == 0:
            print(
                f"[MC] puts={self.put_count} hit={self.hit_lookups} "
                f"miss={self.miss_lookups} evicted={self.evicted_keys} "
                f"avg_put={self.put_ms_total / self.put_count:.2f}ms",
                flush=True,
            )


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
        backend = str(extra.get("store_backend", "memory")).lower()
        if backend == "mooncake":
            store_gb = float(extra.get("store_gb", 8.0))
            payload_bytes = int(extra.get("payload_bytes", 4096))
            capacity_blocks = int(store_gb * 1024**3 // self.block_bytes)
            self.store = _MooncakeStore(
                master=str(extra.get("mooncake_master", "mc-master:50051")),
                payload_bytes=payload_bytes,
                segment_mb=int(extra.get("segment_mb", 512)),
                buffer_mb=int(extra.get("buffer_mb", 128)),
                capacity_blocks=capacity_blocks,
            )
        else:
            store_gb = float(extra.get("store_gb", 8.0))
            self.store = _LRUStore(int(store_gb * 1024**3) // self.block_bytes)
        self.bytes_per_token = self.block_bytes / max(1, self.block_size)
        print(
            f"[MC] backend={backend} store={type(self.store).__name__} "
            f"payload={getattr(self.store, 'payload_bytes', None)} "
            f"capacity={getattr(self.store, 'capacity', None)} "
            f"block_bytes={self.block_bytes} block_size={self.block_size}",
            flush=True,
        )
        # Set by vllm's simulated_kv_connector: books transfer time.
        self.simulated_transfers = None
        self._pending: dict[str, int] = {}
        logger.info(
            "Simulated AscendStore (backend=%s): block_size=%d block_bytes=%d payload=%s",
            backend,
            self.block_size,
            self.block_bytes,
            getattr(self.store, "payload_bytes", "n/a"),
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
        # A load submitted for a request that was later preempted (KV pressure)
        # completes after the request left WAITING_FOR_REMOTE_KVS; the scheduler
        # asserts on that, so only report loads that are still pending.
        scheduler = getattr(self, "_scheduler", None)
        if scheduler is not None and recving:
            from vllm.v1.request import RequestStatus

            before = len(recving)
            recving = {
                rid
                for rid in recving
                if rid in scheduler.requests
                and scheduler.requests[rid].status == RequestStatus.WAITING_FOR_REMOTE_KVS
            }
            if before != len(recving):
                print(f"[MC] drop stale recving {before - len(recving)}/{before}", flush=True)
        return (sending or None), (recving or None)
