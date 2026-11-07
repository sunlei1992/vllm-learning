# bpftrace 速查：单行命令与常用脚本

> 对照《BPF 之巅》（*BPF Performance Tools*）附录 D 的 bpftrace one-liners，按本工作区的
> 推理服务 / 容器场景重排，并**在本机 Docker 环境逐条冒烟验证**。

## 0. 元信息

- 日期：2026-11-07
- 来源：Brendan Gregg《BPF 之巅》附录 D（bpftrace 单行命令）、bpftrace 官方 reference、
  本机实测。
- 验证环境：macOS → Docker Desktop，内核 `6.10.14-linuxkit`，
  容器 `debian:bookworm-slim` + `bpftrace v0.17.0`，
  启动方式 `--privileged --pid=host`。
- 一句话结论：**这套东西在 Docker Desktop 上能跑通**（kprobe / tracepoint / profile /
  hist 全部实测可用），但追踪的是 **LinuxKit 虚拟机的内核**，不是 macOS 宿主。
- 相关笔记：`../vllm架构笔记/13-性能调试方法论-系统级瓶颈归因.md`（分层归因）、
  `../vllm架构笔记/09-调度层可观测性与性能测量.md`（vLLM 自己的观测面）。

---

## 1. 先决条件与最小验证

### 1.1 bpftrace 需要内核具备什么

| 能力 | 说明 | 缺失时的表现 |
| :-- | :-- | :-- |
| `CONFIG_BPF_SYSCALL` | bpf() 系统调用 | 直接起不来 |
| `CONFIG_KPROBES` | 内核动态探针 | `kprobe:` 挂不上 |
| `CONFIG_BPF_JIT` | 字节码编译成机器码 | 能跑但很慢 |
| BTF（`/sys/kernel/btf/vmlinux`） | 无内核头文件也能解析结构体/参数 | `arg0`/`args->` 不可用 |
| `tracefs` 已挂载 | `/sys/kernel/tracing` 或 `/sys/kernel/debug/tracing` | `-l` 列不出探针 |
| `perf_event_paranoid ≤ 2` | 采样类探针 | `profile:`/`hardware:` 权限不足 |

### 1.2 启动模板（Docker Desktop）

```bash
docker run --rm -it --privileged --pid=host \
  -v /sys/kernel/debug:/sys/kernel/debug \
  debian:bookworm-slim bash

# 容器内
apt-get update && apt-get install -y bpftrace procps
bpftrace -e 'BEGIN { printf("ok %s\n", comm); exit(); }'
```

三个参数都不能省：

- `--privileged`：需要 `CAP_SYS_ADMIN`、`CAP_PERFMON`、`CAP_BPF`。
- `--pid=host`：否则看不到宿主机（VM）里的其他进程，`-p` 会失效。
- `-v /sys/kernel/debug`：tracefs 的经典挂载点。

> 如果不想动现有镜像，就用这个**旁路容器**：它和 vLLM 容器共享同一个 VM 内核，
> 用 `pgrep -f vllm` 拿到的是宿主 PID，`bpftrace -p <pid>` 直接就能挂。

### 1.3 本机实测记录（2026-11-07）

| 能力 | 命令 | 结果 |
| :-- | :-- | :-- |
| 内核版本 | `uname -r` | `6.10.14-linuxkit` |
| BTF | `ls /sys/kernel/btf/vmlinux` | ✅ 存在 |
| `kptr_restrict` | `cat /proc/sys/kernel/kptr_restrict` | `0` |
| `perf_event_paranoid` | 同上 | `2` |
| 基础探针 | `BEGIN { printf(...) }` | ✅ |
| kprobe | `kprobe:vfs_read` | ✅ |
| tracepoint | `tracepoint:sched:sched_switch` | ✅ |
| 采样 | `profile:hz:99` | ✅ |
| 直方图 | `hist()` / `lhist()` | ✅ |
| 无参 `print()` | `print()` | ❌ 0.17 报 “requires at least one argument” |
| 位置参数 | `$1` / `$2` | ✅ |
| `END` + `clear()` | 退出时抑制 map 打印 | ✅ |
| 通配 tracepoint | `sys_enter_*` / `sys_exit_*` | ✅ |
| 块层 tracepoint | `block:block_rq_issue` / `complete` | ✅ |
| socket tracepoint | `sock:inet_sock_set_state` | ✅ |
| `cgroup` 内建 | `@[cgroup, comm]` | ✅ |
| `kprobe:__kmalloc` | 分配计数 | ❌ 已 inline，改用 `__kmalloc_noprof` |
| `-p` 对 `profile` 的过滤 | 采样是否只落目标进程 | ❌ **不过滤**，必须 `/pid == N/` |

