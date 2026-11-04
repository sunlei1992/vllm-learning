#!/usr/bin/env bash
# P4: pure vLLM CPU P/D, per-layer KV saved/loaded through Mooncake TCP.
# Prerequisites: Docker image sim030:mooncake built from p4.Dockerfile,
# Qwen2.5-tiny created by make_tiny_model.py.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
STORE="$ROOT/vllm-ascend-src/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store"
NET=p4-net
MASTER=mooncake-master
IMAGE=sim030:mooncake
STORE_DIR="$ROOT/tmp/p4-store"

python3 "$ROOT/wiki/vllm架构笔记/assets/qwen_cpu_kv/p4/make_tiny_model.py"
docker network create "$NET" >/dev/null 2>&1 || true
docker rm -f "$MASTER" >/dev/null 2>&1 || true
docker run -d --name "$MASTER" --network "$NET" --platform linux/arm64 \
  "$IMAGE" /opt/v030/bin/mooncake_master >/dev/null
cleanup() {
  docker rm -f "$MASTER" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
sleep 3
rm -rf "$STORE_DIR" && mkdir -p "$STORE_DIR"

run_side() {
  local role="$1"
  docker run --rm --network "$NET" --memory 14g --platform linux/arm64 \
    -v "$ROOT/models:/models:ro" \
    -v "$ROOT/wiki/vllm架构笔记/assets/qwen_cpu_kv/p4/p4_mooncake_connector.py:/app/p4_mooncake_connector.py:ro" \
    -v "$ROOT/wiki/vllm架构笔记/assets/qwen_cpu_kv/p4/p4_run.py:/app/p4_run.py:ro" \
    -v "$STORE/mooncake_tcp_transport.py:/app/mooncake_tcp_transport.py:ro" \
    -v "$STORE/layerwise_pd.py:/app/layerwise_pd.py:ro" \
    -v "$STORE_DIR:/store" \
    "$IMAGE" bash -lc "PYTHONPATH=/app VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 /opt/v030/bin/python /app/p4_run.py $role 2>&1 | tail -12"
}

run_side kv_producer
run_side kv_consumer
