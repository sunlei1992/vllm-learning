#!/bin/bash
# Reproduce PR #47922 --simulate-forward on linux/arm64 (Docker Desktop).
# The Triton cache is persisted under tmp/triton-cache; the first run pays
# ~150s of kernel JIT compilation, later runs take well under a second.
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"
mkdir -p "$ROOT/tmp/triton-cache"
docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp":/wheels:ro \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/triton-cache":/triton-cache \
  sim-built bash -c '
    set -e
    uv pip install --system -q --force-reinstall --no-deps \
      /wheels/triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl \
      /wheels/torchvision-0.28.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchaudio-2.11.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchcodec-0.17.0+cpu-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
    cd /work
    export VLLM_TARGET_DEVICE=cpu
    export TRITON_CACHE_DIR=/triton-cache
    python /out/sim_smoke.py
  '
