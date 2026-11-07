# 15 ShardQ：Token-sharded sparse-MLA prefill 解析与昇腾 950DT 迁移评估

## 0. 元信息

- 日期：2026-11-07
- 上游来源（均已核对）：
  - PR [#63956](https://github.com/vllm-project/vllm/pull/63956)，merged 2026-11-05 09:42 UTC，merge commit `1efcaa98ff11c4`
  - main 分支 `vllm/config/attention.py`（`sparse_mla_shard_q` / `sparse_mla_shard_q_min_tokens`）
  - `vllm/v1/attention/ops/shardq.py`（新增 363 行）、`tests/v1/attention/test_shardq.py`
  - 相关未合入 PR：[#66071](https://github.com/vllm-project/vllm/pull/66071)（DSv4.1，open draft）、
    [#66052](https://github.com/vllm-project/vllm/pull/66052)（竞态修复，open）、
    [#66027](https://github.com/vllm-project/vllm/pull/66027)（DCP ShardQ，open draft）
- 本地对照：`vllm-ascend-src`（HEAD `aba653618`，vLLM pin `a98247ab`，2026-10-10）、`vllm-src`（v0.28.0）
- 昇腾资料：950DT 超节点公开规格、`NPU_SHMEM_SYMMETRIC_SIZE` 文档、triton-ascend 迁移指南

## 1. 一句话结论

ShardQ 把 sparse-MLA **prefill 的 TP 切分维度从「按 head」换成「按 token」**：
每个 TP rank 只对属于自己的 token 跑 indexer 和 sparse attention（用全部 head），
Q 和输出各做一次 all-to-all 换布局。收益随上下文变长而放大（32K 1.24× → 1M 2.62×），
代价是 KV 预算里扣一块交换缓冲。

迁移到昇腾：**布局层可以 1:1 搬，交换层和 attention 层必须重写**。
"因为它用 Triton 所以好迁"这个前提不成立——昇腾侧的 indexer 和 sparse attention
都是 CANN 厂商算子，不是 Triton。

## 2. 它解决什么问题

### 2.1 TP 下 MLA 的尴尬

MLA 只有 1 个 KV head，TP 切分后 **KV cache 在每个 rank 上是复制的**。
于是 prefill 时：

- **indexer**（DSA 的稀疏打分）对每个 token 都要算 —— 但每个 rank 的 KV 一样，
  所以 **TP 个 rank 把同一份打分算了两遍/四遍/八遍**，这是纯浪费；
- **sparse attention** 每个 rank 只持有 `H/tp` 个 head，kernel 的 head 维度被切得很窄，
  算力和带宽都用不满。

token 越长，indexer 的 `rows × keys` 越大，这份浪费越贵。这就是 ShardQ 的动机。

### 2.2 做法

```
按 head 切（现状）           按 token 切（ShardQ）
rank0: 全 token, H/4 head    rank0: T/4 token, 全 H head
rank1: 全 token, H/4 head    rank1: T/4 token, 全 H head
...                          ...
indexer 算 4 遍               indexer 算 1 遍
attention kernel 窄          attention kernel 满
```

两次 all-to-all：Q 从 `[T, H/tp, D]` 换成 `[T_rank, H, D]`，输出再换回 `[T, H/tp, D_v]`。

### 2.3 zigzag 切分（关键细节）

不是简单按前后切，而是每个请求切成 `2 × tp` 段，rank `r` 拿第 `r` 段和倒数第 `r` 段：

```
请求切成 8 段（tp=4）：
| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
rank0: 0                       7
rank1:     1               6
rank2:         2       5
rank3:             3 4
```

原因是 causal attention：**段越靠后，每个 token 要看的 context 越长**，计算量越大。
一前一后配对，才能让各 rank 的因果工作量接近。这是 ShardQ 里最巧的一步，
也是纯逻辑、最容易移植的部分。

## 3. 落地状态（已核实）

| 项目 | 结论 | 证据 |
| :-- | :-- | :-- |
| 核心 PR | ✅ merged 2026-11-05 | `"merged":true`，merge commit `1efcaa98` |
| 默认开启 | ✅ | `sparse_mla_shard_q: bool = True` |
| 阈值 | ✅ 默认 **1024** | `Field(default=1024, ge=1)` |
| 旧 row sharding | ✅ 废弃 | `indexer_tp_shard_min_rows` 无效果，v0.34.0 删除 |
| 规模 | 21 文件 +856/−465 | PR API |
| DSv4.1 支持 | ❌ **仍是 open draft** | `#66071`：`state=open, draft=true, merged_at=null` |
| 已知竞态 | ⚠️ **未修复** | `#66052` open：async scheduling 下 pinned buffer 被覆写 |

> 常见误读：PR 描述里"4K 低于阈值、ShardQ 不生效"来自**旧的 8192 阈值**下的测量，
> 描述自己也写了"with the earlier 8192-token default threshold; they have not been re-run
> on the current head"。当前默认 1024，4K 是超过阈值的。

## 4. 触发条件与边界（源码 docstring 原文归纳）

生效需要**同时**满足：

1. TP > 1，且走 sparse MLA 路径（DSA 模型，如 GLM-5.x / DeepSeek-V3.2 / V4）；
2. 本步 **prefill token 数 ≥ `sparse_mla_shard_q_min_tokens`（默认 1024）**，
   这里的计数要**先扣掉 decode 请求**（长度 ≤ `1 + num_speculative_tokens` 的请求算 decode）；
3. backend 是 **FlashInfer sparse MLA**，或 **FlashMLA sparse + FP8 DeepSeek KV cache**；
4. **不是** DCP / PCP / HiSparse；
5. 至少一个请求的 seq_len > `index_topk`（短序列不稀疏，没意义）；
6. 每个 rank 至少分到一个 token。

不满足时静默回退到按 head 切，不报错。

**数值**：全部 head 在一个 rank 上跑，和 head-sharded 路径**不是逐位一致**
（bf16/fp8 归约顺序变了），所以上游用功能测试而非 logprob 对齐来验证。

## 5. 性能与代价

### 5.1 收益（GLM-5.3 NVFP4，TP4，GB200）

| 上下文 | TTFT 关 | TTFT 开 | 提升 |
| :-- | --: | --: | --: |
| 8K | 203 ms | 232 ms | 噪声内 |
| 32K | 634 ms | 511 ms | 1.24× |
| 64K | 1228 ms | 950 ms | 1.29× |
| 128K | 2546 ms | 1819 ms | 1.40× |
| 1M | 162.5 s | 62.0 s | 2.62× |

per-step forward 在 16K chunk @128K context 上 926 → 544 ms（1.70×）。

### 5.2 代价

- **显存**：交换缓冲按最坏情况预分配，从 KV cache 预算里扣。
  GLM-5.3 TP4 / 16K budget 下 KV 少 **0.47 GiB/卡**；V4.1 draft 说 16K batch 约 270 MB。
- **eager/图模式**：交换在 ACL graph（对应 CUDA graph）里需要固定形状，
  变长 all-to-all 会 desync —— 昇腾侧这条约束比 GPU 更硬。
- **小 batch 无收益**：低于阈值时两次 all-to-all 的开销大于省下的计算，所以有 1024 下限。

## 6. 代码结构（`vllm/v1/attention/ops/shardq.py`）

| 符号 | 作用 |
| :-- | :-- |
| `zigzag_split(query_lens, world)` | 纯 numpy，返回「按 rank 分组的 token id」+「每 rank token 数」 |
| `build_shardq_split(metadata, cfg)` | 判断是否触发、构造 `ShardQSplit` |
| `ShardQMetadata` | 每步的分片信息 + 本 rank 的 `forward_mqa` metadata |
| `_shard_q_kernel` | Triton：把 Q 推到各 peer 的对称内存缓冲 |
| `_unshard_out_kernel` | Triton：把输出按 head 块推回各 rank |
| `ShardQWorkspace` | 对称内存工作区，每 ubatch 一个槽 |
| `shard_q` / `unshard_out` | 两条路径：有对称内存走 Triton push，否则 `dist.all_to_all_single` |

indexer 侧的改动（`vllm/v1/attention/backends/mla/indexer.py`）：

- 新增 `positions` 指针参数 —— 因为分片后 token 在 `query_start_loc` 里不再连续；
- 新增 `shardq_gather_indices` —— 本 rank 的 token 紧凑排列；
- `DeepseekV32IndexerPrefillMetadata.row_shard_sizes` 被 `shardq_gather_indices` 取代。

也就是说 **indexer 的 Triton kernel 只需要「按 positions 取 context 长度」**，
打分本体不用改 —— 这点对昇腾很关键（见 7.3）。

## 7. 昇腾 950DT 迁移评估

### 7.1 先纠正前提：这不是一个 Triton 特性

| 组件 | vLLM (CUDA) | vllm-ascend (NPU) |
| :-- | :-- | :-- |
| Q/输出交换 | Triton push 对称内存，或 NCCL all_to_all | **无**，需新建 |
| DSA indexer 打分 | Triton (`sparse_attn_indexer`) | **CANN 算子**（`npu_lightning_indexer` / `DeviceOperator.indexer_select_post_process`） |
| sparse MLA attention | FlashInfer / FlashMLA（CUDA） | **CANN 算子**（`cann_ops_transformer.sparse_flash_mla`，CANN 9.2） |
| 布局/切分 | Python + numpy | 可直接复用 |

`vllm-ascend` 确实大量用 Triton（`vllm_ascend/ops/triton/` 下约 50 个文件，
含 `dsa_cp.py`、`prepare_indexer_indices.py`、`query_gather_prep.py`），
但**恰好是 ShardQ 最核心的两个 kernel 不是 Triton**。

所以正确的心智模型是：**搬的是布局，重写的是通信；kernel 能不能接住全 head 是最大未知数。**

### 7.2 平台能力对照

| ShardQ 需要 | 950DT / CANN 现状 | 判断 |
| :-- | :-- | :-- |
| 对称内存（peer 直接读写） | `aclshmem` / `NPU_SHMEM_SYMMETRIC_SIZE`，**950DT 在支持列表** | ✅ 能力有，API 要接 |
| 全局统一编址 | 超节点 256 TB 统一内存 | ✅ 但只在超节点形态成立 |
| all-to-all | HCCL 有 AllToAll；VA 已在 o-proj TP 路径用 `dist.all_to_all_single` | ⚠️ **变长 split（AllToAllV）粒度与性能未验证** |
| 局部 query 的 indexer | `actual_seq_lengths_query` 已支持，**DSA-CP 正在这么用** | ✅ 现成 |
| 全 head 的 sparse MLA | `sparse_flash_mla` 的 head 数约束未知 | ❓ 需实测 |
| 显存 | 144 GB HBM / 4 TB/s | ✅ 交换缓冲不是问题 |
| 上下文 | 1.72 PB/s 互联、跨柜 3 µs | ✅ 对 all-to-all 友好 |

950DT 公开规格（2026-09 超节点展出，Q4 上市）：144 GB HiZQ 2.0 HBM、4 TB/s、
FP16/BF16/FP8/MXFP4、单柜 1024 卡、256 TB 全局内存统一编址。

### 7.3 能 1:1 搬的部分

1. `zigzag_split` —— 纯 numpy，无依赖；
2. `build_shardq_split` 的判定逻辑（阈值、decode 扣除、topk 判定、空 rank 保护）；
3. **"把本 rank 的 token run 表达成多个伪请求"这个技巧**（V4.1 draft 的做法）：
   zigzag 会把一个请求切成早晚两段，每段都是「以自己最后一个 token 结尾的 prefill chunk」，
   于是可以直接复用现有的 metadata builder，不用改 kernel 的批量语义。

### 7.4 必须重写的部分

**(1) 交换层** —— 从易到难三档：

| 档 | 做法 | 成本 | 适用 |
| :-- | :-- | :-- | :-- |
| A | `dist.all_to_all_single` + 定长 padding，eager 模式 | 低 | PoC 验证正确性 |
| B | 同上，但静态缓冲 + ACL graph 捕获 | 中 | 生产必需（VA 的 o-proj 已趟过这条路） |
| C | `aclshmem` + Ascend C 自定义 push kernel | 高 | 追性能 |

VA 源码里已经写明了 B 档的坑（`dsa_v1.py` 的 o-proj）：

> "Pad to a static exchange size so the all_to_all / reduce_scatter shapes are identical
> across all ACL graph buckets — variable shapes desync the HCCL communicator during graph replay."

ShardQ 的 split size 每步都变（取决于 batch 里各请求长度），所以**A 档只能在 eager 下跑**，
上 ACL graph 必须 pad 到 `max_num_batched_tokens`。这会把交换量放大，
是昇腾侧相对 GPU 的**额外税**。

**(2) attention 层** —— 需要确认 `sparse_flash_mla`：

- 能接受 `H` 个 head（而不是 `H/tp`）；
- 能接受 `query_start_loc` 描述的**非连续 run**（多个小 prefill chunk）；
- 对齐要求（NPU vector 32B / cube 512B）。

这是整个迁移里**风险最高**的一步：厂商算子黑盒，head 数或 tile 形状可能有硬约束，
不满足就只能退回 head-shard，特性白做。

**(3) indexer 层** —— 比想象中轻：

VA 的 DSA-CP 已经在构造 `local_query_start_loc` / `local_query_lens`，
并通过 `actual_seq_lengths_query` 传给 indexer。ShardQ 要的「只给本 rank 的 token 打分」
是同一套接口，只是 run 的划分从"连续前缀"变成"zigzag 两段"。**这块大概率能复用，不是从零写。**

**(4) 元数据层** —— `AscendDSAMetadataBuilder.build()` 里插入 split 逻辑，
把 shardq 的 token 映射写进 `AscendDSAMetadata`。

### 7.5 风险清单

| 风险 | 影响 | 缓解 |
| :-- | :-- | :-- |
| `sparse_flash_mla` 不支持全 head / 非连续 run | 特性不成立 | Phase 0 先用单算子脚本验证 |
| HCCL AllToAllV 变长 split 性能差或语义受限 | 收益被吃掉 | 先做定长 pad 版，量一下 |
| ACL graph 要求定长 → 交换量放大 | 1.6× 变 1.1× | 按实际 batch 分布评估 pad 浪费 |
| 950DT 是新平台，功能有缺口（如 sparse KV offload 明确不支持） | 踩到未知坑 | 先跑通 baseline DSA |
| 数值与 head-shard 路径不一致 | 精度回归 | 用检索/功能测试，不看 logprob |
| 上游 `#66052` 竞态未修 | async scheduling 下偶发挂死 | 先关 async scheduling |
| CANN 9.2 依赖 | 版本锁死 | 确认公司环境版本 |

### 7.6 收益判断：可能小于 GPU 的 1.6×

ShardQ 的收益 = 省下的 indexer 重复计算 + attention kernel 变饱满 − 两次 all-to-all。

在 950DT 上：

- **4 TB/s HBM** 让 indexer 的 KV 读取更快，重复计算的绝对代价下降；
- **互联更强**（1.72 PB/s、3 µs）让 all-to-all 更便宜，这是有利面；
- 但如果 VA 的 `npu_lightning_indexer` 本身已经很快、或者 prefill 瓶颈在 MoE/GEMM
  而不在 attention，那 ShardQ 的收益会很有限。

**结论：必须先 profile 再决定。** 判据是：长上下文 prefill 的 torch profile 里，
`indexer` + `sparse attention` 合计占比是否 > 30%。低于这个数，投入产出不划算。

### 7.7 分阶段计划（建议）

| 阶段 | 内容 | 产出 | 估时 |
| :-- | :-- | :-- | :-- |
| P0 | 950DT 上跑 GLM-5.3 或 DSv4.1 baseline，torch profile 拆 indexer / attention / MoE | 收益上限判断 | 1 周 |
| P1 | 单算子验证：`sparse_flash_mla` 能否吃全 head + 多 run | go / no-go | 3–5 天 |
| P2 | 移植 zigzag + 伪请求 metadata，交换用 HCCL eager | 正确性 PoC | 2–3 周 |
| P3 | 静态缓冲 + ACL graph，量 pad 税 | 性能数字 | 2 周 |
| P4 | SHMEM push（可选），对齐全 head kernel 调优 | 追平 CUDA 收益 | 3–4 周 |

P1 是 go/no-go 点：如果算子吃不下全 head，整个方案要重新设计
（备选：head 分片 + token 分片的混合切法，收益打折但可行）。

## 8. 结论

- **能迁，但不是"移植"，是"重写交换层 + 复用布局层"**。
- 真正的好消息不是 Triton，而是：**MLA 的 KV 在 TP 下本来就是复制的**，
  所以 token 分片不需要搬 KV；而且 VA 的 DSA-CP 已经把「局部 query 打分」的接口趟通了。
- 真正的坏消息是：**attention 算子能不能吃全 head 未知**，以及**变长 all-to-all 与 ACL graph 冲突**。
- 建议先做 P0/P1（约两周），用数据决定要不要继续。

## 9. 本机原型进度（2026-11-07）

Step 0 已完成，代码在 `assets/shardq/`：

| 文件 | 内容 |
| :-- | :-- |
| `shardq_ref.py` | zigzag 切分、触发判定、run 划分、positions、query_start_loc 重编号、参考交换、定长 pad、最小 sparse MLA |
| `test_shardq_ref.py` | 32 个单测（无 NPU、无 vLLM 依赖） |

```
$ python -m pytest -q
32 passed in 0.91s
```

三个值得记住的设计点：

1. **切分公式逐行照搬上游**，并用 `test_zigzag_matches_known_layout` 把
   「长度 8 / 4 rank → `[0,7,1,6,2,5,3,4]`」钉死在测试里，防止以后漂移。
2. **交换的验证方式不是"能跑"，而是"每个 peer 的缓冲区被各 owner 恰好写一次"**：
   往返测试对所有 rank 做全量重建并逐位比对，能同时抓住"漏写"和"重复写"。
3. **交换按定长 pad 设计**（`pad_to_static`），既规避 AllToAllV 的不确定性，
   也让将来万一进图不会炸。

下一步（Step 1 剩余）：接 `CommonAttentionMetadata` 与 `split_decodes_and_prefills`，
再用真 Scheduler 跑一遍，确认单元测试构造不出来的真实 batch 形状。

### 9.1 后续进展（同日）

| 步骤 | 产出 | 本机验证 |
| :-- | :-- | :-- |
| Step 1 | `shardq_vllm.split_from_common_attn_metadata`（取字段 + 调纯函数） | vLLM 0.28 与 `a98247ab` 两版各跑一遍，37 passed |
| Step 2 | `vllm_ascend/attention/shardq.py` + `AscendDSAMetadataBuilder` 钩子（默认关） | `tests/ut/attention` 1899 passed / 10 skipped，无回归 |
| Step 3 | `plan_exchange` / `static_shard_q` / `static_unshard_out`（定长、可注入 all_to_all） | 40 个 CPU 用例，含置换方向的双向校验 |

VA 代码在 worktree `tmp/va-shardq`（分支 `feat/shardq`，提交 `8edb38678`）。

两个工程约束要记住：

1. **VA 锁定的 vLLM `a98247ab` 早于 #63956**，没有 `sparse_mla_shard_q` 配置项，
   所以开关先用环境变量 `VLLM_ASCEND_SPARSE_MLA_SHARD_Q`（默认关）顶着，
   等 pin 越过 11-05 再换回上游配置。
2. 当前钩子**只产出布局、不改执行**：attention 仍是 head-shard。
   这样先把元数据路径测绿，把行为切换留到真机。

还没做：attention 路径切换、真 Scheduler 联调、950DT 的 Step 4。

## 10. 参考

- [PR #63956](https://github.com/vllm-project/vllm/pull/63956)（merged）
- [PR #66071](https://github.com/vllm-project/vllm/pull/66071)（DSv4.1，open draft）
- [PR #66052](https://github.com/vllm-project/vllm/pull/66052)（ShardQ 竞态，open）
- [PR #66027](https://github.com/vllm-project/vllm/pull/66027)（DCP ShardQ，open draft）
- `vllm/config/attention.py`（main）
- [昇腾 950 超节点公开报道](https://m.163.com/dy/article/L7C72V680511CPVM.html)
- [NPU_SHMEM_SYMMETRIC_SIZE](https://github.com/ascend/pytorch/blob/master/docs/zh/api/environment_variable/memory_management/NPU_SHMEM_SYMMETRIC_SIZE.md)
- [triton-ascend 迁移指南](https://github.com/triton-lang/triton-ascend/blob/main/docs/en/migration_guide/migrate_from_gpu.md)
- 本地：`vllm-ascend-src/vllm_ascend/attention/{dsa_v1.py,dsa_v41.py,indexer.py,sparse_flash_mla.py}`
