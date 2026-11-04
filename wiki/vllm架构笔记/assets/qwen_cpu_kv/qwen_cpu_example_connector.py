import shutil
from pathlib import Path

from vllm import LLM, SamplingParams
from vllm.config import KVTransferConfig

storage = Path("/tmp/vllm-cpu-example-kv")
shutil.rmtree(storage, ignore_errors=True)
storage.mkdir(parents=True)

kv = KVTransferConfig(
    kv_connector="ExampleConnector",
    kv_role="kv_both",
    kv_connector_extra_config={"shared_storage_path": str(storage)},
)

llm = LLM(
    model="models/Qwen_Qwen3-0.6B",
    load_format="dummy",
    max_model_len=256,
    gpu_memory_utilization=0.3,
    enforce_eager=True,
    kv_transfer_config=kv,
)
params = SamplingParams(max_tokens=4, temperature=0.0)
prompt = "Hello, my name is"
for round_id in range(2):
    out = llm.generate([prompt], params)
    item = out[0]
    print(f"ROUND {round_id} TEXT:", item.outputs[0].text)
    print(f"ROUND {round_id} TOKENS:", item.outputs[0].token_ids)
print("STORAGE:", sorted(p.name for p in storage.iterdir())[:10])
