# Single-engine layerwise shared buffer (pure vLLM CPU)

One engine, N layers alias a few physical KV slots, and a per-layer
save/load connector fences slot reuse. The 2026-11-21 pass makes the decode
path byte-correct on fixed weights.

## Result

`MAX_TOKENS=2`, `LOAD_FORMAT=auto`:

| Model | baseline | shared buffer |
| :-- | :-- | :-- |
| Qwen2.5-tiny4-fixed | `[6212, 6212]` | **`[6212, 6212]`** |
| Qwen2.5-tiny28-fixed | `[87630, 87630]` | **`[87630, 87630]`** |

28-layer counters: `load zero 28 / hit 28`, `save 112`, `save skip 0`,
`checksum ok 28 / bad 0`.

## Three root causes

The earlier note claimed the CPU decode path never triggers the layerwise
hook. That was wrong: `attn_metadata` is a dict and the hook runs. The real
bugs were:

1. **Key bound too late.** `start_load_kv` runs in `post_forward` for
   connectors without sync loads, after the step's `save_kv_layer`. The first
   prefill save was skipped (`_current_key is None`), so decode loaded zero.
   Fix: bind the request key in `bind_connector_metadata` (`pre_forward`).
2. **Load ran after the KV update.** Upstream wraps only
   `unified_attention_with_output`, so the order is
   `unified_kv_cache_update` -> `wait_for_layer_load` -> attention. Loading
   history then overwrites the new tokens' rows. Fix: call
   `wait_for_layer_load` before the update (the script wraps
   `Attention.forward`) and dedupe per layer.
3. **Alias patch gave every slot `offset=0`.** Upstream `allocate_kv_cache`
   uses one backing allocation plus per-descriptor offsets, so all slots
   aliased the same bytes. Fix: `size = total across slots`, cumulative
   `offset`, `layer_stride=0` per shared slot.

Note: vllm-ascend's GLM-Next path allocates one backing **per descriptor**,
so it is not affected by (3); (1) and (2) still matter for any connector
whose load must precede the layer's KV write.

## Files

- `run_shared_buffer.py`: alias patch (fixed offsets), load-before-update
  wrapper, per-layer connector wiring.
- `layerwise_shared_buffer_connector.py`: slot store, key binding, dedupe.
- `test_layerwise_wait_order.py`: engine-free UT for the ordering contract.
- `make_tiny4_model.py`: build the tiny model.

## Run

UT (no engine, ~seconds):

```bash
docker run --rm --platform linux/arm64 \
  -v "$PWD/wiki/vllm架构笔记/assets/qwen_cpu_kv/shared_buffer:/app:ro" \
  sim030:mooncake bash -lc \
  'cd /app && PYTHONPATH=/app /opt/v030/bin/python test_layerwise_wait_order.py'
```

4-layer:

```bash
docker run --rm --memory 6g --platform linux/arm64 \
  -v "$PWD/models:/models:ro" \
  -v "$PWD/wiki/vllm架构笔记/assets/qwen_cpu_kv/shared_buffer:/app:ro" \
  sim030:mooncake bash -lc \
  'PYTHONPATH=/app VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 \
   ALIAS=1 NUM_SHARED=3 MODEL_DIR=/models/Qwen2.5-tiny4-fixed \
   LOAD_FORMAT=auto MAX_TOKENS=2 /opt/v030/bin/python /app/run_shared_buffer.py'
```

28-layer: same with `MODEL_DIR=/models/Qwen2.5-tiny28-fixed`.

Baseline: `ALIAS=0` (no connector) with the same model.

## Scope

Validates the single-engine shared-slot lifecycle and decode correctness on a
tiny CPU model. It does not use Mooncake for the shared-buffer store, and it
is not a GLM/Qwen3 full-model or performance test.
