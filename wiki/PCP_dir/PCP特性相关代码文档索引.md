# PCP 特性相关代码文档索引

> 定位：**代码指路**——给想研究 vLLM PCP（Prefill Context Parallelism，prefill 上下文并行）的初学者，
> 按"入口 → 配置 → 切分 → 通信 → 注意力 → 还原"的顺序带你看代码。
> 环境基线：vLLM v0.28.0。所有路径相对 `vllm-src/vllm/`，行号为实测核对的。
> 阅读前提：了解 MLA 注意力（见 `../vllm架构笔记/03-KV Cache 与注意力.md`）。

---

## 0. 30 秒总览

**PCP 解决什么**：超长请求的 prefill 是单点瓶颈（首 token 前要算完整段上下文）。
把一次长 prefill 的 token 序列**分到 N 个 rank 上并行计算**，摊薄 TTFT（time to first token）。

**一句话实现**（对应配置注释 `config/parallel.py:127`）：
> PCP expands the process world size **but does not increase the KV-cache shard count**
> （PCP 扩大进程数，但 KV cache 不分片——每 rank 持有完整 KV，只分 query 计算）

**核心机制**：把 prefill 序列按 **DualChunkSwap** 模式切成 `2×PCP` 块 → 每 rank 算自己那块的
Q/K/V → **all-gather 完整 KV** → 本地注意力 → **all-gather 输出 + 索引还原**成全局 batch。

```
┌─────────────────────────────────────────────────────────┐
│ 调用链主线                                               │
│  CLI --prefill-context-parallel-size                     │
│   → ParallelConfig (config/parallel.py:126)             │
│   → VllmConfig (config/vllm.py:620 校验: 仅 V2 runner)   │
│   → pcp 进程组 (distributed/parallel_state.py:1885)      │
│   → PCPManager 构建 (v1/worker/gpu/model_runner.py:563)  │
│   → 每步: partition_batch (model_runner.py:1301)         │
│       → pcp_manager.py:319 partition_batch              │
│       → pcp_manager.py:195 _get_rank_segments (切块)     │
│       → pcp_manager.py:252 _build_batch_layout (索引)    │
│   → 前向 (每 rank 本地计算)                              │
│       → attention/pcp.py:26 all_gather latent KV        │
│       → MLA 注意力 (use_pcp 标志贯穿)                    │
│   → 还原: restore_hidden_states (pcp_manager.py:608)    │
│       → model_runner.py:1745 采样前还原                  │
└─────────────────────────────────────────────────────────┘
```

---

## 1. 分层代码索引（速查表）

| 层 | 文件 | 关键符号（行号） | 看什么 |
|---|---|---|---|
| 配置 | `config/parallel.py` | `prefill_context_parallel_size`（126） | 字段定义、world size 计算（505） |
| 配置校验 | `config/vllm.py` | （620） | ⚠️ 仅 V2 model runner 支持 |
| 进程组 | `distributed/parallel_state.py` | `get_pcp_group()`（1445）、group 构建（1885） | pcp 组怎么形成 |
| 批次切分 | `v1/worker/gpu/pcp_manager.py` | `PCPManager`（37） | **核心文件**，见 §3 |
| Runner 集成 | `v1/worker/gpu/model_runner.py` | 构建（563）、partition（1301）、还原（1745） | PCP 挂在 V2 runner 的哪里 |
| KV 通信 | `model_executor/layers/attention/pcp.py` | `_gather_prefill_cache_inputs`（11）、`finalize_mla_pcp_decode`（83） | MLA 的 KV 交换与 decode 合并 |
| 注意力后端 | `v1/attention/backend.py` | `supports_pcp`（313, 407） | 哪些后端支持 PCP |
| MLA 集成 | `model_executor/layers/attention/mla_attention.py` | `use_pcp`（545）、decode 合并（975） | PCP 在 MLA forward 的开关 |
| 通信工具 | `v1/worker/cp_utils.py` | `check_attention_cp_compatibility`（22）等 | CP/DCP 通用工具（DCP 为主） |
| 文档 | `docs/serving/context_parallel_deployment.md` | 全文 | 设计动机、PCP/DCP 分工 |

---

## 2. 入口与配置（先看这里）

### 2.1 CLI 参数 → `ParallelConfig`

打开 `config/parallel.py`，看 **126 行**：

```python
prefill_context_parallel_size: int = Field(default=1, ge=1)
"""Number of ranks that split prefill sequence computation. PCP expands
the process world size but does not increase the KV-cache shard count."""
```