---

## 2. 语法五分钟

### 2.1 探针（probe）

```text
类型:目标                    触发时机
─────────────────────────────────────────────────
kprobe:func                 内核函数入口
kretprobe:func              内核函数返回
uprobe:/path:func           用户态函数入口
uretprobe:/path:func        用户态函数返回
tracepoint:cat:name         内核预置探针（稳定 ABI，首选）
usdt:/path:prov:name        用户态预埋的静态探针
profile:hz:99               每 CPU 每 99Hz 采样（近似 on-CPU 时间）
interval:s:5                每 5 秒触发一次（做快照/退出）
software:faults:1           软件事件（缺页）
hardware:cache-misses:1e6   硬件计数器（每 100 万次触发一次）
BEGIN / END                 程序开始 / 结束
```

通配符：`kprobe:tcp_*`、`tracepoint:syscalls:sys_enter_*`、`uprobe:/bin/bash:*`。

### 2.2 内置变量

| 变量 | 含义 |
| :-- | :-- |
| `pid` / `tid` | 进程 / 线程 id（内核视角） |
| `uid` / `gid` | 用户 / 组 |
| `comm` | 进程名（**只有 15 字符**，会被截断） |
| `cpu` | CPU 编号 |
| `nsecs` | 单调时钟纳秒（做差值用） |
| `elapsed` | 程序启动至今的纳秒数 |
| `arg0` … `argN` | kprobe/uprobe 的第 N 个参数 |
| `retval` | kretprobe/uretprobe 的返回值 |
| `args->field` | tracepoint 的字段（有 BTF 时最可靠） |
| `kstack` / `ustack` | 内核 / 用户调用栈 |
| `func` / `probe` | 当前函数名 / 探针全名 |
| `str(ptr)` / `buf(ptr, len)` | 读字符串 / 读原始内存 |
| `$1` … `$N` | 命令行位置参数 |
| `cgroup` | 当前 cgroup id（0.17+，用于容器归因） |

### 2.3 聚合与 map

```text
@name[key1, key2] = 聚合函数(值)
```

| 函数 | 输出 |
| :-- | :-- |
| `count()` | 次数 |
| `sum(x)` | 求和 |
| `avg(x)` | 平均 |
| `min(x)` / `max(x)` | 极值 |
| `stats(x)` | 计数 + 均值 + 方差 |
| `hist(x)` | 2 的幂直方图（看分布首选） |
| `lhist(x, min, max, step)` | 线性分桶（已知量程时更直观） |

map 操作：

```text
delete(@m[k])   删一个键
clear(@m)       清空整个 map（保留 map 本身）
zero(@m)        值归零（保留键）
print(@m)       立即打印
```

> `@` 不带名字就是默认 map；退出时**所有非空 map 会自动打印**（实测会混进你不想看的
> 中间态），所以脚本结尾用 `END { clear(@start); }` 收尾。

### 2.4 过滤、格式化、控制流

```text
probe /条件/ { 动作 }        # 条件不成立就不执行
if (x > 0) { ... } else { ... }
unroll(10) { ... }           # 编译期展开（比循环便宜）
printf("%-16s %6d\n", comm, pid)
time("%H:%M:%S ")            # 输出加时间戳前缀
exit()                       # 立刻退出（会打印 map）
```

### 2.5 命令行参数

| 参数 | 作用 |
| :-- | :-- |
| `-e 'prog'` | 直接执行程序 |
| `-l 'pattern'` | 列出匹配的探针（**写之前先查**） |
| `-p PID` | 只跟踪这个进程 |
| `-c 'cmd'` | 启动命令并跟踪它（含子进程） |
| `-q` | 安静模式，不打印 `Attaching N probes...` |
| `-d` | 干跑：编译但不挂载，检查语法 |
| `-v` | 详细日志（挂载失败时看） |
| `-B line` | 行缓冲，实时输出到管道 |
| `-o FILE` | 输出重定向到文件 |
| `--unsafe` | 允许 `system()` / `override()` 等危险内建 |
| `-I DIR` | 增加 include 搜索路径 |

