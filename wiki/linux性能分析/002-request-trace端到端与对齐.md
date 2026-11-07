# 002 request_trace 端到端验证与「请求层 × 系统层」对齐

## 0. 元信息

- 日期：2026-11-07
- 对象：mxllm `feat/request-trace-main`（MR !146），`ascend_vllm/patch/platform/patch_request_trace.py`
  + `tools/request_trace/`
- 环境：macOS → Docker Desktop（`6.10.14-linuxkit`），容器 `sim030:int3`
  （vLLM `0.31.1rc1+cpu`，editable `/work`，pin `ced6857af`），CPU simulate-forward
- 结论一句话：**打点链路在真实 vLLM 上跑通了，StepID 聚合可用；但暴露出 1 个必崩 bug、
  2 个会让报表失真的缺陷；"请求层 × 系统层"对齐方法也验证成功。**

---

## 1. 两个目标与方法

| 目标 | 做法 | 结果 |
| :-- | :-- | :-- |
| 端到端跑通，产出第一份 `time_analysis.xlsx` | 真实 vLLM + simulate-forward + 打点 + parser | ✅ 产出，31 行 `stage_timings` / 12 个 StepID |
| 把 `stage_timings` 的 StepID 窗口和 bpftrace 采样对齐 | `sched_switch` 事件重建 off-CPU 区间，按窗口裁剪 | ✅ 6 个 ok 窗口全部算出 on-CPU 占比 |

### 为什么不是"直接起 mxllm"

mxllm 的启动路径是 `ascend_vllm.patch.platform.__init__`，会连带 import
`torch_npu` / `vllm_ascend`，本机（无 NPU）起不来。所以用了一个 **overlay harness**：

```text
按文件路径加载 patch_request_trace.py  →  绕开 ascend_vllm 包 __init__
        ↓
apply_all()                            →  按 namelist 包装真实 vLLM 类
        ↓
LLM(simulate_forward=True)             →  真实 Scheduler / KV / ModelRunner
```

**这验证的是"打点机制 + parser"，不是 NPU 上的打点语义**（后者仍需内网 8.1–8.8）。

---

## 2. Part 1：端到端跑通

### 2.1 运行参数

```text
模型        Qwen3-0.6B（meta device，不读权重）
max_num_batched_tokens=64        → 长 prompt 强制 chunked prefill
3 个请求（1 长 2 短），max_tokens=8
REQUEST_PD_ROLE=prefill，单进程（VLLM_ENABLE_V1_MULTIPROCESSING=0）
```

### 2.2 结果

| 指标 | 值 |
| :-- | :-- |
| 成功包装的 target | 21 条 `is wrapped`（V1/V2 各一份） |
| 写出的 action | 57 条 |
| 不同 StepID | 12 个 |
| `stage_timings` 行数 | 31（6 行 `ok`，25 行 `missing-start`） |
| `time_analysis` 行数 | 7（3 个请求 × 2 种 RequestID） |
| 引擎耗时 | init 2.36s / generate 0.34s |

StepID 长相：`330-1794019751.9495504`（`<pid>-<scheduler step 起点 epoch>`），
和设计文档一致，同一 step 内的 action 正确归并。

**StageID 聚合是有效的**：3 个请求的长 prompt 被切成多步，每个 step 一行，
`Occurrence` 能区分同名 action 的多次出现。

### 2.3 发现的四个问题

| # | 严重度 | 现象 | 根因 | 影响 |
| :-- | :-- | :-- | :-- | :-- |
| 1 | **P0** | 第一次 `schedule()` 就 `AttributeError: 'CustomList' object has no attribute '_trace_step_id'` | namelist 里 `class CustomList(list)` 的 `def append(self, item)` 参数 `self` **遮蔽**了外层的 Scheduler `self`，而方法体里写的是 `self._trace_step_id` | 直接崩，trace 完全不可用 |
| 2 | P1 | 25/31 行 `missing-start` | `Prefill start execute_model` 只在 `scheduled_new_reqs` 上打点；chunk 续步没有新请求，只有 `done execute_model` | chunked prefill 的每步耗时算不出来（只能拿到 end） |
| 3 | P1 | `total_time_ms` / `ttft_ms` 全是 `-` | 同一请求出现两个 ID：`0` 和 `0-a581abc6`；parser 当成两个请求，起止点对不上 | 请求级汇总指标为空 |
| 4 | P2 | coverage 打印 `wrapped=0`，实际包了 21 个 | `_TRACE_TARGET_STATS["wrapped"] += 1` 只在**模块级函数**分支；**类方法**分支 `return True` 前没计数 | 运维会误判"没生效" |

