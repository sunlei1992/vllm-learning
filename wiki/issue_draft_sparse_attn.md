## Environment

- vLLM version: v0.28.0
- Platform: Apple Silicon (M3), macOS 15.7.4, CPU backend
- HF transformers: 5.16.1
- Model: `zai-org/GLM-5.2` (`glm_moe_dsa` / `GlmMoeDsaForCausalLM`)

## Bug

Any GLM-5.x model (DSA / sparse-attention architecture) fails during engine initialization on the CPU backend:

```
NotImplementedError: Sparse Attention is not supported on CPU.
  File "vllm/platforms/cpu.py", line 89, in get_attn_backend_cls
    raise NotImplementedError("Sparse Attention is not supported on CPU.")
```

This makes GLM-5.2 unusable on CPU even for functional verification / CI, and there is **no user-facing way to disable sparse attention**.

## Root cause

Sparse attention is enabled implicitly by a `hasattr` check in the model code, while the config class always injects the trigger attribute:

1. `vllm/model_executor/models/deepseek_v2.py:1080` and `:1373`:
   ```python
   self.is_v32 = hasattr(config, "index_topk")
   ```
   → `is_v32=True` → sparse MLA path → CPU raises `NotImplementedError`.

2. The trigger attribute can never be removed by the user: `GlmMoeDsaConfig.__init__` (transformers 5.16.1, `configuration_glm_moe_dsa.py:125`) hard-codes it as a default parameter:
   ```python
   index_topk: int = 2048
   ```
   Even if `index_topk` is deleted from `config.json`, the loaded config object always has the attribute (verified: `hasattr(config, "index_topk")` is `True` after removing it from the JSON).

So there is no config-level workaround: sparse attention is architecturally forced for DSA models on every platform, and the CPU platform has no sparse support (no kernels, and the sparse indexer/top-k machinery is GPU-oriented).

## Reproduction

With only the model config (dummy weights, no weight download needed):

```bash
# fetch config.json + tokenizer only, e.g. into models/GLM-5.2
vllm bench latency --model models/GLM-5.2 --load-format dummy \
  --dtype float16 --enforce-eager --max-model-len 4096
```

Fails at engine init with the `NotImplementedError` above.

## Impact

- GLM-5.x family (`glm_moe_dsa`): all versions with `index_topk` in config (e.g. GLM-5.2) cannot run on CPU at all.
- Likely also affects other sparse-attention MLA models routed through the same `is_v32` path on CPU.
- Related: PR #51471 ([CPU][MLA] Fix prefill backend selection so MLA runs end-to-end on CPU) fixes the CPU MLA *prefill* gap but does **not** touch the sparse-attention path; the new AMX MLA backend is x86+AMX-only, so Apple Silicon remains stuck on the reference backend where this error fires.

## Suggested directions

1. A platform-aware fallback: on CPU, disable sparse attention with a warning (fall back to dense attention), gated by a config/env flag so behavior is explicit — or at least a clear, actionable error message that names the offending config field and the workaround.
2. Alternatively, honor a user-supplied override (e.g. allow `index_topk` to be disabled through `hf_overrides`/config), so `is_v32` becomes False.

## Temporary local workaround (for reference)

Setting `self.is_v32 = False` in `deepseek_v2.py` (both occurrences) makes DSA models run on CPU with dense attention (verified end-to-end with GLM-5.2 truncated to 3/78 layers, dummy weights).