### 2.6 先查探针，再写脚本

```bash
bpftrace -l 'kprobe:tcp_*'                      # 内核函数
bpftrace -l 'tracepoint:sched:*'                # 调度相关
bpftrace -l 'uprobe:/usr/bin/python3.11:*'      # 用户态符号
bpftrace -l 'usdt:/usr/bin/python3.11:*'        # Python 的 USDT（多数发行版没有）
bpftrace -l | wc -l                             # 本机一共多少探针
```

找不到函数时，先怀疑它被 **inline** 掉了（`kmalloc`、`vfs_*` 的部分路径），
换 `__kmalloc`、`vfs_read` 这类真实符号，或直接查：

```bash
grep -w vfs_read /sys/kernel/tracing/available_filter_functions
```

---

## 3. 系统全局（System-Wide）

```bash
# 3.1 最忙的系统调用 top（每 5 秒快照一次）
bpftrace -q -e '
tracepoint:syscalls:sys_enter_* { @[probe] = count(); }
interval:s:5 { print(@); clear(@); }'

# 3.2 谁在 exec（进程创建）
bpftrace -e '
tracepoint:sched:sched_process_exec {
  printf("%-16s %6d -> %s\n", comm, pid, str(args->filename));
}'

# 3.3 谁在打开文件
bpftrace -e '
tracepoint:syscalls:sys_enter_openat {
  printf("%-16s %s\n", comm, str(args->filename));
}'

# 3.4 系统级 on-CPU 采样（先看谁在烧 CPU）
bpftrace -e 'profile:hz:99 { @[comm] = count(); }'

# 3.5 每秒打印一次时间戳 + 采样计数，确认探针真的在工作
bpftrace -q -e '
profile:hz:10 { @[comm] = count(); }
interval:s:1 { time("%H:%M:%S "); print(@); clear(@); }'
```

**怎么读**：`count()` 在 `profile:hz:99` 下近似等于「占了多少个采样点」，
乘 10ms 就是大致 CPU 时间。它**不是**精确的 CPU 时间统计（那是 `perf stat` 的活）。

---

## 4. CPU 与调度

```bash
# 4.1 on-CPU：谁在跑（按进程）
bpftrace -e 'profile:hz:99 { @[comm] = count(); }'

# 4.2 on-CPU：按 CPU 看是否负载不均
bpftrace -e 'profile:hz:99 { @[cpu] = count(); }'

# 4.3 on-CPU：用户态火焰（native 程序有效，Python 只看到 C 层）
bpftrace -e 'profile:hz:99 { @[ustack] = count(); }'

# 4.4 内核栈：卡在哪个内核路径
bpftrace -e 'profile:hz:99 { @[kstack] = count(); }'

# 4.5 调度次数（≠ CPU 时间，但能看出谁被频繁唤醒）
bpftrace -e 'tracepoint:sched:sched_switch { @[args->next_comm] = count(); }'

# 4.6 唤醒延迟 / run queue latency（关键指标：被唤醒到真正上 CPU 等了多久）
bpftrace -q -e '
tracepoint:sched:sched_wakeup { @w[args->pid] = nsecs; }
tracepoint:sched:sched_switch /@w[args->next_pid]/ {
  @us[args->next_comm] = hist((nsecs - @w[args->next_pid]) / 1000);
  delete(@w[args->next_pid]);
}
END { clear(@w); }'

# 4.7 off-CPU：每个进程「不在 CPU 上」的时间分布（阻塞/等锁/等 IO）
bpftrace -q -e '
tracepoint:sched:sched_switch /args->prev_state != 0/ { @s[args->prev_pid] = nsecs; }
tracepoint:sched:sched_switch /@s[args->next_pid]/ {
  @us[args->next_comm] = hist((nsecs - @s[args->next_pid]) / 1000);
  delete(@s[args->next_pid]);
}
END { clear(@s); }'

# 4.8 软中断分布（网络收包压力）
bpftrace -e 'tracepoint:irq:softirq_entry { @[args->vec] = count(); }'
```

**关键区分**：

- `profile:hz` 给的是 **on-CPU**（在跑）。
- 4.6 给的是 **runnable 但没 CPU**（排队）——调度器/CPU 超卖的信号。
- 4.7 给的是 **blocked**（在等）——锁、IO、sleep。
- 三者加起来才是完整的时间账。**vLLM 的调度线程大量时间在 4.7 和 4.6，不在 4.1。**

