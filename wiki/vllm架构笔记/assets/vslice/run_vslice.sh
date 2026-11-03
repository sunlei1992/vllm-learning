#!/bin/bash
# Vertical slice: one image, two scheduler configs (VSLICE_POLICY=fcfs|srs).
#   MODE=baseline RUNS=2 bash run_vslice.sh
#   MODE=candidate RUNS=2 bash run_vslice.sh
#   KEEP=1 PORT=18083 MODE=baseline bash run_vslice.sh
set -uo pipefail

VS="$(cd "$(dirname "$0")" && pwd)"
ROOT="${VLLM_LAB_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$VS"
  while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/AGENTS.md" ]; do ROOT="$(dirname "$ROOT")"; done
fi
MODE="${MODE:?set MODE=baseline|candidate}"
if [ "$MODE" = "candidate" ]; then
  POLICY="${POLICY:-srs}"
  PORT="${PORT:-18082}"
else
  POLICY="${POLICY:-fcfs}"
  PORT="${PORT:-18081}"
fi
RUNS="${RUNS:-2}"
IMAGE="${IMAGE:-sim-int:dry-run}"
LOGDIR="$VS/logs/$MODE"
RESULTS="$VS/results"
NAME="vslice-$MODE"
TRACE='{"trace_decode_token_ids":[100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115],"return_token_ids":true}'

echo "== mode=$MODE policy=$POLICY port=$PORT runs=$RUNS"

case "$MODE" in baseline|candidate) ;; *) echo "bad MODE=$MODE"; exit 1;; esac
# clean this variant's artifacts (container writes as root)
docker run --rm --platform linux/arm64 -v "$VS/logs:/x" --entrypoint bash "$IMAGE" \
  -c "rm -rf /x/$MODE" >/dev/null 2>&1 || true
mkdir -p "$LOGDIR" "$RESULTS"

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --platform linux/arm64 --shm-size=16g \
  -p "$PORT":8000 \
  -e VSLICE_POLICY="$POLICY" \
  -e PYTHONPATH=/tools \
  -e VLLM_TARGET_DEVICE=cpu \
  -e TRITON_CACHE_DIR=/triton-cache \
  -v "$ROOT/models:/models:ro" \
  -v "$VS:/tools:ro" \
  -v "$LOGDIR:/logs" \
  -v "$ROOT/tmp/triton-cache:/triton-cache" \
  "$IMAGE" bash /tools/start_server.sh >/dev/null || { echo "docker run failed"; exit 1; }

echo "== waiting for /health"
ok=0
for i in $(seq 1 180); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" || true)
  if [ "$code" = "200" ]; then ok=1; echo "healthy after $((i * 2))s"; break; fi
  if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "container exited"; docker logs "$NAME" 2>&1 | tail -80; exit 1
  fi
  sleep 2
done
if [ "$ok" != "1" ]; then
  echo "server never became healthy"; docker logs "$NAME" 2>&1 | tail -80; exit 1
fi

bench() {
  "$ROOT/.venv/bin/python" -m vllm.entrypoints.cli.main bench serve \
    --backend openai --endpoint /v1/completions \
    --base-url "http://127.0.0.1:$PORT" --model qwen \
    --tokenizer "$ROOT/models/Qwen_Qwen3-0.6B" \
    --dataset-name custom --dataset-path "$VS/case_mixed.jsonl" \
    --custom-output-len -1 --disable-shuffle --skip-chat-template --ignore-eos \
    --num-prompts 16 --request-rate inf --max-concurrency 16 --num-warmups 0 \
    --percentile-metrics ttft,tpot,itl,e2el --metric-percentiles 50,90,99 \
    --goodput ttft:200 \
    --extra-body "$TRACE" \
    --save-result --result-dir "$RESULTS" "$@"
}

echo "== full-load warmup (discarded)"
if ! bench --result-filename "warmup-$MODE.json" --label "warmup-$MODE" > "$LOGDIR/warmup.log" 2>&1; then
  tail -40 "$LOGDIR/warmup.log"; exit 1
fi
rm -f "$RESULTS/warmup-$MODE.json"

before=$(wc -l < "$LOGDIR/steps.jsonl" 2>/dev/null || echo 0)
curl -s "http://127.0.0.1:$PORT/metrics" > "$LOGDIR/metrics_before.txt"

for i in $(seq 1 "$RUNS"); do
  echo "== measured bench $i/$RUNS"
  if ! bench --result-filename "$MODE-run$i.json" --label "$MODE-run$i" > "$LOGDIR/bench-run$i.log" 2>&1; then
    tail -40 "$LOGDIR/bench-run$i.log"; exit 1
  fi
done

echo "== per-request collector"
if ! "$ROOT/.venv/bin/python" "$VS/collect.py" \
      --url "http://127.0.0.1:$PORT" --case "$VS/case_mixed.jsonl" \
      --out "$LOGDIR/collect.json" > "$LOGDIR/collect.log" 2>&1; then
  tail -40 "$LOGDIR/collect.log"; exit 1
fi

curl -s "http://127.0.0.1:$PORT/metrics" > "$LOGDIR/metrics_after.txt"
tail -n +"$((before + 1))" "$LOGDIR/steps.jsonl" > "$RESULTS/$MODE-steps.jsonl"

echo "== done: $LOGDIR"
if [ "${KEEP:-0}" != "1" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1
fi
