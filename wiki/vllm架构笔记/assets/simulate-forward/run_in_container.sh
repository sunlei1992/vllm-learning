#!/bin/bash
# Run an arbitrary script from tmp/ inside the simulator container.
# usage: ./tmp/run_in_container.sh sim_steps.py
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"
SCRIPT="${1:?usage: run_in_container.sh <script-in-tmp>}"
mkdir -p "$ROOT/tmp/triton-cache" "$ROOT/tmp/simlogs"
ENVARGS=()
for v in KV_MB N_REQS PROMPT_REP MAX_SEQS MAX_BATCHED MAX_TOKENS MAX_MODEL_LEN SIM_MODEL; do
  [ -n "${!v:-}" ] && ENVARGS+=(-e "$v")
done
docker run --rm --platform linux/arm64 --shm-size=16g ${ENVARGS[@]+"${ENVARGS[@]}"} \
  -v "$ROOT/tmp":/wheels:ro \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  -v "$ROOT/tmp/triton-cache":/triton-cache \
  sim-built bash -c "
    set -e
    uv pip install --system -q --force-reinstall --no-deps \
      /wheels/triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl \
      /wheels/torchvision-0.28.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchaudio-2.11.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchcodec-0.17.0+cpu-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
    cd /work
    export VLLM_TARGET_DEVICE=cpu
    export TRITON_CACHE_DIR=/triton-cache
    python /out/$SCRIPT
  "
