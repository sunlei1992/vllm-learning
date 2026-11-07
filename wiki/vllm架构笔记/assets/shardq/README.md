# ShardQ 本机原型

把 vLLM 上游 `vllm/v1/attention/ops/shardq.py` 里**与设备无关的布局层**抽出来，
做成可以在 Mac / CPU 上开发和验证的原型，供迁移到 `vllm-ascend` 时当基线。

- 上游依据：PR [#63956](https://github.com/vllm-project/vllm/pull/63956)（merged 2026-11-05）
- 设计分析：`../../15-ShardQ特性解析与昇腾迁移评估.md`
- 目标：在本机证明「切分 + 元数据 + 交换语义」正确，真机只验 kernel 和通信

## 文件

| 文件 | 内容 |
| :-- | :-- |
| `shardq_ref.py` | zigzag 切分、触发判定、run 划分、positions、query_start_loc 重编号、参考交换、定长 pad、最小 sparse MLA 参考实现 |
| `test_shardq_ref.py` | 32 个单测，无 NPU / 无 vLLM 依赖 |

## 跑法

```bash
cd "wiki/vllm架构笔记/assets/shardq"
/Users/sunlei/code/dsh/vllm/.venv/bin/python -m pytest -q
```

## 已验证（2026-11-07）

```
32 passed in 0.91s
Python 3.12.14 / numpy 2.3.5 / torch 2.13.0
```

覆盖点：

| 性质 | 用例 |
| :-- | :-- |
| 切分覆盖全部 token、组内升序 | `test_zigzag_partitions_all_tokens` |
| 切分与纸上推导一致 | `test_zigzag_matches_known_layout` |
| token 数均衡（差 ≤ 1） | `test_zigzag_balances_token_count` |
| 因果工作量均衡（单请求 ratio < 1.01） | `test_zigzag_balances_causal_work` |
| 阈值 / 稀疏性 / 空 rank 回退 | `test_split_*` |
| decode token 不进分片 | `test_split_keeps_decode_tokens` |
| run 划分覆盖且每请求 ≤ 2 段 | `test_local_runs_*` |
| positions 与绝对位置一致 | `test_positions_match_absolute_offsets` |
| query_start_loc 重编号紧凑单调 | `test_renumber_query_start_loc_is_compact` |
| 交换 + 回写逐位还原 | `test_reference_exchange_round_trip` |
| 每个 head 块来自正确 rank | `test_exchange_delivers_all_head_blocks` |
| decode 逐位不变 | `test_exchange_preserves_decode_tokens_bitwise` |
| 定长 pad 形状与内容 | `test_pad_to_static` |
| 参考 sparse MLA 与因果注意力等价 | `test_ref_sparse_mla_*` |

## 与上游的对应关系

| 本原型 | 上游 |
| :-- | :-- |
| `zigzag_split` | 同名函数，公式逐行照搬 |
| `build_shardq_split` | 同名函数，输入改成显式数组 |
| `local_runs` | 上游 V4.1 草案里「token run 表达成伪请求」的等价物 |
| `compute_positions` | 上游 `positions = gather + seq_len - query_end` |
| `reference_shard_q` | 上游 `shard_q` 的集体语义（单进程版） |
| `reference_unshard_out` | 上游 `unshard_out` 的集体语义（单进程版） |
| `pad_to_static` | 昇腾侧新增：ACL graph / 等长 all-to-all |
| `RefSparseMla` | 无对应；上机对拍用的参考实现 |

## 还没做

1. 接 `CommonAttentionMetadata` 与 `split_decodes_and_prefills`（Step 1 剩余）；
2. 接进 `AscendDSAMetadataBuilder.build()`（Step 2）；
3. 多进程 gloo 版交换（验证集体语义，不只是单进程置换）；
4. 真机后端的契约守卫（head 数、对齐、`cu_seqlens`）。

## 移植到 vllm-ascend 时的注意

- `reference_*` 换成 HCCL 实现，**保持函数签名不变**，单测可以直接复用；
- 交换按定长 pad 设计（`pad_to_static`），避免变长 all-to-all 和 AllToAllV；
- 任何 host→device 的每步上传，都不要复用 pinned buffer（见上游 `#66052`）。
