#!/bin/bash
# Dry-run GLM-5.3 (config + tokenizer only, no weights) on image sim030:glm53.
# The image contains the vLLM 0.30 build with `is_v32 = False` patched in
# deepseek_v2.py, which sidesteps the CPU sparse-attention rejection.
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
MODEL_DIR="$ROOT/models/zai-org_GLM-5.3"
BASE=https://hf-mirror.com/zai-org/GLM-5.3/resolve/main

if [ ! -f "$MODEL_DIR/config.json" ]; then
  mkdir -p "$MODEL_DIR"
  for f in config.json generation_config.json tokenizer.json tokenizer_config.json chat_template.jinja; do
    curl -sL -o "$MODEL_DIR/$f" "$BASE/$f"
  done
fi

docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  -e SIM_MODEL=/models/zai-org_GLM-5.3 \
  sim030:glm53 bash -c '
    cd /work030
    export VLLM_TARGET_DEVICE=cpu
    export TRITON_CACHE_DIR=/logs/triton-cache-030
    /opt/v030/bin/python /out/sim_smoke.py
  '
