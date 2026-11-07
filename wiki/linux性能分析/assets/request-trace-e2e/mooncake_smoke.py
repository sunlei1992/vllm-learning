"""Minimal Mooncake TCP store smoke test: no vLLM involved."""

import sys
import time

from mooncake_tcp_transport import connect_mooncake_tcp_session

t0 = time.time()
print("[smoke] connecting ...", flush=True)
t = connect_mooncake_tcp_session(
    master_server_addr="mooncake-master:50051",
    num_shards=1,
    key_prefix="smoke",
)
print(f"[smoke] connected in {time.time() - t0:.2f}s", flush=True)

payload = bytes(range(256)) * 4096  # 1 MiB
t1 = time.time()
t.put_layer("k0", 0, 0, payload)
t.wait_put("k0")
print(f"[smoke] put {len(payload)} bytes in {time.time() - t1:.3f}s", flush=True)

t2 = time.time()
data = t.get_layer("k0", 0)
t.wait_get("k0")
print(f"[smoke] get {len(data)} bytes in {time.time() - t2:.3f}s", flush=True)
print("[smoke] match:", data == payload, flush=True)
