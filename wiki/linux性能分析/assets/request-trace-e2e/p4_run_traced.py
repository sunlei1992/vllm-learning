"""p4 Mooncake producer/consumer with request_trace applied."""

import argparse
import faulthandler
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")

faulthandler.dump_traceback_later(480, exit=True)

import torch  # noqa: E402

ROOT = os.environ.get("MXLLM_TRACE_ROOT", "/mxllm")
spec = importlib.util.spec_from_file_location(
    "patch_request_trace",
    os.path.join(ROOT, "ascend_vllm/patch/platform/patch_request_trace.py"),
)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
patch.apply_all()

from vllm import LLM, SamplingParams  # noqa: E402
from vllm.config import KVTransferConfig  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("role", choices=["kv_producer", "kv_consumer"])
args = parser.parse_args()
torch.manual_seed(0)

kv = KVTransferConfig(
    kv_connector="MooncakeExampleConnector",
    kv_connector_module_path="p4_mooncake_connector",
    kv_role=args.role,
    engine_id="p4-" + args.role,
    kv_connector_extra_config={
        "shared_storage_path": "/store",
        "mooncake_master": "mooncake-master:50051",
        "mooncake_key_prefix": "p4",
        "mooncake_segment_size": 2 * 1024**3,
        "mooncake_local_buffer": 256 * 1024**2,
    },
)
Path("/store").mkdir(parents=True, exist_ok=True)
llm = LLM(
    model="/models/Qwen2.5-tiny",
    load_format="dummy",
    max_model_len=64,
    gpu_memory_utilization=0.25,
    enforce_eager=True,
    kv_transfer_config=kv,
)
out = llm.generate(
    ["Hello, my name is"],
    SamplingParams(max_tokens=1, temperature=0.0, seed=0),
)
print(args.role, "TOKENS", out[0].outputs[0].token_ids)
