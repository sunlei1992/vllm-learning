# 03 KV Cache 与注意力：GLM-5.2 的 MLA 深度拆解

> 学习方式：跟读源码 + trace 实机打印 tensor shape（`trace_mla.py`）。
> 环境：v0.28.0 / M3 CPU / GLM-5.2 截断 3 层（dummy）。
> 结论：**MLA 用 576 维 latent 替代 32768 维标准 KV，57 倍压缩**——这是 GLM-5.2 能上 1M context 的地基。

## 0. 元信息

| 项目 | 值 |
|---|---|
| 日期 | 2026-08-28 |
| 源码路径 | `vllm-src/vllm/model_executor/layers/mla.py`（前处理）、`model_executor/models/deepseek_v2.py`（投影构建）、`v1/attention/backends/mla/cpu_sdpa.py`（prefill）、`cpu_mla.py`（decode） |
| 核心类/函数 | `MultiHeadLatentAttentionWrapper.forward`（mla.py:150）、`DeepseekV2MLAAttention`（deepseek_v2.py:948） |
| 复现工具 | `trace_mla.py`（打印每个阶段 tensor shape） |
| 状态 | ☑ 已掌握（概念 + 代码 + 实机数据） |

## 1. 核心问题

1. **MLA 和标准 MHA 的 KV cache 差多少？** —— 每 token：576 维 vs 32768 维（57 倍）
2. **压缩是怎么做到的？** —— K/V 先投影到低维 latent（512 维）存储，计算时再展开
3. **展开的代价去哪了？** —— 展开是线性变换，可"吸收"进 Q（decode 时甚至不展开，见 cpu_mla）
4. **Q 为什么也要压缩？** —— `q_lora_rank=2048` 先降维再升维，减少每步计算量

## 2. 一句话总结

> **MLA = 把"每 token 的 K/V"压缩成一个 512 维 latent 存进 KV cache，注意力计算时现场展开**；
> Q 同步走"压缩-展开"路径保持数学等价。存储 57 倍压缩，换来超长 context。

## 3. 关键概念速记（GLM-5.2 真实维度）

| 概念 | 值/解释 | 代码位置 |
|---|---|---|
| hidden_size | 6144 | config |
| num_heads | 64（KV 头 = Q 头，MQA 风格） | config |
| q_lora_rank | 2048：Q 的压缩中间维度 | config |
| kv_lora_rank | **512**：KV latent 维度（存缓存的） | config |
| qk_nope_head_dim / qk_rope_head_dim | 192 / 64（qk_head_dim=256） | config |
| v_head_dim | 256 | config |
| **KV cache 每 token** | kv_lora(512) + rope(64) = **576 维** | `kv_cache_utils.py` |
| 对比标准 MHA | 64 头 × 256 × 2 = **32768 维** | — |
| fused_qkv_a_proj | 融合投影：hidden → [q_lora(2048), kv_lora+rope(576)] | `mla.py:160` |
| kv_b_proj | latent(512) → 64头×(192+256)，展开 K_nope/V | `mla.py` / forward |
| weight absorption | 展开矩阵吸收进 Q，decode 免展开 | `cpu_mla.py` |

## 4. 数据流 / 时序（mla.py:150 前处理，实测 shape）

```
hidden_states (3, 6144)
  │ fused_qkv_a_proj（一次融合投影）
  ▼
qkv_lora (3, 2624)
  │ split [2048, 576]
  ├── q_c (3, 2048) ── q_a_layernorm ── q_b_proj ──► q (3, 64, 256)   ← Q 展开
  └── kv_lora (3, 576)
        ├── kv_c (3, 512) ── kv_a_layernorm ──► kv_c_normed (3, 512)  ★ 存 KV cache
        └── k_pe (3, 1, 64)                                          ★ 跟着存（rope）
之后：kv_c_normed 经 kv_b_proj 展开成 k_nope(192)/v(256) 用于 prefill；
      decode 直接对 latent 做 MQA（不展开，见 cpu_mla.py forward_mqa）
```

## 5. 代码走读记录

- [x] `deepseek_v2.py:948` `DeepseekV2MLAAttention` —— 只负责构建投影层，forward 直接转发给 `mla_attn`（1183 行）
- [x] `deepseek_v2.py:1000` `fused_qkv_a_proj = DeepSeekV2FusedQkvAProjLinear` —— Q/KV 融合投影的落点
- [x] `mla.py:150` `MultiHeadLatentAttentionWrapper.forward` —— **MLA 前处理核心**：fused 投影 → split → layernorm → q_b_proj 展开 → 交给 impl
- [x] `mla.py:160-175` —— `qkv_lora.split([q_lora_rank, kv_lora_rank + qk_rope_head_dim])`：一次投影产出 Q 和 KV 两部分
- [x] `mla.py:177-180` —— `kv_c, k_pe = kv_lora.split(...)`；`kv_c_normed = kv_a_layernorm(kv_c)`：进 cache 前的最后形态
- [ ] `cpu_sdpa.py _ragged_sdpa` —— prefill：kv_b_proj 展开 latent → 逐请求 dense attention（待细读）
- [ ] `cpu_mla.py forward_mqa` —— decode：weight absorption，latent 空间 MQA（待细读，下一步）

## 6. 实验 / 断点记录

| 实验 | 怎么做的 | 观察到 | 说明了什么 |
|---|---|---|---|
| MLA trace | monkey-patch `MultiHeadLatentAttentionWrapper.forward` 打印 shapes | 见 §4 数据流 | 压缩-展开全过程可视化 |
| KV cache 容量 | 同一次运行日志 | `407,232 tokens, 并发 3181x`（128 token/请求） | 57 倍压缩 → 海量并发 |
| 存储对比 | trace 里打印 | MLA 576 vs 标准 32768 维 | 压缩率实锤 |

## 7. 疑问清单（待解决）

- [ ] decode 的 weight absorption 具体数学？（Q 怎么吸收 kv_b_proj 转置 → 下一步学 cpu_mla.py）
- [ ] `kv_a_proj_with_mqa`（q_lora_rank=None 时）和 fused 版本的关系？
- [ ] rope 只作用在 64 维上，对长 context 的外推能力影响？

## 8. 与其他模块的关系

| 依赖/被依赖 | 模块 | 关系说明 |
|---|---|---|
| 构建 | `deepseek_v2.py DeepseekV2MLAAttention` | 投影层构建，forward 转发 |
| 执行 | `mla_attention.py MLAAttention` | 编排 prefill（forward_mha）/ decode（forward_mqa） |
| 执行 | `cpu_sdpa.py`（prefill）/ `cpu_mla.py`（decode） | CPU 上的两种计算路径 |
| 上游 | KV cache 分配 | latent 576 维/层/token 决定缓存容量 |
| 上游 | 稀疏注意力（is_v32） | GLM-5.2 的 DSA 在 MLA 之上叠加 indexer（本环境已关闭） |

---

> 复现：`source env.sh && VLLM_ENABLE_V1_MULTIPROCESSING=0 .venv/bin/python trace_mla.py`
> 下一步建议：学 `cpu_mla.py forward_mqa` 的 weight absorption（问题 7 的第一条）。
