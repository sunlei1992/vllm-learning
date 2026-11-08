"""Mooncake store-only benchmark: put/get latency and bandwidth.

Run inside a sim container that can reach mc-master:50051.
"""

import os
import time

from mooncake.store import MooncakeDistributedStore

MASTER = os.environ.get("MC_MASTER", "mc-master:50051")
SIZES = [int(x) for x in os.environ.get("MC_SIZES", "1,4").split(",")]
N = int(os.environ.get("MC_N", "30"))

store = MooncakeDistributedStore()
rc = store.setup(
    "lab3",
    "P2PHANDSHAKE",
    512 * 1024 * 1024,
    128 * 1024 * 1024,
    "tcp",
    "",
    MASTER,
)
print(f"setup rc={rc} master={MASTER}", flush=True)


def q(xs, frac):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(frac * len(xs)))]


for size_mb in SIZES:
    payload = os.urandom(size_mb * 1024**2)
    put_ms, get_ms = [], []
    for i in range(N):
        key = f"bench/{size_mb}/{i}"
        t = time.perf_counter()
        rc = store.put(key, payload)
        put_ms.append((time.perf_counter() - t) * 1000)
        if rc != 0:
            raise RuntimeError(f"put rc={rc}")
    for i in range(N):
        key = f"bench/{size_mb}/{i}"
        t = time.perf_counter()
        data = store.get(key)
        get_ms.append((time.perf_counter() - t) * 1000)
        if data is None or len(data) != len(payload):
            raise RuntimeError(f"get bad len={None if data is None else len(data)}")
    p50_put, p99_put = q(put_ms, 0.5), q(put_ms, 0.99)
    p50_get, p99_get = q(get_ms, 0.5), q(get_ms, 0.99)
    print(
        f"size={size_mb}MiB n={N} "
        f"put p50={p50_put:.2f}ms p99={p99_put:.2f}ms "
        f"get p50={p50_get:.2f}ms p99={p99_get:.2f}ms "
        f"bw_put={size_mb / 1024 / p50_put * 1000:.2f}GB/s "
        f"bw_get={size_mb / 1024 / p50_get * 1000:.2f}GB/s",
        flush=True,
    )
