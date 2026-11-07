# 003 request_trace 设计复盘：从「算子级打点」到「系统级可观测」

> 对照《性能之巅》《BPF 之巅》复盘 request_trace 的设计，并把结论落成可执行的改造方向。
> 配套：`004-trace开销专题.md`（问题记录，暂不改）、`005-数据与展示分离.md`。

## 0. 元信息

- 日期：2026-11-07
- 对象：mxllm `feat/request-trace-main`（MR !146）
- 依据：`002-request-trace端到端与对齐.md` 的实测（31 行 stage_timings、StepID 对齐、
  2ms 步只有 71–73% on-CPU）
- 状态：设计文档；实现见同一 MR 的后续提交

## 1. 一句话结论

我们现在的 trace 能回答「**这一步花了多久**」，但回答不了「**为什么慢**」。
下一个版本的目标不是加更多打点，而是把观测对象从「算子执行」换成「**请求等待与资源争用**」，
同时把「数据可信度」和「开销」做成产品的一部分。

## 2. 从两本书提炼的六条

| # | 原则 | 出处 | 对我们的含义 |
| :-- | :-- | :-- | :-- |
| 1 | 观测手段有经济学：计数器 < 采样 < 追踪 | SP | 必须有 L0 计数器默认常开，trace 只在深挖时开 |
| 2 | on-CPU / off-CPU 是两种时间 | SP / BPF | 每个阶段要能区分「在算」和「在等」 |
| 3 | 追踪数据要有统一上下文（span） | SP / BPF | 从「日志行」升级成 `trace_id/span_id/parent` |
| 4 | 监控器本身也要被监控（USE 三问） | SP | dropped_events、coverage 必须可见 |
| 5 | 测量开销是一等指标 | SP / BPF | 开销未知的功能不能默认开 |
| 6 | 别犯反方法：路灯效应、把缺失当正常 | SP | 「测不到」要显式输出，不能悄悄跳过 |

## 3. 逐条复盘

### 3.1 观测手段经济学

vLLM 本来就有 `queue_time / prefill_time / decode_time` 三个直方图（`vllm/v1/metrics/loggers.py`），
我们却又用最贵的手段把同一件事测了一遍。

**改法**：三层。

```text
L0 counters   默认常开，纯内存自增，退出/定时落盘      （本次实现）
L1 metrics    按 step 聚合，记录 waiting/running/KV    （本次实现骨架）
L2 trace      逐事件日志 + StepID，深挖时开            （现状）
```

### 3.2 on-CPU / off-CPU

实测：`execute_model` 首步 261.9ms / 90.3% on-CPU；后续 2ms 步只有 **71–73%**。
纯 wall-clock 会把「被调度走」算成「计算慢」。

**改法**：每条事件附带线程 CPU 时钟 `time.thread_time_ns()`；
任意两个事件之间的 `Δcpu` 就是 on-CPU 时间，`Δwall − Δcpu` 就是 off-CPU。
这是本次实现的最小改动（一处 `safe_print` + parser），不改 953 行 namelist。

### 3.3 span 化数据模型

现在的模型是「带 RequestID/StepID 的文本行」，代价已经在 002 里全部出现：
RequestID 分裂、阶段配对靠手写元组、跨节点无法关联。

**改法（下一阶段）**：一行一个 span —— `trace_id, span_id, parent_id, name, start, end,
on_cpu, status, attrs`。阶段关系用父子表达，不再维护 `_STAGE_PAIRS`。
本次先保留行格式，只把 `on_cpu` 塞进去，避免一次改动过大。

### 3.4 监控器自身

| USE | 我们的对应物 | 现在 |
| :-- | :-- | :-- |
| Utilization | 每秒写入行数 | 不可见 |
| Saturation | 写阻塞 / 缓冲积压 | 不可见 |
| Errors | `execute_operation` 吞掉的异常 | 不可见 |

**改法**：`stats.py` 全局计数 `logged / dropped / dropped_reasons`，
退出时写 `trace_stats_<pid>.json`；parser 生成 `trace_health` sheet。

### 3.5 开销

`safe_print` 每次调用重建 logger + FileHandler + open 文件。这个问题**本次不改**，
单独记录在 `004-trace开销专题.md`，因为它会冲击实现机制，需要先测量再决策。

### 3.6 反方法

我们犯过两个：

- **路灯效应**：`execute_model` 测得很细，真正等待的 `waiting → running` 很粗。
- **把缺失当正常**：为了「31 行全 ok」把 entry-only 的 `missing-start` 直接跳过。

**改法**：保留行，但加 `coverage` 字段并在 health sheet 里显式统计，
而不是让行消失。

## 4. 重构：观测对象从「执行」转向「等待」

### 4.1 现在测错了什么

