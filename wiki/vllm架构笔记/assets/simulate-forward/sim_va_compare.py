"""Compare dry-run scheduling with vllm-ascend platform patches on vs off.

VA_PATCHES=0 -> plain vLLM main (no vllm_ascend import)
VA_PATCHES=1 -> import vllm_ascend and call register_connector(), which applies
                the whole vllm_ascend.patch.platform package
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

USE_PATCHES = os.environ.get("VA_PATCHES") == "1"

if USE_PATCHES:
    import vllm_ascend

    vllm_ascend.register_connector()  # applies ascend_vllm patches

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
            "kv_total": total,
        }
    )
    return out


Scheduler.schedule = _schedule

C_PREFILL, C_DECODE, C_OVERHEAD = 0.1, 1.0, 0.05


def simulate():
    cum: dict[str, int] = {}
    ttft: dict[str, float] = {}
    end: dict[str, float] = {}
    t = 0.0
    for s in steps:
        prefill = decode = 0
        for rid, n in s["tokens_map"].items():
            pl = prompt_len.get(rid, 0)
            before = cum.get(rid, 0)
            if before < pl:
                prefill += n
            else:
                decode += n
            cum[rid] = before + n
        t += C_PREFILL * prefill + C_DECODE * decode + C_OVERHEAD
        for rid in s["tokens_map"]:
            pl = prompt_len.get(rid, 0)
            if rid not in ttft and pl > 0 and cum[rid] >= pl:
                ttft[rid] = t
            end[rid] = t
    tpot = {r: (end[r] - v) / max(1, MAX_TOKENS - 1) for r, v in ttft.items()}
    return ttft, tpot, t


def main() -> None:
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        max_num_seqs=8,
        max_num_batched_tokens=256,
        enable_prefix_caching=False,
        trust_remote_code=True,
    )
    sp = SamplingParams(max_tokens=MAX_TOKENS, trace_decode_token_ids=TRACE)
    t0 = time.time()
    llm.generate(PROMPTS, sp)
    dt = time.time() - t0
    ttft, tpot, makespan = simulate()
    tts = sorted(ttft.values())
    out = {
        "patches": USE_PATCHES,
        "steps": len(steps),
        "kv_total": steps[0]["kv_total"] if steps else 0,
        "peak_kv": max(s["kv_used"] for s in steps),
        "mean_ttft": round(sum(tts) / len(tts), 2),
        "p95_ttft": round(tts[int(0.95 * (len(tts) - 1))], 2),
        "mean_tpot": round(sum(tpot.values()) / len(tpot), 2),
        "makespan": round(makespan, 2),
        "wall_s": round(dt, 3),
    }
    print("[va-compare] " + json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
