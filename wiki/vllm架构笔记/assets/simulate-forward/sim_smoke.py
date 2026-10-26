"""Minimal smoke test for vLLM --simulate-forward on CPU (PR #47922)."""

import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")


def main() -> None:
    from vllm import LLM, SamplingParams  # noqa: E402

    t0 = time.time()
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        disable_log_stats=False,
    )
    print(f"[sim] engine init: {time.time() - t0:.2f}s", flush=True)

    sp = SamplingParams(
        max_tokens=8,
        trace_decode_token_ids=[100, 101, 102, 103, 104, 105, 106, 107],
    )

    t1 = time.time()
    out = llm.generate(["Hello, my name is"], sp)
    print(f"[sim] generate: {time.time() - t1:.2f}s", flush=True)
    print("[sim] token_ids:", out[0].outputs[0].token_ids)
    print(f"[sim] total: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
