#!/bin/bash
# Start the dry-run OpenAI server (vLLM main) on port 18000.
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
docker run --rm --name dryrun-server --platform linux/arm64 --shm-size=16g \
  -p 18000:8000 \
  -v "$ROOT/tmp":/wheels:ro \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  sim-built bash -c '
    set -e
    uv pip install --system -q --force-reinstall --no-deps \
      /wheels/triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl \
      /wheels/torchvision-0.28.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchaudio-2.11.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchcodec-0.17.0+cpu-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
    export VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/logs/triton-cache
    python -m vllm.entrypoints.openai.api_server \
      --model /models/Qwen_Qwen3-0.6B \
      --served-model-name qwen \
      --simulate-forward \
      --kv-cache-memory-bytes 2147483648 \
      --enforce-eager \
      --max-model-len 2048 \
      --host 0.0.0.0 --port 8000
  '
