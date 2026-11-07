#!/bin/bash
# Sidecar: wait for run_e2e.py, then record sched_switch in/out + 99Hz samples.
# NOTE: printf must use %lld for nsecs -- "%d" truncates to 32-bit and the
# timestamps wrap (observed 2026-11-07).
export BPFTRACE_PERF_RB_PAGES=256
OUT=/out/bpf-sched.txt
: > "$OUT"

pid=""
for i in $(seq 1 600); do
  pid=$(pgrep -f '^python /out/run_e2e.py' | head -1)
  [ -n "$pid" ] && break
  sleep 0.2
done
if [ -z "$pid" ]; then echo "NO_PID_FOUND" >> "$OUT"; exit 1; fi

echo "PID=$pid" >> "$OUT"
timeout 90 bpftrace -p "$pid" -q -e "
BEGIN { printf(\"BEGIN %lld\\n\", nsecs); }
tracepoint:sched:sched_switch /args->prev_pid == $pid/ { printf(\"OUT %lld %d\\n\", nsecs, args->prev_state); }
tracepoint:sched:sched_switch /args->next_pid == $pid/ { printf(\"IN %lld\\n\", nsecs); }
profile:hz:99 /pid == $pid/ { printf(\"S %lld\\n\", nsecs); }
interval:s:30 { exit(); }
" >> "$OUT" 2>&1
echo "DONE" >> "$OUT"
