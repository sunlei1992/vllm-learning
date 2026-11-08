"""Unit tests for store_backends (no vllm, no real Mooncake needed).

Run with pytest, or directly: ``python test_store_backends.py``.
"""

import sys
import types


class FakeMooncakeStore:
    """Minimal stand-in recording the client calls."""

    instances = []

    def __init__(self):
        self.data = {}
        self.closed = False
        self.setup_args = None
        FakeMooncakeStore.instances.append(self)

    def setup(self, *args):
        self.setup_args = args
        return 0

    def is_exist(self, key):
        return 1 if key in self.data else 0

    def put(self, key, value):
        self.data[key] = value
        return 0

    def remove(self, key):
        self.data.pop(key, None)
        return 0

    def close(self):
        self.closed = True


def _install_fake_mooncake():
    pkg = types.ModuleType("mooncake")
    store_mod = types.ModuleType("mooncake.store")
    store_mod.MooncakeDistributedStore = FakeMooncakeStore
    pkg.store = store_mod
    sys.modules["mooncake"] = pkg
    sys.modules["mooncake.store"] = store_mod


_install_fake_mooncake()

from store_backends import (  # noqa: E402
    LRUStore,
    MooncakeStore,
    make_store,
    resolve_latency,
)


def test_lru_capacity_and_stats() -> None:
    store = LRUStore(capacity_blocks=2)
    store.put("a", 1)
    store.put("b", 2)
    assert store.has("a")
    store.put("c", 3)  # evicts b (a was refreshed by has)
    assert not store.has("b")
    assert store.has("a") and store.has("c")
    stats = store.stats()
    assert stats["puts"] == 3
    assert stats["evictions"] == 1
    assert stats["hits"] == 3
    assert stats["misses"] == 1


def test_mooncake_backend_roundtrip_and_eviction() -> None:
    store = MooncakeStore(
        "mc:50051", payload_bytes=64, capacity_blocks=2, segment_mb=64, buffer_mb=8
    )
    client = FakeMooncakeStore.instances[-1]
    assert client.setup_args is not None
    store.put("a", 1)
    store.put("b", 2)
    assert store.has("a")
    assert len(client.data["a"]) == 64
    store.put("c", 3)
    assert "b" not in client.data  # evicted through the real client
    assert store.stats()["evictions"] == 1
    store.close()
    assert client.closed


def test_make_store_defaults_and_validation() -> None:
    lru = make_store({}, capacity_blocks=10)
    assert isinstance(lru, LRUStore) and lru.capacity == 10
    mc = make_store(
        {"store_backend": "mooncake", "payload_bytes": 32}, capacity_blocks=5
    )
    assert isinstance(mc, MooncakeStore) and mc.payload_bytes == 32
    try:
        make_store({"store_backend": "redis"}, capacity_blocks=1)
    except ValueError as exc:
        assert "unknown store_backend" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_resolve_latency() -> None:
    assert resolve_latency({}, "memory") == "zero"
    assert resolve_latency({}, "mooncake") == "real"
    assert resolve_latency({"store_latency": "modeled"}, "memory") == "modeled"
    try:
        resolve_latency({"store_latency": "real"}, "memory")
    except ValueError as exc:
        assert "requires store_backend" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
    try:
        resolve_latency({"store_latency": "fast"}, "memory")
    except ValueError as exc:
        assert "unknown store_latency" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name}: ok")
