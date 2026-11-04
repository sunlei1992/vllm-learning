import argparse
from pathlib import Path

from vllm import LLM, SamplingParams
from vllm.config import KVTransferConfig

parser = argparse.ArgumentParser()
parser.add_argument("role", choices=["kv_producer", "kv_consumer"])
args = parser.parse_args()

storage = Path("/tmp/vllm-cpu-pd-example")
storage.mkdir(parents=True, exist_ok=True)
kv = KVTransferConfig(
    kv_connector="ExampleConnector",
    kv_role=args.role,
    engine_id=args.role,
    kv_connector_extra_config={"shared_storage_path": str(storage)},
)
llm = LLM(
    model="models/Qwen_Qwen3-0.6B",
    load_format="dummy",
    max_model_len=256,
    gpu_memory_utilization=0.25,
    enforce_eager=True,
    kv_transfer_config=kv,
)
params = SamplingParams(max_tokens=4, temperature=0.0)
out = llm.generate(["Hello, my name is"], params)
print(args.role, "TOKENS:", out[0].outputs[0].token_ids)
print(args.role, "TEXT:", out[0].outputs[0].text)
