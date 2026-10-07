## Apple Silicon (M3) validation — CPU SDPA MLA prefill backend works

Thanks for this fix! I ported the PR's changes (`cpu_sdpa.py`, `registry.py` CPU entry, `selector.py` CPU branch, `_custom_ops.py` `gather_mla_context_cache_cpu`, and the `mla_attention.py` CPU gather fallback) onto a v0.28.0-based tree and validated end-to-end on Apple Silicon, which is a platform the current CI/reference backend path doesn't cover.

**Environment**: Mac M3, macOS 15.7.4, 24 GB, CPU backend, `dummy` weights.

**Test 1 — official smoke scenario** (mirrors `test_cpu_mla_backend_smoke`: DeepSeek-V2-Lite + `hf_overrides` shrink to 2 layers / 4 experts / all-MoE):

```
Using CPU SDPA MLA prefill backend.      ← selector now picks the CPU backend
Using CPU Unquantized MoE backend
PASSED: both requests generated 4 tokens
```

**Test 2 — GLM-5.2 (glm_moe_dsa) truncated to 3/78 layers**:

```
Using CPU SDPA MLA prefill backend.
Avg latency: 2.51s per batch (batch=4, 16+16 tokens)
```

Both pass with only the PR's changes applied (no other patches). The log confirms the selector routes to `CPU_SDPA_MLA` and prefill runs through the new backend.

**Notes / suggestions**:

1. **Out of scope, not covered by this PR**: sparse-attention models on CPU still fail with `NotImplementedError: Sparse Attention is not supported on CPU` (`platforms/cpu.py:89`), because e.g. `GlmMoeDsaConfig` hard-codes `index_topk=2048` so `DeepseekV2.is_v32` (`hasattr(config, "index_topk")`) is always True. I had to disable that locally for the GLM-5.2 test. Worth a follow-up issue/PR (config-flag or clear error path).
2. I validated the **fresh-prefill path** (no `num_computed_tokens > 0`). The contextful/LMCache path (`run_prefill_context_chunk`, `gather_mla_context_cache_cpu`, merge) was ported but not exercised here — would be good to see a CPU CI test for that too.
3. Minor: the `is_available()`/`supports_*` classmethods on `CPUSDPAMLAPrefillBackend` are inherited defaults — fine since the selector special-cases CPU, but `supports_mla_dimensions` could be declared to fail fast on unsupported dims like the FlashAttn backend does.

Happy to run any additional scenario you'd like checked on Apple Silicon.
