# 16 ShardQ Step 2b 实现规格（交给内网 agent 直接执行）

> 给执行者的话：**按 §4 的清单逐项改，不要重构无关代码，不要改上游 vLLM。**
> 每完成一项就跑 §8 对应的测试。卡住了先看 §9，那里列的全是真实踩过的坑。
> 本文档之外的"优化想法"一律不要做。

## 0. 元信息

- 日期：2026-11-07
- 前置：Step 0–3 已完成，代码在 `vllm-ascend` worktree `tmp/va-shardq`（分支 `feat/shardq`，提交 `8edb38678`）
- 上游参考：vLLM PR #63956（`vllm/v1/attention/ops/shardq.py`）
- 背景分析：`15-ShardQ特性解析与昇腾迁移评估.md`
- 目标读者：内网 agent（需要逐条可执行，不接受"自行设计"）

## 1. 目标

当前 ShardQ 只计算布局、不改执行（attention 仍按 head 分片）。
Step 2b 让 **prefill** 真正按 token 分片：

```
q [T, H/tp, D]
  → all_to_all（换成本 rank 的 token + 全 head）
  → sparse MLA（全 head，KV 复制）
  → all_to_all（把各 head 块送回各 rank）
  → out [T, H/tp, D_v]
```

decode token 全程保持 head 分片、不参与交换。

## 2. 明确不做

1. 不改 decode 路径；
2. 不改 KV cache 布局（MLA 的 KV 在 TP 下本来就是复制的）；
3. 不改 indexer kernel，只改喂给它的 query 子集；
4. 不引入新依赖、不改上游 vllm；
5. 不做性能调优（Step 5 才做）。

## 3. 现状（已存在，直接复用）

| 位置 | 内容 |
| :-- | :-- |
| `vllm_ascend/attention/shardq.py` | `zigzag_split`、`build_shardq_split`、`local_runs`、`compute_positions`、`renumber_query_start_loc`、`plan_exchange`、`static_shard_q`、`static_unshard_out`、`pad_to_static` |
| `vllm_ascend/attention/dsa_v1.py` | `_maybe_build_shardq_split()` 产出 `metadata.shardq_split`（当前**没人用**） |
| `vllm_ascend/envs.py` | `VLLM_ASCEND_SPARSE_MLA_SHARD_Q`（默认 0）、`..._MIN_TOKENS`（默认 1024） |
| `tests/ut/attention/test_shardq.py` | 40 个布局/交换单测 |

## 4. 改动清单

### 4.1 `vllm_ascend/attention/shardq.py`：新增 3 个函数

1. `validate_split(split, num_decode_tokens, num_prefill_tokens, world) -> None`
2. `build_local_run_metadata(split, rank, query_lens, seq_lens, num_decodes) -> LocalRunMetadata`
3. `token_shard_prefill(q, split, plan, rank, *, run_sparse_mla, all_to_all=None, decode_out=None) -> torch.Tensor`

### 4.2 `vllm_ascend/attention/dsa_v1.py`：加一个分支

在 `AscendDSAMetadataBuilder` 已有的 attention 调用点（DSV4 indexer/attention 的
prefill 分支）加：

```python
if metadata.shardq_split is not None:
    out = token_shard_prefill(...)   # 见 §6.2
else:
    out = <原有路径>
```

**只加这一个分支，其他行不要动。**

### 4.3 `tests/ut/attention/test_shardq_token_shard.py`：新增测试

骨架已放在 worktree 里（未实现时自动 skip）。实现完成后 skip 自动消失。

## 5. 函数规格

### 5.1 `validate_split`

```python
def validate_split(
    split: ShardQSplit,
    *,
    num_decode_tokens: int,
    num_prefill_tokens: int,
    world: int,
) -> None:
    """不满足就 raise ValueError，不要 assert（生产代码里 assert 会被 -O 掉）。"""
```

必须检查（8 条）：

1. `split.world == world`
2. `split.num_decode_tokens == num_decode_tokens`
3. `split.num_split_tokens == num_prefill_tokens`
4. `(split.num_tokens_per_rank > 0).all()`
5. `split.token_ids` 无重复
6. `split.token_ids` 全部落在 `[0, num_prefill_tokens)`
7. `split.token_ids` 组内升序（每个 rank 的切片）
8. `split.num_tokens_per_rank.sum() == num_prefill_tokens`

### 5.2 `build_local_run_metadata`

```python
@dataclass(frozen=True)
class LocalRunMetadata:
    run_query_lens: np.ndarray   # [num_runs] int64，每个 run 的 query 长度
    run_seq_lens: np.ndarray     # [num_runs] int64，每个 run 最后一个 token 的可见 KV 长度
    run_req_idx: np.ndarray      # [num_runs] int64，父请求下标（prefill 内，0 起）
    token_ids: np.ndarray        # [T_rank] int64，本 rank 的 token（升序）
    positions: np.ndarray        # [T_rank] int64，每个 token 的绝对位置
```

