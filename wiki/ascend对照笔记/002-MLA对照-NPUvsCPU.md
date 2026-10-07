# 002 MLA 注意力对照：NPU（vllm-ascend） vs CPU（vllm 主仓）

> 对照结论：**两者解决同一个问题（MLA 的 prefill/decode 注意力），但架构层级完全不同——
> CPU 走主仓的"wrapper 预处理 + forward_mha/mqa 拆分 + 通用调度"；
> NPU 是 impl 自含一切的"统一 forward + 融合算子 + 预吸收权重"**。
> 前置：先读 `../vllm架构笔记/03-KV Cache 与注意力.md`（MLA 基础）和 `001-PCP对照-主仓vsAscend.md`。
> 基线：vllm v0.28.0 `vllm-src/`、vllm-ascend v0.23.0 `vllm-ascend-src/`

---

## 1. 一句话结论

> CPU MLA 是**"参考实现"**（结构清晰、性能随意）：主仓共享 wrapper 做预处理，
> 按 prefill/decode 拆两个方法，prefill 用 PyTorch SDPA、decode 用自研 C++ kernel。
> NPU MLA 是**"性能实现"**：impl 接收原始 hidden_states 自己包办预处理+注意力，
> 全程走 `torch_npu` 融合算子 + 加载期预吸收成 NPU 专有格式的权重，
> 并叠加 graph capture / MTP padding / FA 量化 / CP 支持。

## 2. ★ 最大的架构差异：接口分层

```
主仓 CPU（v0.28.0）:
  mla.py wrapper 预处理（fused 投影/split/layernorm/RoPE）
    → MLAAttention 编排（拆 prefill/decode token）
      → MLACommonImpl.forward_mha / forward_mqa     ← 按阶段拆方法
        → CPUMLAImpl 只覆写 forward_mqa + do_kv_cache_update

ascend NPU（v0.23.0）:
  AscendMLAImpl.forward(layer_name, hidden_states, kv_cache, ...)   ← 统一入口
    → 内部 _mla_preprocess 自己预处理（937 行）
    → 内部统一调度 prefill/decode
  （forward_mha / forward_mqa 直接 raise NotImplementedError, "Use forward() instead"）
```

| 接口 | 主仓 CPU | ascend NPU |
|---|---|---|
| impl 基类 | `MLACommonImpl`（拆 mha/mqa） | `MLAAttentionImpl`（统一 forward） |
| impl 收到什么 | **预处理后的** q / kv_c_normed / k_pe | **原始** hidden_states（自己预处理） |
| 预处理位置 | 共享 wrapper（mla.py，所有平台共用） | impl 内部（`_mla_preprocess`，NPU 专属） |
| 阶段拆分 | forward_mha（prefill）/ forward_mqa（decode） | 一个 forward 内部分派 |

> ⚠️ 版本注意：ascend 的 `MLAAttentionImpl` 接口（hidden_states 入参风格）看起来比
> v0.28.0 主仓的 `MLACommonImpl` 更"V1 时代"——对照时注意 ascend v0.23.0 目标 vllm 版本可能不同，
> 接口差异部分是版本演进，部分是平台自研。

## 3. 执行路径对照

### Prefill

| | CPU（cpu_sdpa.py） | NPU（mla_v1.py） |
|---|---|---|
| 方式 | 展开 latent → 逐请求 dense attention（`_ragged_sdpa` 循环） | `npu_fused_infer_attention_score_v2`（融合算子，TND layout，874 行） |
| KV 获取 | all-gather（PCP 时）或本地 | `exec_kv_prefill`（641）+ `_reorg_kvcache`（418，reorder 缓存） |
| 量化 | 无 | FA 量化（`enable_fa_quant`，761 行） |

### Decode

| | CPU（cpu_mla.py） | NPU（mla_v1.py） |
|---|---|---|
| 方式 | C++ kernel `mla_decode_kvcache`（模板 576/512/16） | `npu_fused_infer_attention_score_v2` decode 路径（874 行） |
| 吸收 | 运行时 `torch.bmm(q_nope, W_UK_T)`（主仓共享代码 mla_attention.py:918） | 权重**加载期预吸收**：`_process_weights_for_fused_mlapo`（310）、`wd_qkv`、`npu_format_cast(ACL_FORMAT_FRACTAL_ND)` |
| graph | 无 | graph capture（`update_graph_params`，大量 padding 逻辑） |
| MTP/spec | 无 | 深度支持（`pad_actual_seq_len_q_mtp_*`，357/402） |

