"""Prefix-cache experiment: shared prompt prefix across sequential requests.

Runs the same 8-request workload twice, once with prefix caching disabled and
once enabled, and reports how many prompt tokens each request actually has to
compute plus the KV blocks retained.
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
PREFIX = "You are a helpful assistant. " * 60
QUESTIONS = [f"Question {i}: what is the capital of France?" for i in range(8)]
PROMPTS = [PREFIX + q for q in QUESTIONS]
MAX_BATCHED = int(os.environ.get("MAX_BATCHED", "512"))

steps: list[dict] = []
_orig_schedule = Scheduler.schedule


def _schedule(self, *args, **kwargs):
    out = _orig_schedule(self, *args, **kwargs)
    infos = []
    for r in out.scheduled_new_reqs:
        req = self.requests.get(r.req_id)
        infos.append(
            {
                "req_id": r.req_id,
                "prompt": req.num_prompt_tokens if req else None,
                "cached": r.num_computed_tokens,
                "first_scheduled": out.num_scheduled_tokens.get(r.req_id),
            }
        )
    pool = self.kv_cache_manager.block_pool
    total = pool.num_gpu_blocks - 1
    steps.append(
        {
            "tokens": sum(out.num_scheduled_tokens.values()),
            "prefill_tokens": sum(n for n in out.num_scheduled_tokens.values() if n > 1),
            "reqs": len(out.num_scheduled_tokens),
            "kv_used": total - pool.get_num_free_blocks(),
            "new_infos": infos,
        }
    )
    return out


Scheduler.schedule = _schedule


def kv_used(llm) -> int | None:
    try:
        core = llm.llm_engine.engine_core.engine_core
        pool = core.scheduler.kv_cache_manager.block_pool
        return (pool.num_gpu_blocks - 1) - pool.get_num_free_blocks()
    except Exception:
        return None


def run(enabled: bool) -> dict:
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        max_num_seqs=8,
        max_num_batched_tokens=MAX_BATCHED,
        enable_prefix_caching=enabled,
    )
    tok = llm.get_tokenizer()
    sp = SamplingParams(max_tokens=2, trace_decode_token_ids=[100, 101])
    rounds = []
    for i, prompt in enumerate(PROMPTS):
        steps.clear()
        t0 = time.time()
        llm.generate([prompt], sp)
        dt = time.time() - t0
        info = steps[0]["new_infos"][0] if steps and steps[0]["new_infos"] else {}
        rounds.append(
            {
                "i": i,
                "prompt_tokens": len(tok.encode(prompt)),
                "cached": info.get("cached"),
                "first_scheduled": info.get("first_scheduled"),
                "steps": len(steps),
                "prefill_tokens": sum(s["prefill_tokens"] for s in steps),
                "kv_peak": max(s["kv_used"] for s in steps),
                "time": round(dt, 3),
            }
        )
    final_kv = kv_used(llm)
    del llm
    return {"enabled": enabled, "rounds": rounds, "final_kv": final_kv}


def main() -> None:
    out = {}
    for enabled in (False, True):
        r = run(enabled)
        out["on" if enabled else "off"] = r
        print(f"\n=== prefix caching {'ON' if enabled else 'OFF'} ===")
        print("i  prompt  cached  first_sched  prefill  steps  kv_peak")
        for x in r["rounds"]:
            print(
                f"{x['i']}  {x['prompt_tokens']:6d}  {x['cached']:6d}  "
                f"{x['first_scheduled']:11d}  {x['prefill_tokens']:6d}  "
                f"{x['steps']:5d}  {x['kv_peak']:7d}"
            )
        total_computed = sum(x["prefill_tokens"] for x in r["rounds"])
        total_prompt = sum(x["prompt_tokens"] for x in r["rounds"])
        print(f"computed prefill tokens: {total_computed} / {total_prompt} "
              f"({100 * total_computed / total_prompt:.1f}%)")
        print(f"final kv blocks retained: {r['final_kv']}")
    with open("/logs/prefix.json", "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