**学习要点**：
- 和邻居字段对比：`tensor_parallel_size`（切权重）、`data_parallel_size`（切 batch）、
  `decode_context_parallel_size`（切 KV cache 沿 T 维）——各自切什么、不切什么，是理解 PCP 的第一步
- 看 **505 行附近** world size 怎么把 PCP 乘进去
- 看 **524 行**：`PCP does not support data parallelism yet`——限制第一条

### 2.2 仅 V2 model runner 支持

打开 `config/vllm.py`，搜 **620 行**附近注释。`model_runner.py`（V2 runner）才有 `pcp_manager` 字段，
旧 V1 runner 没有——这是"为什么本地 CPU 用不了 PCP"的代码级答案（V1 runner + CPU）。

---

## 3. 核心文件：`v1/worker/gpu/pcp_manager.py`（682 行，精读）

### 3.1 类结构速览（先看方法清单建立地图）

```python
class RankSegment:                      # 27 行：一个"块"的元数据（全局哪段、本地哪段）
class PCPManager:                       # 37 行：主管理器
    validate_config                     # 125
    _reorder_segments                   # 164
    _get_rank_segments                  # 195  ★ 切块算法（见 3.2）
    _build_batch_layout                 # 252  ★ 索引构建（见 3.3）
    partition_batch                     # 319  ★ 入口：全局 batch → 本地块
    prepare_attn / prepare_slot_mappings # 545 / 560
    restore_hidden_states               # 608  ★ 输出还原（见 3.4）
    restore_for_sampling                # 614
```

### 3.2 `_get_rank_segments`（195 行）：DualChunkSwap 切块 ★

**先看 201-208 行的注释图**（PCP=4，一个序列切 8 块）：

```
full:  | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
rank 0:  0                           7
rank 1:      1                   6
rank 2:          2           5
rank 3:              3   4
```

再看代码逻辑（215-245 行）：
```python
num_chunks = 2 * self.pcp_world_size          # 每序列切 2×PCP 块
if is_prefilling:
    chunk_indices = (rank, num_chunks - 1 - rank)   # prefill：拿"第 rank 块"和"倒数第 rank 块"
else:
    chunk_indices = (0,)                            # decode：整条复制（decodes are replicated）
```

**学习要点**：
- 为什么 prefill 每 rank 拿**两块**（首尾配对）？——为 ring 式 KV 交换预留的结构（每 rank 两块，
  可以和相邻 rank 交换一次完成全部 KV 覆盖）。当前实现用 all-gather，但切块模式是 DualChunkSwap
- 为什么 decode 复制？——decode 只有 1 个 query token，但需要全量 KV；复制后每 rank 都能本地完成，
  最后 decode 输出用 `finalize_mla_pcp_decode` 按头合并（见 §5）

### 3.3 `_build_batch_layout`（252 行）：索引预计算 ★

**先读 273-280 行注释**（PCP=2 的完整例子，这是理解全文件的钥匙）：

```
#   global batch:       [A B C D E F G]
#   rank 0 / rank 1:    [A B G] / [C D E F]     ← 各自算的块
#   padded gathered:    [A B G _ | C D E F]     ← all-gather 后（含 padding 对齐）
#   hidden_restore_idx: [0, 1, 4, 5, 6, 7, 2]   ← gathered → global 的取数索引
#   padded_gather_idx:  [0, 1, 6, 0, 2, 3, 4, 5] ← global → padded 的取数索引
# 因此 global = gathered[hidden_restore_idx]
```

**学习要点**：两个索引数组每步前向**一次性建好**（281-310 行），之后纯查表——这是性能关键设计。
注意 `gathered_kv_write_mask`（306-310）：**decode 的 KV 写入只有 rank 0 做**（`rank != 0: continue`）。

### 3.4 `restore_hidden_states`（608 行）：输出还原 ★

```python
gathered = get_pcp_group().all_gather(hidden_states, dim=0)   # 各 rank 输出汇合（沿 token 维）
return gathered[self._hidden_restore_idx]                      # 查表还原全局顺序
```

配合 `model_runner.py:1745` 的 `maybe_restore_pcp_for_sampling`——采样前把全局视图还回去。

---

## 4. Runner 集成：`v1/worker/gpu/model_runner.py`

PCP 挂在 **V2 model runner** 的四个点（全文搜索 `pcp`）：