### KV cache 写入

| | CPU | NPU |
|---|---|---|
| 实现 | `do_kv_cache_update`：flat view + slot 写入（纯 PyTorch） | `exec_kv_prefill/decode` 内嵌 + `_reorg_kvcache`（format cast 后写入） |

## 4. 权重吸收（MLA 精髓）的平台差异 ★

MLA decode 的"吸收"（把 `kv_b_proj` 展开吸收进 Q）两平台做法不同：

```
CPU: 权重保持原始形态，吸收在【运行时】做一次小矩阵乘
     mla_attention.py:918  torch.bmm(mqa_q_nope, W_UK_T)   # (192→512)

NPU: 权重在【加载时】就处理成融合形态（MLAPRO fused weights）
     mla_v1.py:310  _process_weights_for_fused_mlapo(act_dtype)
     mla_v1.py:902  npu_transpose_batchmatmul(x, self.W_UV)   # 输出侧吸收
     mla_v1.py:1028 wd_qkv = npu_format_cast(wd_qkv, 29)      # NPU 专有张量格式
```

> 原因：NPU 算子对权重格式有硬性要求（Fractal ND 等），加载期预处理一次、
> 运行时零转换成本，是 NPU 性能实现的标准做法；CPU 是参考实现，怎么简单怎么来。

## 5. 平台特化对比（谁更"重"）

| 特性 | CPU（主仓 cpu_mla） | NPU（ascend mla_v1） |
|---|---|---|
| 文件规模 | ~230 行（+cpu_sdpa 137） | **1807 行** |
| metadata builder | 主仓共享 `MLACommonMetadataBuilder` | 自研 `AscendMLAMetadataBuilder`（234）+ CP 版（mla_cp.py） |
| graph capture | ❌ | ✅（含 reorder/padding 全套） |
| MTP/spec decode | ❌ | ✅ |
| FA 量化 | ❌ | ✅（`_process_weights_for_fused_fa_quant`） |
| CP（PCP/DCP） | 主仓 pcp.py 共享逻辑 | 自研 `AscendMlaCPImpl`（context_parallel/mla_cp.py） |
| C++ kernel | `csrc/cpu/mla_decode.cpp` | `torch_npu` 官方算子 |

## 6. 代码对照阅读路线

1. 回顾 CPU 基准：`vllm-src/vllm/v1/attention/backends/mla/cpu_mla.py` 全文（~230 行，短）
2. 看主仓共享编排：`vllm-src/vllm/model_executor/layers/attention/mla_attention.py:2838/3001`（mha/mqa 签名）
3. 看 NPU 统一入口：`vllm-ascend-src/vllm_ascend/attention/mla_v1.py:1016`（forward）
4. 对照预处理：主仓 `mla.py:150` vs NPU `mla_v1.py:937 _mla_preprocess`
5. 对照吸收：主仓 `mla_attention.py:918` vs NPU `mla_v1.py:310/902`

## 7. 疑问清单

- [ ] ascend 的 `_mla_preprocess` 和主仓 wrapper 预处理算出来的张量是否数学等价？（实现路径差这么多，值得对拍验证）
- [ ] `npu_fused_infer_attention_score_v2` 的 TND layout 和主仓注意力后端的 layout 语义对应关系？
- [ ] MLAPRO fused weight 是什么格式，为什么能省运行时吸收？

## 8. 方法收获

1. **"参考实现" vs "性能实现"是平台代码差异的第一解释**：CPU 后端定位是 CI/功能验证（我们最开始读到的 docstring），NPU 是生产性能
2. **接口差异先于实现差异**：看一个插件后端，先看它 impl 的基类和入口签名，再看内部——NPU 的"统一 forward"直接暴露了它和主仓"拆分 forward"的分层哲学不同
3. **同一数学、两种落地**：weight absorption 在 CPU 是运行时一行 bmm，在 NPU 是加载期融合权重+专有格式——平台的算子生态决定了实现的形态
