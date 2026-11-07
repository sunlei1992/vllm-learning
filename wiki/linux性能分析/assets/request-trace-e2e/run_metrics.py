"""Metrics-mode smoke: REQUEST_TRACE_MODE=metrics, no per-event logging."""

import importlib.util
import os
import time

ROOT = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
os.environ["REQUEST_TRACE_MODE"] = "metrics"
os.environ["REQUEST_TRACE_METRICS_DIR"] = "/out/trace_metrics"
os.environ.pop("REQUEST_TRACE_OUTPUT_DIRECTORY", None)
os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

spec = importlib.util.spec_from_file_location(
    "patch_request_trace",
    os.path.join(ROOT, "ascend_vllm/patch/platform/patch_request_trace.py"),
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
patch.apply_all()

from vllm import LLM, SamplingParams  # noqa: E402

t0 = time.time()
llm = LLM(
    model="/models/Qwen_Qwen3-0.6B",
    simulate_forward=True,
    kv_cache_memory_bytes=2 * 1024**3,
    enforce_eager=True,
    max_model_len=2048,
    max_num_batched_tokens=64,
)
sp = SamplingParams(max_tokens=8, trace_decode_token_ids=[100, 101, 102, 103, 104, 105, 106, 107])
llm.generate(["Hello", "Hi there"], sp)
print(f"[metrics] done in {time.time() - t0:.2f}s")
