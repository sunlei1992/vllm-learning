"""Multi-request simulate-forward run with per-step scheduler observation.

Uses in-process engine mode so the real Scheduler runs in this process and
can be wrapped to record each scheduling step.
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
_orig_schedule = Scheduler.schedule


def _schedule(self, *args, **kwargs):
    out = _orig_schedule(self, *args, **kwargs)
    total = sum(out.num_scheduled_tokens.values())
    decode_tokens = 0
    for req_id, n in out.num_scheduled_tokens.items():
        req = self.requests.get(req_id) if hasattr(self, "requests") else None
        if req is not None and n == 1:
            decode_tokens += 1
    steps.append(
        {
            "step": len(steps),
            "reqs": len(out.num_scheduled_tokens),
            "tokens": total,
            "new_reqs": len(out.scheduled_new_reqs),
            "preempted": len(out.preempted_req_ids or ()),
            "running": len(self.running),
            "waiting": len(self.waiting),
        }
    )
    return out


Scheduler.schedule = _schedule


def main() -> None:
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        max_num_seqs=4,
        max_num_batched_tokens=64,
    )

    prompts = [
        "Hello",
        "Hello " * 300,     # long prompt: forces chunked prefill (limit 64)
        "Hi there",
        "Hello " * 20,
    ]
    sp = SamplingParams(max_tokens=2, trace_decode_token_ids=[100, 101])

    t0 = time.time()
    outs = llm.generate(prompts, sp)
    elapsed = time.time() - t0

    print(f"[steps] generate {elapsed:.2f}s over {len(outs)} requests")
    print(f"[steps] total scheduler steps: {len(steps)}")
    for s in steps[:30]:
        print(
            f"  step {s['step']:2d}: reqs={s['reqs']} tokens={s['tokens']:3d} "
            f"new={s['new_reqs']} running={s['running']} waiting={s['waiting']} "
            f"preempted={s['preempted']}"
        )
    peak = max((s["tokens"] for s in steps), default=0)
    avg_reqs = sum(s["reqs"] for s in steps) / max(1, len(steps))
    print(f"[steps] peak tokens/step={peak}, avg reqs/step={avg_reqs:.2f}")
    print("[steps] output token ids:", [o.outputs[0].token_ids for o in outs])
    with open("/logs/steps.json", "w") as f:
        json.dump(steps, f, indent=1)


if __name__ == "__main__":
    main()
