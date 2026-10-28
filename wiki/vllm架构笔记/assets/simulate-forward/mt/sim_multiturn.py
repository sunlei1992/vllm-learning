"""Multi-turn APC experiment: HBM-only vs a simulated second-tier (CPU offload)."""
import os

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")

from vllm import SamplingParams
from vllm.engine.arg_utils import EngineArgs
import vllm.v1.core.sched.scheduler as sched_mod
from vllm.v1.worker.simulated.offline import (
    REQUEST_ID_PREFIX,
    TimedRequest,
    make_engine,
    run,
)

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
SESSIONS = int(os.environ.get("SESSIONS", "8"))
TURNS = int(os.environ.get("TURNS", "6"))
BASE = int(os.environ.get("BASE", "1024"))
NEW = int(os.environ.get("NEW", "512"))
OUT = int(os.environ.get("OUT", "8"))
HBM_GB = float(os.environ.get("HBM_GB", "1"))
BW = float(os.environ.get("BW_GBPS", "50"))

# prompt length -> cached tokens, captured from the scheduler on first schedule
CACHED: dict[str, int] = {}
_orig_schedule = sched_mod.Scheduler.schedule


def _schedule(self, *args, **kwargs):
    out = _orig_schedule(self, *args, **kwargs)
    for rid in out.num_scheduled_tokens:
        if rid not in CACHED:
            req = self.requests[rid]
            CACHED[rid] = max(0, req.num_tokens - out.num_scheduled_tokens[rid])
    return out


def install_hook(engine) -> None:
    """Wrap the real scheduler class (vllm-ascend may use a subclass)."""
    scheduler = engine.engine_core.engine_core.scheduler
    cls = type(scheduler)
    orig = cls.schedule

    def wrapper(self, *args, **kwargs):
        out = orig(self, *args, **kwargs)
        for rid in out.num_scheduled_tokens:
            if rid not in CACHED:
                req = self.requests[rid]
                CACHED[rid] = max(0, req.num_tokens - out.num_scheduled_tokens[rid])
        return out

    cls.schedule = wrapper


def make_args(tier_gb: float, bw: float) -> EngineArgs:
    kwargs = {}
    if tier_gb > 0:
        kwargs["kv_transfer_config"] = {
            "kv_connector": "OffloadingConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {"cpu_bytes_to_use": int(tier_gb * 1024**3)},
        }
    return EngineArgs(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=int(HBM_GB * 1024**3),
        simulation_config={
            "simulate_forward": True,
            "clock": "fast_forward",
            "timing": "linear",
            "timing_args": {"fixed_us": 1000, "prefill_us_per_token": 10},
            "kv_transfer_timing": {"load_gbps": bw, "store_gbps": bw},
        },
        enforce_eager=True,
        max_model_len=8192,
        **kwargs,
    )


def build_requests():
    """Sessions interleaved turn by turn; each turn's prompt extends the previous."""
    params = SamplingParams(max_tokens=OUT, ignore_eos=True)
    base = list(range(1000, 1000 + BASE))
    conv = [list(base) for _ in range(SESSIONS)]
    reqs = []
    for t in range(TURNS):
        for s in range(SESSIONS):
            new = [10000 + s * 1000 + t * 100 + i for i in range(NEW)]
            prompt = conv[s] + new
            reqs.append(TimedRequest(prompt, params, arrival_time=len(reqs) * 0.05))
            conv[s] = prompt
    return reqs


def run_config(name: str, tier_gb: float, bw: float) -> None:
    CACHED.clear()
    engine = make_engine(make_args(tier_gb, bw))
    install_hook(engine)
    try:
        reqs = build_requests()
        result = run(engine, reqs)
    finally:
        engine.engine_core.shutdown()

    rows = []
    for i, timing in enumerate(result.requests):
        cached = next((v for k, v in CACHED.items() if k.split("-")[1:2] == [str(i)]), 0)
        prompt = timing.num_prompt_tokens
        rows.append(
            {
                "turn": i // SESSIONS,
                "prompt": prompt,
                "cached": cached,
                "ttft": timing.ttft or 0.0,
            }
        )
    n = len(rows)
    total_prompt = sum(r["prompt"] for r in rows)
    cached_ratio = sum(r["cached"] for r in rows) / total_prompt
    miss_tokens = sum(
        max(0, r["prompt"] - NEW - r["cached"]) for r in rows if r["turn"] > 0
    )
    evicted = sum(
        1 for r in rows if r["turn"] > 0 and r["cached"] < r["prompt"] - NEW
    )
    ttfts = sorted(r["ttft"] for r in rows)
    mean = sum(ttfts) / n
    p90 = ttfts[int(0.9 * (n - 1))]
    per_turn = " ".join(
        f"t{k}={sum(r['ttft'] for r in rows if r['turn'] == k) / SESSIONS * 1000:.0f}ms"
        for k in range(TURNS)
    )
    print(
        f"{name:14s} cached={cached_ratio*100:5.1f}% evicted={evicted:2d}/{n} "
        f"miss={miss_tokens:5d}tok "
        f"mean_ttft={mean*1000:7.1f}ms p90={p90*1000:7.1f}ms {per_turn}",
        flush=True,
    )


_tiers = [float(x) for x in os.environ.get("TIERS", "0,1,2,4,8,16").split(",")]
_bws = [float(x) for x in os.environ.get("BWS", "50").split(",")]
CONFIGS = [
    (f"{'hbm-only' if t == 0 else f'tier{t:g}G'}@{b:g}G", t, b)
    for t in _tiers
    for b in _bws
]

if __name__ == "__main__":
    print(
        f"sessions={SESSIONS} turns={TURNS} base={BASE} new={NEW} hbm={HBM_GB}GiB",
        flush=True,
    )
    for name, tier, bw in CONFIGS:
        run_config(name, tier, bw)