实现步骤（**严格按顺序**）：

1. `runs = local_runs(split, rank, query_lens, num_decodes=num_decodes)`
2. `token_ids = split.local_token_ids(rank)`
3. `positions = compute_positions(split, rank, query_lens, seq_lens, num_decodes=num_decodes)`
4. `run_query_lens = [len(run) for run in runs]`
5. `run_req_idx = [run.req for run in runs]`
6. `run_seq_lens[i] = positions[run.stop - 1] + 1`

第 6 步是关键：**chunked prefill 下，run 的因果上界是它最后一个 token 的位置 + 1，
不是请求的 seq_len**。用 `seq_lens[req]` 会算多了。

不变量（函数末尾 `validate`）：

- `run_query_lens.sum() == token_ids.size`
- `len(positions) == token_ids.size`
- `run_seq_lens >= run_query_lens`（每个 run 至少能看见自己）
- `run_req_idx` 单调不减
- 同一个 `run_req_idx` 最多出现 2 次（zigzag 的早晚两段）

### 5.3 `token_shard_prefill`

```python
def token_shard_prefill(
    q: torch.Tensor,                 # [T, H_local, D]，T 含 decode 前缀
    split: ShardQSplit,
    plan: ExchangePlan,
    rank: int,
    *,
    query_lens: np.ndarray,          # [num_reqs] 本步每个请求新算的 token 数
    seq_lens: np.ndarray,            # [num_reqs] 本步步末的 seq_len
    num_decodes: int,                # 本步 decode 请求数
    run_sparse_mla: Callable[[torch.Tensor, LocalRunMetadata], torch.Tensor],
    all_to_all: Callable[[torch.Tensor], torch.Tensor] | None = None,
    decode_out: torch.Tensor | None = None,   # [num_decode, H_local, D_v]，None 表示等于 q 的 decode 部分
) -> torch.Tensor:                   # [T, H_local, D_v]
```

实现步骤（**7 步，顺序不能变**）：

1. `validate_split(split, num_decode_tokens=split.num_decode_tokens, num_prefill_tokens=split.num_split_tokens, world=split.world)`
2. `decode_q, local_q = static_shard_q(q, split, plan, rank, all_to_all=all_to_all)`
   - `local_q: [T_rank, world*H, D]`
3. `meta = build_local_run_metadata(split, rank, query_lens, seq_lens, num_decodes)` ——
   `query_lens/seq_lens` 从 `split` 反推不出来，**必须作为参数传进来**（见下方签名修订）
4. `local_out = run_sparse_mla(local_q, meta)` → `[T_rank, world*H, D_v]`
5. `sends = static_unshard_out(local_out, split, plan, rank, all_to_all=all_to_all)`
6. `out = q.new_zeros((T, H_local, D_v))`；`out[:nd] = decode_out if decode_out is not None else decode_q[..., :D_v]`
7. `for peer, (rows, block) in sends.items(): out[rows] = block`；返回 `out`

> 为什么需要 `query_lens/seq_lens`：`split` 里只有 token id，没有请求边界，
> 算不出 run 的划分和因果上界。

## 6. 伪代码

### 6.1 布局侧（已实现，仅示意）

```
def zigzag_split(lens, world):
    chunk_id = ((pos+1)*2*world - 1) // len_of_req
    owner = min(chunk_id, 2*world-1-chunk_id)
    return stable_sort_by(owner), bincount(owner)
```

### 6.2 执行侧（Step 2b 要写的）

```
token_shard_prefill(q, split, plan, rank, query_lens, seq_lens, num_decodes, run_sparse_mla):
    validate_split(...)

    # 1) Q 换布局：每个 peer 拿到它自己的 token，带全部 head
    decode_q, local_q = static_shard_q(q, split, plan, rank)

    # 2) 本 rank 的 token 变成「伪请求」（每个 run 一条）
    meta = build_local_run_metadata(...)

    # 3) 全 head 跑 sparse MLA（KV 复制，不需要额外通信）
    local_out = run_sparse_mla(local_q, meta)

    # 4) 按 head 块寄回各 peer，再落回全局 token 顺序
    sends = static_unshard_out(local_out, split, plan, rank)
    out = zeros([T, H_local, D_v])
    out[:nd] = decode_q
    for peer, (rows, block) in sends.items():
        out[rows] = block
    return out
```

### 6.3 builder 侧接入