> `prev_state != 0` 表示「切出去时不是 RUNNING」，也就是真的阻塞了；
> 值为 0 是被抢占（还在 runnable）。两个都想要就把它去掉，但会混入抢占时间。

---

## 5. 内存

```bash
# 5.1 谁在缺页（minor + major 合计）
bpftrace -e 'software:faults:1 { @[comm] = count(); }'

# 5.2 内核分配页的次数 + 调用栈（找分配热点）
bpftrace -e 'kprobe:__alloc_pages { @[kstack] = count(); }'

# 5.3 谁分配了多少字节（size 是第 2 个参数 arg1）
# 注意：6.10 上 __kmalloc 已被 inline，实际符号是 __kmalloc_noprof
bpftrace -e 'kprobe:__kmalloc_noprof { @bytes[comm] = sum(arg1); }'

# 5.4 直接回收压力（内存吃紧时才会频繁出现）
bpftrace -e 'kprobe:try_to_free_pages { @[comm] = count(); }'
```

**局限**：`kfree` 拿不到大小，所以「分配 − 释放 = 泄漏」这种账 bpftrace 单行做不了，
用 BCC 的 `memleak`。5.3 只适合看「谁分配得多」，不适合算净占用。

---

## 6. 文件系统与 VFS

```bash
# 6.1 谁读了多少字节（vfs_read(file, buf, count, pos)，arg2 = count）
bpftrace -e 'kprobe:vfs_read { @bytes[comm] = sum(arg2); }'

# 6.2 谁写了多少字节
bpftrace -e 'kprobe:vfs_write { @bytes[comm] = sum(arg2); }'

# 6.3 每次 read 的延迟分布（找慢 IO）
bpftrace -q -e '
kprobe:vfs_read { @s[tid] = nsecs; }
kretprobe:vfs_read /@s[tid]/ {
  @us[comm] = hist((nsecs - @s[tid]) / 1000);
  delete(@s[tid]);
}
END { clear(@s); }'

# 6.4 大块 IO（> 1 MiB）
bpftrace -e 'kprobe:vfs_read /arg2 > 1048576/ { @[comm] = count(); }'

# 6.5 慢 open（含路径）
bpftrace -q -e '
tracepoint:syscalls:sys_enter_openat { @s[tid] = nsecs; }
tracepoint:syscalls:sys_exit_openat /@s[tid]/ {
  @us[comm] = hist((nsecs - @s[tid]) / 1000);
  delete(@s[tid]);
}
END { clear(@s); }'
```

> 6.1/6.2 的 `sum(arg2)` 是**调用方请求的字节数**，不是真正落盘量；
> 真实 IO 大小看 §7 的块层。

---

## 7. 磁盘与块层

```bash
# 7.1 按进程统计块层发出的字节（args->bytes 是实际块大小）
bpftrace -e 'tracepoint:block:block_rq_issue { @bytes[comm] = sum(args->bytes); }'

# 7.2 读写比例
bpftrace -e 'tracepoint:block:block_rq_issue { @[args->rwbs] = count(); }'

# 7.3 IO 错误
bpftrace -e 'tracepoint:block:block_rq_complete /args->error != 0/ {
  printf("io error: %s\n", args->rwbs);
}'

# 7.4 块层延迟分布（注意：complete 在中断上下文，comm 不可靠）
bpftrace -q -e '
tracepoint:block:block_rq_issue { @s[args->dev, args->sector] = nsecs; }
tracepoint:block:block_rq_complete /@s[args->dev, args->sector]/ {
  @us = hist((nsecs - @s[args->dev, args->sector]) / 1000);
  delete(@s[args->dev, args->sector]);
}
END { clear(@s); }'
```

7.4 只能给**全局**延迟分布：`block_rq_complete` 跑在中断上下文里，
`comm` 已经不是发起 IO 的进程了。想按进程/设备分组，用 **BCC `biolatency -m`**
（按设备分组）或 `biosnoop`（逐条 IO + 进程名）。

---

## 8. 网络

