"""Start the vLLM OpenAI server with request_trace applied (CPU simulate-forward).

The patch is applied at *import* time, not under ``__main__``: vLLM may spawn
``EngineCore`` as a child process, and multiprocessing/spawn re-imports this
module in the child. Applying at import time is what gets the scheduler hooks
into the engine process.
"""

import importlib.util
import os
import runpy
import sys

sys.path.insert(0, "/app")

ROOT = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
spec = importlib.util.spec_from_file_location(
    "patch_request_trace",
    os.path.join(ROOT, "ascend_vllm/patch/platform/patch_request_trace.py"),
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
patch.apply_all()


if __name__ == "__main__":
    runpy.run_module("vllm.entrypoints.openai.api_server", run_name="__main__")
