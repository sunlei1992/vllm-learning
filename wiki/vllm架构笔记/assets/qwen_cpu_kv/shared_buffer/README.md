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

## 28-layer known failure (2026-11-04)

4-layer fixed random weights pass; 28-layer fixed weights fail after the
first token:

```text
baseline: [87630, 87630, 87630, 87630]
shared:   [87630, 47704, 539, 92925]
```

- The 28-layer model is `models/Qwen2.5-tiny28-fixed` (55M params, actual random
  safetensors, not dummy).
- `ALIAS_CONFIG layers=28 tensors=4`.
- `CONN_LOAD`/`CONN_SAVE` are called; this is not a "connector not invoked" issue.
- 28 layers with `NUM_SHARED=1` (2 slots) also fails; not specific to 4 slots.
- The failure is still open; do not claim 28-layer decode passes.

## 28-layer root cause (2026-11-04)

UT trace:

```text
prefill:
  CONN_LOAD zero -> CONN_SAVE for all 28 layers
  CONN_CHECK all ok

decode:
  CONN_START <request>
  ... no CONN_LOAD / CONN_SAVE ...
```

So the connector is not called on the decode attention path. The first token
comes from prefill; decode runs on the stale shared slot and diverges.

This is not an alias bug and not a save/load checksum bug. It means pure vLLM
CPU's decode attention path bypasses `maybe_transfer_kv_layer` (the layerwise
connector wrapper). The 4-layer pass is a false positive because the random
tiny model emits a degenerate repeated token.

Fix boundary:

- pure vLLM CPU needs a decode-path hook/model-runner patch;
- vllm-ascend NPU has its own `save_kv_layer`/`wait_for_layer_load` worker path,
  so the NPU task must validate there rather than assume CPU P6 is complete.
