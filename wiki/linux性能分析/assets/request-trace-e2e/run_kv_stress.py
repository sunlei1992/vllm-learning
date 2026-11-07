"""KV-pressure run: small KV cache + several long requests -> evictions."""

import importlib.util
import os
import time

ROOT = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
os.environ["REQUEST_TRACE_OUTPUT_DIRECTORY"] = "/out/trace_e2e_kv"
os.environ.setdefault("REQUEST_PD_ROLE", "prefill")
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

KV_MB = int(os.environ.get("KV_MB", "64"))
N_REQS = int(os.environ.get("N_REQS", "8"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "64"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "1024"))

t0 = time.time()
llm = LLM(
    model="/models/Qwen_Qwen3-0.6B",
    simulate_forward=True,
    kv_cache_memory_bytes=KV_MB * 1024**2,
    enforce_eager=True,
    max_model_len=MAX_MODEL_LEN,
    max_num_batched_tokens=128,
    max_num_seqs=N_REQS,
)
print(f"[kv] engine init {time.time() - t0:.2f}s, KV={KV_MB}MB", flush=True)

prompt = "The quick brown fox jumps over the lazy dog. " * 20
sp = SamplingParams(
    max_tokens=MAX_TOKENS,
    trace_decode_token_ids=list(range(100, 100 + MAX_TOKENS)),
)
t1 = time.time()
llm.generate([prompt] * N_REQS, sp)
print(f"[kv] generate {time.time() - t1:.2f}s", flush=True)
