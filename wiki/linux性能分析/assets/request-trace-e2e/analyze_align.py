"""Align request_trace stage_timings with bpftrace sched_switch events.

Both sides share CLOCK_MONOTONIC on the same host:
  - request_trace logs  time.time()      (epoch wall clock)
  - bpftrace prints     nsecs            (CLOCK_MONOTONIC, via %lld!)
The driver records (t0_wall, t0_mono_ns) at start, so:

    mono_ns(wall) = t0_mono_ns + (wall - t0_wall) * 1e9

Usage:
    python analyze_align.py <trace_log_dir> <bpf-sched.txt> [out.csv]
"""

import json
import sys

import pandas as pd


def main() -> None:
    logdir, bpf_path = sys.argv[1], sys.argv[2]
    out_csv = sys.argv[3] if len(sys.argv) > 3 else f"{logdir}/align.csv"

    meta = json.load(open(f"{logdir}/meta.json"))
    t0w, t0m = meta["t0_wall"], meta["t0_mono_ns"]

    # off-CPU intervals from sched_switch OUT/IN pairs
    events = []
    for line in open(bpf_path):
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("OUT", "IN"):
            events.append((int(parts[1]), parts[0]))
    events.sort()

    off, start = [], None
    for t, kind in events:
        if kind == "OUT" and start is None:
            start = t
        elif kind == "IN" and start is not None:
            off.append((start, t))
            start = None

    span_s = (events[-1][0] - events[0][0]) / 1e9
    total_off_ms = sum(b - a for a, b in off) / 1e6
    print(f"off-CPU intervals={len(off)} total_off={total_off_ms:.0f}ms over {span_s:.2f}s")

    def overlap_ms(s: float, e: float) -> float:
        return sum(max(0, min(e, b) - max(s, a)) for a, b in off) / 1e6

    st = pd.read_excel(f"{logdir}/time_analysis.xlsx", sheet_name="stage_timings")
    rows = []
    for _, r in st[st["Status"] == "ok"].iterrows():
        s = t0m + (r["Start"] - t0w) * 1e9
        e = t0m + (r["End"] - t0w) * 1e9
        dur = float(r["Duration(ms)"])
        off_ms = overlap_ms(s, e)
        rows.append(
            {
                "RequestID": r["RequestID"],
                "StepID": r["StepID"],
                "Stage": r["Stage"],
                "duration_ms": round(dur, 3),
                "offcpu_ms": round(off_ms, 3),
                "on_cpu_pct": round((dur - off_ms) / dur * 100, 1) if dur else None,
            }
        )

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv(out_csv, index=False)
    print(f"\nwrote {out_csv}")


if __name__ == "__main__":
    main()
