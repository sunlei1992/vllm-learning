#!/bin/bash
# XpYd dry-run + `vllm bench serve`, one command.
#
#   PRE=1 DEC=1 ./pd/bench/pd_bench.sh                     # 1P1D, 16 prompts
#   PRE=2 DEC=1 NPROMPTS=32 ./tmp/pd_bench.sh         # 2P1D
#   KEEP=1 PRE=2 DEC=2 ./tmp/pd_bench.sh              # leave services running
#
# Env knobs: PRE DEC NPROMPTS INLEN OUTLEN TRACE_LEN LOAD_GBPS IMG LABEL
# Extra args are appended to the `vllm bench serve` command.
set -uo pipefail

PD_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${VLLM_LAB_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$PD_DIR"
  while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/AGENTS.md" ]; do ROOT="$(dirname "$ROOT")"; done
fi
cd "$ROOT" || exit 1

IMG=${IMG:-sim-int:dry-run}
PRE=${PRE:-1}
DEC=${DEC:-1}
NPROMPTS=${NPROMPTS:-16}
INLEN=${INLEN:-256}
OUTLEN=${OUTLEN:-8}
TRACE_LEN=${TRACE_LEN:-16}
LOAD_GBPS=${LOAD_GBPS:-10}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-4096}
KV_MB=${KV_MB:-2048}
PROXY_PORT=${PROXY_PORT:-18000}
LABEL=${LABEL:-pd${PRE}p${DEC}d}
RESULT_DIR=${RESULT_DIR:-tmp/simlogs/pd_bench}
PY=${PY:-$ROOT/.venv/bin/python}

mkdir -p "$RESULT_DIR" tmp/simlogs

echo "=== 1/4 start ${PRE}P${DEC}D (img=$IMG, load=${LOAD_GBPS}GB/s)"
docker rm -f pd_bench >/dev/null 2>&1
docker run -d --name pd_bench --platform linux/arm64 --shm-size=16g \
  -p "$PROXY_PORT":18000 \
  -e PRE="$PRE" -e DEC="$DEC" -e LOAD_GBPS="$LOAD_GBPS" -e SIM_TIMING \
  -e MAX_MODEL_LEN="$MAX_MODEL_LEN" -e KV_MB="$KV_MB" \
  -v "$ROOT/models:/models:ro" -v "$PD_DIR:/tools" -v "$ROOT/tmp/simlogs:/logs" \
  "$IMG" bash /tools/pd_sim_launch.sh >/dev/null || { echo "docker run failed"; exit 1; }

echo "=== 2/4 wait for proxy (engines are awaited inside the container)"
for i in $(seq 1 180); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PROXY_PORT/health")" = "200" ]; then
    echo "proxy healthy after $((i * 2))s"
    break
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx pd_bench; then
    echo "container exited:"; docker logs pd_bench 2>&1 | tail -40; exit 1
  fi
  sleep 2
done
[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PROXY_PORT/health")" = "200" ] || {
  echo "proxy never became healthy"; docker logs pd_bench 2>&1 | tail -40; exit 1; }

TRACE=$("$PY" - "$TRACE_LEN" <<'PY'
import json, sys
n = int(sys.argv[1])
print(json.dumps({"trace_decode_token_ids": [100 + i for i in range(n)],
                  "return_token_ids": True}))
PY
)

echo "=== 3/4 bench serve -> $LABEL"
"$PY" -m vllm.entrypoints.cli.main bench serve \
  --backend openai --endpoint /v1/completions \
  --base-url "http://127.0.0.1:$PROXY_PORT" \
  --model qwen --tokenizer "$ROOT/models/Qwen_Qwen3-0.6B" \
  --dataset-name random --random-input-len "$INLEN" --random-output-len "$OUTLEN" \
  --num-prompts "$NPROMPTS" --num-warmups 2 --request-rate inf --max-concurrency "$NPROMPTS" \
  --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,90,99 \
  --disable-tqdm \
  --extra-body "$TRACE" \
  --save-result --result-dir "$RESULT_DIR" --label "$LABEL" "$@"

rc=$?
echo "=== 4/4 result files"
ls -1t "$RESULT_DIR"/*"$LABEL"*.json 2>/dev/null | head -1

if [ "${KEEP:-0}" = "1" ]; then
  echo "KEEP=1 -> services left running: container=pd_bench proxy=127.0.0.1:$PROXY_PORT"
else
  docker rm -f pd_bench >/dev/null 2>&1
  echo "cleaned up"
fi
exit $rc
