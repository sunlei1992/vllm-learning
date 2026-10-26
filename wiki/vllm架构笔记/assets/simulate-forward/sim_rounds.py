"""Multi-round simulate-forward experiment with per-step scheduler observation.

Each round calls llm.generate() on the same engine instance. Per scheduling
step we record tokens, batch composition (prefill / chunk / decode), queue
occupancy, preemptions, and KV block usage.
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")

steps: list[dict] = []
state = {"round": -1}
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
            "round": state["round"],
            "reqs": len(out.num_scheduled_tokens),
            "tokens": sum(out.num_scheduled_tokens.values()),
            "new": len(out.scheduled_new_reqs),
            "prefill": prefill,
            "chunk": chunk,
            "decode": decode,
            "running": len(self.running),
            "waiting": len(self.waiting),
            "preempted": len(out.preempted_req_ids or ()),
            "kv_used": total - pool.get_num_free_blocks(),
            "kv_total": total,
        }
    )
    return out


Scheduler.schedule = _schedule

ROUNDS = [
    ["Hello", "Hi there"],
    ["Hello " * 300],
    ["Hello", "Hi", "Hey", "Yo"],
]


def main() -> None:
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        max_num_seqs=4,
        max_num_batched_tokens=64,
        enable_prefix_caching=False,
    )
    sp = SamplingParams(max_tokens=2, trace_decode_token_ids=[100, 101])

    for i, prompts in enumerate(ROUNDS):
        state["round"] = i
        before = len(steps)
        t0 = time.time()
        outs = llm.generate(prompts, sp)
        dt = time.time() - t0
        rs = steps[before:]
        toks = sum(s["tokens"] for s in rs)
        peak_kv = max((s["kv_used"] for s in rs), default=0)
        print(
            f"[round {i}] reqs={len(prompts)} steps={len(rs)} tokens={toks} "
            f"peak_kv_blocks={peak_kv}/{rs[0]['kv_total'] if rs else 0} "
            f"preempted={sum(s['preempted'] for s in rs)} time={dt:.3f}s",
            flush=True,
        )
        for s in rs:
            print(
                f"    step r{s['round']}: reqs={s['reqs']} tokens={s['tokens']:3d} "
                f"new={s['new']} prefill={s['prefill']} chunk={s['chunk']} "
                f"decode={s['decode']} running={s['running']} waiting={s['waiting']} "
                f"kv={s['kv_used']:3d}",
                flush=True,
            )
        print("    ids:", [o.outputs[0].token_ids for o in outs], flush=True)

    print(f"[total] steps={len(steps)}")
    with open("/logs/rounds.json", "w") as f:
        json.dump(steps, f, indent=1)


if __name__ == "__main__":
    main()