```bash
# 8.1 谁在发 TCP、发了多少（tcp_sendmsg(sk, msg, size)，arg2 = size）
bpftrace -e 'kprobe:tcp_sendmsg { @bytes[comm] = sum(arg2); }'

# 8.2 谁在收
bpftrace -e 'kprobe:tcp_recvmsg { @bytes[comm] = sum(arg2); }'

# 8.3 TCP 重传（网络质量 / 拥塞的直接信号）
bpftrace -e 'kprobe:tcp_retransmit_skb { @[comm] = count(); }'

# 8.4 谁在发起连接
bpftrace -e 'kprobe:tcp_connect { @[comm] = count(); }'

# 8.5 连接状态迁移（oldstate -> newstate，数字含义见下）
bpftrace -e 'tracepoint:sock:inet_sock_set_state {
  @[args->oldstate, args->newstate] = count();
}'

# 8.6 tcp_sendmsg 的延迟（发送阻塞 = 窗口满 / 对端慢）
bpftrace -q -e '
kprobe:tcp_sendmsg { @s[tid] = nsecs; }
kretprobe:tcp_sendmsg /@s[tid]/ {
  @us[comm] = hist((nsecs - @s[tid]) / 1000);
  delete(@s[tid]);
}
END { clear(@s); }'
```

TCP 状态数字（`inet_sock_set_state` 输出）：

```text
1 ESTABLISHED   2 SYN_SENT    3 SYN_RECV    4 FIN_WAIT1
5 FIN_WAIT2     6 TIME_WAIT   7 CLOSE      10 LISTEN
11 CLOSING     12 LAST_ACK
```

> 8.3 的 `tcp_retransmit_skb` 有时被 inline，找不到就用
> `bpftrace -l 'kprobe:tcp_retransmit*'` 查实际符号（实测 6.10 上有
> `tcp_retransmit_skb` 和 `tcp_retransmit_timer`）。

---

## 9. 系统调用与进程

```bash
# 9.1 哪个 syscall 最频繁（5 秒快照）
bpftrace -q -e '
tracepoint:syscalls:sys_enter_* { @[probe] = count(); }
interval:s:5 { print(@); clear(@); }'

# 9.2 失败的 syscall（ret < 0）
bpftrace -e 'tracepoint:syscalls:sys_exit_* /args->ret < 0/ { @[probe] = count(); }'

# 9.3 read 的延迟分布
bpftrace -q -e '
tracepoint:syscalls:sys_enter_read { @s[tid] = nsecs; }
tracepoint:syscalls:sys_exit_read /@s[tid]/ {
  @us[comm] = hist((nsecs - @s[tid]) / 1000);
  delete(@s[tid]);
}
END { clear(@s); }'

# 9.4 进程退出（配合 3.2 的 exec 看生命周期）
bpftrace -e 'tracepoint:sched:sched_process_exit { printf("%-16s %6d\n", comm, pid); }'
```

只有 9.1 全量挂 `sys_enter_*` 开销大（几千个探针），别在线上长期开，
按需缩到具体 syscall。

---

## 10. 语言运行时：Python

Python 是最大的坑：**bpftrace 的 `ustack` 只能看到 C 层符号**（`_PyEval_EvalFrameDefault`
这类），看不到 Python 函数名。所以定位策略要分两层。

```bash
# 10.1 先确认符号在哪（可能在 libpython 而不是解释器本体）
bpftrace -l 'uprobe:/usr/bin/python3.11:*EvalFrame*'
# 实测输出：
#   uprobe:/usr/bin/python3.11:PyEval_EvalFrame
#   uprobe:/usr/bin/python3.11:PyEval_EvalFrameEx
#   uprobe:/usr/bin/python3.11:_PyEval_EvalFrameDefault
#   uprobe:/usr/bin/python3.11:_PyInterpreterState_GetEvalFrameFunc

# 10.2 解释器「单帧执行时长」分布（找长帧，不是找具体 Python 函数）
bpftrace -q -e '
uprobe:/usr/bin/python3.11:_PyEval_EvalFrameDefault { @s[tid] = nsecs; }
uretprobe:/usr/bin/python3.11:_PyEval_EvalFrameDefault /@s[tid]/ {
  @us[comm] = hist((nsecs - @s[tid]) / 1000);
  delete(@s[tid]);
}
END { clear(@s); }'

# 10.3 哪条 C 扩展在烧时间（numpy / torch 的 native 部分能看到）
bpftrace -e 'profile:hz:99 /comm == "python3.11"/ { @[ustack] = count(); }'
```

**结论（重要）**：

- 想看 **Python 函数级火焰图** → 用 `py-spy record --pid <PID> --flamegraph -o out.svg`，
  不要指望 bpftrace。
