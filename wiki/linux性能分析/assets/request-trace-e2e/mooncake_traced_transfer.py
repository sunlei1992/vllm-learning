"""Traced transport-level put/get: proves both directions are instrumented."""

import importlib.util
import os
import sys

sys.path.insert(0, "/app")

ROOT = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
spec = importlib.util.spec_from_file_location(
    "patch_request_trace",
    os.path.join(ROOT, "ascend_vllm/patch/platform/patch_request_trace.py"),
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
patch.apply_all()

from mooncake_tcp_transport import connect_mooncake_tcp_session  # noqa: E402

t = connect_mooncake_tcp_session(
    master_server_addr="mooncake-master:50051",
    num_shards=1,
    key_prefix="trace",
)
payload = bytes(range(256)) * 4096  # 1 MiB
t.put_layer("k0", 0, 0, payload)
t.wait_put("k0")
data = t.get_layer("k0", 0)
t.wait_get("k0")
print("[xfer] match:", data == payload, "bytes:", len(data), flush=True)
