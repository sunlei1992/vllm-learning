# 006 trace 开销实测（2026-11-07）

> 目标是回答一个问题：**`metrics` 能不能默认开？`trace` 的开销到底花在哪？**
> 对应 `004-trace开销专题.md` 的测量方案，本文是第一次实测。

## 1. 环境

| 项 | 值 |
| :-- | :-- |
| 容器 | `sim030:int3`（vLLM 0.31.1rc1+cpu，simulate-forward） |
| workload | `run_e2e.py`：3 请求，长 prompt chunked prefill，132 条 trace 事件 |
| 采样 | 每种模式 3 次，取中位数；输出写到容器本地盘（排除 virtiofs 干扰） |

## 2. 微基准：写一条事件要多久

`tools/request_trace/bench_safe_print.py`，20000 次调用：

| 实现 | µs/次 |
| :-- | --: |
| 当前 `safe_print`（每次新建 logger + FileHandler） | **23.37** |
| 缓存 handler 的变体 | **5.78** |
| 比值 | **4.05×** |
| `time.thread_time_ns()`（每条事件多一次） | 0.22 |

折算到 100 QPS × 57 actions = 5,700 事件/秒：

```text
当前实现   13.3% 单核
缓存 handler 3.3% 单核
```

**写盘路径本身就是 10% 量级**，不是「可忽略」。

## 3. 微基准：每事件两次 `exec`

打点代码是 YAML 里的字符串，每次调用 `execute_operation` 都 `exec` 一遍（Python 每次都会重新编译）：

| 操作 | µs/次 |
| :-- | --: |
| `execute_operation`（一段典型 entry 代码） | **23.1** |

每个被包装的调用 = 1 次 entry exec + 1 次 exit exec ≈ 46 µs，**比写一条日志还贵**。

## 4. 端到端

同一 workload，三种模式，各 3 次，进程 CPU 时间（utime+stime）中位数：

| 模式 | CPU (s) | 相对 off |
| :-- | --: | --: |
| `off` | 6.505 | — |
| `metrics` | 6.613 | **+1.0%** |
| `trace` | 6.982 | **+7.2%** |

注意：这个 workload 只有 132 条事件。按微基准算，132 条 × (2×23 + 23) µs ≈ 9 ms，
解释不了 470 ms 的差值。**说明 trace 的开销不在日志，而在包装本身**：

- `BlockPool._maybe_evict_cached_block` 是**按块**调用的热路径，每次调用 2 次 exec；
  simulate-forward 一轮里有数千次块分配，几千 × 46 µs ≈ 0.2–0.3 s；
- 其余 target 的调用次数远小于它。

**结论：先优化「包装了什么」和「exec 怎么执行」，再优化写盘。**

## 5. 决策

| 模式 | 默认 | 理由 |
| :-- | :-- | :-- |
| `off` | ✅ 当前默认 | 风险不在开销，而在**默认给所有部署打 monkey patch**；应由部署显式开启 |
| `metrics` | 建议显式开启 | 实测 +1.0%，且只挂 3 个 target；启动脚本加一行 `REQUEST_TRACE_MODE=metrics` |
| `trace` | 按需 | +7.2%，且热路径 target 未优化前不适合常开 |

所以**不把默认值改成 metrics**。这不是因为开销不可接受，而是因为「默认打补丁」这个行为
需要内网验证背书；等 8.1–8.8 跑完，再把启动脚本里的这一行固化。

## 6. 下一步（按收益排序）

1. **预编译 snippet**：`compile(src, "<trace>", "exec")` 一次，之后 `exec(code, globals)`，
   预计省掉每事件 ~23 µs（exec 的编译部分）；
2. **缓存 handler**：写盘 23.4 → 5.8 µs（4×）；
3. **把 `_maybe_evict_cached_block` 移出默认 target**（它只提供计数，可以改成块池自身计数）；
4. 重测，目标：trace ≤3%，metrics ≤0.5%。

## 7. 复现

```bash
# 微基准
python -m request_trace.bench_safe_print --n 20000

# 端到端（容器内）
TRACE_MODE=off|metrics|trace python /out/run_e2e.py
```

## 8. 优化后（同日，三项落地）

| 优化 | 做法 |
| :-- | :-- |
| 移除按块热路径 | `_maybe_evict_cached_block` 不再默认包装；改为每次 `schedule` 采样 `cached_block_hash_to_block` 的下降量（下界估计） |
| 预编译 snippet | `compile()` 一次，`_COMPILED_SNIPPETS` 缓存 code object，之后只 `exec(code)` |
| 缓存 handler | `safe_print` 按文件缓存 logger + FileHandler（目录只 `mkdir` 一次），`atexit` 统一关闭 |

**微基准**

| 项 | 优化前 | 优化后 | 倍数 |
| :-- | --: | --: | --: |
| `safe_print` | 23.4 µs | **7.0 µs** | 3.3× |
| `execute_operation` | 23.1 µs | **0.9 µs** | 25× |
| 每事件合计（估） | ~69 µs | **~9 µs** | 7.7× |

**端到端**（进程 CPU，3 次中位）

| workload | off | trace | delta |
| :-- | --: | --: | --: |
| 132 事件 | 6.520 | 6.939 | +0.419 s |
| 8,735 事件 | 6.643 | 7.191 | +0.548 s |

拆解：**固定 +0.42 s + 每事件约 15 µs**（两次 workload 的差值 / 8603 事件）。

固定那 0.42 s 来自 `apply_all()` 里 eager import
`vllm.entrypoints.openai.chat_completion.serving`（冷导入 4.07 s，与后续导入部分重叠）。
离线 `LLM.generate` 本来不需要这个模块；**生产走 OpenAI server 时这部分本来就要付，净开销接近 0**。
这是 harness 假象，不是真实成本。

**结论**：稳态从 ~69 µs/事件降到 ~15 µs/事件；按 5,700 事件/秒算，
单核占用从 ~39% 降到 **~8.6%**。trace 已经进入「可以常开」的量级，
剩下的大头是每事件 7 µs 的写盘（004 的 ring buffer 方案还能再降）。

**下一步可做**：serving target 惰性包装（消掉 0.42 s 固定成本）；
`sm.scan`/`kv.scan` 的频率也可以从「每 step」降到「每 N step」。