- 想看 **C 扩展 / 内核侧**（torch 的算子、KV offload 的 syscall）→ bpftrace 很合适。
- `usdt` 探针在官方 CPython 构建里通常**没有**，`bpftrace -l 'usdt:...:*'` 返回空是正常的。

---

## 11. 容器

```bash
# 11.1 按 cgroup 归因（需要 0.17+ 的 cgroup 内建）
bpftrace -e 'profile:hz:99 { @[cgroup, comm] = count(); }'

# 11.2 只看某个容器（先查它的 cgroup id）
cat /proc/<PID>/cgroup
```

cgroup id 到容器名的映射要自己对 `/sys/fs/cgroup`（v2）或
`/sys/fs/cgroup/<subsystem>/docker/<id>`（v1）。**更省事的做法是反过来**：
用 `-p <PID>` 锁定进程，或直接在容器内起 bpftrace。

```bash
# 11.3 容器内直接跑（容器本身就是被测对象时）
docker exec -it --privileged <vllm-container> bash
```

---

## 12. 安全（Security）

只用一条就够日常排查：谁在监听、谁在连。

```bash
# 12.1 新监听端口（inet_csk_listen_start(struct sock *sk)，arg0 = sk）
bpftrace -e 'kprobe:inet_csk_listen_start { @[comm] = count(); }'

# 12.2 完成三次握手的连接数（SYN 队列 → accept 队列）
bpftrace -e 'kprobe:tcp_v4_syn_recv_sock { @[comm] = count(); }'
```

容器逃逸/提权检测是 Falco 那类工具的领域（它们就是 BPF 的 LSM/ tracepoint 应用），
不建议用单行命令手搓。

---

## 13. vLLM / 推理服务专用配方

> 前提：vLLM 跑在容器里，bpftrace 用 §1.2 的旁路容器 + `--pid=host`。
> 先 `pgrep -f vllm` 拿宿主 PID。

### 13.1 引擎进程在烧 CPU 还是空转

> **实测修正（2026-11-07）**：bpftrace 0.17 的 `-p` **不会**给 `profile` 探针加 pid 过滤。
> 只写 `-p "$PID"` 会采到全系统——`swapper/*`、`dockerd`、`containerd` 全混进来
> （实测第一次跑，idle 的样本数比 python 还多）。**必须显式加 `/pid == $PID/`。**

```bash
PID=$(pgrep -f "python /out/sim_rounds.py" | head -1)

# on-CPU：确认采样确实落在这个进程上（正常输出只应该有 python 一行）
bpftrace -p "$PID" -e "profile:hz:99 /pid == $PID/ { @[comm] = count(); }"

# 内核侧：空栈占比 = 用户态时间；非空栈才是 syscall / 缺页 / 调度
bpftrace -p "$PID" -e "profile:hz:99 /pid == $PID/ { @[kstack] = count(); }"
```

**怎么读**（`sim-int:dry-run` + `sim_rounds.py`，697 个采样点的实测结果）：

| 输出 | 含义 |
| :-- | :-- |
| `@on[python]: 697` | 采样全部落在目标进程，过滤生效 |
| `@kstack[]: 662`（95.0%） | **在用户态跑**，没有内核栈 |
| 非空栈 35 个 | 5%：缺页 9、mmap/munmap/exit 8、read 4、openat 3、调度 1 |

结论：引擎初始化阶段是**用户态 CPU 密集**——内核态只有模型文件读取（overlayfs +
virtiofs）和内存映射，没有等 IO、没有等锁。这种「在算还是在等」的判断，
`profile` + `@[comm]` 一句话就能给。

两个配套事实：

- 目标进程有 **8 个线程**（`ls /proc/$PID/task | wc -l`），`-p` + `/pid ==/` 覆盖全部线程。
- **`ustack` 在这个环境里不可用**：输出全是 `0xffff...` 裸地址，还有
  `ERROR: failed to look up stack id -17`，所以 vLLM 的 Python 层没法靠 bpftrace 看，
  得换 `py-spy`（见 §14）。

复现脚本与原始采样：`assets/bpf-vllm-trace/`（`run.sh` / `trace.sh` / `RESULTS.md`）。

对照 `../vllm架构笔记/实验C` 的记录：空跑时 Triton CPU 后端 JIT 会让进程
**连续 60s 占满一个核**，`profile` 上会看到 `comm` 稳定增长；但 Python 栈看不到
`make_asm`，得靠 `py-spy` 或 `TRITON_CACHE_DIR` 直接规避。

