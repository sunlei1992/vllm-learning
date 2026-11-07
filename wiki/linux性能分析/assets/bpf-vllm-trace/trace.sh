#!/bin/bash
# 在侧挂容器（--pid=host）里执行：等 vLLM 进程出现 -> 采样 -> 退出。
# 关键点：bpftrace 0.17 的 -p 不会给 profile 探针加 pid 过滤，必须显式 /pid == N/。
OUT=/out/bpf-trace2.txt
: > "$OUT"

pid=""
for i in $(seq 1 240); do
  pid=$(pgrep -f "^python /out/${SCRIPT:-sim_rounds.py}" | head -1)
  [ -n "$pid" ] && break
  sleep 0.25
done

if [ -z "$pid" ]; then echo "NO_PID_FOUND" >> "$OUT"; exit 1; fi

echo "target_pid=$pid comm=$(cat /proc/$pid/comm 2>/dev/null) nthreads=$(ls /proc/$pid/task | wc -l)" >> "$OUT"
echo "--- bpftrace start: $(date +%H:%M:%S) ---" >> "$OUT"

PROG='profile:hz:99 /pid == PIDVAL/ { @on[comm] = count(); @kstack[kstack] = count(); } interval:s:40 { exit(); }'
PROG=${PROG/PIDVAL/$pid}

timeout 60 bpftrace -p "$pid" -q -e "$PROG" >> "$OUT" 2>&1

echo "--- bpftrace end: $(date +%H:%M:%S) ---" >> "$OUT"
echo TRACE_DONE >> "$OUT"
