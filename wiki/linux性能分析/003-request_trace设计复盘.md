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
| P1 | KV 视角（驱逐/峰值/换入换出） | 🟡 驱逐与峰值已实现；换入换出 timing 已有，bytes/层待补（§9.7） |
| P1 | 算子级打点降级到 deep 模式 | ✅ 已实现（§9.8） |
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

### 9.6 KV 视角（§4.5 的实现）

新增 `kv_stats.py`，挂在四个位置：

| 位置 | 采集 |
| :-- | :-- |
| `BlockPool._maybe_evict_cached_block` | 驱逐计数（块被复用时） |
| `KVCacheManager.allocate_slots` | 分配失败计数 |
| `Scheduler.schedule` 出口 | 每步 `free / usage / running / waiting` 时间序列 |
| `Scheduler._free_request` 入口 | 每请求峰值 blocks、prefill 次数、抢占次数 |

产出：`kv_series`（步级时间序列 + 驱逐/失败增量）、`kv_requests`（每请求峰值）、
`trace_health` 里的 `kv:*` 汇总。

**压力实测**（KV 128MB，8 请求 × 201 prompt + 64 output）：

```text
kv:evictions   4        kv:alloc_fail  61
kv:min_free    0        kv:max_usage   1.0

State   Reason            Intervals  Requests  Total(ms)  Max(ms)
WAITING CHUNK_BUDGET             38         7   2366.938  302.771
WAITING KV_INSUFFICIENT          52         1    655.714   59.803
WAITING NEW                       8         8     92.483   16.157
```

两个结论：

1. **原因是有优先级的**：8 个请求里只有 1 个被归因为 `KV_INSUFFICIENT`，其余 7 个是
   `CHUNK_BUDGET`——它们根本没轮到分配 KV，是被 token 预算挡住的。如果只看「KV 用满」
   就会误判，必须看每个请求在**哪一步、因为什么**被拒。
2. **峰值 blocks 是近似值**：用 `ceil(num_computed_tokens / block_size)` 算，不依赖
   vLLM 内部结构，代价是忽略 block 对齐误差（实测每请求 3 blocks，201 prompt tokens）。

`kv_requests` 还显示 8 个请求里有 4 个 `Preemptions=1`——KV 压力下驱逐→重排队是真实发生的，
这条链路现在可以从「等待原因」一路追到「抢占次数」。

### 9.7 换入换出：先纠正 9.6 的说法

**timing 其实早就接了**，缺的是 bytes 和层标识。已有（`request_logger_namelist.yml`）：

| 位置 | 产出 |
| :-- | :-- |
| `AscendStoreConnector.start_load_kv` | `[KVTiming] P_ascend_store_load_kv_ms` / `D_...` |
| `KVCacheRecvingThread._transfer_kv_cache_all_groups` | `[KVTiming] D_p2p_pull_kv_ms` |

缺的三样：

1. **bytes**：只知道"搬了多久"，不知道"搬了多少"，无法算带宽；
2. **目标层**：HBM / CPU / Mooncake Store 没有区分；
3. **本机路径没覆盖**：CPU + Mooncake 用的是
   `p4_mooncake_connector.MooncakeExampleConnector`（`tmp/p4_run.py`），
   不在 namelist 里，所以在空跑环境里跑不到这几个点。

**本机验证是可行的**，两条路：

- **A（推荐）**：用 `sim030:mooncake` + `mooncake-tcp-p2p` master 跑 `tmp/p4_run.py`，
  给 `MooncakeExampleConnector.start_load_kv` / `save_kv_layer` 加 target；
  `save_kv_layer(layer_name, kv_layer, ...)` 里直接有 tensor，
  `bytes = kv_layer.numel() * kv_layer.element_size()`。
- **B**：按 `004-...` 的思路把 vllm-ascend 加载进空跑环境（stub torch_npu），
  直接复用现成的 ascend target。

两条路都能在本机产出「bytes + 耗时」，前提是补 target / 补字段。

### 9.8 算子级打点降级（§4.7 的实现）