### 13.2 调度线程的等待时间（异步调度 / 多进程）

```bash
# 唤醒延迟：调度器线程被唤醒后，多久才真正拿到 CPU
bpftrace -q -e '
tracepoint:sched:sched_wakeup { @w[args->pid] = nsecs; }
tracepoint:sched:sched_switch /@w[args->next_pid]/ {
  @us[args->next_comm] = hist((nsecs - @w[args->next_pid]) / 1000);
  delete(@w[args->next_pid]);
}
END { clear(@w); }'
```

hist 的 `[0,1)`、`[1,2)`、`[2,4)` … 如果主体落在 `[64,128)` 以上，
说明 CPU 已经超卖，**调度延迟会直接反映成 TTFT 抖动**。

### 13.3 KV cache offload / 换页的 IO 延迟

```bash
# 进程级 read/write 耗时
bpftrace -p "$PID" -q -e '
kprobe:vfs_read { @s[tid] = nsecs; }
kretprobe:vfs_read /@s[tid]/ {
  @us[comm] = hist((nsecs - @s[tid]) / 1000);
  delete(@s[tid]);
}
END { clear(@s); }'
```

换 `vfs_write` 看写。如果直方图长尾明显（> 10ms），说明 KV 换出被存储卡住了，
这时候扩带宽或加本地盘才有意义，调调度参数没用。

### 13.4 P/D 分离的 KV 传输

```bash
# 发送量 by 进程（NIXL / RDMA 走 TCP 回退时才有意义）
bpftrace -e 'kprobe:tcp_sendmsg { @bytes[comm] = sum(arg2); }'

# 重传（RDMA 不走这里，只有 TCP 回退能看到）
bpftrace -e 'kprobe:tcp_retransmit_skb { @[comm] = count(); }'
```

> RDMA / NIXL 的传输在用户态驱动里，**bpftrace 看不到**，
> 这类要走 `ibstat`、`perfquery`、厂商计数器。

### 13.5 和 vLLM 自己的 metrics 对齐

bpftrace 是**系统层**的尺子，vLLM metrics 是**请求层**的尺子，两者要对齐才有结论：

| 现象（vLLM metrics） | 先用 bpftrace 排除 |
| :-- | :-- |
| `queue_time` 高、`prefill_time` 正常 | §4.6 唤醒延迟 / CPU 超卖 |
| `prefill_time` 高 | §13.1 是否在 JIT / 缺页（§5.1） |
| `decode` 每步抖动 | §4.7 off-CPU（等锁/等 IO）+ §8 网络 |
| 吞吐上不去、CPU 不满 | §5.2 分配热点、§4.8 软中断、`vfs` 长尾 |

---

## 14. 火焰图：别硬用 bpftrace

bpftrace 的 `@[ustack] = count()` 输出是 `@[ ... 多行栈 ... ]: 42` 的形式，
要转成 flamegraph.pl 吃的 folded 格式得自己写转换，而且 Python 栈没有函数名。
**实践建议**：

| 场景 | 工具 |
| :-- | :-- |
| native / C++ 程序 | `perf record -g` + `perf script` + FlameGraph |
| Python 程序（含 vLLM 的 Python 层） | `py-spy record -o out.svg --pid <PID>` |
| 内核路径 | BCC `profile -af 10 > out.folded` + `flamegraph.pl` |
| off-CPU | BCC `offcputime -f -p <PID>` + `flamegraph.pl` |
| 单点计数 / 分布 | **bpftrace**（本文档） |

一句话：**bpftrace 强在「定向问一个问题」，不强在「全景火焰图」。**

---

## 15. 与 BCC 工具的对照

书里两个附录（D 的 bpftrace one-liners 和 B 的 BCC 工具）解决的是同一批问题，
记住这个映射，排查时少纠结用哪个：

