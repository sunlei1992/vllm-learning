"""Chunk-fill experiment: why does a step not use the full token budget?

Builds 24 shared prefixes x N requests, 90% prefix-cache hit, and records
per-step scheduled tokens / free blocks / running / waiting.

Env:
  PREFIX_TOKENS=11520  SUFFIX_TOKENS=1280  REQ_PER_PREFIX=4  N_PREFIX=24
  CHUNK=3276  CONC=64  KV_MB=65536  MAX_MODEL_LEN=32768
  CHUNKED=1  LONG_THRESHOLD=0
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

PREFIX_TOKENS = int(os.environ.get("PREFIX_TOKENS", "11520"))
SUFFIX_TOKENS = int(os.environ.get("SUFFIX_TOKENS", "1280"))
REQ_PER_PREFIX = int(os.environ.get("REQ_PER_PREFIX", "4"))
N_PREFIX = int(os.environ.get("N_PREFIX", "24"))
CHUNK = int(os.environ.get("CHUNK", "3276"))
CONC = int(os.environ.get("CONC", "64"))
KV_MB = int(os.environ.get("KV_MB", "65536"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "32768"))
CHUNKED = os.environ.get("CHUNKED", "1") == "1"
LONG_THRESHOLD = int(os.environ.get("LONG_THRESHOLD", "0"))
WARM = os.environ.get("WARM", "0") == "1"
RESERVE = os.environ.get("RESERVE", "1") == "1"
OUT_TOKENS = int(os.environ.get("OUT_TOKENS", "1"))

steps = []
_orig_schedule = Scheduler.schedule


def _schedule(self, *args, **kwargs):
    out = _orig_schedule(self, *args, **kwargs)
    try:
        pool = self.kv_cache_manager.block_pool
        free = pool.get_num_free_blocks()
        total_blocks = getattr(pool, "num_gpu_blocks", -1)
    except Exception:
        free, total_blocks = -1, -1
    steps.append(
        {
            "tokens": sum(out.num_scheduled_tokens.values()),
            "reqs": len(out.num_scheduled_tokens),
            "running": len(self.running),
            "waiting": len(self.waiting),
            "free": free,
            "total_blocks": total_blocks,
            "preempted": len(out.preempted_req_ids or ()),
        }
    )
    return out


Scheduler.schedule = _schedule

prefixes = []
for p in range(N_PREFIX):
    base = [(p * 100003 + i) % 30000 + 100 for i in range(PREFIX_TOKENS)]
    prefixes.append(base)

prompts = []
for p in range(N_PREFIX):
    for r in range(REQ_PER_PREFIX):
        suffix = [((p * 7 + r) * 99991 + i * 17) % 30000 + 100 for i in range(SUFFIX_TOKENS)]
        prompts.append({"prompt_token_ids": prefixes[p] + suffix})

t0 = time.time()
llm = LLM(
    model=os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B"),
    simulate_forward=True,
    kv_cache_memory_bytes=KV_MB * 1024**2,
    enforce_eager=True,
    max_model_len=MAX_MODEL_LEN,
    max_num_batched_tokens=CHUNK,
    max_num_seqs=CONC,
    enable_chunked_prefill=CHUNKED,
    long_prefill_token_threshold=LONG_THRESHOLD,
    scheduler_reserve_full_isl=RESERVE,
)
init_s = time.time() - t0

sp = SamplingParams(max_tokens=OUT_TOKENS, temperature=0.0, ignore_eos=True)
if WARM:
    # one request per prefix to populate the prefix cache, then measure hot requests
    warm_prompts = [{"prompt_token_ids": p + [7] * SUFFIX_TOKENS} for p in prefixes]
    llm.generate(warm_prompts, sp)
    steps.clear()

t1 = time.time()
llm.generate(prompts, sp)
gen_s = time.time() - t1

fills = [s["tokens"] for s in steps]
total_blocks = steps[0]["total_blocks"] if steps else -1
low = [s for s in steps if s["tokens"] < 0.8 * CHUNK]
print(
    json.dumps(
        {
            "requests": len(prompts),
            "chunk": CHUNK,
            "conc": CONC,
            "chunked": CHUNKED,
            "long_threshold": LONG_THRESHOLD,
            "total_blocks": total_blocks,
            "steps": len(steps),
            "init_s": round(init_s, 2),
            "gen_s": round(gen_s, 2),
            "fill_mean": round(sum(fills) / len(fills), 1),
            "fill_min": min(fills),
            "fill_max": max(fills),
            "low_fill_steps": len(low),
            "low_fill_free_median": (sorted(s["free"] for s in low)[len(low) // 2] if low else None),
            "low_fill_running_median": (sorted(s["running"] for s in low)[len(low) // 2] if low else None),
            "low_fill_waiting_median": (sorted(s["waiting"] for s in low)[len(low) // 2] if low else None),
            "gated_steps": sum(
                1
                for s in steps
                if s["waiting"] > 0 and s["tokens"] < 0.8 * CHUNK and s["free"] >= CHUNK // 32
            ),
            "gated_free_median": (
                sorted(
                    s["free"]
                    for s in steps
                    if s["waiting"] > 0 and s["tokens"] < 0.8 * CHUNK and s["free"] >= CHUNK // 32
                )[
                    sum(
                        1
                        for s in steps
                        if s["waiting"] > 0 and s["tokens"] < 0.8 * CHUNK and s["free"] >= CHUNK // 32
                    )
                    // 2
                ]
                if any(
                    s["waiting"] > 0 and s["tokens"] < 0.8 * CHUNK and s["free"] >= CHUNK // 32
                    for s in steps
                )
                else None
            ),
            "max_running": max(s["running"] for s in steps),
            "min_free": min(s["free"] for s in steps),
            "low_samples": [
                (s["tokens"], s["reqs"], s["free"], s["running"], s["waiting"])
                for s in steps
                if s["waiting"] > 0 and s["tokens"] < 0.8 * CHUNK
            ][:6],
            "preemptions": sum(s["preempted"] for s in steps),
            "tokens_total": sum(fills),
            "tokens_per_s": round(sum(fills) / max(gen_s, 1e-9), 1),
            "reserve_full_isl": RESERVE,
            "first20": steps[:20],
        },
        ensure_ascii=False,
    )
)
