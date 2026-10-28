# 006 PrefixCache 插件详解

> 一句话：这是 AISBench 里**唯一能"指定缓存命中率造数据"**的组件。它先离线反解出"公共前缀该多长"并算出理论命中率，再在线用 Prometheus 差分算实际命中率，两者对账。
> 引入版本：2026-09-03（`v3.1-20260912-master` 起）；基线 `v3.1-20261013-master`。
> 源码：`plugins/prefix_cache/`（独立包，**不改 AISBench 核心逻辑**）。

## 1. 为什么需要它

vLLM 的 APC（Automatic Prefix Caching）命中率是**结果**，不是**输入**：你给什么 prompt，命中率就是多少，压测时不可控、不可复现、不可对比。

而评估"APC 到底省了多少 prefill"要求：

1. 输入长度、前缀长度、组数、发送顺序都是**已知量**；
2. 理论命中率能**离线算出来**；
3. 实际命中率能从服务端**采出来**（而不是靠客户端猜）。

插件就是干这三件事。它适用于验证：输入长度、公共前缀比例、Prefix Group、请求顺序、单入口多 DP 对命中率的影响。

## 2. 五个子命令

【文档】

| 命令 | 作用 | 连服务？ |
|---|---|---|
| `inspect` | 预览配置、理论命中率**可达区间**、长度分布；只做规划 | ❌ |
| `prepare` | 生成正式请求数据 + Manifest + 理论分析 | ❌ |
| `validate` | 校验已有产物是否被改/截断/换序 | ❌ |
| `run` | 探活 → reset → 按组逐 DP 预热 → AISBench 正式压测 → 采指标 | ✅ |
| `analyze` | 用两份 Prometheus 快照**离线复算**实际命中率 | ❌ |

流程：

```
GSM8K JSONL ─┐
Tokenizer  ──┼─> prepare ──> requests.jsonl / full.jsonl / manifest / analysis
Scenario   ──┘                     │
                                   ├─> run ──> AISBench perf (TTFT/TPOT/ITL)
                                   │        └─> Prometheus baseline/after 差分 ──> actual
                                   └─> analyze（用保存的 .prom 快照离线复算）
```

## 3. 安装

```bash
cd <ais-bench 仓库根>          # 含 setup.py、ais_bench/、plugins/

# 只造数据（inspect/prepare/validate/analyze）
pip3 install -e ./plugins/prefix_cache

# 要 run（在线压测）
pip3 install -e ./ --use-pep517
pip3 install -r requirements/api.txt
pip3 install -r requirements/extra.txt
```

验证：`ais-bench-prefix-cache --help`（连字符！等价 `python -m ais_bench_prefix_cache.cli --help`）。

## 4. 六条前置条件

【文档】

1. **Python ≥ 3.10**。
2. 可用的 AISBench 仓库与依赖。
3. **与目标服务一致的 tokenizer** —— 不一致会导致 token 长度、Block 边界、理论命中率全部偏。
4. **JSONL 语料** —— 每个非空行是 JSON 对象，含 `corpus.field` 指定字段（默认 `question`，即 GSM8K 格式）。
5. **正确的 `block_size`** —— 必须与服务端实际值一致（vLLM 默认 16，很多部署改成 128）。
6. **`run` 需要服务能力**：`/v1/completions`、`/metrics`、可选 `/reset_prefix_cache`；多 DP 还需 `X-data-parallel-rank` 定向路由 + 带 `engine` 标签的分 DP 指标。

## 5. 数据模型：一条请求由三段拼成

```
[ 公共前缀 P（同一 Prefix Group 内完全相同） ][ 唯一 seed S ][ 自然文本后缀 N ]
 |<---------- 可被缓存命中 ---------->|<-- 必 miss -->|<-- 必 miss -->|
```

- **P（canonical prefix）**：每个 Group 独立生成，长度由求解器反解。
- **S（seed）**：`seed_blocks × block_size` 个 token，**全局唯一**，防止公共前缀结束后继续误共享（否则两个请求在 P 之后碰巧相同的 token 也会命中，理论值就不准了）。
- **N（natural suffix）**：从 `corpus` 里按 seed 随机选的文本，拼接填充到目标输入长度。

约束：

```
P_max = floor((input_length - minimum_non_shared_length) / block_size) × block_size
```

`minimum_non_shared_length` 默认 = seed 长度；不能小于 seed 长度。

**这解释了为什么"128K 输入 + 90% 命中"里只有约 10% 是 GSM8K 原文**：P 才是主体，N 只是尾巴。这一点在 007 篇会重点提醒。

## 6. Scenario 配置（分组速查）

完整逐字段见 `plugins/prefix_cache/config_examples/scenario.example.md`（53 KB）。这里只列**改得上**的。Scenario 采用**严格白名单**：写了不存在的字段直接被拒。