> #1 是硬阻塞，必须修；#2/#3 是"报表失真"，比崩溃更隐蔽——数字看着有，但缺一半。

### 2.4 修复

#1 的修复很小：在 class 定义前把 Scheduler 存成别名，方法里引用别名。

```python
_trace_sched = self
class CustomList(list):
    def append(self, item):
        ... f"...StepID:{_trace_sched._trace_step_id}..."
```

补丁：`assets/request-trace-e2e/0001-request-trace-fixes.patch`
（只改 2 处别名 + 6 处引用；注意 yaml 里 `{self._trace_step_id}` 共 17 处，
**不能全局替换**，只有 CustomList 块内那 6 处需要）。

### 2.5 修复后复验（2026-11-07）

| 项 | 修复前 | 修复后 |
| :-- | :-- | :-- |
| `stage_timings` | 31 行（6 ok / 25 missing-start） | **31 行全部 `ok`**（28 个 execute_model + 3 个 running→schedule） |
| coverage | `wrapped=0` | **`wrapped=21`** |
| RequestID | 3 个请求裂成 7 行 | 每个请求 1 行 |
| 离线 `ttft_ms` / `total_time_ms` | `-` | 仍为 `-`（离线路径没有 OpenAI 服务层，属预期） |

**为什么离线拿不到 ttft**：parser 的总时长/TTFT 固定在
`PD api server get request` → `First decode output token` / `Finish decode pickle...`，
这些 action 只在 OpenAI serving 层产生，`LLM.generate()` 不经过它。

于是补跑了一次**在线**验证（OpenAI server + `--simulate-forward` + 流式请求，
`VLLM_ENABLE_V1_MULTIPROCESSING=0`）：

| 指标 | 值 |
| :-- | :-- |
| `total_time_ms` | **249.94** |
| `ttft_ms` | **249.71** |
| `RequestID` | `cmpl-95953438d507582e`（单行，未分裂） |

关键点：请求体里显式带 `request_id`，API 层和引擎侧才会用同一个 ID
（引擎会追加 `-0-<8hex>`，由 parser 归一）。

已推送：`77e7c54`（运行时打点）、`92daf47`（parser）→ MR !146。

一个遗留：在线单节点跑不出 P/D 的完整阶段（`D: engine first token to response`
仍是 missing-start），因为 `decode` 侧的 action 需要真正的 D 节点，这是场景限制不是 bug。

---

## 3. Part 2：请求层 × 系统层对齐

### 3.1 时钟对齐原理

两侧本来是两个时钟：

| 侧 | 时间源 | 分辨率 |
| :-- | :-- | :-- |
| request_trace | `time.time()`（epoch 墙钟） | µs |
| bpftrace | `nsecs`（`CLOCK_MONOTONIC`） | ns |

driver 在启动时同时记录 `(t0_wall, t0_mono_ns)`，于是：

```text
mono_ns(wall) = t0_mono_ns + (wall - t0_wall) * 1e9
```

两者在同一台机器上是同一个 `CLOCK_MONOTONIC`，所以这个换算没有漂移。

### 3.2 采集方式

```bash
# 只跟主线程（tid == pid）
tracepoint:sched:sched_switch /args->prev_pid == $PID/ { printf("OUT %lld %d\n", nsecs, args->prev_state); }
tracepoint:sched:sched_switch /args->next_pid  == $PID/ { printf("IN %lld\n", nsecs); }
profile:hz:99 /pid == $PID/ { printf("S %lld\n", nsecs); }
```

- `OUT/IN` 重建 off-CPU 区间（阻塞 + 被抢占都算）；
- `S` 做交叉验证；
- `BPFTRACE_PERF_RB_PAGES=256`，实测 OUT/IN 完全配平（29804 / 29803），无丢事件。

### 3.3 结果

