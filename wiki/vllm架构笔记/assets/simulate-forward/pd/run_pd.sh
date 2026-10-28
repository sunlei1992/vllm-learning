#!/bin/bash
# Disaggregated prefill/decode simulation on the ported #61506 tree.
# Image: sim-int:dry-run (branch sim-integrated, worktree tmp/vllm-sim-int).
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
SCRIPT="${1:-sim_pd_ratio.py}"
docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  sim-int:dry-run bash -c "
    cd /work
    export VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/logs/triton-cache
    python /out/$SCRIPT
  "