### 6.1 `run` / `tokenizer` / `corpus`

| 字段 | 默认 | 说明 |
|---|---|---|
| `run.run_id` | — | 任务名，执行时自动追加 `_YYYYMMDD_HHMMSS` |
| `run.random_seed` | — | 全局种子：语料选择、长度采样、组分配、顺序、seed 全由它决定 |
| `run.output_dir` | — | 产物根目录，同样追加时间戳 |
| `run.overwrite` | `false` | 重建用 `prepare --overwrite`（只覆盖本次时间戳内该 run 的四个文件） |
| `tokenizer.path` | — | 传 `AutoTokenizer.from_pretrained`，**必须与服务端一致** |
| `tokenizer.block_size` | — | **必须与服务端一致** |
| `tokenizer.revision` | `null` | 固定 tokenizer 版本 |
| `tokenizer.trust_remote_code` | `false` | |
| `corpus.path` | — | JSONL 路径 |
| `corpus.field` | `question` | 只用这个字段，不拼 answer |
| `corpus.selection.mode` | `random` | `random`（按种子打乱）/ `indices`（零基行号）/ `question_sha256`（按问题哈希选）/ `mixed` |

### 6.2 `requests`：长度分布

输入 `requests.input_length`：

| mode | 参数 | 说明 |
|---|---|---|
| `fixed` | `value` | 固定长度（默认 1024） |
| `explicit` | `values[]` | 逐条显式，元素数 = 请求数 |
| `range` | `ranges[{min,max,count}]` | 闭区间采样，各 `count` 之和 = 请求数 |
| `truncated_normal` | `min/max/mean/std` | 截断正态 |
| `csv` | `path` | 列名 `input_prompt_tokens` / `content_tokens` / `input_tokens` 之一 |

输出 `requests.output_length`：`fixed` / `uniform` / `truncated_normal` / `csv`（列名必须是 `output_tokens`）。该值写进 requests 的 `max_tokens`。

### 6.3 `prefix_cache`：核心

| 字段 | 默认 | 说明 |
|---|---|---|
| `mode` | `warmup` | `cold` / `warmup`（见 §8） |
| `target_hit_rate` | — | 期望的**全局 token 加权**命中率，`[0,1]` |
| `seed_blocks` | `1` | seed 占几个 Block；seed 长度 = `seed_blocks × block_size` |
| `minimum_non_shared_length` | = seed 长度 | 每条请求至少保留的非共享 token 数 |
| `groups.count` | `1` | Prefix Group 总数，生成 `group-0`…`group-(n-1)` |
| `groups.assignment.mode` | `uniform` | `uniform` / `zipf`（`exponent`，越大越集中）/ `weights`（`weights[]`，和 `count` 等长） |
| `groups.overrides.group-N.*` | `{}` | 单组独立覆盖 `input_length` / `output_length` / `corpus_selection` |
| `order.strategy` | `interleave` | `sequential` / `within_group_shuffle` / `interleave` / `global_shuffle` / `input_len_asc` |

> `cold` + `input_len_asc` = 模拟"无预热、请求由短到长逐步建立缓存"的经典场景。

### 6.4 `service` / `validation` / `aisbench`

| 字段 | 说明 |
|---|---|
| `service.inference_url` | text 模式用 `/v1/completions`；mm 模式必须 `/v1/chat/completions` |
| `service.metrics_url` | Prometheus `/metrics` |
| `service.reset_url` | `/reset_prefix_cache`；为空或失败时只有 `assume_empty_cache=true` 才继续 |
| `service.model` | 请求体里的模型名 |
| `service.dp_size` | 默认 2；**必须与线上 DP 数一致**（影响 warmup 计划和逐 DP 校验） |
| `service.engine_label_map` | Prometheus `engine` 标签 → DP rank 的显式映射；不配则尝试解析标签尾号 |
| `service.poll_interval_seconds` | 压测期间 KV 采样间隔，默认 5.0；`0` 关闭（baseline/after 仍采） |
| `service.api_key` | 不明文落盘，Manifest 里只有 `api_key_configured: true` |
| `validation.target_warning_pp` | 理论值偏离目标的告警阈值，默认 1.0 pp |
| `validation.actual_warning_pp` | 实际值偏离理论值的告警阈值，默认 5.0 pp |
| `aisbench.config` | AISBench Python 配置模板，默认 `./plugins/prefix_cache/config_examples/prefix_cache_perf.py` |
| `aisbench.work_dir` | AISBench 结果目录，默认 `./outputs/default` |
| `aisbench.extra_args` | 附加 CLI，如 `{"--num-warmups": 0}` |
| `aisbench.dataset` | `input_columns` / `output_column` / `prompt_template` **三个数据契约字段必须保持示例值**，只有 `abbr` / `pred_role` 可改 |
| `aisbench.model` | `attr` 只能是 `"service"`；`stream` 默认 `true` |

