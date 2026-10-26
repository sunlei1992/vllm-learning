"""Short-request-first with staggered arrivals (to exercise aging).

Two long requests arrive first, then short requests keep arriving. That is the
only pattern where `long_max_wait_ms` aging can change the schedule.
"""

import json
import os

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.v1.core.sched.scheduler import Scheduler  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
MAX_TOKENS = 8
TRACE = [100 + (i % 4) for i in range(MAX_TOKENS)]
THRESHOLD = int(os.environ.get("SRS_THRESHOLD", "100"))
AGING_MS = float(os.environ.get("SRS_AGING_MS", "10"))

# (add_before_step, prompt)
ARRIVALS = [
    (0, "Hello " * 400),
    (0, "Hello " * 800),
    (0, "Hello " * 400),
    (0, "Hello " * 800),
    (2, "Hello"),
    (2, "Hello " * 10),
    (4, "Hello"),
    (4, "Hello " * 50),
]

C_PREFILL, C_DECODE, C_OVERHEAD = 0.1, 1.0, 0.05

policy = "fcfs"
sim_time = 0.0
steps: list[dict] = []
prompt_len: dict[str, int] = {}
arrive: dict[str, float] = {}
cum: dict[str, int] = {}
_orig_schedule = Scheduler.schedule


def _reorder(self):
    items = list(self.waiting)
    for r in items:
        arrive.setdefault(r.request_id, sim_time)
    short = [r for r in items if r.num_prompt_tokens <= THRESHOLD]
    long = [r for r in items if r.num_prompt_tokens > THRESHOLD]
    aged = []
    if policy == "srs_aged" and AGING_MS > 0:
        aged = [r for r in long if sim_time - arrive[r.request_id] >= AGING_MS]
        aged.sort(key=lambda r: arrive[r.request_id])
    aged_ids = {id(r) for r in aged}
    order = aged + short + [r for r in long if id(r) not in aged_ids]
    if order != items:
        self.waiting.clear()
        self.waiting.extend(order)


def _schedule(self, *args, **kwargs):
    global sim_time
    if policy.startswith("srs") and len(self.waiting) > 1:
        _reorder(self)
    out = _orig_schedule(self, *args, **kwargs)
    for r in out.scheduled_new_reqs:
        req = self.requests.get(r.req_id)
        if req is not None:
            prompt_len[r.req_id] = req.num_prompt_tokens
    prefill = decode = 0
    for rid, n in out.num_scheduled_tokens.items():
        pl = prompt_len.get(rid, 0)
        before = cum.get(rid, 0)
        if before < pl:
            prefill += n
        else:
            decode += n
        cum[rid] = before + n
    cost = C_PREFILL * prefill + C_DECODE * decode + C_OVERHEAD
    sim_time += cost
    steps.append({"tokens_map": dict(out.num_scheduled_tokens), "cost": cost})
    return out


Scheduler.schedule = _schedule


def metrics() -> dict:
    cum2: dict[str, int] = {}
    ttft: dict[str, float] = {}
    end: dict[str, float] = {}
    t = 0.0
    for s in steps:
        for rid, n in s["tokens_map"].items():
            cum2[rid] = cum2.get(rid, 0) + n
        t += s["cost"]
        for rid in s["tokens_map"]:
            pl = prompt_len.get(rid, 0)
            if rid not in ttft and pl > 0 and cum2[rid] >= pl:
                ttft[rid] = t
            end[rid] = t
    tpot = {r: (end[r] - v) / max(1, MAX_TOKENS - 1) for r, v in ttft.items()}
    short = [v for r, v in ttft.items() if prompt_len.get(r, 0) <= THRESHOLD]
    long_ = [v for r, v in ttft.items() if prompt_len.get(r, 0) > THRESHOLD]
    tts = sorted(ttft.values())
    return {
        "steps": len(steps),
        "mean_ttft": round(sum(tts) / len(tts), 2),
        "max_ttft": round(tts[-1], 2),
        "short_mean": round(sum(short) / len(short), 2) if short else None,
        "long_mean": round(sum(long_) / len(long_), 2) if long_ else None,
        "mean_tpot": round(sum(tpot.values()) / len(tpot), 2),
        "makespan": round(t, 2),
    }


def run(name: str) -> dict:
    global policy, sim_time
    policy = name
    sim_time = 0.0
    steps.clear()
    prompt_len.clear()
    arrive.clear()
    cum.clear()
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
    pending = list(ARRIVALS)
    done: set[str] = set()
    idx = 0
    step_i = 0
    while pending or len(done) < len(ARRIVALS):
        while pending and pending[0][0] <= step_i:
            _, prompt = pending.pop(0)
            rid = str(idx)
            idx += 1
            llm.llm_engine.add_request(rid, prompt, sp)
        outs = llm.llm_engine.step()
        for o in outs:
            if getattr(o, "finished", False):
                done.add(o.request_id)
        step_i += 1
        if step_i > 5000:
            raise RuntimeError("runaway")
    del llm
    return {"policy": name, **metrics()}


def main() -> None:
    rows = []
    for name in ("fcfs", "srs", "srs_aged"):
        r = run(name)
        rows.append(r)
        print(
            f"[srs] {name:9s} steps={r['steps']:2d} mean={r['mean_ttft']:7.2f} "
            f"max={r['max_ttft']:7.2f} short={r['short_mean']} long={r['long_mean']} "
            f"tpot={r['mean_tpot']:6.2f} makespan={r['makespan']:7.2f}",
            flush=True,
        )
    with open("/logs/srs_arrivals.json", "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
