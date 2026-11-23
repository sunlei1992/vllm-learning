#!/usr/bin/env bash
# Class-level: MembPullReadThread._do_read_batch with MooncakeTransport (TCP).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LAB="$(cd "$ROOT/../.." && pwd)"   # workspace root
VA_SRC="${VA_SRC:-$LAB/tmp/vllm-ascend-layerwise-v030}"
NPU_STUB="${NPU_STUB:-$LAB/wiki/vllm架构笔记/assets/simulate-forward/va/torch_npu_stub}"
VA_RT="${VA_RT:-/tmp/va_rt}"
NET="${NET:-pullnet2}"
IMAGE="${IMAGE:-mooncake-tcp-p2p:latest}"
SIM_IMAGE="${SIM_IMAGE:-sim030:mooncake}"

# 1. Copy VA source and add the build-info stub.
rm -rf "$VA_RT"
rsync -a --exclude .git "$VA_SRC/" "$VA_RT/"
printf '__soc_version__ = "ASCEND910B1"\n' > "$VA_RT/vllm_ascend/_build_info.py"

# 2. Metadata server + P.
docker network create "$NET" >/dev/null 2>&1 || true
docker rm -f pull-meta pull-p >/dev/null 2>&1 || true
docker run -d --name pull-meta --network "$NET" --platform linux/arm64 \
  -e MC_METADATA_HTTP_ALLOW_INSECURE=1 "$IMAGE" \
  mooncake_http_metadata_server --port 8080 >/dev/null
sleep 2
docker run -d --name pull-p --network "$NET" --platform linux/arm64 \
  -e MC_METADATA_HTTP_ALLOW_INSECURE=1 -v "$ROOT:/app:ro" "$IMAGE" \
  python -u /app/p_kv_side.py >/dev/null
sleep 3

# 3. D runs the real read_thread code with the Mooncake transport.
docker run --rm --network "$NET" \
  -e MC_METADATA_HTTP_ALLOW_INSECURE=1 \
  -v "$ROOT:/app:ro" -v "$VA_RT:/va:ro" -v "$NPU_STUB:/stub:ro" \
  "$SIM_IMAGE" bash -lc \
  'PYTHONPATH=/app:/va:/stub /opt/v030/bin/python -u /app/d_read_thread_test.py'
