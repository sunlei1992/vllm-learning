#!/usr/bin/env python3
"""GLM-5.3 128K / 24-prefix / 90% APC dry-run: round-robin vs prefix-affinity.

Two simulated P ranks (TP8 DP2 emulated as two TP1 sim servers, aggregate KV
320 GiB each). Prefill-only: max_tokens=1, so timing=zero is enough; we compare
prefix-cache residency / preemption / steps, not wall-clock performance.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import aiohttp
import numpy as np

PREFIX_LEN = 115_200   # 90% of 128K
SUFFIX_LEN = 12_800    # 10%
N_PREFIX = 24
PER_PREFIX = 4         # 96 measured requests
OUT = Path(__file__).resolve().parent / "results"

PORTS = [18100, 18101]


def make_data(per_prefix=PER_PREFIX):
    rng = np.random.default_rng(42)
    prefixes = [
        rng.integers(100, 100_000, size=PREFIX_LEN, dtype=np.int32) for _ in range(N_PREFIX)
    ]
    suffixes = [
        rng.integers(100, 100_000, size=SUFFIX_LEN, dtype=np.int32)
        for _ in range(N_PREFIX * per_prefix)
    ]
    return prefixes, suffixes


def prompts_for(prefixes, suffixes, per_prefix=PER_PREFIX, order="grouped"):
    out = []
    if order == "grouped":
        pairs = ((i, j) for i in range(N_PREFIX) for j in range(per_prefix))
    else:  # interleaved: i cycles fastest, so the waiting queue is mixed
        pairs = ((i, j) for j in range(per_prefix) for i in range(N_PREFIX))
    for i, j in pairs:
        out.append((i, prefixes[i], suffixes[i * per_prefix + j]))
    return out


async def post(session, port, prompt, max_tokens=1):
    body = {
        "model": "glm",
        "prompt": prompt.tolist() if hasattr(prompt, "tolist") else prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "ignore_eos": True,
    }
    async with session.post(f"http://127.0.0.1:{port}/v1/completions", json=body) as r:
        data = await r.json()
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}: {str(data)[:500]}")
        return data


async def reset(session, port):
    try:
        async with session.post(f"http://127.0.0.1:{port}/reset_prefix_cache") as r:
            return r.status
    except Exception as e:  # noqa: BLE001
        return repr(e)


async def snapshot(session, port):
    async with session.get(f"http://127.0.0.1:{port}/metrics") as r:
        text = await r.text()
    out = {"port": port}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith("vllm:"):
            continue
        name = line.split("{", 1)[0].split(" ", 1)[0]
        if name not in {
            "vllm:prefix_cache_queries_total",
            "vllm:prefix_cache_hits_total",
            "vllm:num_preemptions_total",
            "vllm:iteration_tokens_total_count",
        } and not line.startswith("vllm:kv_cache_usage_perc"):
            continue
        try:
            val = float(line.rsplit(" ", 1)[1])
        except ValueError:
            continue
        if name == "vllm:kv_cache_usage_perc":
            out["kv_usage"] = val
        else:
            out[name.replace("vllm:", "").replace("_total", "")] = (
                out.get(name.replace("vllm:", "").replace("_total", ""), 0.0) + val
            )
    return out


def delta(a, b):
    return {k: round(b.get(k, 0) - a.get(k, 0), 2) for k in b if k != "port"}


async def run(mode, prefixes, suffixes, per_prefix=PER_PREFIX, order="grouped"):
    requests = prompts_for(prefixes, suffixes, per_prefix, order)
    timeout = aiohttp.ClientTimeout(total=1800)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for p in PORTS:
            await reset(session, p)

        # Warm: baseline warms all 24 prefixes on both ranks; affinity warms 12 each.
        if mode == "baseline":
            warm = [(p, prefixes[i]) for p in PORTS for i in range(N_PREFIX)]
        else:
            warm = [(PORTS[i % 2], prefixes[i]) for i in range(N_PREFIX)]

        sem = asyncio.Semaphore(16)
        async def warm_one(port, pref):
            async with sem:
                await post(session, port, pref)
        t0 = time.time()
        await asyncio.gather(*(warm_one(p, pref) for p, pref in warm))
        warm_s = time.time() - t0

        before = {p: await snapshot(session, p) for p in PORTS}

        sem = asyncio.Semaphore(64)
        async def one(req_idx, pidx, pref, suff):
            # baseline: round-robin by request; affinity: pin by prefix id.
            port = PORTS[req_idx % 2] if mode == "baseline" else PORTS[pidx % 2]
            prompt = np.concatenate([pref, suff])
            async with sem:
                t = time.time()
                await post(session, port, prompt)
                return time.time() - t
        t0 = time.time()
        walls = await asyncio.gather(
            *(one(k, i, p, s) for k, (i, p, s) in enumerate(requests))
        )
        measured_s = time.time() - t0

        after = {p: await snapshot(session, p) for p in PORTS}

    total = {"prefix_cache_queries": 0.0, "prefix_cache_hits": 0.0,
             "num_preemptions": 0.0, "iteration_tokens": 0.0}
    for p in PORTS:
        d = delta(before[p], after[p])
        for k in total:
            total[k] += d.get(k, 0)
    total["hit_rate"] = (
        total["prefix_cache_hits"] / total["prefix_cache_queries"]
        if total["prefix_cache_queries"] else 0.0
    )
    total["warm_s"] = round(warm_s, 2)
    total["measured_s"] = round(measured_s, 2)
    total["requests"] = len(requests)
    total["wall_p50"] = round(float(np.percentile(walls, 50)), 3)
    total["kv_usage_after"] = {p: round(after[p].get("kv_usage", 0), 4) for p in PORTS}
    total["kv_usage_before"] = {p: round(before[p].get("kv_usage", 0), 4) for p in PORTS}
    return {"mode": mode, **total}


async def run_grouped(prefixes, suffixes, per_prefix):
    """Finish all requests of one prefix before moving to the next."""
    timeout = aiohttp.ClientTimeout(total=3600)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for p in PORTS:
            await reset(session, p)
        total = {"prefix_cache_queries": 0.0, "prefix_cache_hits": 0.0,
                 "num_preemptions": 0.0, "iteration_tokens": 0.0}
        walls = []
        warm_s = measured_s = 0.0
        for i in range(N_PREFIX):
            port = PORTS[i % 2]
            t0 = time.time()
            await post(session, port, prefixes[i])
            warm_s += time.time() - t0
            before = await snapshot(session, port)
            sem = asyncio.Semaphore(64)
            async def one(suff):
                prompt = np.concatenate([prefixes[i], suff])
                async with sem:
                    t = time.time()
                    await post(session, port, prompt)
                    return time.time() - t
            t0 = time.time()
            walls.extend(await asyncio.gather(*(one(suffixes[i * per_prefix + j])
                                                 for j in range(per_prefix))))
            measured_s += time.time() - t0
            after = await snapshot(session, port)
            d = delta(before, after)
            for k in total:
                total[k] += d.get(k, 0)
        total["hit_rate"] = (
            total["prefix_cache_hits"] / total["prefix_cache_queries"]
            if total["prefix_cache_queries"] else 0.0
        )
        total["warm_s"] = round(warm_s, 2)
        total["measured_s"] = round(measured_s, 2)
        total["requests"] = N_PREFIX * per_prefix
        total["wall_p50"] = round(float(np.percentile(walls, 50)), 3)
        total["wall_max"] = round(float(np.max(walls)), 3)
        return {"mode": "grouped", **total}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["baseline", "affinity", "grouped"], required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--per-prefix", type=int, default=PER_PREFIX)
    ap.add_argument("--order", choices=["grouped", "interleaved"], default="grouped")
    args = ap.parse_args()
    prefixes, suffixes = make_data(args.per_prefix)
    if args.mode == "grouped":
        result = await run_grouped(prefixes, suffixes, args.per_prefix)
    else:
        result = await run(args.mode, prefixes, suffixes, args.per_prefix, args.order)
    OUT.mkdir(exist_ok=True)
    path = Path(args.out) if args.out else OUT / f"{args.mode}.json"
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
