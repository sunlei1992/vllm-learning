# 实验B — vLLM 原生 simulator（PR #47922）跑通与 60s 停顿排查

> 日期：2026-10-26
> 目标：在本地（Mac M3 / 无 NPU）跑通 vLLM 的 `--simulate-forward`，
> 让真实 Scheduler/KVCacheManager 在没有模型计算、没有 GPU 的情况下跑起来。
> 相关：`../../AGENTS.md` 的「vLLM 原生 simulator 实验环境」。

---

## 1. 这是什么

PR [vllm#47922](https://github.com/vllm-project/vllm/pull/47922) 给 vLLM 加了一个模拟前向模式：

- 模型建在 `meta` device，**不下载/不加载权重**
- KV cache 只算容量，**不分配 tensor**（`--kv-cache-memory-bytes` 指定虚拟大小）
- 输出 token 来自 **trace replay**（`SamplingParams.trace_decode_token_ids`）
- 除了 `execute_model` 里的 forward，其余（API server / EngineCore / Scheduler /
  Executor / Worker / ModelRunner 的记账逻辑）全是真代码

后续 [vllm#61305](https://github.com/vllm-project/vllm/issues/61305) RFC 计划给它加**时间模型**
（`TimingProvider` + 虚拟时钟），那时才能回答 TTFT/TPOT 这类性能问题。

> 注意：#47922 **尚未合并**（2026-10-26 状态：open，来自 `sagearc/vllm` fork），
> 所以任何 release 里都没有，只能打 patch 或拉分支。

---

## 2. 为什么 macOS 原生不行

跑起来会卡在第一个 Triton kernel：

```
File "vllm/v1/worker/gpu/buffer_utils.py", line 215, in apply_write
    _apply_write_kernel[(n,)](
TypeError: 'function' object is not subscriptable
```

MRV2（Model Runner V2）在 `buffer_utils` / `input_batch` / `block_table` 里用了十几个
Triton kernel，而 `triton-cpu` **只发布 Linux wheel**（x86_64 / aarch64），没有 macOS。

结论：**macOS 上无解**，必须 Linux。

---

## 3. Docker 方案（linux/arm64）

最终可用的路径：Docker Desktop + `linux/arm64` 容器。

### 3.1 代码

- `tmp/vllm-030` 建分支 `sim`（基于 `a98247ab`），提交 `16ab166382`
- #47922 的 diff 13 个文件，11 个干净应用，2 个手工处理：
  - `vllm/engine/arg_utils.py`：`create_model_config` 插入 `simulate_forward` 的量化跳过逻辑
  - `vllm/model_executor/model_loader/base_loader.py`：meta device 跳过 `process_weights_after_loading`
- 本地还放宽了 `_validate_v2_model_runner` 的 Triton 守卫（只为实验，带 `LOCAL-EXPERIMENT` 注释）

### 3.2 依赖坑（按踩坑顺序）

| 问题 | 现象 | 解法 |
| :-- | :-- | :-- |
| apt 源 | `deb.debian.org` 502 | 换 `mirrors.aliyun.com` |
| GitHub 下载慢 | triton-cpu 241MB 只有 ~160KB/s | 换 `ghfast.top`，~17MB/s |
| PyPI torch 拉 CUDA 依赖 | aarch64 上 `torch==2.13.0` 依赖 `nvidia-*` 数 GB | 用 PyTorch CPU index 或阿里云 `pytorch-wheels/cpu` 的 `+cpu` wheel |
| CMake 拉 ACL | `arm_compute` clone 卡死 | 宿主机 clone `ComputeLibrary v52.6.0`，挂载 + `ACL_ROOT_DIR` |
| CMake 拉 oneDNN | `onednn-populate` clone 失败 | 宿主机 fetch 指定 commit `9c5be1cc`，`FETCHCONTENT_SOURCE_DIR_ONEDNN` |
| 编译 OOM | `cc1plus: Killed signal` | `MAX_JOBS=2`（Docker 内存只有 7.6GB） |
| 缺系统头 | `numa.h: No such file` | `apt install libnuma-dev` |
| torchvision 不匹配 | `operator torchvision::nms does not exist` | 换 `torchvision==0.28.0+cpu` |
| torchaudio 不匹配 | `Could not load lib/_torchaudio.abi3.so` | 换 `torchaudio==2.11.0+cpu` |
| torchcodec 是 CUDA 版 | `libnvrtc.so.13 not found` | 换 `torchcodec==0.17.0+cpu` |
| shm 太小 | `Insufficient space in /dev/shm` | `--shm-size=16g` |

### 3.3 一键复现

```bash
./tmp/sim_forward_run.sh
```

内部：挂载 `tmp/`（wheel）、`models/`、`tmp/triton-cache`，在镜像 `sim-built` 里跑 `tmp/sim_smoke.py`。

---

## 4. 冒烟结果

```text
Using 2.0 GiB simulated KV cache memory for virtual KV cache.
CPU KV cache size: 18,688 tokens, Maximum concurrency for 2,048 tokens per request: 9.12x
Initialized virtual KV cache with 1 groups and 146 blocks; skipped KV tensor allocation.
Model loading took 0.01 GiB memory and 0.423034 seconds

[sim] engine init: 11.70s
[sim] generate: 0.26s
[sim] token_ids: [100, 101, 102, 103, 104, 105, 106, 107]
[sim] total: 11.95s
```

三个关键证据：

1. `Model loading took 0.01 GiB` → 没有加载权重
2. `skipped KV tensor allocation` + `146 blocks` → KV 是虚拟的
3. `token_ids == [100..107]` → 输出完全来自注入的 trace，forward 确实被绕过

---

## 5. 60 秒停顿排查（本次最有价值的结论）

### 5.1 现象

单次 generate 耗时约 148 秒，日志里两次：

```
shm_broadcast.py:874 No available shared memory broadcast block found in 60 seconds.
```

### 5.2 定位

| 步骤 | 观察 |
| :-- | :-- |
| py-spy 抓 EngineCore | 卡在 `MultiprocExecutor._wait_for_response` → `rpc_broadcast_mq.dequeue()`，在等 worker |
| 看进程 CPU | `VLLM::Worker` **99.9% CPU**，不是阻塞 |
| py-spy 抓 Worker | `apply_write` → `triton/runtime/jit.py:764` → `compile` → `cpu/compiler.py:make_asm` |
| 看 Triton 缓存 | 卡住期间从 76KB 涨到 1.7MB，**正在编译 kernel** |

### 5.3 根因

`triton-cpu` 的 kernel 是**首次调用时 JIT 编译**的（MLIR → LLVM → asm → `.so`）。
MRV2 的 `apply_staged_writes` 首次触发 `_apply_write_kernel`，在 aarch64 容器里约 60 秒/个，
两个 kernel 就是两次 60 秒警告。

> 那条 `shm_broadcast` 日志只是**误导性提示**：它只说"读者等太久了"，
> 真正的原因在 worker 的 CPU 侧。

### 5.4 解决

把 Triton 的磁盘缓存挂到持久目录：

```bash
export TRITON_CACHE_DIR=/triton-cache   # 挂载宿主机的 tmp/triton-cache
```

效果（同一容器连跑两次）：

| 运行 | generate |
| :-- | :-- |
| 冷缓存 | 146.32s |
| 热缓存 | **0.26s** |

缓存大小只有 6.6MB。`tmp/sim_forward_run.sh` 已默认挂载。

---

## 6. 现在能做什么

| 能力 | 状态 |
| :-- | :-- |
| 真 Scheduler 跑在 CPU 上 | ✅ |
| 无需模型权重 / NPU | ✅ |
| 单次请求 < 1s（热缓存） | ✅ |
| 注入指定输出 token 序列 | ✅（trace replay） |
| 逐 step batch 组成 + KV block 占用 | ✅（`tmp/sim_rounds.py`） |
| 排队 / 抢占路径 | ✅（`tmp/sim_kv_stress.py`，7 次抢占） |
| 参数扫描（预算 × 并发） | ✅（`tmp/sim_sweep.py`，12 组） |
| 性能数字（TTFT/TPOT） | ❌ 需要 #61305 的 timing model |
| vllm-ascend 的 connector | ❌ 官方 simulator 不覆盖 |

适合：调度策略对比、chunked prefill 行为、prefix cache 命中、抢占逻辑。
不适合：算子/数值正确性、通信、显存实测。

---

## 7. 多请求与 step 级观测（2026-10-26 追加）

### 7.1 关键技巧：进程内模式

Scheduler 默认跑在 EngineCore 子进程里，主进程 monkey-patch 不到。开启：

```bash
export VLLM_ENABLE_V1_MULTIPROCESSING=0
```

之后 `Scheduler` 就在主进程里，可以直接包一层：

```python
from vllm.v1.core.sched.scheduler import Scheduler

_orig = Scheduler.schedule
def _schedule(self, *a, **k):
    out = _orig(self, *a, **k)
    steps.append({
        "reqs": len(out.num_scheduled_tokens),
        "tokens": sum(out.num_scheduled_tokens.values()),
        "new": len(out.scheduled_new_reqs),
        "running": len(self.running),
        "waiting": len(self.waiting),
        "preempted": len(out.preempted_req_ids or ()),
    })
    return out
Scheduler.schedule = _schedule
```

脚本：`tmp/sim_steps.py`，跑法：`./tmp/run_in_container.sh sim_steps.py`。

### 7.2 结果（`max_num_batched_tokens=64`，4 个请求）

```text
[steps] generate 0.23s over 4 requests
[steps] total scheduler steps: 7
  step  0: reqs=2 tokens= 64 new=2 running=2 waiting=2 preempted=0
  step  1: reqs=2 tokens= 64 new=0 running=2 waiting=2 preempted=0
  step  2: reqs=1 tokens= 64 new=0 running=1 waiting=2 preempted=0
  step  3: reqs=1 tokens= 64 new=0 running=1 waiting=2 preempted=0
  step  4: reqs=3 tokens= 64 new=2 running=3 waiting=0 preempted=0
  step  5: reqs=3 tokens=  8 new=0 running=3 waiting=0 preempted=0
  step  6: reqs=1 tokens=  1 new=0 running=1 waiting=0 preempted=0
[steps] peak tokens/step=64, avg reqs/step=1.86
```

能直接读出来的现象：

| 现象 | 解释 |
| :-- | :-- |
| step 0–3 都是一个长请求在吃满 64 token | **chunked prefill**：长 prompt 被切成 4 段 |
| step 2–3 `running=1, waiting=2` | 另外两个请求在排队等 token 预算 |
| step 4 一次进来 2 个新请求 | 长请求 prefill 结束后，预算释放 |
| step 6 只剩 1 个请求 1 token | decode 尾巴，典型的 batch 收缩 |
| `avg reqs/step=1.86` | batch 利用率很低（预算太小 + 长度差异大） |

### 7.3 冷/热缓存对多请求的影响

| 场景 | generate |
| :-- | :-- |
| 新 workload 首次（新 kernel 形状） | 48.55s |
| 同一 workload 再跑 | **0.23s** |

说明：**每换一种 batch 形状，可能触发新的 Triton JIT**；实验脚本要固定 workload，
或者先跑一遍预热。

---

## 8. 多轮实验：batch 组成与 KV block（2026-10-26 追加）

同一个引擎实例连续 `llm.generate()`，每轮 workload 不同，观察调度行为。

脚本：`tmp/sim_rounds.py`；跑法：`./tmp/run_in_container.sh sim_rounds.py`。
配置：`max_num_batched_tokens=64`、`max_num_seqs=4`、`enable_prefix_caching=False`（便于解释 KV）。

### 8.1 三轮汇总

| 轮次 | workload | steps | 调度 token | KV 峰值 | 耗时 |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 0 | 2 个短请求 | 2 | 5 | 2 / 145 | 0.219s |
| 1 | 1 个长请求（~301 token） | 6 | 302 | 3 / 145 | 0.002s |
| 2 | 4 个短请求 | 2 | 8 | 4 / 145 | 0.002s |

> 第 0 轮的 0.219s 包含一次性预热；之后每轮 2ms 量级。

### 8.2 逐 step 观测

```text
[round 0] reqs=2 steps=2 tokens=5 peak_kv=2/145 time=0.219s
  r0: reqs=2 tokens=  3 new=2 prefill=2 chunk=0 decode=0 kv=  2
  r0: reqs=2 tokens=  2 new=0 prefill=0 chunk=0 decode=2 kv=  2

[round 1] reqs=1 steps=6 tokens=302 peak_kv=3/145 time=0.002s
  r1: reqs=1 tokens= 64 new=1 prefill=1 chunk=0 decode=0 kv=  1
  r1: reqs=1 tokens= 64 new=0 prefill=0 chunk=1 decode=0 kv=  1
  r1: reqs=1 tokens= 64 new=0 prefill=0 chunk=1 decode=0 kv=  2
  r1: reqs=1 tokens= 64 new=0 prefill=0 chunk=1 decode=0 kv=  2
  r1: reqs=1 tokens= 45 new=0 prefill=0 chunk=1 decode=0 kv=  3
  r1: reqs=1 tokens=  1 new=0 prefill=0 chunk=0 decode=1 kv=  3

[round 2] reqs=4 steps=2 tokens=8 peak_kv=4/145 time=0.002s
  r2: reqs=4 tokens=  4 new=4 prefill=4 chunk=0 decode=0 kv=  4
  r2: reqs=4 tokens=  4 new=0 prefill=0 chunk=0 decode=4 kv=  4
```

### 8.3 能读出的东西

| 现象 | 结论 |
| :-- | :-- |
| r1 前 5 步全是 prefill/chunk | 长请求被 `max_num_batched_tokens=64` 切成 4×64 + 45 |
| r1 的 `kv` 从 1 → 2 → 3 | **KV block 随 prefill 推进逐块分配**（block=128 token） |
| r0/r2 只有 prefill 1 步 + decode 1 步 | 短请求一轮就 prefill 完 |
| 每轮第一个 step 的 `kv` 等于本轮请求数 | 上一轮结束后 **block 已释放**（round 1 从 1 开始，而不是接着 round 0 的 2） |
| `waiting` 始终为 0 | `max_num_seqs=4` ≥ 每轮请求数，没有排队 |
| `preempted` 始终为 0 | KV 只用了 4/145，远未触发抢占 |

### 8.4 这个实验的价值

- 证明**同一引擎实例多轮**可用（模拟服务化场景，而不是每次都重启引擎）
- `kv_used` 是**真实调度器**算出来的 block 占用，不是估算
- 想看到抢占/排队，需要把 `kv_cache_memory_bytes` 调小、或让并发超过 `max_num_seqs`

## 9. KV 压力实验：排队与抢占（2026-10-26 追加）

前面的实验 KV 只用了 4/145，抢占路径从没被触发。这一节把 KV 压到 8 个 block，
观察调度器的准入控制和抢占。

脚本：`tmp/sim_kv_stress.py`（可调 `KV_MB / N_REQS / PROMPT_REP / MAX_SEQS /
MAX_BATCHED / MAX_TOKENS / MAX_MODEL_LEN`）。

### 9.1 第一次尝试：只排队，不抢占

`KV_MB=256`（17 blocks）、8 个 ~500 token 的长 prompt：

```text
[stress] kv_blocks=17 steps=11 peak_kv=16/17 max_waiting=6 preemptions=0
  step 0: reqs=2 tokens=512 new=2 running=2 waiting=6 kv=5/17
  step 1: reqs=3 tokens=512 new=1 running=3 waiting=5 kv=9/17
  ...
  step 7: reqs=4 tokens=504 new=1 running=4 waiting=0 kv=16/17
```

**结论**：vLLM 的准入控制是"没 block 就不放进来"，所以请求在 `waiting` 里排队，
不会出现"先放进来再抢占"。

### 9.2 触发抢占：让运行中的请求自己长大

抢占需要**已运行的请求在 decode 过程中需要新 block，而池子正好空了**。
所以改成：短 prompt + 长输出 + 小 KV。

配置：

| 参数 | 值 |
| :-- | :-- |
| `kv_cache_memory_bytes` | 128 MiB（8 blocks） |
| `max_model_len` | 1024（必须 ≤ 8×128，否则启动就报 KV 不足） |
| 请求数 | 8 个短 prompt |
| `max_tokens` | 300 |
| `max_num_seqs` | 8 |
| `max_num_batched_tokens` | 512 |

结果：

```text
[stress] kv_blocks=8 steps=564 time=0.353s
[stress] peak_kv=8/8 max_waiting=6 preemptions=7
```

### 9.3 抢占发生的那一步

```text
step 124: reqs=8 tokens=8 decode=8 running=8 waiting=0 preempted=0 kv=8/8
step 125: reqs=8 tokens=8 decode=8 running=8 waiting=0 preempted=0 kv=8/8
step 126: reqs=8 tokens=8 decode=8 running=8 waiting=0 preempted=0 kv=8/8
step 127: reqs=4 tokens=4 decode=4 running=4 waiting=4 preempted=4 kv=8/8   ← 抢占
step 128: reqs=4 tokens=4 decode=4 running=4 waiting=4 preempted=0 kv=8/8
```

解释：

1. 8 个请求各占 1 个 block，正好 8/8
2. 第 128 个 token 之后，每个请求都需要**第 2 个 block**（block = 128 token）
3. 池子没有空闲 block → 调度器**抢占 4 个**（优先级最低的），放回 `waiting`
4. 腾出的 block 给剩下 4 个请求各分配第 2 块，于是仍是 8/8
5. 后续又发生了 2 次 + 1 次抢占，共 **7 次**

### 9.4 这验证了什么

| 机制 | 观察 |
| :-- | :-- |
| 准入控制 | 无 block 时请求在 `waiting` 排队，不进入 `running` |
| 抢占触发条件 | **运行中请求需要新 block 且池子为空** |
| 抢占粒度 | 按请求抢占（不是按 block），一次可以抢多个 |
| 抢占后行为 | 请求回到 `waiting`，之后重新 prefill（recompute，非 swap） |
| 抢占的必要性 | `max_num_seqs=8` 时，8 个请求恰好占满 8 blocks，必然发生 |

### 9.5 冷/热缓存

| 场景 | 耗时 |
| :-- | :-- |
| 首次（新形状，含 JIT） | 47.899s |
| 同形状再跑 | **0.353s**（564 步，约 0.6ms/步） |

## 10. 参数扫描：`max_num_batched_tokens` × `max_num_seqs`（2026-10-26 追加）

固定 workload，只动两个调度参数，看调度行为怎么变。
脚本：`tmp/sim_sweep.py`。

### 10.1 实验设置

| 项 | 值 |
| :-- | :-- |
| workload | 8 个请求，长度从 1 token 到 ~500 token（`"Hello"`、`"Hello "*10/50/200/400/800`、两个短请求） |
| 输出 | `max_tokens=8`（固定 trace） |
| KV | 2 GiB（145 blocks），**故意给足**，避免抢占干扰 |
| 扫描 | `max_num_batched_tokens` ∈ {64,128,256,512} × `max_num_seqs` ∈ {2,4,8} |
| 其他 | `enable_prefix_caching=False`，进程内模式 |

### 10.2 结果

| batched | seqs | steps | avg_reqs | peak_tok | prefill | chunk | decode | max_waiting | preempt | gen_s |
|---|---|---|---|---|---|---|---|---|---|---|
| 64 | 2 | 50 | 1.7 | 64 | 6 | 21 | 25 | 6 | 0 | 0.23 |
| 64 | 4 | 35 | 2.49 | 64 | 4 | 23 | 10 | 4 | 0 | 0.012 |
| 64 | 8 | 31 | 2.81 | 64 | 4 | 23 | 7 | 4 | 0 | 0.012 |
| 128 | 2 | 41 | 1.8 | 128 | 6 | 10 | 26 | 6 | 0 | 0.013 |
| 128 | 4 | 25 | 3.0 | 128 | 4 | 11 | 12 | 4 | 0 | 0.011 |
| 128 | 8 | 19 | 3.95 | 128 | 4 | 11 | 7 | 4 | 0 | 0.010 |
| 256 | 2 | 36 | 1.89 | 256 | 6 | 4 | 27 | 6 | 0 | 0.012 |
| 256 | 4 | 20 | 3.45 | 256 | 4 | 5 | 13 | 4 | 0 | 0.010 |
| 256 | 8 | 13 | 5.31 | 256 | 4 | 5 | 7 | 4 | 0 | 0.009 |
| 512 | 2 | 34 | 1.94 | 512 | 5 | 2 | 27 | 6 | 0 | 0.013 |
| 512 | 4 | 18 | 3.67 | 512 | 3 | 2 | 14 | 4 | 0 | 0.009 |
| 512 | 8 | 10 | 6.60 | 512 | 3 | 2 | 7 | 3 | 0 | 0.008 |

引擎 init 每次 1.5–5.8s（每次组合重建引擎）；12 组 generate 合计仅 **0.349s**。

### 10.3 趋势

| 观察 | 数据 |
| :-- | :-- |
| **步数随预算/并发下降** | 50 → 10 步（**5 倍**） |
| **平均并发随预算/并发上升** | 1.70 → 6.60 reqs/step（**3.9 倍**） |
| **chunked prefill 步数骤降** | 21 → 2（预算够大后长 prompt 一步装下） |
| **decode-only 步数基本恒定** | 7–8 步（受 `max_tokens=8` 限制） |
| **排队减少** | max_waiting 6 → 3 |
| **KV 峰值随并发上升** | 8 → 18 blocks |
| **预算总被吃满** | 每行 `peak_tok` 都正好等于预算 |

### 10.4 一个重要结论（也是局限）

- 参数越大 → 步数越少、并发越高 → **吞吐潜力更大**
- 但每步处理的 token 也更多 → **单步延迟更长**
- 模拟器**没有时间模型**，所以这里只能说"调度行为变了"，**不能**说"端到端更快"

要回答"哪个配置更好"，需要 #61305 的 `StepCost`：给 prefill / chunk / decode 分别定价。
这正是下一步（见待办）。

## 11. 待办

1. ✅ 多请求 + step 级观测（`tmp/sim_steps.py`）
2. ✅ 多轮实验 + KV block 观测（`tmp/sim_rounds.py`）
3. ✅ 参数扫描（`tmp/sim_sweep.py`）：预算/并发 ↑ → 步数 50→10，chunk 21→2，avg_reqs 1.7→6.6
4. ✅ KV 压力实验：调小 `kv_cache_memory_bytes` + 长输出，触发排队与抢占（`tmp/sim_kv_stress.py`）
5. 如需时间维度，按 #61305 的 `StepDescriptor → StepCost` 自己实现一个最简 `TimingProvider`
6. 关注 #47922 的合并进度；合并后可以去掉本地 patch

---

## 12. 参考

- PR #47922: https://github.com/vllm-project/vllm/pull/47922
- RFC #61305: https://github.com/vllm-project/vllm/issues/61305
- trace replay 前置 PR #46701（2026-08-20 合入 main）
- 相关外部工作：Vidur、Frontier、BLIS（llm-d）、SimAI