| 需求 | bpftrace 写法 | BCC 工具 |
| :-- | :-- | :-- |
| on-CPU 火焰图 | `profile:hz:99 { @[ustack]=count() }` | `profile -af 10` |
| off-CPU 火焰图 | §4.7 | `offcputime -f` |
| 调度延迟 | §4.6 | `runqlat` / `runqlen` |
| syscall 计数 | §3.1 | `syscount` |
| 慢 syscall | §9.3 | `syscount -L` |
| 文件读写 top | §6.1 | `filetop` |
| 谁打开文件 | §3.3 | `opensnoop` |
| 块层延迟 | §7.4 | `biolatency` |
| 块层事件 | §7.1 | `biosnoop` |
| 文件系统延迟 | §6.3 | `ext4slower` / `xfsdist` |
| TCP 重传 | §8.3 | `tcpretrans` |
| 连接追踪 | §8.5 | `tcplife` / `tcpstates` |
| 内存分配 | §5.3 | `memleak` / `kmalloc` |
| 缺页 | §5.1 | `cachestat` |
| 进程创建 | §3.2 | `execsnoop` |
| CPU 频率/降频 | — | `cpufreq` |

---

## 16. 坑清单（都是实测踩过的）

1. **退出时 map 会全部打印**。中间态的 `@start[tid] = nsecs` 会混进结果，
   结尾加 `END { clear(@start); }`。
2. **0.17 的 `print()` 必须带参数**，`print()` 无参会直接语法错误（实测）；
   要打多个 map 就逐个 `print(@x)`。
3. **`comm` 只有 15 字符**。vLLM 的线程名基本都会被截断，定位靠 `-p` + `pid`。
4. **kprobe 参数随内核版本变**。优先用 `tracepoint`（ABI 稳定），
   其次 kprobe + `args->`（有 BTF 时可靠），最后才是裸 `arg0`。
5. **inline 函数挂不上**。实测 6.10 上 `kprobe:__kmalloc` 直接告警
   “not traceable”，改用 `__kmalloc_noprof` 才行；`kmalloc_trace` 则是
   **挂载时**才报 `cannot attach kprobe, Invalid argument`。
   先用 `bpftrace -l 'kprobe:*kmalloc*'` 查实际符号，再写脚本。
6. **采样会丢事件**。`-B none` 丢得更狠；高频探针（`sys_enter_*`）要限时使用。
7. **verifier 限制**：循环必须可证明有界、栈 512B、单程序指令数有上限。
   写复杂逻辑时用 `unroll()` 而不是 `while`。
8. **容器里必须 `--privileged --pid=host` 并挂 tracefs**，
   否则 `-p` 找不到进程、`-l` 列不出探针。
9. **Docker Desktop 追踪的是 LinuxKit 虚拟机**，不是 macOS。macOS 上的进程
   完全看不到；好在 vLLM 容器也在这个 VM 里，所以能追。
10. **`--unsafe` 才允许** `system()`、`override()`、`signal()`。默认禁用是好事。
11. **符号缺失先查内核配置**：`kptr_restrict` 非 0、`perf_event_paranoid` 过高、
   容器 seccomp 拦截，都会表现为「探针挂不上」。
12. **别把 bpftrace 当长期监控**。它是交互式诊断工具；要常驻采集用
    Prometheus exporter（如 `ebpf_exporter`）或 BCC 的 `*stat` 类工具。
13. **`-p` 不过滤 `profile` 探针**（0.17 实测）。采样探针是 per-CPU 的，
    `-p` 只负责「目标进程退出时跟着退出」和 uprobe 的二进制定位；
    要把样本限制在目标进程，必须自己写 `/pid == N/`。
    第一次跑 §13.1 时没加，结果 `swapper/*` 的样本数（530–1383/CPU）把 python（1437）
    淹没了一半，看起来像"空跑把机器压满了"，其实是 idle 也在被采样。
14. **`ustack` 在该环境不可用**。Python 进程的用户栈输出全是裸地址
    （`0xffff...`）外加 `failed to look up stack id`，需要 frame pointer 或
    内核/perf 的 unwind 支持。看 Python 层请直接上 `py-spy`。

---

## 17. 下一步

- [x] 在 `sim-int:dry-run` 镜像里装 bpftrace，跑一次 §13.1，确认能追到 vLLM 进程。
  **已完成（2026-11-07）**：697 个采样点全落在 python 上，95% 是用户态执行；
  同时发现 `-p` 不过滤 `profile` 探针、`ustack` 不可用。见 `assets/bpf-vllm-trace/RESULTS.md`。
- [ ] 用 §4.6 量化空跑环境下的调度延迟，和 `实验D` 的 TTFT 抖动对齐。
- [ ] 把 §15 的对照表补成「vLLM 场景 → 首选工具」决策树。
