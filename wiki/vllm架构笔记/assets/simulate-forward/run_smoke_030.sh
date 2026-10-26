#!/bin/bash
# vLLM v0.30.0 dry-run smoke (image sim030:dry-run, venv /opt/v030).
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"
mkdir -p "$ROOT/tmp/simlogs"
docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  sim030:dry-run bash -c '
    export VLLM_TARGET_DEVICE=cpu
    export TRITON_CACHE_DIR=/logs/triton-cache-030
    /opt/v030/bin/python /out/sim_smoke.py
  '
