"""Minimal simulate-forward run with debug logging (2 tokens)."""

import os
import time

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")


def main() -> None:
    from vllm import LLM, SamplingParams

    t0 = time.time()
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
    )
    print(f"[sim] init {time.time() - t0:.2f}s", flush=True)
    sp = SamplingParams(max_tokens=2, trace_decode_token_ids=[100, 101])
    t1 = time.time()
    out = llm.generate(["Hello"], sp)
    print(f"[sim] generate {time.time() - t1:.2f}s ids={out[0].outputs[0].token_ids}", flush=True)


if __name__ == "__main__":
    main()
