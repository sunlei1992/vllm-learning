#!/usr/bin/env python3
"""Compare baseline vs candidate artifacts from run_vslice.sh."""

import json
import statistics
from pathlib import Path

VS = Path(__file__).resolve().parent
RESULTS = VS / "results"


def load_bench(mode):
    rows = []
    for p in sorted(RESULTS.glob(f"{mode}-run*.json")):
        rows.append(json.loads(p.read_text()))
    return rows


def med(rows, key):
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(statistics.median(vals), 3) if vals else None


def load_collect(mode):
    p = VS / "logs" / mode / "collect.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_steps(mode):
    p = RESULTS / f"{mode}-steps.jsonl"
    if not p.exists():
        return None
    steps = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            steps.append(json.loads(line)["step"])
    first = {"SHORT": None, "LONG": None}
    early = {"SHORT": 0, "LONG": 0}
    for i, s in enumerate(steps):
        for r in s.get("requests", []):
            label = "SHORT" if r["num_prompt_tokens"] < 200 else "LONG"
            if r["num_scheduled_tokens"] <= 0:
                continue
            if first[label] is None:
                first[label] = i
            if i < 3:
                early[label] += 1
    return {
        "steps": len(steps),
        "tokens": sum(s["num_prefill_tokens"] + s["num_decode_tokens"] for s in steps),
        "first_short_step": first["SHORT"],
        "first_long_step": first["LONG"],
        "first3_short_tokens": early["SHORT"],
        "first3_long_tokens": early["LONG"],
    }


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def delta(base, cand):
    if base is None or cand is None:
        return "-"
    if isinstance(base, (int, float)) and isinstance(cand, (int, float)):
        if base == 0:
            return "-"
        return f"{(cand - base) / base * 100:+.1f}%"
    return "-"


def main():
    b = load_bench("baseline")
    c = load_bench("candidate")
    if not b or not c:
        raise SystemExit(f"missing bench results: baseline={len(b)} candidate={len(c)}")

    bc = load_collect("baseline")
    cc = load_collect("candidate")
    bs = load_steps("baseline")
    cs = load_steps("candidate")

    print(f"baseline runs={len(b)}  candidate runs={len(c)}\n")
    print(f"{'metric':38s} {'baseline':>12s} {'candidate':>12s} {'delta':>9s}")
    print("-" * 75)

    for key in (
        "p99_ttft_ms", "p50_ttft_ms", "mean_ttft_ms",
        "p99_tpot_ms", "mean_tpot_ms",
        "p99_itl_ms", "mean_itl_ms",
        "total_token_throughput", "output_throughput",
        "request_goodput", "completed", "failed",
    ):
        print(f"{key:38s} {fmt(med(b, key)):>12s} {fmt(med(c, key)):>12s} "
              f"{delta(med(b, key), med(c, key)):>9s}")

    if bc and cc:
        print("\nper-request metrics (collector):")
        for label in ("SHORT", "LONG"):
            for field in ("queue_p50", "queue_p99", "ttft_p50", "ttft_p99",
                          "gen_p50", "itl_p50", "wall_p50"):
                bv = bc["classes"][label].get(field)
                cv = cc["classes"][label].get(field)
                print(f"{label + ' ' + field:38s} {fmt(bv):>12s} {fmt(cv):>12s} "
                      f"{delta(bv, cv):>9s}")
        print(f"{'collector missing_metrics':38s} "
              f"{fmt(bc['overall']['missing_metrics']):>12s} "
              f"{fmt(cc['overall']['missing_metrics']):>12s}")

    if bs and cs:
        print("\nstep trace (measured phase, first 3 steps):")
        for key in ("steps", "tokens", "first_short_step", "first_long_step",
                    "first3_short_tokens", "first3_long_tokens"):
            print(f"{key:38s} {fmt(bs.get(key)):>12s} {fmt(cs.get(key)):>12s} "
                  f"{delta(bs.get(key), cs.get(key)):>9s}")

    print("\nraw bench runs:")
    for name, rows in (("baseline", b), ("candidate", c)):
        vals = [(r.get("p99_ttft_ms"), r.get("total_token_throughput")) for r in rows]
        print(f"  {name}: (p99_ttft_ms, total_token_throughput) = {vals}")


if __name__ == "__main__":
    main()
