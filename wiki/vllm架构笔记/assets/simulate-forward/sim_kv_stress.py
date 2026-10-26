"""KV pressure experiment: shrink the virtual KV cache and oversubscribe it.

Goal: trigger queueing (waiting > 0) and preemption (preempted > 0), which the
light workload in sim_rounds.py never reached.

Env knobs:
  KV_MB        virtual KV cache size in MiB (default 256)
  N_REQS       number of concurrent requests (default 8)
  PROMPT_REP   "Hello " repetitions per prompt (default 500)
  MAX_SEQS     max_num_seqs (default 8)
  MAX_BATCHED  max_num_batched_tokens (default 512)
"""

import json
import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
KV_MB = int(os.environ.get("KV_MB", "256"))
N_REQS = int(os.environ.get("N_REQS", "8"))
PROMPT_REP = int(os.environ.get("PROMPT_REP", "500"))
MAX_SEQS = int(os.environ.get("MAX_SEQS", "8"))
MAX_BATCHED = int(os.environ.get("MAX_BATCHED", "512"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "4"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "2048"))

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
            "running": len(self.running),
            "waiting": len(self.waiting),
            "preempted": len(out.preempted_req_ids or ()),
            "kv_used": total - pool.get_num_free_blocks(),
            "kv_total": total,
        }
    )
    return out


Scheduler.schedule = _schedule


def main() -> None:
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=KV_MB * 1024**2,
        enforce_eager=True,
        max_model_len=MAX_MODEL_LEN,
        max_num_seqs=MAX_SEQS,
        max_num_batched_tokens=MAX_BATCHED,
        enable_prefix_caching=False,
    )
    prompts = ["Hello " * PROMPT_REP] * N_REQS
    trace = [100 + (i % 4) for i in range(MAX_TOKENS)]
    sp = SamplingParams(max_tokens=MAX_TOKENS, trace_decode_token_ids=trace)

    t0 = time.time()
    outs = llm.generate(prompts, sp)
    dt = time.time() - t0

    total = steps[0]["kv_total"] if steps else 0
    print(f"[stress] kv_mb={KV_MB} reqs={N_REQS} rep={PROMPT_REP} "
          f"seqs={MAX_SEQS} batched={MAX_BATCHED} max_tokens={MAX_TOKENS}")
    print(f"[stress] kv_blocks={total} steps={len(steps)} time={dt:.3f}s")
    print(f"[stress] peak_kv={max(s['kv_used'] for s in steps)}/{total} "
          f"max_waiting={max(s['waiting'] for s in steps)} "
          f"preemptions={sum(s['preempted'] for s in steps)}")
    for i, s in enumerate(steps):
        if i < 40:
            print(
                f"  step {i:2d}: reqs={s['reqs']} tokens={s['tokens']:4d} "
                f"new={s['new']} prefill={s['prefill']} chunk={s['chunk']} "
                f"decode={s['decode']} running={s['running']} waiting={s['waiting']} "
                f"preempted={s['preempted']} kv={s['kv_used']:3d}/{s['kv_total']}"
            )
    ok = all(o.outputs[0].token_ids == trace for o in outs)
    print("[stress] outputs ok:", ok)
    with open("/logs/kv_stress.json", "w") as f:
        json.dump(steps, f, indent=1)


if __name__ == "__main__":
    main()
