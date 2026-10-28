"""P/D ratio comparison under contention."""
import json
import os

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")

from vllm import SamplingParams
from vllm.engine.arg_utils import EngineArgs
from vllm.v1.worker.simulated.disaggregated import simulate_disaggregated
from vllm.v1.worker.simulated.offline import TimedRequest

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
N = int(os.environ.get("PD_N", "16"))
PROMPT = int(os.environ.get("PD_PROMPT", "1024"))
GAP = float(os.environ.get("PD_GAP", "0.002"))


def make_args() -> EngineArgs:
    return EngineArgs(
        model=MODEL,
        max_model_len=4096,
        kv_cache_memory_bytes=2 * 1024**3,
        simulation_config={
            "simulate_forward": True,
            "timing": "linear",
            "timing_args": {"fixed_us": 1000, "prefill_us_per_token": 10},
            "kv_transfer_timing": {"load_gbps": 10},
        },
    )


def run(p: int, d: int) -> None:
    params = SamplingParams(max_tokens=8, ignore_eos=True)
    requests = [
        TimedRequest(list(range(1000, 1000 + PROMPT)), params, i * GAP) for i in range(N)
    ]
    result = simulate_disaggregated(make_args(), make_args(), requests, num_prefill=p, num_decode=d)
    s = result.summary()
    keys = [k for k in s if "ttft" in k or "tpot" in k]
    print(
        f"{p}P{d}D duration={result.duration:.3f}s wall={result.wall_time:.1f}s "
        + " ".join(f"{k}={s[k]:.2f}" for k in keys),
        flush=True,
    )


if __name__ == "__main__":
    print(json.dumps({"n": N, "prompt": PROMPT, "gap": GAP}), flush=True)
    for p, d in ((1, 1), (2, 1), (1, 2), (2, 2)):
        run(p, d)