| 现在测的 | 值不值 |
| :-- | :-- |
| V2 execute_model outer / inner / model forward 三层边界 | 这是**算子执行效率**，属于另一个问题域 |
| `_update_states`、`_gather_mm_embeddings` | 太细，单次 <1ms，噪声大于信号 |
| `Prefill start/done execute_model` | 有用，但它只是「跑起来之后」 |

真正影响 TTFT/吞吐的是**跑起来之前**：排队、等 KV、等 P/D 传输、被驱逐。

### 4.2 应该回答的五个问题

1. 请求在 `waiting` 里等了多久？**为什么**等？
2. KV cache 什么时候吃紧？分配失败、驱逐、换入换出各花了多久？
3. 等待期间线程是 **on-CPU 忙等** 还是 **off-CPU 睡眠**？
4. 抢占发生了几次？恢复（重算 + 重新调度）代价多大？
5. 时间都去哪了：queue / prefill / transfer / decode 的占比。

### 4.3 请求状态机

```text
ARRIVED
  └─→ QUEUED ──┬─→ SCHEDULED(prefill chunk) ─→ PREFILL_DONE
               │                                   │
               │                                   ├─[P]→ KV_WAIT → TRANSFER → DECODE_READY
               │                                   └─[单机]→ DECODING
               └─→ PREEMPTED ─→ QUEUED
                                   DECODING → FINISHED
```

每个状态迁移是一个 span：

```text
state      from → to
start/end  单调时钟 ns
reason     NO_SLOT | KV_INSUFFICIENT | CHUNK_BUDGET | PRIORITY |
           PD_NOT_READY | KV_EVICT | NONE
snapshot   free_blocks / running / waiting / scheduled_tokens / apc_hit
on_cpu_ns  Δcpu（判断忙等还是睡眠）
```

### 4.4 每 step 的资源快照

在 `Scheduler.schedule` 退出时记录一次（现在已经有 `start_free_block_num`，扩成完整快照）：

```text
step_id, num_scheduled_tokens, num_running, num_waiting,
free_blocks_before/after, chunk_budget, apc_hit_tokens, preempted
```

有了这张表，「waiting 为什么长」可以直接归因：
`free_blocks` 持续走低 → KV 压力；`num_waiting` 高但 `running` 未满 → 预算/优先级问题。

### 4.5 KV cache 视角

| 指标 | 数据来源 |
| :-- | :-- |
| 分配失败次数/耗时 | `allocate_slots` 返回 None 的次数 |
| 驱逐次数 | block 被复用（`free_blocks` 不增但 cache 失效） |
| 换入换出耗时/字节 | `start_load_kv` / `done`，已有 `[KVTiming]`，补 bytes 与目标层 |
| 每请求峰值 blocks | `start_free_block_num - end_free_block_num` 的最大值 |

**注意**：`[KVTiming]` 已经存在，本轮不重写，只补齐 `bytes` 和层标识（HBM/CPU/Mooncake）。

### 4.6 CPU-off waiting

waiting 状态期间，线程通常阻塞在队列/事件上。用 §3.2 的 `Δcpu/Δwall` 直接判断：

```text
on_cpu_pct < 5%   → 真睡眠（正常）
on_cpu_pct > 50%  → 忙等 / 空转（问题）
```

这一类问题现在完全不可见，是我们和「系统级可观测」最大的差距。

### 4.7 与算子级观测分层

| 层 | 内容 | 默认 |
| :-- | :-- | :-- |
| 系统层 | 状态机、等待原因、KV、调度快照 | 开 |
| 模型层 | 一个 `model_forward` span（含 on_cpu） | 开 |
| 算子层 | V2 outer/inner/forward 三段、`_update_states` | `REQUEST_TRACE_DEEP=1` 才开 |

把现在默认打开的算子级打点降级成 deep 模式，是**减少**而不是增加开销。

## 5. 轻量计数器

### 5.1 三个计数器（L0，纯内存）

| 计数器 | 位置 | 代价 |
| :-- | :-- | :-- |
| `steps_total / tokens_total / scheduled_tokens` | `Scheduler.schedule` 出口 | 3 次整数加法 |
| `waiting_len / running_len` 的 max 与 hist | `add_request` / `schedule` | 2 次 len() |
| `kv_alloc_fail` | `allocate_slots` 返回 None | 1 次判断 |

每 10s 或退出时落一个 `metrics_<pid>.json`，不写逐事件日志。

### 5.2 默认策略

```text
REQUEST_TRACE_MODE = off | metrics | trace      （默认 off，保持回滚语义）
```

**建议**：`metrics` 实测开销 <1% 后，再把默认改成 `metrics`。
在 004 的死结解开之前，不擅自把默认打开——这是对「开销未知不能默认开」原则的遵守。

## 6. 数据可信度

`stage_timings` 增加三列：`on_cpu_ms / off_cpu_ms / on_cpu_pct`；
新增 `trace_health` sheet：

