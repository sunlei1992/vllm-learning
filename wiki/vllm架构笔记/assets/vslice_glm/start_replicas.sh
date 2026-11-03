#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KV_BYTES="${KV_BYTES:-69793218560}"
SCHED_ARGS="${SCHED_ARGS:-}"
PREFIX_ACTIVE="${PREFIX_ACTIVE:-1}"
MAX_SEQS="${MAX_SEQS:-32}"
for n in glmtest glmtest2; do docker rm -f "$n" >/dev/null 2>&1 || true; done
for spec in "glmtest 18100" "glmtest2 18101"; do
  set -- $spec; name=$1; port=$2
  docker run -d --name "$name" --platform linux/arm64 --shm-size=16g -p "$port":8000 \
    -e VLLM_TARGET_DEVICE=cpu -e TRITON_CACHE_DIR=/triton-cache -e VLLM_SIM_MLA_ALLOW=1 -e KV_BYTES="$KV_BYTES" -e SCHED_ARGS="$SCHED_ARGS" -e PREFIX_ACTIVE="$PREFIX_ACTIVE" -e MAX_SEQS="$MAX_SEQS" -e PYTHONPATH=/tools \
    -v "$ROOT/models:/models:ro" -v "$ROOT/tmp/triton-cache:/triton-cache" \
    -v "$ROOT/tmp/vslice_glm/cpu.py:/work030/vllm/platforms/cpu.py:ro" \
    -v "$ROOT/tmp/vslice_glm:/tools:ro" \
    --entrypoint bash sim030:glm53 -lc 'cd /work030 && /opt/v030/bin/python -m vllm.entrypoints.openai.api_server \
      --model /models/zai-org_GLM-5.3 --served-model-name glm --trust-remote-code \
      --simulate-forward --enforce-eager --max-model-len 131072 \
      --kv-cache-memory-bytes $KV_BYTES --block-size 128 \
      --max-num-seqs $MAX_SEQS --max-num-batched-tokens 32768 \
      --enable-prefix-caching $SCHED_ARGS --host 0.0.0.0 --port 8000' >/dev/null 2>&1
  echo "started $name :$port"
done
for i in $(seq 1 90); do
  a=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18100/health || true)
  b=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18101/health || true)
  [ "$a" = 200 ] && [ "$b" = 200 ] && { echo "both healthy after $((i*2))s"; exit 0; }
  sleep 2
done
echo "not healthy: $a $b"; exit 1