- 6 个 target 标记 `deep_only`（`_update_states`、`execute_model`、
  `_execute_mm_encoder`、`_gather_mm_embeddings`）；
- 默认跳过，`REQUEST_TRACE_DEEP=1` 才包装；
- coverage 行会打印 `skipped_deep`，避免"静默没打"。

实测：

```text
默认       wrapped=19  skipped_deep=6  (REQUEST_TRACE_DEEP=off)
开 deep    wrapped=23  skipped_deep=0  (REQUEST_TRACE_DEEP=on)
```

注意：V2 的 action 本身还有 `"worker.v2.model_runner" in type(self).__module__` 判断，
CPU 上即使开 deep 也不会出现——这是打点条件，不是 deep 开关的问题。

### 9.9 换入换出：本机跑通（2026-11-07）

**先纠错**：上一版说「卡在 Mooncake store」是误判。用 `faulthandler` 抓栈后，
卡点是 **Triton CPU JIT**（`block_table.compute_slot_mappings`），单次约 90 秒；
看门狗从 90s 放宽到 480s 后，producer / consumer 都正常结束。store 一直是好的。

**传输通路（transport 直测，1 MiB）**：

| 方向 | 字节 | 耗时 |
| :-- | --: | --: |
| put | 1,048,576 | 0.796 ms |
| get | 1,048,576 | 2.048 ms |

内容一致（`match: True`）。

**连接器级（Qwen2.5-tiny，2 层，1 token）**：

```text
prefill-7   put_count=2  put_bytes=3026  put_ms=0.718
decode-7    put_count=2  put_bytes=3026  put_ms=0.670
            get_count=0
```

**两个必须记住的教训**：

1. `save_kv_layer` 收到的是**整层 KV cache tensor**（2.6 GB），不是本次要传的
   slice。用它算字节会高估 6 个数量级（2.6 GB vs 实际 3026 B）。字节必须下沉到
   `transport.put_layer/get_layer` 取 payload 长度。
2. **standalone 跑 consumer 不会触发 get**：example connector 的 `is_store`
   依赖 P→D 的 `kv_transfer_params` 握手，单跑时它把自己的请求也当成 store
   （所以 decode-7 也有 put_count=2）。get 侧目前靠 transport 直测验证，
   连接器级要真 P/D 并发才能看到。

**新增字段**：

```text
[KVTiming] P4_put_count / P4_put_bytes / P4_put_ms     ← 权威字节数
[KVTiming] P4_get_count / P4_get_bytes / P4_get_ms
[KVTiming] P4_save_kv_* / P4_load_kv_*                 ← 连接器级调用，仅计时可信
```

复现脚本：`tmp/trace-e2e/p4_run_traced.py`、`tmp/trace-e2e/mooncake_traced_transfer.py`
（后者不需要 vLLM，直接验证 put/get 双向埋点）。

### 9.10 单测、开销与字段修正（2026-11-07）

- **单测**：新增 `tests/patch/platform/test_request_trace_observability.py`（18 条），覆盖
  reason 分类、KV 计数与峰值、layer_transfer 聚合、stats 落盘、parser 的两个 sheet builder，
  以及**同一函数叠加两个 wrapper 的调用顺序**（`e2e → e1 → body → x1 → x2`）。
  合计 36 条 request_trace 单测通过。
- **开销**：见 `006-trace开销实测.md`。`metrics` +1.0%、`trace` +7.2%；
  默认值保持 `off`，建议部署显式开 `metrics`。
- **reason 精度**：新增 `KV_PRESSURE`（`free_blocks == 0` 或本步有驱逐），
  避免把「KV 快满但还没分配失败」误判成 `CHUNK_BUDGET`。
- **字段修正**：删掉 `P4_save_kv_bytes`（整层 tensor 的 numel，实测高估 6 个数量级）；
  字节数只保留 `P4_put_bytes` / `P4_get_bytes`（payload 级）。

### 9.11 per-request coverage（2026-11-07）

`trace_health` 之前只有 stage 粒度，看不出「某个请求的日志断了一半」。新增
`coverage_by_request` sheet，一行一个请求：

