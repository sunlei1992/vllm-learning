#!/usr/bin/env python3
"""Send the mixed case concurrently and collect per-request metrics.

This complements `vllm bench serve`: bench gives aggregate percentiles, this
gives per-class (short/long) queue and TTFT distributions.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import aiohttp

TRACE = [100 + i for i in range(64)]


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, int(round(p / 100.0 * (len(values) - 1))))
    return round(values[idx], 3)


def summarize(rows, label):
    subset = [r for r in rows if r["label"] == label and r.get("metrics")]
    q = [r["metrics"]["queue_time_ms"] for r in subset if r["metrics"].get("queue_time_ms") is not None]
    ttft = [r["metrics"]["time_to_first_token_ms"] for r in subset if r["metrics"].get("time_to_first_token_ms") is not None]
    gen = [r["metrics"]["generation_time_ms"] for r in subset if r["metrics"].get("generation_time_ms") is not None]
    itl = [r["metrics"]["mean_itl_ms"] for r in subset if r["metrics"].get("mean_itl_ms") is not None]
    wall = [r["wall_ms"] for r in subset]
    return {
        "label": label,
        "n": len(subset),
        "queue_p50": pct(q, 50),
        "queue_p99": pct(q, 99),
        "ttft_p50": pct(ttft, 50),
        "ttft_p99": pct(ttft, 99),
        "gen_p50": pct(gen, 50),
        "itl_p50": pct(itl, 50),
        "wall_p50": pct(wall, 50),
    }


async def one(session, url, model, row, idx, sem):
    async with sem:
        body = {
            "model": model,
            "prompt": row["prompt"],
            "max_tokens": row["output_tokens"],
            "temperature": 0,
            "stream": False,
            "return_token_ids": True,
            "trace_decode_token_ids": TRACE[: row["output_tokens"]],
        }
        try:
            t0 = time.perf_counter()
            async with session.post(url, json=body) as resp:
                data = await resp.json()
                status = resp.status
            wall_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as e:  # noqa: BLE001
            return {"idx": idx, "label": row["label"], "error": repr(e)}
        return {
            "idx": idx,
            "label": row["label"],
            "status": status,
            "metrics": data.get("metrics"),
            "usage": data.get("usage"),
            "wall_ms": round(wall_ms, 3),
        }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:18081")
    ap.add_argument("--case", required=True)
    ap.add_argument("--model", default="qwen")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = [json.loads(line) for line in open(args.case, encoding="utf-8") if line.strip()]
    for i, r in enumerate(rows):
        r["label"] = "LONG" if r["prompt"].startswith("LONG-") else "SHORT"

    sem = asyncio.Semaphore(len(rows))
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        t0 = time.perf_counter()
        results = await asyncio.gather(
            *(one(session, args.url.rstrip("/") + "/v1/completions", args.model, r, i, sem)
              for i, r in enumerate(rows))
        )
        elapsed = time.perf_counter() - t0

    out = {
        "elapsed_s": round(elapsed, 3),
        "rows": results,
        "classes": {label: summarize(results, label) for label in ("LONG", "SHORT")},
        "overall": {
            "n": len([r for r in results if r.get("metrics")]),
            "missing_metrics": len([r for r in results if not r.get("metrics")]),
            "errors": len([r for r in results if r.get("error")]),
        },
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("elapsed_s", "overall", "classes")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