## 7. 命中率：怎么算、能不能达到

### 7.1 定义

**全局 token 加权**：`命中率 = 命中 token 总数 / 输入 token 总数`。不是请求数口径。

### 7.2 可达区间

求解器在 `inspect` 阶段同时算出：

- 全局 `reachable_min` / `reachable_max`
- 每个 Group 的 `reachable_min` / `reachable_max`
- `target_reachable`（目标是否落在区间内）
- `requested` / `effective` / `theoretical` 三档命中率

目标超出区间时，求解器**不报错**，而是取边界命中量（`effective`），并记 `TARGET_UNREACHABLE` 告警。目标在区间内时，按 Block 单位取**最近可达**值。

### 7.3 规划算法（按场景自动选路）

【文档】设 `N` = 请求数，`cap_i` = 第 i 条请求可用的 Prefix Block 数，`T` = 全部 prompt 的输入 token 总数：

| 条件 | 路径 | 复杂度 |
|---|---|---|
| `warmup` | 按累计输入比例分配 | `O(N)`，精确命中 Block 对齐后的目标 |
| `cold` 且 `256 × Σ(cap_i+1) ≤ 2,000,000` | 受限 beam search（≤256 状态） | 无精确解时继续走 scalable |
| `cold`、超阈值或 beam 无解 | scalable lane 构造（lane 内容量非递减） | `O(N log N)` 时间、`O(N)` 空间 |
| `cold`、前提不满足或分配失败 | exact lane fallback | 保证最终 hit token 精确，`trajectory.issues` 记原因 |

`prepare` 端到端约 `O(T + N log N)`，实际墙钟取决于 tokenizer、CPU、磁盘、prompt 总长。

### 7.4 一个必须自己算的约束【推算】

因为**每个 Group 的第一条请求必然全 miss**（缓存是空的），均匀分配时：

```
可达命中率 ≈ (P / input_length) × (n−1)/n        n = 每組请求数
```

代入 `input_length = 128K`、`block = 16`（`P_max = 131056`）：

- 每組 10 条：上限 ≈ 89.96% → **90% 不可达**
- 每組 11 条：上限 ≈ 90.9% → 刚好够
- 每組 20 条：上限 ≈ 95.0% → 舒适

**24 组 × 11 = 264 是 90% 的理论下限；推荐 24 组 × 20 = 480。** 这条不是文档写的，是按"首条必 miss"推的，必须用 `inspect` 验证。

> ⚠️ **适用范围（2026-10-28 补）**：上面这个 `(n−1)/n` 是 **`cold` 模式**的账，前提是"缓存从空开始"。
> `warmup`（默认模式）会先把每组前缀预热好，之后每条都命中，上限回到 `P/input_length`
> —— 实测 1K/24 组/每组 2 条：warmup 0.9001，cold 只有 0.4922。见 [009](009-实测-1K-90%-24组.md)。

### 7.5 另一个偏差来源

`trajectory.status` 可能是 `BEST_EFFORT`：请求长度突增、容量约束、不适合比例分配时，**累计命中率仍可能回落或超调**。此时只告警（`TRAJECTORY_BEST_EFFORT`），不改退出码。文档明确不承诺所有顺序都严格单调。

## 8. `warmup` vs `cold`

| | `warmup`（默认） | `cold` |
|---|---|---|
| 缓存起点 | 逐 `Group × DP` 先预热好 | 每个 `(group, dp)` lane 从零水位开始 |
| 预热请求 | 写进 `manifest.warmup.plan`，**不计入** requests/统计 | 无 |
| 全局理论命中率 | 有效 | 有效 |
| 分 DP 理论值 | 主要展示实际值 | 可输出严格分 DP 理论值 |
| 复现性 | 高（缓存状态被构造出来） | 依赖顺序与淘汰，较难 |
| 成本 | 预热 = `groups × dp_size` 次长 prefill | 无额外成本 |

**warmup 的请求不进正式指标**，这是设计意图：如果计入，正式结果就混进了准备阶段成本。

## 9. 理论 vs 实际：两边怎么对账

- **理论**：`prepare` 离线算，写进 `manifest.prefix_cache.theoretical_hit_rate`。
- **实际**：`run` 在正式请求前后各抓一次 `/metrics` 全文，用 `after − baseline` 的 `queries` / `hits` 计数器增量算出。

```bash
# 手工版（正常 run 会自动做）
curl -fsS "$METRICS_URL" -o baseline.prom     # 第一条正式请求前
# ... 压测 ...
curl -fsS "$METRICS_URL" -o after.prom        # 最后一条完成后立刻
```

