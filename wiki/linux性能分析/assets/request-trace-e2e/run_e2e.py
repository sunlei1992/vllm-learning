"""Local end-to-end harness for request_trace on CPU simulate-forward.

Loads mxllm's patch_request_trace.py directly (bypassing ascend_vllm package
__init__ so no torch_npu is required), applies the namelist patches, then runs
a real vLLM scheduler with the simulate-forward PR.

Records time.time()/time.monotonic_ns() at start so bpftrace samples (also
CLOCK_MONOTONIC) can be mapped onto the same wall-clock axis.
"""

import importlib.util
import json
import logging
import os
import sys
import resource
import time

TRACE_ROOT = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
OUT_DIR = os.environ.get("REQUEST_TRACE_OUTPUT_DIRECTORY", "/out/trace_e2e")
TRACE_MODE = os.environ.get("TRACE_MODE", "trace").lower()
os.environ["REQUEST_TRACE_MODE"] = TRACE_MODE
if TRACE_MODE == "off":
    os.environ.pop("REQUEST_TRACE_OUTPUT_DIRECTORY", None)
else:
    os.environ["REQUEST_TRACE_OUTPUT_DIRECTORY"] = OUT_DIR
os.environ.setdefault("REQUEST_PD_ROLE", "prefill")
os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

t0_wall = time.time()
t0_mono = time.monotonic_ns()

t_apply0 = time.process_time()
spec = importlib.util.spec_from_file_location(
    "patch_request_trace",
    os.path.join(TRACE_ROOT, "ascend_vllm/patch/platform/patch_request_trace.py"),
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
patch.apply_all()
apply_s = time.process_time() - t_apply0

from vllm import LLM, SamplingParams  # noqa: E402

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")

t_init0 = time.time()
llm = LLM(
    model=MODEL,
    simulate_forward=True,
    kv_cache_memory_bytes=2 * 1024**3,
    enforce_eager=True,
    max_model_len=2048,
    max_num_batched_tokens=64,
)
init_s = time.time() - t_init0

sp = SamplingParams(
    max_tokens=int(os.environ.get("MAX_TOKENS", "8")),
    trace_decode_token_ids=list(range(100, 200)),
)

# one long prompt (forces chunked prefill with budget=64) + two short ones
long_prompt = " ".join(["The quick brown fox jumps over the lazy dog."] * 30)
prompts = [long_prompt] * int(os.environ.get("N_REQS", "1")) + ["Hello", "Hi there"]

t_gen0 = time.time()
outs = llm.generate(prompts, sp)
gen_s = time.time() - t_gen0

meta = {
    "t0_wall": t0_wall,
    "t0_mono_ns": t0_mono,
    "init_s": init_s,
    "gen_s": gen_s,
    "vllm_version": __import__("vllm").__version__,
    "outputs": [o.outputs[0].token_ids for o in outs],
    "pid": os.getpid(),
    "trace_mode": TRACE_MODE,
    "apply_s": round(apply_s, 3),
}
ru = resource.getrusage(resource.RUSAGE_SELF)
meta["cpu_s"] = round(ru.ru_utime + ru.ru_stime, 3)
os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, "meta.json"), "w") as f:
    json.dump(meta, f, indent=2)
print("[meta]", json.dumps(meta, ensure_ascii=False))