```
# dsa_v1.py，attention 调用点
if metadata.shardq_split is not None:
    out = token_shard_prefill(
        q,
        metadata.shardq_split,
        self._shardq_plan,          # 在 __init__ 里用 plan_exchange 建一次
        rank=get_tp_group().rank_in_group,
        query_lens=...,             # 本步的 query_start_loc_cpu.diff()
        seq_lens=...,               # 本步的 seq_lens
        num_decodes=metadata.num_decodes,
        run_sparse_mla=self._run_sparse_mla_prefill,
    )
else:
    out = <原有代码>
```

`_run_sparse_mla_prefill` 是包装函数：把 `LocalRunMetadata` 翻译成
`sparse_flash_mla` 的 kwargs（`cu_seqlens_q` = run_query_lens 的 cumsum，
`seqused_k` = run_seq_lens，`block_table` = 父请求的 block table 按 run 展开）。
**这一步的字段名以内网环境的 CANN 算子签名为准，先用 `inspect.signature` 打出来再写。**

## 7. 与厂商算子的边界

- 本机只能测「喂进去的 metadata 对不对」，测不了算子；
- `run_sparse_mla` 注入的意义：单测里替换成 `lambda q, meta: q` 就能验证整条管线；
- 真机实现必须单独写一个 adpater，并加 `inspect.signature` 打印做一次人工核对。

## 8. 测试清单

放在 `tests/ut/attention/test_shardq_token_shard.py`，全部 CPU、无 NPU。

| # | 用例 | 输入 | 期望 |
| :-- | :-- | :-- | :-- |
| 1 | `test_round_trip_identity_op` | world=4，3 个请求 65/300/7000 | `run_sparse_mla = lambda q, m: q` 时，输出 == 输入 `q`（逐位） |
| 2 | `test_decode_tokens_untouched` | num_decodes=2 | 输出的前 2 行与输入逐位相等 |
| 3 | `test_padding_not_leaked` | 连跑两次不同 split | 第二次结果里不含第一次的残留（pad 位必须是 0） |
| 4 | `test_exchange_shape_is_static` | 注入 all_to_all 记录形状 | 每次调用形状都是 `[world, plan.max_local_tokens, H, D]` |
| 5 | `test_run_metadata_query_lens_sum` | 任意 split | `run_query_lens.sum() == T_rank` |
| 6 | `test_run_metadata_seq_lens_use_last_position` | 构造 chunked prefill（seq_len > query_len） | `run_seq_lens[i] == positions[run.stop-1]+1`，**不是** `seq_lens[req]` |
| 7 | `test_validate_split_rejects` | 参数化 8 种坏输入 | 每种都 `pytest.raises(ValueError)` |
| 8 | `test_single_rank_noop` | world=1 | `split` 为 None 时 `token_shard_prefill` 不被调用（在 builder 层测） |

## 9. 坑清单（真实踩过，逐条检查）

1. **`seq_len` 重复计数**：vLLM 这个版本的 `schedule()` 已经把本步 token 记进
   `num_computed_tokens`，`base + n` 会翻倍（实测 9811 vs 真实 6003）。
   本规划里所有 seq_len 都是**步末值**。
2. **run 的因果上界不是 `seq_lens[req]`**：chunked prefill 下要用
   `positions[run.stop-1] + 1`（见 §5.2 第 6 步）。
3. **head 顺序是 rank-major**：`local_q[:, r*H:(r+1)*H]` 属于 rank r，
   写反了数值能跑但结果错。
4. **空 rank 必须提前回退**：`build_shardq_split` 已处理，但下游还要再 `validate` 一次。
5. **静态 buffer 必须每步清零**：pad 位如果留上一步的垃圾，kernel 会把它当真实 token 算。
6. **all_to_all 用 uint8 view**：fp8 等 dtype 不一定被 HCCL 支持；交换只搬字节。
7. **不要复用 pinned host buffer**：上游 `#66052` 的竞态就是复用导致的；
   每步新建 host 数组 + `async_tensor_h2d`。
8. **数值不逐位一致**：全 head 归约顺序变了，只能用功能测试（检索/生成），
   不能拿 logprob 对拍。

## 10. 验收标准

1. `test_shardq.py` 40 个用例全绿；
2. 新文件 8 个用例全绿；
3. `tests/ut/attention/` 全量不回归（基线 1899 passed / 10 skipped）；
4. `ruff check` + `ruff format --check` 通过；
5. `VLLM_ASCEND_SPARSE_MLA_SHARD_Q=0` 时**逐位 no-op**（同一输入两次输出完全一致）。

## 11. 回滚

- 代码层：环境变量默认 0，自动走原路径；
- 若已开 1 出问题：设置 `VLLM_ASCEND_SPARSE_MLA_SHARD_Q=0` 即可，无需回滚代码。
