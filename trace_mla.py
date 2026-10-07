"""GLM-5.2 MLA 注意力教学 trace v2 —— 单 token 生成，聚焦 prefill 阶段

hook 4 个点，打印真实 tensor shape 和阶段拆分：
1. MultiHeadLatentAttentionWrapper.forward (mla.py)   — MLA 前处理
2. MLAAttention.forward (mla_attention.py)            — prefill/decode 拆分
3. MLACommonImpl.forward_mha                          — latent 展开成 K/V
4. CPUSDPAMLAPrefillBackend._ragged_sdpa             — 注意力数学

用法:
    source env.sh && VLLM_ENABLE_V1_MULTIPROCESSING=0 .venv/bin/python trace_mla.py
"""
from vllm import LLM, SamplingParams
from vllm.model_executor.layers import mla as mla_mod
from vllm.model_executor.layers.attention import mla_attention as attn_mod
from vllm.v1.attention.backends.mla.prefill import cpu_sdpa as sdpa_mod

# ── Hook 1: MLA 前处理 ──
_orig_wrapper = mla_mod.MultiHeadLatentAttentionWrapper.forward


def traced_wrapper(self, positions, hidden_states, llama_4_scaling=None):
    def sh(name, t):
        print(f"      {name:30s} {tuple(t.shape)}")

    print("  [前处理] fused 投影 → split → layernorm → Q展开")
    qkv_lora = self.fused_qkv_a_proj(hidden_states)[0]
    sh("fused_qkv_a_proj", qkv_lora)
    q_c, kv_lora = qkv_lora.split(
        [self.q_lora_rank, self.kv_lora_rank + self.qk_rope_head_dim], dim=-1)
    sh("q_c (Q latent)", q_c)
    sh("kv_lora", kv_lora)
    q_c = self.q_a_layernorm(q_c)
    kv_c, k_pe = kv_lora.split([self.kv_lora_rank, self.qk_rope_head_dim], dim=-1)
    kv_c_normed = self.kv_a_layernorm(kv_c)
    k_pe = k_pe.unsqueeze(1)
    sh("kv_c_normed (★存cache)", kv_c_normed)
    sh("k_pe", k_pe)
    q = self.q_b_proj(q_c)[0].view(-1, self.num_heads, self.qk_head_dim)
    sh("q (heads, qk_dim)", q)
    return _orig_wrapper(self, positions, hidden_states, llama_4_scaling)


mla_mod.MultiHeadLatentAttentionWrapper.forward = traced_wrapper

# ── Hook 2: MLAAttention.forward 编排（prefill/decode 拆分）──
from vllm.forward_context import get_forward_context

_orig_mla_forward = attn_mod.MLAAttention.forward


def traced_mla_forward(self, q, kv_c_normed, k_pe, output_shape=None,
                       q_dcp_replicated=None):
    forward_context = get_forward_context()
    attn_metadata = forward_context.attn_metadata
    if isinstance(attn_metadata, dict):
        attn_metadata = attn_metadata[self.layer_name]
    elif isinstance(attn_metadata, list):
        attn_metadata = attn_metadata[0][self.layer_name]
    num_mqa = attn_metadata.num_decode_tokens
    num_mha = q.size(0) - num_mqa
    print(f"  [编排] 本轮共 {q.size(0)} 个 token: "
          f"prefill(MHA)={num_mha}, decode(MQA)={num_mqa}")
    return _orig_mla_forward(self, q, kv_c_normed, k_pe, output_shape,
                             q_dcp_replicated)


attn_mod.MLAAttention.forward = traced_mla_forward

# ── Hook 3: forward_mha 的 latent 展开 ──
_orig_forward_mha = attn_mod.MLACommonImpl.forward_mha


def traced_forward_mha(self, q, kv_c_normed, k_pe, kv_c_and_k_pe_cache, attn_metadata,
                       k_scale, output, output_scale=None):
    def sh(name, t):
        print(f"      {name:30s} {tuple(t.shape)}")

    print("  [prefill] kv_b_proj 展开 latent → K/V")
    kv_nope = self.kv_b_proj(kv_c_normed)[0].view(
        -1, self.num_heads, self.qk_nope_head_dim + self.v_head_dim)
    sh("kv_b_proj 展开", kv_nope)
    k_nope, v = kv_nope.split([self.qk_nope_head_dim, self.v_head_dim], dim=-1)
    sh("k_nope", k_nope)
    sh("v", v)
    return _orig_forward_mha(self, q, kv_c_normed, k_pe, kv_c_and_k_pe_cache,
                             attn_metadata, k_scale, output, output_scale)


attn_mod.MLACommonImpl.forward_mha = traced_forward_mha

# ── Hook 4: prefill 注意力数学 ──
_orig_sdpa = sdpa_mod.CPUSDPAMLAPrefillBackend._ragged_sdpa


def traced_sdpa(self, q, k, v, q_cu_seq_lens, kv_cu_seq_lens, causal, return_softmax_lse):
    def sh(name, t):
        print(f"      {name:30s} {tuple(t.shape)}")

    print("  [注意力数学] softmax(QK^T/√d)V，逐请求计算")
    sh("q (ragged)", q)
    sh("k (ragged)", k)
    sh("v (ragged)", v)
    num_reqs = q_cu_seq_lens.numel() - 1
    print(f"      本轮 {num_reqs} 个请求")
    return _orig_sdpa(self, q, k, v, q_cu_seq_lens, kv_cu_seq_lens, causal,
                      return_softmax_lse)


sdpa_mod.CPUSDPAMLAPrefillBackend._ragged_sdpa = traced_sdpa

# ── 只生成 1 个 token：第一步纯 prefill，无 decode ──
llm = LLM(
    model="models/zai-org_GLM-5.2",
    load_format="dummy",
    enforce_eager=True,
    max_model_len=128,
    dtype="float16",
    gpu_memory_utilization=0.3,
)
out = llm.generate(["The quick brown fox"], SamplingParams(max_tokens=1, temperature=0.0))
print("=== GENERATED ===", repr(out[0].outputs[0].text[:30]))
