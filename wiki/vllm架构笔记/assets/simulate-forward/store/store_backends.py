# SPDX-License-Identifier: Apache-2.0
"""Storage backends for the simulated AscendStore connector.

Two modes, selected with ``store_backend``:

``memory``
    Dict of block hashes, no IO at all. Capacity is a logical LRU over blocks.
    Use it for scheduling / hit-rate sweeps where store cost should be zero.

``mooncake``
    Real Mooncake master. Each block writes a small placeholder payload
    (``payload_bytes``, default 4 KiB) through the real client: real memory,
    real RPC, real round-trip. Capacity is still the connector's logical LRU
    (``store_gb``), not Mooncake's eviction policy.

``store_latency`` controls how transfer time is booked:

``zero``      no modelled transfer time (fastest)
``modeled``   book load/store on the simulated clock (needs kv_transfer_timing)
``real``      rely on the backend's own latency (only valid for mooncake)
"""

from __future__ import annotations

import os
import socket
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class StoreStats:
    hits: int = 0
    misses: int = 0
    puts: int = 0
    evictions: int = 0
    put_ms_total: float = 0.0

    @property
    def avg_put_ms(self) -> float:
        return self.put_ms_total / self.puts if self.puts else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "puts": self.puts,
            "evictions": self.evictions,
            "avg_put_ms": round(self.avg_put_ms, 3),
        }


class StoreBackend:
    """Common interface: has / put / stats / close."""

    name = "base"

    def __init__(self, capacity_blocks: int) -> None:
        self.capacity = max(1, capacity_blocks)
        self.stats_obj = StoreStats()

    def has(self, key: str) -> bool:
        raise NotImplementedError

    def put(self, key: str, block_id: int) -> None:
        raise NotImplementedError

    def stats(self) -> dict[str, float | int]:
        return self.stats_obj.as_dict()

    def close(self) -> None:
        return None


class LRUStore(StoreBackend):
    """Block-hash keyed dict with a capacity measured in blocks. No IO."""

    name = "memory"

    def __init__(self, capacity_blocks: int) -> None:
        super().__init__(capacity_blocks)
        self.blocks: OrderedDict[str, int] = OrderedDict()

    def has(self, key: str) -> bool:
        if key in self.blocks:
            self.blocks.move_to_end(key)
            self.stats_obj.hits += 1
            return True
        self.stats_obj.misses += 1
        return False

    def put(self, key: str, block_id: int) -> None:
        self.blocks[key] = block_id
        self.blocks.move_to_end(key)
        self.stats_obj.puts += 1
        while len(self.blocks) > self.capacity:
            self.blocks.popitem(last=False)
            self.stats_obj.evictions += 1


class MooncakeStore(StoreBackend):
    """Real Mooncake store, small placeholder payload per block."""

    name = "mooncake"

    def __init__(
        self,
        master: str,
        *,
        payload_bytes: int = 4096,
        segment_mb: int = 512,
        buffer_mb: int = 128,
        capacity_blocks: int = 0,
        verify_lookups: bool = False,
    ) -> None:
        super().__init__(capacity_blocks)
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
        self.master = master
        self.payload_bytes = payload_bytes
        self.verify_lookups = verify_lookups
        self._payload = b"\0" * payload_bytes
        self._order: OrderedDict[str, None] = OrderedDict()

    def has(self, key: str) -> bool:
        # Hit decision is logical (same as LRUStore) so both backends produce
        # identical scheduling. With verify_lookups=True the real store is also
        # consulted; a disagreement drops the key (and shows up as a miss).
        if key not in self._order:
            self.stats_obj.misses += 1
            return False
        if self.verify_lookups and self._store.is_exist(key) <= 0:
            self._order.pop(key, None)
            self.stats_obj.misses += 1
            return False
        self._order.move_to_end(key)
        self.stats_obj.hits += 1
        return True

    def put(self, key: str, block_id: int) -> None:  # noqa: ARG002
        started = time.perf_counter()
        rc = self._store.put(key, self._payload)
        self.stats_obj.put_ms_total += (time.perf_counter() - started) * 1000
        self.stats_obj.puts += 1
        if rc != 0:
            raise RuntimeError(f"Mooncake put failed rc={rc} key={key}")
        self._order[key] = None
        self._order.move_to_end(key)
        while len(self._order) > self.capacity:
            old_key, _ = self._order.popitem(last=False)
            if old_key != key:
                self._store.remove(old_key)
                self.stats_obj.evictions += 1

    def close(self) -> None:
        try:
            self._store.close()
        except Exception:  # pragma: no cover - best effort on teardown
            pass


def make_store(extra: dict, *, capacity_blocks: int) -> StoreBackend:
    """Build the backend named by ``store_backend`` (default: memory)."""
    backend = str(extra.get("store_backend", "memory")).lower()
    if backend == "memory":
        return LRUStore(capacity_blocks)
    if backend == "mooncake":
        return MooncakeStore(
            str(extra.get("mooncake_master", "mc-master:50051")),
            payload_bytes=int(extra.get("payload_bytes", 4096)),
            segment_mb=int(extra.get("segment_mb", 512)),
            buffer_mb=int(extra.get("buffer_mb", 128)),
            capacity_blocks=capacity_blocks,
            verify_lookups=bool(int(extra.get("verify_lookups", 0))),
        )
    raise ValueError(f"unknown store_backend {backend!r}; use 'memory' or 'mooncake'")


def resolve_latency(extra: dict, backend: str) -> str:
    """Pick how transfer time is booked for this backend."""
    value = str(extra.get("store_latency") or os.environ.get("STORE_LATENCY") or "").lower()
    if not value:
        value = "real" if backend == "mooncake" else "zero"
    if value not in ("zero", "modeled", "real"):
        raise ValueError(
            f"unknown store_latency {value!r}; use 'zero', 'modeled' or 'real'"
        )
    if value == "real" and backend != "mooncake":
        raise ValueError("store_latency='real' requires store_backend='mooncake'")
    return value
