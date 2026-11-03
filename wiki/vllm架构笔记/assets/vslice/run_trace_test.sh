#!/bin/bash
# Golden scheduling-trace unit test, run inside the simulator image.
set -euo pipefail

VS="$(cd "$(dirname "$0")" && pwd)"
ROOT="${VLLM_LAB_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$VS"
  while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/AGENTS.md" ]; do ROOT="$(dirname "$ROOT")"; done
fi
IMAGE="${IMAGE:-sim-int:dry-run}"

docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/models:/models:ro" \
  -v "$VS:/tools:ro" \
  -e PYTHONPATH=/work:/tools \
  -e VLLM_TARGET_DEVICE=cpu \
  --entrypoint bash "$IMAGE" \
  -lc 'cd /tools && python -m unittest -v test_vslice_trace'
