"""Compare scheduling policies on the dry-run simulator.

Policies are implemented by reordering the scheduler's waiting queue before
each schedule() call, so no vLLM code changes are needed:

  fcfs            - leave the queue as is
  shortest_first  - sort by prompt length ascending
  longest_first   - sort by prompt length descending

Everything else (workload, KV size, token budget, cost model) is fixed.
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
MAX_TOKENS = 8
TRACE = [100 + (i % 4) for i in range(MAX_TOKENS)]

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

# cost model (uncalibrated, fixed across policies)
C_PREFILL = 0.1
C_DECODE = 1.0
C_OVERHEAD = 0.05

policy = "fcfs"
steps: list[dict] = []
prompt_len: dict[str, int] = {}
_orig_schedule = Scheduler.schedule


def _schedule(self, *args, **kwargs):
    if policy != "fcfs" and len(self.waiting) > 1:
        items = list(self.waiting)
        items.sort(
            key=lambda r: r.num_prompt_tokens,
            reverse=(policy == "longest_first"),
        )
        self.waiting.clear()
        self.waiting.extend(items)
    out = _orig_schedule(self, *args, **kwargs)
    for r in out.scheduled_new_reqs:
        req = self.requests.get(r.req_id)
        if req is not None:
            prompt_len[r.req_id] = req.num_prompt_tokens
    steps.append(
        {
            "tokens_map": dict(out.num_scheduled_tokens),
            "waiting": len(self.waiting),
            "preempted": len(out.preempted_req_ids or ()),
        }
    )
    return out


Scheduler.schedule = _schedule


def simulate(steps_list, plen):
    cum: dict[str, int] = {}
    ttft: dict[str, float] = {}
    end: dict[str, float] = {}
    t = 0.0
    for s in steps_list:
        prefill = decode = 0
        for rid, n in s["tokens_map"].items():
            pl = plen.get(rid, 0)
            before = cum.get(rid, 0)
            if before < pl:
                prefill += n
            else:
                decode += n
            cum[rid] = before + n
        t += C_PREFILL * prefill + C_DECODE * decode + C_OVERHEAD
        for rid in s["tokens_map"]:
            pl = plen.get(rid, 0)
            if rid not in ttft and pl > 0 and cum[rid] >= pl:
                ttft[rid] = t
            end[rid] = t
    tpot = {rid: (end[rid] - tt) / max(1, MAX_TOKENS - 1) for rid, tt in ttft.items()}
    return ttft, tpot, t


def run(name: str) -> dict:
    global policy
    policy = name
    steps.clear()
    prompt_len.clear()
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        max_num_seqs=8,
        max_num_batched_tokens=256,
        enable_prefix_caching=False,
    )
    sp = SamplingParams(max_tokens=MAX_TOKENS, trace_decode_token_ids=TRACE)
    llm.generate(PROMPTS, sp)
    del llm
    ttft, tpot, makespan = simulate(steps, prompt_len)
    tts = sorted(ttft.values())
    return {
        "policy": name,
        "steps": len(steps),
        "mean_ttft": round(sum(tts) / len(tts), 2),
        "p50_ttft": round(tts[len(tts) // 2], 2),
        "p95_ttft": round(tts[int(0.95 * (len(tts) - 1))], 2),
        "max_ttft": round(tts[-1], 2),
        "mean_tpot": round(sum(tpot.values()) / len(tpot), 2),
        "makespan": round(makespan, 2),
    }


def main() -> None:
    rows = []
    for name in ("fcfs", "shortest_first", "longest_first"):
        r = run(name)
        rows.append(r)
        print(
            f"[policy] {name:15s} steps={r['steps']:3d} "
            f"mean_ttft={r['mean_ttft']:7.2f} p50={r['p50_ttft']:7.2f} "
            f"p95={r['p95_ttft']:7.2f} max={r['max_ttft']:7.2f} "
            f"mean_tpot={r['mean_tpot']:6.2f} makespan={r['makespan']:8.2f}",
            flush=True,
        )
    with open("/logs/policy.json", "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
