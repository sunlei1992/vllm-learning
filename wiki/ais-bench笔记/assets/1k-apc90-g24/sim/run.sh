#!/bin/bash
# 复现 010：混部（单实例）空跑 + APC 命中率回放
# 前提：镜像 sim-built、models/Qwen_Qwen3-0.6B、tmp/*.whl 已就位
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../../.." && pwd)}"
KV_GB="${KV_GB:-8}"
PORT="${PORT:-18000}"

docker rm -f apc-sim >/dev/null 2>&1 || true
docker run -d --name apc-sim --platform linux/arm64 --shm-size=16g -p "${PORT}:8000" \
  -v "$ROOT/tmp":/wheels:ro -v "$ROOT/models":/models:ro -v "$ROOT/tmp/simlogs":/logs \
  sim-built bash -c "
    set -e
    uv pip install --system -q --force-reinstall --no-deps /wheels/triton-*.whl /wheels/torchvision-*.whl /wheels/torchaudio-*.whl /wheels/torchcodec-*.whl
    export VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/logs/triton-cache
    exec python -m vllm.entrypoints.openai.api_server \
      --model /models/Qwen_Qwen3-0.6B --served-model-name qwen \
      --simulate-forward --enable-prefix-caching \
      --kv-cache-memory-bytes $((KV_GB*1024*1024*1024)) --enforce-eager --max-model-len 4096 \
      --host 0.0.0.0 --port 8000" >/dev/null

for i in $(seq 1 60); do curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null && break; sleep 2; done
curl -s "http://127.0.0.1:${PORT}/metrics" | grep -o 'kv_cache_size_tokens="[0-9]*"\|block_size="[0-9]*"' | sort -u

cd "$(dirname "$0")/.."
python3 sim/apc_sim_test.py --full full.jsonl --mode cold
docker restart apc-sim >/dev/null; sleep 3
for i in $(seq 1 60); do curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null && break; sleep 2; done
python3 sim/apc_sim_test.py --full full.jsonl --mode warmup
