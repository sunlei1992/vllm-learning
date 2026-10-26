"""Minimal timing model on top of the simulator.

Each scheduling step is priced as:

    step_cost = c_prefill * prefill_tokens + c_decode * decode_tokens + c_overhead

Per request we then derive TTFT (end of the step where its prefill completes)
and TPOT (decode span / (output_len - 1)). Because the coefficients are not
calibrated on real hardware, we sweep the ratio r = c_prefill / c_decode and
show how the winner changes with it.
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")

PROMPTS = [
    "Hello",
    "Hello " * 10,
    "Hello " * 50,
    "Hello " * 200,
    "Hello " * 400,
    "Hello " * 800,
    "Hello",
    "Hello " * 20,
]
MAX_TOKENS = 8
TRACE = [100 + (i % 4) for i in range(MAX_TOKENS)]

steps: list[dict] = []
prompt_len: dict[str, int] = {}
_orig_schedule = Scheduler.schedule


def _schedule(self, *args, **kwargs):
    out = _orig_schedule(self, *args, **kwargs)
    for r in out.scheduled_new_reqs:
        req = self.requests.get(r.req_id)
        if req is not None:
            prompt_len[r.req_id] = req.num_prompt_tokens
    pool = self.kv_cache_manager.block_pool
    total = pool.num_gpu_blocks - 1
    steps.append(
        {
            "tokens_map": dict(out.num_scheduled_tokens),
            "waiting": len(self.waiting),
            "preempted": len(out.preempted_req_ids or ()),
            "kv_used": total - pool.get_num_free_blocks(),
        }
    )
    return out


Scheduler.schedule = _schedule


def simulate(steps_list: list[dict], plen: dict[str, int],
             c_prefill: float, c_decode: float, c_overhead: float):
    """Return per-request metrics under the given cost model."""
    cum: dict[str, int] = {}
    ttft: dict[str, float] = {}
    end: dict[str, float] = {}
    t = 0.0
    for s in steps_list:
        prefill_tokens = decode_tokens = 0
        for rid, n in s["tokens_map"].items():
            pl = plen.get(rid, 0)
            before = cum.get(rid, 0)
            if before < pl:
                prefill_tokens += n
            else:
                decode_tokens += n
            cum[rid] = before + n
        t += c_prefill * prefill_tokens + c_decode * decode_tokens + c_overhead
        for rid in s["tokens_map"]:
            pl = plen.get(rid, 0)
            if rid not in ttft and pl > 0 and cum[rid] >= pl:
                ttft[rid] = t
            end[rid] = t
    tpot = {}
    for rid, tt in ttft.items():
        span = end.get(rid, tt) - tt
        tpot[rid] = span / max(1, MAX_TOKENS - 1)
    return {"ttft": ttft, "tpot": tpot, "makespan": t, "steps": len(steps_list)}


def run_combo(max_batched: int, max_seqs: int) -> dict:
    steps.clear()
    prompt_len.clear()
    t0 = time.time()
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        max_num_seqs=max_seqs,
        max_num_batched_tokens=max_batched,
        enable_prefix_caching=False,
    )
    init = time.time() - t0
    sp = SamplingParams(max_tokens=MAX_TOKENS, trace_decode_token_ids=TRACE)
    llm.generate(PROMPTS, sp)
    del llm
    return {
        "max_batched": max_batched,
        "max_seqs": max_seqs,
        "init_s": round(init, 2),
        "steps": [dict(s) for s in steps],
        "prompt_len": dict(prompt_len),
    }


def summarize(run: dict, c_prefill: float, c_decode: float, c_overhead: float) -> dict:
    m = simulate(run["steps"], run["prompt_len"], c_prefill, c_decode, c_overhead)
    ttfts = list(m["ttft"].values())
    tpots = list(m["tpot"].values())
    return {
        "max_batched": run["max_batched"],
        "max_seqs": run["max_seqs"],
        "steps": m["steps"],
        "mean_ttft": round(sum(ttfts) / max(1, len(ttfts)), 3),
        "p95_ttft": round(sorted(ttfts)[int(0.95 * (len(ttfts) - 1))], 3) if ttfts else 0,
        "mean_tpot": round(sum(tpots) / max(1, len(tpots)), 3),
        "makespan": round(m["makespan"], 3),
    }


def main() -> None:
    runs = []
    for mb in (64, 128, 256, 512):
        for ms in (2, 4, 8):
            r = run_combo(mb, ms)
            runs.append(r)
            print(f"[run] batched={mb} seqs={ms} steps={len(r['steps'])}", flush=True)

    # c_decode = 1.0, step overhead = 0.05; vary the prefill/decode ratio.
    results = {}
    for ratio in (0.01, 0.1, 1.0):
        rows = [summarize(r, ratio, 1.0, 0.05) for r in runs]
        results[str(ratio)] = rows
        best_ms = min(rows, key=lambda x: x["makespan"])
        best_ttft = min(rows, key=lambda x: x["mean_ttft"])
        print(f"\n=== c_prefill/c_decode = {ratio} ===")
        print("| batched | seqs | steps | mean_ttft | p95_ttft | mean_tpot | makespan |")
        print("|---|---|---|---|---|---|---|")
        for x in rows:
            print(
                f"| {x['max_batched']} | {x['max_seqs']} | {x['steps']} | "
                f"{x['mean_ttft']} | {x['p95_ttft']} | {x['mean_tpot']} | {x['makespan']} |"
            )
        print(f"best makespan: batched={best_ms['max_batched']} seqs={best_ms['max_seqs']}")
        print(f"best mean TTFT: batched={best_ttft['max_batched']} seqs={best_ttft['max_seqs']}")

    with open("/logs/timing.json", "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