| 请求 | 阶段 | 耗时 | off-CPU | on-CPU |
| :-- | :-- | --: | --: | --: |
| 0 | running → schedule end | 1.096 ms | 0.434 ms | **60.4%** |
| 0 | P: execute_model | **261.916 ms** | 25.366 ms | **90.3%** |
| 1 | running → schedule end | 2.276 ms | 0.778 ms | 65.8% |
| 1 | P: execute_model | 2.069 ms | 0.556 ms | **73.1%** |
| 2 | running → schedule end | 0.986 ms | 0.327 ms | 66.8% |
| 2 | P: execute_model | 2.313 ms | 0.657 ms | **71.6%** |

原始数据：`assets/request-trace-e2e/results/align.csv`。

### 3.4 解读

1. **第一步 261.9ms / 90.3% on-CPU**：这是编译/预热主导的一段（Triton JIT + torch 初始化），
   系统层证据是"真的在算"，不是等 IO、不是被调度走。**这类结论只有把两层对齐才拿得到**：
   request_trace 只说"这一步 262ms"，bpftrace 说"其中 236ms 在 CPU 上"。
2. **后续步 2ms / 71–73% on-CPU**：每步仍有约 0.6ms 不在 CPU 上，占 27–29%。
   平均每次切出只有 ~15µs（449ms / 29803 次），频率约 4k 次/秒——这是典型的
   **Python 线程/GIL 交接特征**，不是慢 IO。
3. **`running → schedule end` 阶段更差（60–67%）**：这段是纯 Python 调度逻辑，
   更容易被解释器切换打断。要做调度优化，这里才是真正的"系统税"。

---

## 4. 方法论沉淀

| 坑 | 说明 |
| :-- | :-- |
| `printf("%d", nsecs)` | **32 位截断**，时间戳会变成负数（第一次跑就是这样，全部窗口匹配为 0）。必须 `%lld` |
| off-CPU 区间要"容忍丢事件" | 高频率下 `OUT`/`IN` 可能不成对；用状态机（重复 OUT 忽略、重复 IN 忽略）比严格配对稳 |
| 主线程过滤 | `prev_pid == PID` 只匹配 `tid == pid` 的主线程；多线程模型要换成按 `tid` 白名单 |
| 容器 PID | 容器内 `os.getpid()` 是命名空间 PID，bpftrace 侧要用宿主 PID；`--pid=host` 后 `pgrep -f` 拿到的就是宿主 PID |
| 采样率 × CPU 数 | `profile:hz:N` 是**每 CPU** 触发；8 核机器上系统级事件量 ×8 |

---

## 5. 结论与建议

### 对 MR !146 的修改建议（已全部落地）

1. **P0**：修 `CustomList` 的 `self` 遮蔽 → `77e7c54`。
2. **P1**：`execute_model` 的 start 改成按 `num_scheduled_tokens` 每个 step 都打 → `77e7c54`。
3. **P1**：RequestID 归一（引擎侧 `<n>-<8hex>`、`cmpl-<hex>-<n>-<8hex>`）→ `92daf47`。
4. **P2**：类方法分支补 `wrapped += 1` → `77e7c54`。

额外一条：无 `X-Request-Id` 时回退到请求体 `request_id`，否则 API 层永远是
`cmpl-unknown`，和引擎 ID 对不上 → `77e7c54`。

### 下一步

- [x] 修 #2/#3 并复验：`stage_timings` 全 `ok`，在线 `ttft_ms` 有值。
- [ ] 用 `REQUEST_PD_ROLE=decode` 再跑一遍，补齐 D 侧阶段。
- [ ] 内网真机按 DESIGN §8 跑 8.1–8.8，重点确认 target coverage 和 trace 开销。

---

## 6. 复现

```bash
# 1. 启动实验容器（sim030:int3 + vLLM 0.30 线）
#    挂载：mxllm-trace → /mxllm，本目录 → /out，models、triton-cache
# 2. 安装依赖
uv pip install --system pandas openpyxl pyyaml
# 3. 打补丁（CustomList 遮蔽）后重跑
python /out/run_e2e.py
# 4. 解析
python /mxllm/tools/request_trace/parse_logs.py /out/trace_e2e
# 5. 对齐（需要同时跑 trace_bpf.sh）
python /out/analyze_align.py /out/trace_e2e_bpf /out/bpf-sched.txt
```

脚本见同目录 `run_e2e.py` / `trace_bpf.sh` / `analyze_align.py`。