| 行号 | 调用 | 阶段 |
|---|---|---|
| 563 | `maybe_build_pcp_manager(...)` | 引擎初始化 |
| 1301 | `maybe_partition_pcp_batch(...)` | **每步前**：全局 batch → 本地块 |
| 1306 | `pcp_manager.prepare_attn(...)` | 本地块的 block_table/slot 准备 |
| 1745 | `maybe_restore_pcp_for_sampling(...)` | **采样前**：还原全局 batch |

**学习建议**：在 model_runner.py 里从 1301 行打断点，单步看一个长请求怎么被切成块、
每块的前向输入是什么——这是理解"PCP 做了什么"最直接的方式（需要 V2 runner + 多 GPU 环境）。

---

## 5. MLA 的 KV 交换：`model_executor/layers/attention/pcp.py`

| 行号 | 函数 | 作用 |
|---|---|---|
| 11 | `_gather_prefill_cache_inputs` | **prefill 前 all-gather latent KV**：`pcp_group.all_gather(tensor[num_decode_tokens:], dim=0)`（26 行） |
| 48 | `maybe_gather_mla_latent_cache_inputs` | 上层入口（decodes 部分本地 KV + prefill 部分 gather） |
| 83 | `finalize_mla_pcp_decode` | decode 输出合并：`all_gather(output, dim=1)`（88 行，按头维） |

**为什么 MLA 的 KV 交换小**：MLA cache 每 token 只存 576 维 latent（对比展开后 64 头 × 448），
PCP 的 all-gather 通信量天然小——MLA 和长上下文并行是绝配（DeepSeek/Kimi/GLM 场景）。

MLA forward 里 `use_pcp = prefill_context_parallel_size > 1`（`mla_attention.py:545`），
它控制 decode 的 q 组装（937）、输出合并（975）、padding（1020）等分支——搜索 `use_pcp` 看全貌。

---

## 6. 注意力后端支持（`v1/attention/backend.py`）

- `supports_pcp`（313 行）：后端类方法，默认查 impl 是否支持
- 选择器校验（407 行）：`if use_pcp and not cls.supports_pcp(): invalid_reasons.append("PCP not supported")`
- 元数据里 `pcp_world_size / pcp_rank`（911-912 行）

**含义**：不是所有 attention 后端都能跑 PCP——支持与否是后端的显式声明。

---

## 7. 学习路线（建议顺序 + checkpoint）

### 路线 A：概念建立（1-2 小时）
1. 读 `docs/serving/context_parallel_deployment.md`（了解 PCP/DCP 分工与动机）
2. 读 `config/parallel.py:120-140`（四个并行度字段对比）
3. 读 `pcp_manager.py:201-208` 注释图（DualChunkSwap 直觉）

### 路线 B：代码深潜（半天）
4. 精读 `pcp_manager.py`：`_get_rank_segments` → `_build_batch_layout` → `partition_batch` → `restore_hidden_states`
5. 对照 `model_runner.py:1301 → 1306 → 1745` 看挂载点
6. 读 `attention/pcp.py` 全文（~100 行，很短，一次读完）

### 路线 C：验证性练习
7. 手算一个 PCP=2、batch=[A(3 tokens) B(4 tokens)] 的例子，画出两个索引数组
8. 回答：为什么 decode 请求所有 rank 都处理？为什么 KV 写入只有 rank 0？

### Checkpoint（能答出 = 掌握）
- [ ] PCP 和 DCP 各切什么、不切什么？
- [ ] DualChunkSwap 的块分配规则是什么？
- [ ] `hidden_restore_idx` 是干嘛的？为什么能预计算？
- [ ] MLA 的 KV 交换为什么特别适合 PCP？
- [ ] 为什么本地 CPU 环境跑不了 PCP？（两个原因）

---

## 8. 限制与注意事项（代码证据）

| 限制 | 代码出处 |
|---|---|
| 仅 V2 model runner | `config/vllm.py:620` |
| 注意力后端需 `supports_pcp` | `v1/attention/backend.py:407` |
| 不支持投机解码 | `pcp_manager.py:323` "MRV2 PCP does not support spec decode yet" |
| 不支持数据并行 | `config/parallel.py:524` |
| decode 在所有 rank 复制 | `_get_rank_segments` 的 `chunk_indices=(0,)` |

> 本地调试提示：PCP 需要 V2 runner + 多 GPU，CPU 单机只能读代码。想动手验证调度逻辑，
> 可以单测 `PCPManager`（`tests/` 下搜 pcp 相关测试），或用小张量手动复现 `_build_batch_layout` 的索引计算。
