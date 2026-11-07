# 实测：用 bpftrace 采样 vLLM 空跑进程（2026-11-07）

验证 `../001-bpftrace单行命令速查.md` §13.1 的两条命令能不能真的用到 vLLM 进程上。

## 环境

| 项 | 值 |
| :-- | :-- |
| 宿主 | macOS + Docker Desktop |
| 内核 | `6.10.14-linuxkit`（arm64） |
| 被测镜像 | `sim-int:dry-run`（vLLM 0.31.1rc1，`--simulate-forward`） |
| 负载 | `tmp/sim_rounds.py`（Qwen3-0.6B，CPU 空跑，3 轮 generate） |
| 采样器 | 侧挂 `debian:bookworm-slim` + bpftrace 0.17.0，`--privileged --pid=host` |
| 采样率 | `profile:hz:99` |

拓扑：

```text
┌─────────────────────────── Docker VM (kernel 6.10.14-linuxkit) ───────────────────────────┐
│                                                                                            │
│  vllm-bpf 容器                             bpf-side 容器（--pid=host）                      │
│  python /out/sim_rounds.py  ──同一内核──▶  bpftrace -p <host pid>                           │
│  （8 线程）                                 /pid == N/ 过滤                                  │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

## 结果 1：`-p` 不给 `profile` 探针加过滤（关键发现）

第一版按文档写法只给 `-p "$pid"`，35s 窗口的 `@on[comm]`：

```text
@on[swapper/7]: 1383      @on[swapper/6]: 1382
@on[swapper/5]: 1381      @on[swapper/3]: 1376
@on[swapper/1]: 1383      @on[swapper/2]: 1011
@on[swapper/0]: 530       @on[python]: 1437
@on[dockerd]: 4           @on[init]: 4
@on[containerd]: 2        @on[jbd2/vda1-8]: 4
```

`swapper/*` 是 idle 线程。也就是说：**采样是全系统的**，`-p` 只起了两个作用——
uprobe 的二进制定位、目标进程退出时 bpftrace 跟着退出。要把样本限制在目标进程，
必须显式写 `/pid == N/`。

> 这个坑很危险：如果不看 `@on` 直接看 `@kstack`，会得出「空跑把 8 个核全压满」的
> 错误结论，实际是 idle 也在被采样。

## 结果 2：加 `/pid == N/` 之后

697 个采样点，全部落在 python 上：

```text
target_pid=6638 comm=python nthreads=8
@on[python]: 697
```

内核栈分布：

| 类别 | 样本数 | 占比 |
| :-- | --: | --: |
| 空栈（用户态执行） | 662 | 95.0% |
| 缺页（`el0_da` / `do_page_fault`） | 9 | 1.3% |
| mmap/munmap/exit | 8 | 1.1% |
| read（model 文件，overlayfs→virtiofs） | 4 | 0.6% |
| openat | 3 | 0.4% |
| 调度（`schedule`） | 1 | 0.1% |
| 其它 | 10 | 1.4% |

结论：**引擎初始化是用户态 CPU 密集**，内核态只有加载模型文件 + 内存映射，
没有等 IO、没有等锁。这与 `sim_rounds.py` 的输出一致（3 轮共 13 个调度步，
单轮 `time=0.003s`）。

## 结果 3：`ustack` 不可用

第一版同时采了 `@ustack`，输出长这样：

```text
@ustack[
    0xffff80227f1c
    0xffff801949a0
    ...
]: 13
@ustack[]: 9835
ERROR: failed to look up stack id -17 (pid -1): -2
```

全是裸地址，无法还原 Python 调用栈。所以 vLLM 的 Python 层（调度器、模型 runner）
**不能靠 bpftrace 定位**，要用 `py-spy record --pid <PID> --flamegraph`。

## 对文档的修正

| 原写法 | 问题 | 改为 |
| :-- | :-- | :-- |
| `bpftrace -p "$PID" -e 'profile:hz:99 {...}'` | 采到全系统 | `bpftrace -p "$PID" -e "profile:hz:99 /pid == $PID/ {...}"` |
| 同时采 `@ustack` | 裸地址 + 报错 | 去掉，改用 py-spy |

## 复现

```bash
cd wiki/linux性能分析/assets/bpf-vllm-trace
VLLM_LAB_ROOT=/Users/sunlei/code/dsh/vllm ./run.sh
```

首次运行会在侧挂容器里 `apt-get install bpftrace`（约 60–90s）。
原始采样见同目录 `bpf-trace2.txt`。

## 遗留

- [ ] 用同样的方法验证 §13.2 的唤醒延迟（需要构造高并发场景，让 runqueue 真的排队）。
- [ ] 验证 `py-spy` 在同一容器里能出 Python 火焰图（对照 `tmp/pyspy_probe*.sh` 的旧实验）。
