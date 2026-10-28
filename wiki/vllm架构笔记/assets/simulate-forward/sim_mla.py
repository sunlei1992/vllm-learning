"""Smoke test for an MLA model on the dry-run path."""
import os

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
from vllm import LLM, SamplingParams

MODEL = os.environ.get("SIM_MODEL", "/models/deepseek-ai_DeepSeek-V2-Lite")


def main() -> None:
    llm = LLM(
        model=MODEL,
        simulate_forward=True,
        trust_remote_code=True,
        kv_cache_memory_bytes=2 * 1024**3,
        enforce_eager=True,
        max_model_len=2048,
        enable_prefix_caching=False,
    )
    out = llm.generate(
        ["Hello"], SamplingParams(max_tokens=4, trace_decode_token_ids=[100, 101, 102, 103])
    )
    print("TOKENS", out[0].outputs[0].token_ids, flush=True)


if __name__ == "__main__":
    main()