```text
metric                          value
files                           1
actions                         57
stats_logged                    57
stats_dropped                   0
stage:P: execute_model.coverage 100.0%
stage:D: token 1 to 2.coverage  50.0%
```

**coverage = ok 行 / (ok + missing) 行**。低于 100% 就是「这份 trace 不可全信」的信号。

## 7. 不做的事（本轮）

- 不改 `safe_print` 的写盘机制（004）。
- 不做可视化（005）。
- 不引入 OpenTelemetry SDK（等 span 模型定了再说）。

## 8. Roadmap

| 阶段 | 内容 | 状态 |
| :-- | :-- | :-- |
| P0 | on_cpu 列、dropped/coverage、metrics 模式骨架 | ✅ 本次完成（见 §9） |
| P1 | 状态机事件 + reason code | ✅ 状态机已实现（算子级降级待做） |
| P2 | span 模型 + 跨节点 trace_id | 待设计 |
| P3 | 数据/展示分离 + 瀑布图 | 见 005 |
| P4 | 开销治理 | 见 004 |


## 9. 实现记录（2026-11-07）

### 9.1 on_cpu_ns

实现只动了三处，**953 行 namelist 一行没改**：

- `safe_print` 在消息末尾追加 `; CPU:<time.thread_time_ns()>`（vDSO，~20ns）；
- `execute_operation` 失败时计数（§9.2）；
- parser 按 `(RequestID, StepID, Action)` 存一份 CPU 时钟，阶段行里做差。

实测（离线 chunked prefill，31 行 stage_timings）：

| 阶段 | 耗时 | OnCPU | OnCPU% |
| :-- | --: | --: | --: |
| 首个 `P: execute_model` | 267.5 ms | 241.7 ms | **90.3%** |
| 后续 chunk 步（~0.5–1.6ms） | — | — | **77–93%** |

**交叉验证**：002 里用 bpftrace `sched_switch` 独立算出的首步是 261.9ms / 90.3%。
两套完全独立的机制给出同一个比例，说明 `thread_time_ns` 这条链路可信。

### 9.2 dropped_events + coverage

`stats.py` 全局计数 `logged / dropped / reasons`，退出写 `trace_stats_<pid>.json`；
parser 读回并生成 `trace_health` sheet：

```text
files                          1
actions                        82
stats_logged                   97
stats_dropped                  0
stage:P: execute_model.coverage 100.0%
stage:P: running to schedule end.coverage 100.0%
```

### 9.3 metrics 模式

`REQUEST_TRACE_MODE=metrics`，只挂 3 个 target，纯整数自增：

```json
{"steps": 8, "scheduled_tokens": 17, "enqueued": 2, "kv_alloc_fail": 0,
 "max_waiting": 1, "max_running": 2, "min_free_blocks": 143, "steps_per_s": 33.35}
```

**默认仍是 `off`**：在 004 的开销结论出来之前不擅自改默认值。

### 9.4 回归

`tests/patch/platform/test_request_trace.py`：18 passed。

### 9.5 请求状态机（§4.3 的实现）

新增 `state_machine.py`，挂在 5 个已有 target 上（`add_request` / `allocate_slots` /
`schedule`×2 / `update_from_output`×2 / `_free_request`），没有新增被包装函数。

- `RUNNING` 按 `num_computed_tokens >= num_prompt_tokens` 拆成 `PREFILL` / `DECODING`；
- `WAITING` 在每次 `schedule()` 决策点重采样（其余时刻 100ms 节流），这样等待原因会随
  调度决策更新；
- `FINISHED` 在 `_free_request` 入口发出——等请求被移除后再扫描就看不到了。

实测（3 请求，长 prompt 走 chunked prefill）：

| Request | State | Reason | 时长 |
| :-- | :-- | :-- | --: |
| 0 | WAITING | NEW | 5.5 ms |
| 0 | PREFILL | — | 243.9 ms（on-CPU 96.5%） |
| 0 | DECODING | — | 25.4 ms |
| 1/2 | WAITING | NEW | 3–4 ms |
| 1/2 | WAITING | **CHUNK_BUDGET** | 244 ms（拆成多段） |
| 1/2 | DECODING | — | 25.5 ms |

`waiting_breakdown`：

```text
State   Reason        Intervals  Requests  Total(ms)  Max(ms)
WAITING CHUNK_BUDGET         10         2    487.811  229.120
WAITING NEW                   3         3     12.835    5.529
```

**一个反直觉的发现**：等待区间的 on-CPU 高达 97.6%。单线程引擎「等」的时候，
CPU 正在为别的请求干活。所以：

```text
waiting + on_cpu 高  → 容量饱和（正常排队，该加并发/加机器）
waiting + on_cpu 低  → 调度器/IO 问题（该查锁、查换入换出）
```

这正是 §4.6 想要的那一刀，现在有数据了。
