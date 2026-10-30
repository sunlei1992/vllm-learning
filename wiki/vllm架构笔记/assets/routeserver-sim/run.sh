#!/bin/bash
# Host driver: dry-run P/D + RouteServer, sharing one network namespace.
#   ./tmp/rs_sim/run.sh              # start everything, wait until RS is ready
#   ./tmp/rs_sim/run.sh stop
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${VLLM_LAB_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$HERE"
  while [ "$ROOT" != "/" ] && [ ! -f "$ROOT/AGENTS.md" ]; do ROOT="$(dirname "$ROOT")"; done
fi
RS_IMG=${RS_IMG:-rs-demo:dev}
SIM_IMG=${SIM_IMG:-sim-int:dry-run}
RS_PORT=${RS_PORT:-9800}
PRE_PORT=${PRE_PORT:-8001}
DEC_PORT=${DEC_PORT:-8002}
PATCH=${PATCH:-/patches/pd_separate_with_remote_decode.yaml}

if [ "${1:-}" = "stop" ]; then
  docker rm -f sim-pd rs-pd >/dev/null 2>&1
  echo "stopped"
  exit 0
fi

mkdir -p "$ROOT/tmp/simlogs"
docker rm -f sim-pd rs-pd >/dev/null 2>&1

echo "== 1/4 router container (holds the netns; publishes 9800/9810 + engine ports)"
docker run -d --name rs-pd -p "$RS_PORT":9800 -p 9810:9810 \
  -p "$PRE_PORT":8001 -p "$DEC_PORT":8002 \
  -v "$HERE:/patches:ro" \
  --entrypoint sleep "$RS_IMG" infinity >/dev/null

echo "== 2/4 engines in that netns"
docker run -d --name sim-pd --network container:rs-pd --shm-size=16g \
  -e SIM_TIMING -e LOAD_GBPS -e KV_MB -e MAX_MODEL_LEN \
  -v "$ROOT/models:/models:ro" -v "$ROOT/tmp/simlogs:/logs" -v "$HERE:/tools:ro" \
  "$SIM_IMG" bash /tools/start_sim_pd.sh >/dev/null

for i in $(seq 1 120); do
  a=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PRE_PORT/health")
  b=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$DEC_PORT/health")
  if [ "$a" = "200" ] && [ "$b" = "200" ]; then
    echo "   engines healthy after $((i * 2))s"
    break
  fi
  sleep 2
done
[ "$a" = "200" ] && [ "$b" = "200" ] || {
  echo "   !! engines not healthy (P=$a D=$b)"; docker logs sim-pd 2>&1 | tail -20; exit 1; }

echo "== 3/4 start RouteServer with external backends"
docker exec -d rs-pd bash -lc "
  BACKENDS=external \
  PREFILL_ADDR=127.0.0.1:8001 DECODE_ADDR=127.0.0.1:8002 \
  PIPELINE_PATCH=$PATCH \
  nohup /opt/rs_demo.sh > /tmp/rs_demo.out 2>&1
"

echo "== 3b/4 verify the pipeline patch landed"
for _ in $(seq 1 30); do
  docker exec rs-pd test -f /opt/rs_pkg/pipelines/pd_separate.yaml && break
  sleep 1
done
if ! docker exec rs-pd grep -q vllm_ascend_prepare_request /opt/rs_pkg/pipelines/pd_separate.yaml; then
  echo "   !! pipeline patch NOT applied -- RouteServer would silently skip KV transfer"
  exit 1
fi
echo "   patch ok (vllm_ascend_prepare_request present)"

echo "== 4/4 wait for /status running (max 180s)"
for i in $(seq 1 180); do
  body=$(curl -sf "http://127.0.0.1:$RS_PORT/status" 2>/dev/null || true)
  if echo "$body" | grep -q '"status":"running"'; then
    echo "   ready after ${i}s"
    echo "$body" | python3 -m json.tool 2>/dev/null | head -40
    exit 0
  fi
  sleep 1
done
echo "   !! not ready in 180s"
docker exec rs-pd bash -lc 'tail -40 /tmp/rs_demo.out; ls -1 /opt/route_server/*/DistributedScheduler/log/ 2>/dev/null | head'
exit 1