```text
RequestID  Actions  Steps  StagesOK  StagesTotal  Coverage(%)  FirstState  LastState              Finished  Verdict
0               30      3        13           13          100    WAITING     FINISHED_LENGTH_CAPPED      True complete
1               26      6         9            9          100    WAITING     FINISHED_LENGTH_CAPPED      True complete
2               26      6         9            9          100    WAITING     FINISHED_LENGTH_CAPPED      True complete
```

判定规则：

| Verdict | 条件 |
| :-- | :-- |
| `complete` | 有 FINISHED 事件且 stage 覆盖率 100% |
| `partial` | 有 FINISHED 但 stage 有缺失 |
| `no-finish` | 没看到 FINISHED（请求被打断/进程退出） |
| `no-events` | 只有 action、没有状态事件 |

`trace_health` 同步增加 `requests_total / requests_complete / requests_no_finish`。
KVTiming 这类「伪请求 ID」（如 `prefill-7`）会被过滤，不会污染表。

### 9.12 换入换出接真机（2026-11-07）

本机 P4 路径之外，把真机两条路径也接上了**字节**统计（原先只有耗时）。
计算逻辑抽到 `kv_bytes.py`，用假 config 单测，不依赖 NPU。

**接入点**

| 路径 | hook | 产出 |
| :-- | :-- | :-- |
| Store 读 | `AscendStoreConnector.start_load_kv` | `KVTransfer_get_tokens/blocks/bytes` |
| Store 写 | `AscendStoreConnector.wait_for_save`（非 layerwise） | `KVTransfer_put_blocks/bytes/ms` |
| P2P 拉 | `KVCacheRecvingThread._transfer_kv_cache_all_groups` | `KVTransfer_get_blocks/bytes` |

**计算方式**

```text
store:  tokens(load_spec.vllm_cached + kvpool_cached) → ceil(tokens/block_size) × page_size_bytes（按组累加）
p2p:    sum(len(g) for g in local_block_ids) × page_size_bytes（按组累加）
```

`page_size_bytes` 取 `kv_cache_config.kv_cache_groups[i].kv_cache_spec.page_size_bytes`；
拿不到时返回 **-1（未知）**，绝不猜一个数。P2P 线程没有 config 时用
`kv_bytes.bytes_from_thread_blocks()` 从 kv cache 张量反推，仍失败则 -1。

**三个已知限制**

1. **layerwise 的 put 字节不统计**：`save_kv_layer` 是逐层调用，用整组 page_size 会 ×层数，
   所以只在非 layerwise 的 `wait_for_save` 里统计；layerwise 下 `KVTransfer_put_*` 不出现。
2. **P2P 线程可能没有 `_kv_cache_config`**：代码里它有 `kv_caches` 和 `kv_group2layeridx`，
   走 fallback；若 fallback 也失败，报表里是 -1，需要把 config 传进线程。
3. **MLA + SFA indexer 是两组 cache**：按组累加，不会漏；但若 `kv_cache_groups` 只有一个组，
   说明模型只有一种 attention，属正常。

**内网验证清单（8.1–8.8 之后加一步）**

- [ ] 打印 `kv_cache_groups[i].kv_cache_spec` 的 `block_size` 与 `page_size_bytes`，确认非空；
- [ ] 1P1D + 128K：`KVTransfer_get_bytes` ≈ `tokens × 每 token KV × 组数`，与启动日志
      `GPU KV cache size` 对得上；
- [ ] `KVTransfer_get_blocks` 与 connector 日志里的 block 数一致；
- [ ] P2P 路径若 `bytes=-1`，把 `kv_cache_config` 加进 `KVCacheRecvingThread.__init__`；
- [ ] `bytes / ms` 与 Mooncake/Store 带宽规格对比，确认数量级合理；
- [ ] layerwise 开关切换时，确认 `KVTransfer_put_*` 只在该关掉时出现。

**新增防护**：单测里加了「namelist 所有 entry/exit 片段必须能 compile」——
这类片段是在 vLLM 启动时 exec 的，写错（比如在模块级写 `return`）只有真机才炸，
本地一条 compile 就能拦住。
