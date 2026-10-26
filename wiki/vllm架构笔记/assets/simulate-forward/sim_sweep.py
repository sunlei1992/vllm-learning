"""Parameter sweep: fixed workload, vary max_num_batched_tokens x max_num_seqs.

KV is oversized on purpose so preemption does not confound the comparison.
Each combo builds a fresh engine (in-process mode), so per-combo init cost is
included in the wall time but reported separately as "init".
"""

import gc
import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")

# Fixed workload: 8 requests with a wide length spread.
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
_orig_schedule = Scheduler.schedule


def _schedule(self, *args, **kwargs):
    out = _orig_schedule(self, *args, **kwargs)
    new_ids = {r.req_id for r in out.scheduled_new_reqs}
    prefill = chunk = decode = 0
    for req_id, n in out.num_scheduled_tokens.items():
        if req_id in new_ids:
            prefill += 1
        elif n == 1:
            decode += 1
        else:
            chunk += 1
    pool = self.kv_cache_manager.block_pool
    total = pool.num_gpu_blocks - 1
    steps.append(
        {
            "reqs": len(out.num_scheduled_tokens),
            "tokens": sum(out.num_scheduled_tokens.values()),
            "new": len(out.scheduled_new_reqs),
            "prefill": prefill,
            "chunk": chunk,
            "decode": decode,
            "waiting": len(self.waiting),
            "preempted": len(out.preempted_req_ids or ()),
            "kv_used": total - pool.get_num_free_blocks(),
        }
    )
    return out


Scheduler.schedule = _schedule


def run_combo(max_batched: int, max_seqs: int) -> dict:
    steps.clear()
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
    t1 = time.time()
    llm.generate(PROMPTS, sp)
    gen = time.time() - t1
    del llm
    gc.collect()

    prefill_steps = sum(1 for s in steps if s["prefill"] > 0)
    chunk_steps = sum(1 for s in steps if s["chunk"] > 0)
    decode_only = sum(1 for s in steps if s["decode"] > 0 and s["prefill"] == 0
                      and s["chunk"] == 0)
    return {
        "max_batched": max_batched,
        "max_seqs": max_seqs,
        "init_s": round(init, 2),
        "gen_s": round(gen, 3),
        "steps": len(steps),
        "tokens": sum(s["tokens"] for s in steps),
        "prefill_steps": prefill_steps,
        "chunk_steps": chunk_steps,
        "decode_only_steps": decode_only,
        "avg_reqs": round(sum(s["reqs"] for s in steps) / max(1, len(steps)), 2),
        "peak_tokens": max((s["tokens"] for s in steps), default=0),
        "max_waiting": max((s["waiting"] for s in steps), default=0),
        "preemptions": sum(s["preempted"] for s in steps),
        "peak_kv": max((s["kv_used"] for s in steps), default=0),
    }


def main() -> None:
    results = []
    for mb in (64, 128, 256, 512):
        for ms in (2, 4, 8):
            r = run_combo(mb, ms)
            results.append(r)
            print(
                f"[sweep] batched={mb:3d} seqs={ms}: steps={r['steps']:4d} "
                f"avg_reqs={r['avg_reqs']:4.2f} peak_tok={r['peak_tokens']:3d} "
                f"prefill={r['prefill_steps']:3d} chunk={r['chunk_steps']:3d} "
                f"dec={r['decode_only_steps']:3d} wait={r['max_waiting']} "
                f"preempt={r['preemptions']} kv={r['peak_kv']:3d} "
                f"gen={r['gen_s']:6.2f}s",
                flush=True,
            )
    with open("/logs/sweep.json", "w") as f:
        json.dump(results, f, indent=1)

    print("\n[sweep] markdown")
    print("| batched | seqs | steps | avg_reqs | peak_tok | prefill | chunk | decode | max_waiting | preempt | gen_s |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(
            f"| {r['max_batched']} | {r['max_seqs']} | {r['steps']} | {r['avg_reqs']} | "
            f"{r['peak_tokens']} | {r['prefill_steps']} | {r['chunk_steps']} | "
            f"{r['decode_only_steps']} | {r['max_waiting']} | {r['preemptions']} | {r['gen_s']} |"
        )


if __name__ == "__main__":
    main()
