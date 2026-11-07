# 004 trace 开销专题（问题记录）

> **2026-11-07 更新**：已完成第一次实测，数据与决策见 `006-trace开销实测.md`。
> 结论：写盘 23.4 µs/次（缓存 handler 可降到 5.8）、exec 23.1 µs/次；
> 端到端 metrics +1.0%、trace +7.2%；默认值仍保持 `off`（理由是默认打补丁的风险，不是开销）。

> 状态：**只记录，不改实现**。这个问题会冲击 `safe_print` 的写盘机制，
> 需要先测量、再权衡，不拍脑袋优化。

## 1. 结论先说

`request_trace` 目前的写入路径是「**每个事件重新打开一次文件**」：

```python
def safe_print(directory, message):
    process_id = multiprocessing.current_process().pid
    thread_id = threading.get_ident()
    Path(directory).mkdir(parents=True, exist_ok=True)      # 每次都 stat/mkdir
    filepath = os.path.join(directory, f"log_pid_{process_id}_tid_{thread_id}.log")
    logger = logging.getLogger(f"safe_print_{process_id}_{thread_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers = []                                     # 丢弃旧 handler
    handler = logging.FileHandler(filepath)                  # open()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)
    logger.info(message)                                     # write + flush
```

每次调用的固定开销：`mkdir`（路径已存在时仍是一次 syscall）+ `getLogger` +
构造 `FileHandler`（open）+ 构造 `Formatter` + `emit`（write/flush）。
**没有 close**，handler 被丢给 GC——文件的关闭时机不确定，句柄数也可能涨。

## 2. 规模换算

| 场景 | 事件/秒 | 说明 |
| :-- | --: | :-- |
| 单请求空跑（57 actions） | ~57 | 我们的测试 |
| 100 QPS × 57 | 5,700 | 每个事件一次 open |
| 8 线程并发 | 同上，但 8 个文件 | 每线程一个文件 |

按每次 open/close + 格式化 ≈ 5–20µs 估，5,700 事件/秒 ≈ **3%–11% 的单核占用**，
还没算磁盘写入和 `asctime` 的 `strftime`。

**这个量级足以改变测量结果本身**——尤其我们测的就是调度和等待。

## 3. 为什么不能直接改

1. **多进程 + 多线程**：现在按 `pid/tid` 分文件，改成缓存 handler 要考虑 fork 后句柄继承。
2. **崩溃安全**：每次 open 的「笨」写法有一个优点——进程崩溃时数据基本已经落盘。
   改成缓冲/后台线程会丢最后一段。
3. **顺序性**：`StepID` 归并依赖行内时间戳，不依赖文件顺序，但改成 ring buffer 后
   要保证时间戳仍在事件发生时采集，而不是落盘时。
4. **它同时是「安全网」**：`safe_print` 被 953 行 YAML 里的 `exec` 字符串直接调用，
   改签名会波及全部打点。

## 4. 候选方案（待评估）

| 方案 | 预期收益 | 风险 |
| :-- | :-- | :-- |
| A. 按 `(pid, tid)` 缓存 handler | 去掉 open/close，~50–70% 开销 | fork 后需重建；崩溃丢缓冲 |
| B. 进程内 `queue.Queue` + 后台线程批量写 | 去掉格式化与写盘的主线程阻塞 | 多一个线程；退出要 flush |
| C. 先写内存 ring buffer，定时/退出落盘 | 事件路径最短（~100ns） | 崩溃丢数据；内存占用 |
| D. 二进制/JSONL 代替 logging | 去掉 formatter 的 `strftime` | 解析器要改；可读性下降 |
| E. 采样（只记 N% 请求） | 线性降开销 | 长尾问题可能被采样漏掉 |

**倾向**：A + B（缓存 handler + 后台批量写），保留「定时 flush」作为崩溃安全的折中。
C 更激进，等 A/B 的数据出来再说。

## 5. 怎么测（测量方案）

1. **微基准**：直接循环调用 `safe_print` 10 万次，测 ns/次；对比 A/B/C 实现。
2. **端到端 on/off**：同一 workload（`sim_rounds.py`），`REQUEST_TRACE_MODE=off` vs `trace`，
   各跑 5 次，比较 `init_s`、`gen_s`、进程 CPU 时间（`/proc/<pid>/stat` 的 utime+stime）。
3. **归因**：`perf top` / bpftrace 看 `openat`、`write` 的占比。
4. **报告**：median / p99，以及「每千事件的开销（ms）」。

验收标准（建议）：

```text
L2 trace 模式    额外开销 ≤ 3%（100 QPS 基准）
L0 metrics 模式  额外开销 ≤ 0.5%
```

## 6. 与默认策略的关系

在测量完成前：

- `REQUEST_TRACE_MODE` 默认仍是 `off`；
- 不把 trace 默认打开；
- `metrics` 模式虽然已经实现，但只作为「可选常开」候选，不擅自改默认值。

## 7. 待办

- [ ] 微基准脚本（`bench_safe_print.py`），给出 ns/次。
- [ ] A 方案原型（handler 缓存），对比。
- [ ] B 方案原型（queue + 后台线程），对比崩溃安全性。
- [ ] 端到端 on/off 5 次实验，产出报告。
- [ ] 定默认策略。
