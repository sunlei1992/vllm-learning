# P4: pure vLLM CPU P/D with Mooncake

## Prerequisites

- Docker Desktop VM memory: at least 16GB (vLLM CPU non-KV usage was ~6.6GB)
- Base image `sim030:glm53` (vLLM 0.30 CPU)
- Build `sim030:mooncake`:

```bash
docker build -t sim030:mooncake -f p4.Dockerfile .
```

## Run

```bash
bash run_p4.sh
```

The script:

1. creates `models/Qwen2.5-tiny` (2 layers, random weights);
2. starts `mooncake-master` on `p4-net`;
3. runs P `kv_producer` and D `kv_consumer` sequentially;
4. D must log `External Cache Hit!`.

Expected:

```text
kv_producer TOKENS [16856]
kv_consumer External Cache Hit!
kv_consumer TOKENS [16856]
```

## Scope

This validates the per-layer `MooncakeExampleConnector` path and P/D role separation on CPU.
It is a 2-layer synthetic model with random weights; it is not a GLM/Qwen3 correctness or
performance test. CPU generation took about 5 minutes per side on the local Docker VM.