⚠️ 两份快照必须来自**同一服务进程**、覆盖**全部 DP rank**（多 DP 要保留 `engine` 标签），且 `after` 的累计值不得小于 `baseline`。

- **KV 采样**：`run` 期间按 `poll_interval_seconds` 轮询 KV 用量（瞬时 gauge，跑完会归零，所以必须跑中采）。峰值/均值写进 `actual.by_dp.*.kv_cache_usage_peak/avg`。
- **离线复算**：`analyze --manifest ... --baseline x.prom --after y.prom`。

## 10. 产物四件套

```
outputs/<run_id>_<ts>/
├── log/
│   ├── <run_id>_<ts>.inspect.log
│   ├── <run_id>_<ts>.prepare.log
│   ├── <run_id>_<ts>.validate.log
│   └── <run_id>_<ts>.run.log
└── result/
    ├── <run_id>_<ts>.full.jsonl       # 全审计：组、lane、长度、前缀、seed、理论水位
    ├── <run_id>_<ts>.requests.jsonl   # 最小请求：question + answer(=none) + 可选 max_tokens
    ├── <run_id>_<ts>.manifest.json    # 复现入口：配置、哈希、tokenizer 指纹、可达区间、warmup 计划
    └── <run_id>_<ts>.analysis.json    # requested/effective/theoretical/actual + 偏差 + warnings
```

`full.jsonl` 关键字段（定位"命中率为什么不对"时看这些）：

| 字段 | 用途 |
|---|---|
| `group_id` / `occurrence_index_within_group` | 第几组第几条 |
| `dp_rank` / `lane_sequence` | cold 模式的 DP 路由与 lane 序号（warmup 为 null） |
| `target_input_tokens` / `actual_input_tokens` | 配置值 vs tokenizer 重编码后的真实值（**两者不等就说明 tokenizer 或模板有问题**） |
| `shared_prefix_tokens` / `seed_tokens` / `natural_suffix_tokens` | 三段各占多少 |
| `watermark_before` / `watermark_after` | 请求前后该 lane 的理论缓存水位 |
| `theoretical_hit_tokens` / `theoretical_hit_rate` | 单条请求的理论命中 |
| `collision_status` | seed 唯一性检查，正常是 `pass` |

`requests.jsonl` 只有三个字段：`question`（完整 prompt）、`answer`（固定 `"none"`）、可选 `max_tokens`/`output_tokens`。**所以它不能拿去做精度评测。**

## 11. 告警与退出码

| 状态 | 触发条件 | 影响退出码 |
|---|---|---|
| `TARGET_UNREACHABLE` | 目标超出可达区间 | ❌ 只告警 |
| `TARGET_DEVIATION` | 理论值偏离目标 > `target_warning_pp` | ❌ 只告警 |
| `TRAJECTORY_BEST_EFFORT` | 顺序/容量导致轨迹不平滑 | ❌ 只告警 |
| `ACTUAL_DEVIATION` | 实际值偏离理论值 > `actual_warning_pp` | ❌ 只告警 |
| 配置错误 / 产物损坏 / 服务能力不足 / AISBench 执行失败 | — | ✅ **非零** |

即：**命中率不达标永远不算失败**，只有"跑不起来"才失败。判断实验是否有效得自己看 `analysis.json`。

## 12. 边界与限制

1. **只支持一个 HTTP 入口背后的单 DP 或多 DP**，不支持多个彼此独立的 vLLM 实例编排。
2. **text 模式只走 `/v1/completions`**；mm 模式才用 chat completions。
3. `answer` 固定 `"none"` → **不能做精度**。
4. 插件 warmup 与 AISBench 自带 `--num-warmups` 是**两套**机制；要 baseline 后只含正式请求，必须 `"--num-warmups": 0`。
5. `aisbench.model.stream=false` 时仍能算命中率，但**没有完整 TTFT/TPOT/ITL**。
6. 多 DP 依赖 `X-data-parallel-rank` 与 `engine` 标签，缺了就只能按单 DP 处理。
7. 大场景（如 24 组 × 128K）规划走 scalable lane，`prepare` 时间与内存都随 `N × input_length` 线性涨。

## 13. 待确认

- [ ] `groups.count` 是否有上限（文档没写，只有 `requests.count` 要求正整数）。
- [ ] `cold` 模式下 `dp_rank` 的 round-robin 是否按组内出现顺序严格轮转（文档说"按组内出现顺序 round-robin"，但 DP 数不整除组内请求数时的余数处理没写）。
- [ ] vLLM 之外的引擎（SGLang / TensorRT-LLM）能否复用——文档只提 vLLM 的 `queries/hits` 指标名。
