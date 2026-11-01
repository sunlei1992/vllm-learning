#!/usr/bin/env python3
"""Closed-loop 24-worker benchmark for the 128K / 24-prefix case.

Each worker owns one prefix and sends 40 requests sequentially; the next
request is only sent after the previous one completes. Total concurrency is
fixed at 24. We measure makespan, effective in-flight requests, APC hit, and
per-request latency (output=1, so latency == TTFT).
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import aiohttp
import numpy as np

PREFIX_LEN = 115_200
SUFFIX_LEN = 12_800
N_PREFIX = 24
PER_PREFIX = 40
OUT = Path(__file__).resolve().parent / "results"
PORTS = [18100, 18101]


def make_data(seed=42):
    rng = np.random.default_rng(seed)
    prefixes = [
        rng.integers(100, 100_000, size=PREFIX_LEN, dtype=np.int32)
        for _ in range(N_PREFIX)
    ]
    suffixes = [
        rng.integers(100, 100_000, size=SUFFIX_LEN, dtype=np.int32)
        for _ in range(N_PREFIX * PER_PREFIX)
    ]
    return prefixes, suffixes


async def post(session, port, prompt, max_tokens=1):
    body = {
        "model": "glm",
        "prompt": prompt.tolist(),
        "max_tokens": max_tokens,
        "temperature": 0,
        "ignore_eos": True,
    }
    t0 = time.perf_counter()
    async with session.post(f"http://127.0.0.1:{port}/v1/completions", json=body) as r:
        data = await r.json()
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}: {str(data)[:300]}")
    return time.perf_counter() - t0, data


async def snapshot(session):
    out = {}
    for port in PORTS:
        async with session.get(f"http://127.0.0.1:{port}/metrics") as r:
            text = await r.text()
        vals = {"running": 0.0, "waiting": 0.0, "queries": 0.0, "hits": 0.0,
                "preemptions": 0.0}
        for line in text.splitlines():
            if line.startswith("#"):
                continue
            if line.startswith("vllm:num_requests_running"):
                vals["running"] += float(line.rsplit(" ", 1)[1])
            elif line.startswith("vllm:num_requests_waiting{"):
                vals["waiting"] += float(line.rsplit(" ", 1)[1])
            elif line.startswith("vllm:prefix_cache_queries_total"):
                vals["queries"] += float(line.rsplit(" ", 1)[1])
            elif line.startswith("vllm:prefix_cache_hits_total"):
                vals["hits"] += float(line.rsplit(" ", 1)[1])
            elif line.startswith("vllm:num_preemptions_total"):
                vals["preemptions"] += float(line.rsplit(" ", 1)[1])
        out[port] = vals
    return out


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))
    return round(s[idx], 3)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-prefix", type=int, default=PER_PREFIX)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    prefixes, suffixes = make_data()
    timeout = aiohttp.ClientTimeout(total=3600)
    samples = []
    latencies = []
    peak = {"running": 0.0, "waiting": 0.0}

    async with aiohttp.ClientSession(timeout=timeout) as session:
        before = await snapshot(session)

        async def sample_loop(done: asyncio.Event):
            while not done.is_set():
                s = await snapshot(session)
                running = sum(v["running"] for v in s.values())
                waiting = sum(v["waiting"] for v in s.values())
                peak["running"] = max(peak["running"], running)
                peak["waiting"] = max(peak["waiting"], waiting)
                samples.append((time.perf_counter(), running, waiting))
                await asyncio.sleep(0.05)

        async def worker(i: int):
            port = PORTS[i % 2]
            for j in range(args.per_prefix):
                prompt = np.concatenate([prefixes[i], suffixes[i * args.per_prefix + j]])
                latency, _ = await post(session, port, prompt, max_tokens=1)
                latencies.append(latency)

        done = asyncio.Event()
        sampler = asyncio.create_task(sample_loop(done))
        t0 = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(N_PREFIX)))
        makespan = time.perf_counter() - t0
        done.set()
        await sampler
        after = await snapshot(session)

    queries = sum(after[p]["queries"] - before[p]["queries"] for p in PORTS)
    hits = sum(after[p]["hits"] - before[p]["hits"] for p in PORTS)
    preemptions = sum(after[p]["preemptions"] - before[p]["preemptions"] for p in PORTS)
    running_samples = [r for _, r, _ in samples]
    waiting_samples = [w for _, _, w in samples]
    result = {
        "requests": N_PREFIX * args.per_prefix,
        "per_prefix": args.per_prefix,
        "makespan_s": round(makespan, 3),
        "throughput_req_s": round(N_PREFIX * args.per_prefix / makespan, 4),
        "latency_p50_s": pct(latencies, 50),
        "latency_p99_s": pct(latencies, 99),
        "latency_max_s": round(max(latencies), 3),
        "effective_running_p50": pct(running_samples, 50),
        "effective_running_max": peak["running"],
        "waiting_p50": pct(waiting_samples, 50),
        "waiting_max": peak["waiting"],
        "prefix_cache_queries": queries,
        "prefix_cache_hits": hits,
        "apc_hit_rate": round(hits / queries, 4) if queries else 0.0,
        "preemptions": preemptions,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
