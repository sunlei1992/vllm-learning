# Single-engine layerwise shared buffer (pure vLLM CPU)

This is the missing combined test:

```text
4-layer Qwen2.5 tiny
  + 2 physical KV tensors (layer0 independent, layers 1/2/3 shared)
  + per-layer save/load connector
  + decode
```

## Result

Baseline:

```text
TOKENS [34122, 147096, 136438, 147096]
```

Shared buffer:

```text
ALIAS_CONFIG layers 4 tensors_before 1 page 65536
ALIAS_TENSORS 2 blocks 9047

CONN_LOAD layer0 zero
CONN_SAVE layer0
...
CONN_LOAD layer0 hit
CONN_SAVE layer0
...
TOKENS [34122, 147096, 136438, 147096]
```

The `zero` calls are the prefill pass; after that every decode pass loads the
layer's saved KV before compute and saves it again after compute.

## Files

- `run_shared_buffer.py`: alias patch + offline LLM runner.
- `layerwise_shared_buffer_connector.py`: per-layer save/load connector.
- `make_tiny4_model.py`: create the 4-layer tiny model from Qwen2.5-0.5B config.

## Runtime

`sim030:glm53` (vLLM 0.30 CPU) or `sim030:mooncake`, 16GB Docker VM.

```bash
docker run --rm --memory 14g --platform linux/arm64 \
  -v "$PWD/models:/models:ro" \
  -v "$PWD/wiki/vllm架构笔记/assets/qwen_cpu_kv/shared_buffer:/app:ro" \
  sim030:mooncake bash -lc \
  'PYTHONPATH=/app VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 ALIAS=1 \
   /opt/v030/bin/python /app/run_shared_buffer.py'
```

## Scope

This validates the single-engine shared-slot lifecycle and decode correctness
on a tiny CPU model. It does not use Mooncake for the shared-buffer store, and
it is not a GLM/Qwen3 full-model or performance test.

## Mooncake store mode

The same run can use Mooncake instead of the in-memory dict:

```bash
# mooncake-master must be running on the p4-net Docker network
docker run --rm --network p4-net --memory 14g --platform linux/arm64 \
  -v "$PWD/models:/models:ro" \
  -v "$PWD/wiki/vllm架构笔记/assets/qwen_cpu_kv/shared_buffer:/app:ro" \
  sim030:mooncake bash -lc \
  'PYTHONPATH=/app VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 \
   ALIAS=1 MOONCAKE=1 /opt/v030/bin/python /app/run_shared_buffer.py'
```

Observed:

```text
ALIAS_TENSORS 2 blocks 256
CONN_LOAD layer0 zero
CONN_SAVE layer0
...
CONN_LOAD layer0 hit
CONN_SAVE layer0
...
TOKENS [34122, 147096, 136438, 147096]
```

Notes:

- `kv_cache_memory_bytes=64MiB` keeps each layer object small; otherwise Mooncake
  `put session start` can hit segment-full / overwrite errors.
- Each save uses a versioned key; load uses the latest version.
