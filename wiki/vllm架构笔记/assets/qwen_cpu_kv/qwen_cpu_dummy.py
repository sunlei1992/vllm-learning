from vllm import LLM, SamplingParams

llm = LLM(
    model="models/Qwen_Qwen3-0.6B",
    load_format="dummy",
    max_model_len=512,
    gpu_memory_utilization=0.3,
    enforce_eager=True,
)
out = llm.generate(
    ["Hello, my name is"],
    SamplingParams(max_tokens=8, temperature=0.0),
)
for item in out:
    print("PROMPT:", item.prompt)
    print("TEXT:", item.outputs[0].text)
    print("TOKENS:", item.outputs[0].token_ids)
