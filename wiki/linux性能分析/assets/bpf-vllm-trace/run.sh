#!/bin/bash
# 复现 wiki/linux性能分析/001 §13.1 的实测：
#   在 sim-int:dry-run 里跑空跑负载，同时用 --pid=host 侧挂容器采样 vLLM 进程。
#
# 用法：
#   VLLM_LAB_ROOT=/Users/sunlei/code/dsh/vllm ./run.sh
#
# 可选环境变量：
#   IMAGE=sim-int:dry-run     被测镜像
#   SCRIPT=sim_rounds.py      跑哪个 tmp/ 下的脚本
#   KEEP=1                    结束后保留容器（调试用）
set -euo pipefail

ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)}"
IMAGE="${IMAGE:-sim-int:dry-run}"
SCRIPT="${SCRIPT:-sim_rounds.py}"
LOGDIR="$ROOT/tmp/simlogs"
mkdir -p "$LOGDIR" "$ROOT/tmp/triton-cache"

cleanup() {
  [ "${KEEP:-0}" = "1" ] && { echo "[keep] containers left running"; return; }
  docker rm -f vllm-bpf bpf-side >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker rm -f vllm-bpf bpf-side >/dev/null 2>&1 || true

echo "[1/5] start workload container"
docker run -d --name vllm-bpf --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp":/wheels:ro \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$LOGDIR":/logs \
  -v "$ROOT/tmp/triton-cache":/triton-cache \
  "$IMAGE" bash -c 'cd /work && sleep 3600' >/dev/null

echo "[2/5] start bpftrace sidecar (installs bpftrace on first use)"
docker run -d --name bpf-side --privileged --pid=host \
  -v /sys/kernel/debug:/sys/kernel/debug \
  -v "$LOGDIR":/out \
  debian:bookworm-slim bash -c \
  'apt-get update -qq && apt-get install -y -qq bpftrace procps && touch /out/bpf-ready && sleep 3600' >/dev/null

echo "[3/5] wait for bpftrace"
for _ in $(seq 1 240); do
  if [ -f "$LOGDIR/bpf-ready" ]; then break; fi
  sleep 1
done
docker exec bpf-side bpftrace --version

echo "[4/5] run workload + trace"
docker exec -d -e SCRIPT="$SCRIPT" bpf-side bash /out/trace.sh
sleep 1
docker exec vllm-bpf bash -c \
  "cd /work && VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/triton-cache python /out/$SCRIPT" \
  > "$LOGDIR/workload.log" 2>&1 || true

for _ in $(seq 1 90); do
  grep -q TRACE_DONE "$LOGDIR/bpf-trace2.txt" 2>/dev/null && break
  sleep 1
done

echo "[5/5] result"
echo "--- samples by comm ---"
grep '^@on\[' "$LOGDIR/bpf-trace2.txt" || true
echo "--- empty kstack (user-space samples) ---"
grep '^@kstack\[\]:' "$LOGDIR/bpf-trace2.txt" || true
echo "--- workload tail ---"
tail -3 "$LOGDIR/workload.log"
echo "full trace: $LOGDIR/bpf-trace2.txt"
