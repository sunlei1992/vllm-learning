#!/usr/bin/env python3
"""把 AISBench PrefixCache 造出来的 requests 回放到空跑 vLLM（混部单实例），
用 /metrics 的 prefix_cache 计数器算**实际命中率**，和 009 的理论值对账。

用法:
  python3 apc_sim_test.py --full <...>.full.jsonl --mode warmup
  python3 apc_sim_test.py --full <...>.full.jsonl --mode cold
"""
import argparse
import json
import time
import urllib.request

URL = "http://127.0.0.1:18000"
TRACE = list(range(100, 108))


def post(prompt, max_tokens=8, timeout=120):
    body = json.dumps({
        "model": "qwen",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
        "return_token_ids": True,
        "trace_decode_token_ids": TRACE,
    }).encode()
    req = urllib.request.Request(f"{URL}/v1/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return time.time() - t0, d["usage"]["prompt_tokens"], d["usage"]["completion_tokens"]


def metrics():
    with urllib.request.urlopen(f"{URL}/metrics", timeout=30) as r:
        txt = r.read().decode()
    out = {}
    for line in txt.splitlines():
        if line.startswith("#"):
            continue
        for key in ("vllm:prefix_cache_queries_total", "vllm:prefix_cache_hits_total"):
            if line.startswith(key):
                val = float(line.rsplit(" ", 1)[1])
                out[key] = out.get(key, 0.0) + val
    return out


def reset_cache():
    try:
        req = urllib.request.Request(f"{URL}/reset_prefix_cache", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except Exception as e:
        return f"unavailable: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True)
    ap.add_argument("--mode", choices=["warmup", "cold"], default="warmup")
    ap.add_argument("--out", default=None, help="把结果 JSON 写到这里")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.full, encoding="utf-8") if l.strip()]
    rows.sort(key=lambda r: r["sequence_index"])
    groups = {}
    for r in rows:
        groups.setdefault(r["group_id"], []).append(r)

    print(f"requests={len(rows)} groups={len(groups)} mode={args.mode}")
    print("reset_prefix_cache ->", reset_cache())

    t_start = time.time()
    if args.mode == "warmup":
        t0 = time.time()
        for gid, rs in groups.items():
            post(rs[0]["question"], max_tokens=1)
        warm_s = time.time() - t0
        print(f"warmup: {len(groups)} 条，{warm_s:.2f}s")
    else:
        warm_s = 0.0

    m0 = metrics()
    lat = []
    prompt_tokens = 0
    completion_tokens = 0
    for r in rows:
        dt, pt, ct = post(r["question"], max_tokens=min(8, r.get("max_tokens", 8)))
        lat.append(dt)
        prompt_tokens += pt
        completion_tokens += ct
    m1 = metrics()
    total_s = time.time() - t_start

    dq = m1["vllm:prefix_cache_queries_total"] - m0["vllm:prefix_cache_queries_total"]
    dh = m1["vllm:prefix_cache_hits_total"] - m0["vllm:prefix_cache_hits_total"]
    actual = dh / dq if dq else 0.0
    lat.sort()

    res = {
        "mode": args.mode,
        "requests": len(rows),
        "groups": len(groups),
        "prompt_tokens_reported": prompt_tokens,
        "completion_tokens_reported": completion_tokens,
        "prefix_cache_queries": dq,
        "prefix_cache_hits": dh,
        "actual_hit_rate": round(actual, 6),
        "hits_per_request": round(dh / len(rows), 2),
        "warmup_seconds": round(warm_s, 2),
        "total_seconds": round(total_s, 2),
        "latency_p50_ms": round(lat[len(lat) // 2] * 1000, 1),
        "latency_max_ms": round(lat[-1] * 1000, 1),
    }
    print(json.dumps(res, indent=2, ensure_ascii=False))
    if args.out:
        json.dump(res, open(args.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
