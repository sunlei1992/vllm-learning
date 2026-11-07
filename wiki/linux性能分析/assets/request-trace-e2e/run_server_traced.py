"""Start the vLLM OpenAI server with request_trace applied (CPU simulate-forward).

Run with VLLM_ENABLE_V1_MULTIPROCESSING=0 so the engine core lives in this
process -- the patch is applied to real classes here, and a spawned child
would import vLLM fresh without it.
"""

import importlib.util
import os
import runpy


def main() -> None:
    root = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
    spec = importlib.util.spec_from_file_location(
        "patch_request_trace",
        os.path.join(root, "ascend_vllm/patch/platform/patch_request_trace.py"),
    )
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    patch.apply_all()
    runpy.run_module("vllm.entrypoints.openai.api_server", run_name="__main__")


if __name__ == "__main__":
    main()
