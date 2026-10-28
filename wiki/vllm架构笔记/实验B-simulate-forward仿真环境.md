# 实验B — vLLM 原生 simulator（PR #47922）跑通与 60s 停顿排查

> 代号：**空跑**（dry run）——引擎照跑、模型不真算（`--simulate-forward`，PR #47922）
> 日期：2026-10-26
> 目标：在本地（Mac M3 / 无 NPU）跑通 vLLM 的 `--simulate-forward`，
> 让真实 Scheduler/KVCacheManager 在没有模型计算、没有 GPU 的情况下跑起来。
> 相关：`../../AGENTS.md` 的「vLLM 原生 simulator 实验环境」。
> 全部实验脚本归档在 [`assets/simulate-forward/`](assets/simulate-forward/README.md)；
> 开发时同一份脚本也放在 `tmp/`（已被 `.gitignore` 忽略，不入库）。

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
./assets/simulate-forward/sim_forward_run.sh
```

内部：挂载 `tmp/`（wheel）、`models/`、`tmp/triton-cache`，在镜像 `sim-built` 里跑 `assets/simulate-forward/sim_smoke.py`。

镜像从零构建的逐层命令（apt 换源、torch `+cpu` wheel、ACL/oneDNN 预取、`MAX_JOBS=2` 等）
见 [`assets/simulate-forward/DOCKER.md`](assets/simulate-forward/DOCKER.md)。

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

缓存大小只有 6.6MB。`assets/simulate-forward/sim_forward_run.sh` 已默认挂载。

---

## 6. 现在能做什么

| 能力 | 状态 |
| :-- | :-- |
| 真 Scheduler 跑在 CPU 上 | ✅ |
| 无需模型权重 / NPU | ✅ |
| 单次请求 < 1s（热缓存） | ✅ |
| 注入指定输出 token 序列 | ✅（trace replay） |
| 逐 step batch 组成 + KV block 占用 | ✅（`assets/simulate-forward/sim_rounds.py`） |
| 排队 / 抢占路径 | ✅（`assets/simulate-forward/sim_kv_stress.py`，7 次抢占） |
| 参数扫描（预算 × 并发） | ✅（`assets/simulate-forward/sim_sweep.py`，12 组） |
| 前缀缓存命中 | ✅（`assets/simulate-forward/sim_prefix.py`，prefill -60%） |
| 时间模型（TTFT/TPOT） | ✅（`sim_timing.py`，初版、未标定） |
| 策略对比（FCFS/短优先/长优先） | ✅（`sim_policy.py`，makespan 不变、延迟重新分配） |
| 加载 vllm-ascend main（无 NPU） | ✅（`va/run_va_dry_run.sh`，见 [004](../ascend对照笔记/004-在空跑环境加载vllm-ascend.md)） |
| 复刻 VA 短请求优先策略 | ✅（`sim_srs.py` / `sim_srs_arrivals.py`，短请求 -50%~-69%） |
| 迁移到 vLLM v0.30.0（含 VA 0.30） | ✅（`sim030:*`，见 [005](../ascend对照笔记/005-空跑迁移到v0.30.md)） |
| 在线模式（HTTP server） | ✅（`server/run_server.sh`，trace 必带、并发隔离） |
| MLA 模型（V2 风格） | ✅（`sim_mla.py`，38,836 blocks；V4 未验证） |
| GLM-5.3（78 层 DSA+MoE） | ✅（`glm53/run_glm53.sh`，1,493 blocks；main 与 0.30 结果一致） |
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

脚本：`assets/simulate-forward/sim_steps.py`，跑法：`./assets/simulate-forward/run_in_container.sh sim_steps.py`。

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

脚本：`assets/simulate-forward/sim_rounds.py`；跑法：`./assets/simulate-forward/run_in_container.sh sim_rounds.py`。
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

脚本：`assets/simulate-forward/sim_kv_stress.py`（可调 `KV_MB / N_REQS / PROMPT_REP / MAX_SEQS /
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
脚本：`assets/simulate-forward/sim_sweep.py`。

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

## 11. 前缀缓存（prefix cache）（2026-10-26 追加）

前面所有实验都显式关了前缀缓存（`enable_prefix_caching=False`），这一节补上。

### 11.1 设置

| 项 | 值 |
| :-- | :-- |
| workload | 8 个**依次**发送的请求，共享同一个系统提示词，各自接不同问题 |
| prompt | `"You are a helpful assistant. " * 60 + "Question i: ..."`，共 **371 token** |
| 预算 | 两种：`max_num_batched_tokens=512`（宽松）和 `128`（紧张） |
| 对比 | `enable_prefix_caching=False` vs `True` |
| 输出 | `max_tokens=2` |

脚本：`assets/simulate-forward/sim_prefix.py`（`MAX_BATCHED` 可调）。

### 11.2 结果（预算 512）

```text
=== OFF ===
i  prompt  cached  first_sched  prefill  steps  kv_peak
0     371       0          371     371      2        3
...
computed prefill tokens: 2968 / 2968 (100.0%)

=== ON ===
i  prompt  cached  first_sched  prefill  steps  kv_peak
0     371       0          371     371      2        3
1     371     256          115     115      2        3
2     371     256          115     115      2        3
...
computed prefill tokens: 1176 / 2968 (39.6%)
```

### 11.3 结果（预算 128）

```text
=== OFF ===
  ...  first_sched=128  prefill=371  steps=4   # 128+128+115 + 1 decode
computed prefill tokens: 2968 / 2968 (100.0%)

=== ON ===
0    371       0          128     371      4
1    371     256          115     115      2   # 命中后只需 1 个 prefill step
...
computed prefill tokens: 1176 / 2968 (39.6%)
```

### 11.4 三个结论

**① 命中按 block 对齐，不是按字节**

共享前缀约 308 token，但只能复用 **2 个完整的 128-token block = 256 token**；
剩下的 ~52 token 前缀 + 问题部分共 **115 token** 必须重算。

**② prefill 计算量降 60%**

| 模式 | prefill token | 占比 |
| :-- | :-- | :-- |
| OFF | 2968 | 100% |
| ON | 1176 | **39.6%** |

**③ 步数是否下降，取决于预算**

| 预算 | OFF 步数/请求 | ON 步数/请求 | 总步数 |
| :-- | :-- | :-- | :-- |
| 512 | 2 | 2 | 16 → 16 |
| 128 | 4 | 2 | **32 → 18（-44%）** |

预算宽时，371 和 115 都是"一步装下"，所以步数没区别；
预算紧时，371 要切 3 段，115 只需 1 段，**步数直接减半**。

### 11.5 为什么 `kv_peak` 看不出差别

缓存块是**可驱逐（evictable）**的，仍然留在空闲队列里计数，所以
`block_pool.get_num_free_blocks()` 不会因为它们而减少。

前缀缓存的收益体现在**计算量**（prefill token）和**步数**上，
而不是"KV 占用变高"——这一点和直觉相反，值得记住。

## 12. 时间模型（初版）：把 step 变成 TTFT / TPOT（2026-10-26 追加）

前面的实验只能回答"调度行为变了"，回答不了"哪个配置更快"。这一节补上时间维度。

### 12.1 模型

没有改 vLLM，直接复用 `Scheduler.schedule` 的输出给每步定价：

```
step_cost = c_prefill × prefill_tokens + c_decode × decode_tokens + c_overhead
```

然后逐请求累加：

- **TTFT** = 该请求 prefill 完成那一步结束时的累计时间
- **TPOT** = (最后一步结束时间 - TTFT) / (`max_tokens` - 1)
- **makespan** = 所有 step 成本之和（整体吞吐的代理）

脚本：`assets/simulate-forward/sim_timing.py`。

### 12.2 为什么扫系数比而不是拍脑袋

`c_prefill / c_decode` 在真机上取决于模型、硬件、batch——没有标定之前，
唯一诚实的做法是**扫一组比例看结论怎么变**。

固定 `c_decode = 1.0`、`c_overhead = 0.05`，扫 `c_prefill/c_decode ∈ {0.01, 0.1, 1.0}`。

### 12.3 结果：最优点随成本比例漂移

| `c_prefill/c_decode` | 含义 | 最优 makespan | 最优 mean TTFT |
| :-- | :-- | :-- | :-- |
| 0.01 | prefill 便宜、decode 主导 | 512 / 8（71.38） | **512 / 8（13.38）** |
| 0.1 | 混合 | 512 / 8（205.30） | **64 / 4（88.91）** |
| 1.0 | prefill 昂贵、prefill 主导 | 512 / 8（1544.50） | **64 / 2（710.12）** |

同一个 workload、同一组候选配置，**"吞吐最优"和"延迟最优"不是同一个答案**，
而且延迟最优会随着 prefill 变贵而向小 batch 漂移。

### 12.4 代价对比（ratio = 1.0）

| batched | seqs | mean TTFT | p95 TTFT | makespan |
| :-- | :-- | :-- | :-- | :-- |
| 64 | 2 | **710.1** | 1503.8 | 1546.5 |
| 256 | 8 | 822.4 | 1510.3 | 1544.7 |
| 512 | 8 | 945.5 | 1497.2 | **1544.5** |

- makespan 只差 **0.13%**（1544.5 vs 1546.5）
- 但 mean TTFT 差了 **33%**（945.5 vs 710.1）

**大 batch 换来的是极小的吞吐收益 + 明显的首 token 延迟惩罚。**
这就是为什么线上服务通常不会把 batch 拉满，而是按 SLO 调。

### 12.5 局限（必须写清楚）

| 局限 | 影响 |
| :-- | :-- |
| 系数是示意的，未标定 | 绝对值无意义，只有相对趋势可信 |
| 线性模型 | 忽略了 prefill 的二次项（注意力）与 batch 的非线性 |
| 没有建模 KV 读写、通信、调度开销 | 抢占/前缀缓存的影响被低估 |
| 没有建模 PD 分离 | 不适用于 PD 场景 |

### 12.6 与上游 #61305 的关系

上游 RFC 的 `TimingProvider` 接口是：

```
StepDescriptor → StepCost
```

我们这一步相当于**手写了一个最简 `TimingProvider`**：
输入是 `SchedulerOutput` + 运行状态，输出是每步耗时。
等 #61305 落地后，可以把这个模型塞进它的接口里，复用它的时钟与回放。

## 13. 策略对比：把"调度策略"做成可替换变量（2026-10-26 追加）

前面都是调**配置**，这一节调**策略**——也是"空跑"最初的目的：
验证一个调度策略到底有没有收益。

### 13.1 方法：不改 vLLM，只重排 waiting 队列

`Scheduler.waiting` 是 `FCFSRequestQueue(deque[Request])`，可以直接重排：

```python
items = list(self.waiting)
items.sort(key=lambda r: r.num_prompt_tokens, reverse=(policy == "longest_first"))
self.waiting.clear()
self.waiting.extend(items)
```

脚本：`assets/simulate-forward/sim_policy.py`。三个策略：

| 策略 | 行为 |
| :-- | :-- |
| `fcfs` | 不动，先到先服务 |
| `shortest_first` | 按 prompt 长度升序 |
| `longest_first` | 按 prompt 长度降序 |

其余全部固定：8 个请求（长度 1~500 token）、`max_tokens=8`、KV 2GiB、
`max_num_batched_tokens=256`、`max_num_seqs=8`、成本模型固定
（`c_prefill=0.1, c_decode=1.0, c_overhead=0.05`）。

### 13.2 结果

```text
[policy] fcfs            steps=13 mean_ttft= 90.94 p50= 83.25 p95=171.10 max=171.10 mean_tpot=14.98 makespan=205.45
[policy] shortest_first  steps=13 mean_ttft= 56.50 p50= 25.65 p95= 86.85 max=181.10 mean_tpot=20.39 makespan=205.45
[policy] longest_first   steps=13 mean_ttft=143.04 p50=152.10 p95=152.10 max=152.10 mean_tpot= 8.57 makespan=205.45
```

| 策略 | mean TTFT | p50 | p95 | max | mean TPOT | makespan |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| fcfs | 90.94 | 83.25 | 171.10 | 171.10 | 14.98 | 205.45 |
| shortest_first | **56.50** | **25.65** | **86.85** | 181.10 | 20.39 | 205.45 |
| longest_first | 143.04 | 152.10 | 152.10 | **152.10** | **8.57** | 205.45 |

### 13.3 三个结论

**① makespan 完全相同（205.45）**

总工作量不变，**策略只改变延迟在请求之间的分配**，不改变总吞吐。
这反过来验证了成本模型是自洽的。

**② 短请求优先：均值大幅改善，但长请求被饿**

| 指标 | fcfs | shortest_first | 变化 |
| :-- | :-- | :-- | :-- |
| mean TTFT | 90.94 | 56.50 | **-38%** |
| p50 TTFT | 83.25 | 25.65 | -69% |
| max TTFT | 171.10 | 181.10 | **+6%** |
| mean TPOT | 14.98 | 20.39 | +36% |

短请求几乎立刻返回，但长请求要等所有短的做完——**尾部更差，TPOT 更差**。

**③ 长请求优先：尾部最好，均值最差**

| 指标 | fcfs | longest_first | 变化 |
| :-- | :-- | :-- | :-- |
| mean TTFT | 90.94 | 143.04 | **+57%** |
| max TTFT | 171.10 | 152.10 | **-11%** |
| mean TPOT | 14.98 | 8.57 | **-43%** |

长请求早点开始，TPOT 显著变好；代价是短请求排在后面，均值变差。

### 13.4 这说明什么

- **没有"最好的策略"，只有"对哪个指标最好"**：均值、尾部、TPOT 三者此消彼长
- 线上如果在意 P99，应该偏向 `longest_first` 类策略；如果在意平均体验，`shortest_first` 更好
- 也说明：**只看吞吐（makespan）会得出"策略无所谓"的错误结论**

### 13.5 怎么加自己的策略

在 `sim_policy.py` 的 `_schedule` 里改排序 key，或者按业务字段（优先级、租户）排序：

```python
items.sort(key=lambda r: (r.priority, r.num_prompt_tokens))
```

改完直接跑，脚本会自动输出对比表。

## 14. 复刻 vllm-ascend 的短请求优先策略（T-012）（2026-10-26 追加）

VA 自带的 `ShortRequestFirstAsyncScheduler` 在空跑里用不了
（要求 `async_scheduling=True`，空跑强制关；MLA 模型还要求 `AscendConfig`）。
所以按它的规则在 `sim_policy` 里复刻一份。

### 14.1 策略规则（对齐 VA）

```
短请求队列：num_prompt_tokens <= threshold
长请求队列：其余
老化提权  ：长请求等待 >= long_max_wait_ms 时，排到短请求之前（最老的优先）
```

脚本：

- `assets/simulate-forward/sim_srs.py` —— 全部请求同时到达
- `assets/simulate-forward/sim_srs_arrivals.py` —— 错峰到达（长请求先排队，短请求陆续来）

### 14.2 实验 A：同时到达（threshold=100，budget=256）

| 策略 | steps | mean TTFT | p50 | max | 短请求均值 | 长请求均值 | mean TPOT | makespan |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| fcfs | 13 | 90.94 | 83.25 | 171.10 | 83.83 | 102.78 | 14.98 | 205.45 |
| srs | 13 | **56.50** | **25.65** | 181.10 | **25.65** | 107.92 | 20.39 | 205.45 |
| srs_aged | 13 | 56.50 | 25.65 | 181.10 | 25.65 | 107.92 | 20.39 | 205.45 |

- 短请求均值 **83.83 → 25.65（-69%）**
- 长请求均值 102.78 → 107.92（+5%）
- **老化完全没生效**：短请求在老化阈值到达前就已全部完成，`waiting` 里只剩长请求，
  此时提权没有意义（调试日志显示触发时 `short=0`）

### 14.3 实验 B：错峰到达 + 资源竞争

4 个长请求（400/800/400/800）先排队，短请求在 step 2 / 4 陆续到达（budget=256）。

| 策略 | steps | mean TTFT | max | 短请求均值 | 长请求均值 | mean TPOT | makespan |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| fcfs | 17 | 209.95 | 262.30 | 262.30 | 157.60 | 11.54 | 303.65 |
| srs | 17 | **147.68** | 282.30 | **130.95** | 164.40 | 20.74 | 303.65 |
| srs_aged | 17 | 见下表 | | | | | |

- mean TTFT **209.95 → 147.68（-30%）**
- 短请求均值 **262.30 → 130.95（-50%）**
- 长请求 157.60 → 164.40（+4%）
- makespan 仍相同（303.65）

### 14.4 老化阈值扫描：是个"悬崖"，不是"旋钮"

| `long_max_wait_ms` | 行为 | mean TTFT |
| :-- | :-- | :-- |
| 10 / 30 / 40 / 60 / 100 | 全部长请求都已等够 → 退化为 **FCFS** | 209.95 |
| 120 / 150 / 180 / 200 | 没有长请求等够 → 等价于 **纯 SRS** | 147.68 |

**没有中间态。** 原因：4 个长请求是同一时刻到达的，等待时间几乎一样，
老化阈值要么全部覆盖、要么全部不覆盖。

要得到渐进效果，需要让长请求**错峰到达**（等待时间不同），只提权最老的那个。
这属于后续（见想法池）。

### 14.5 结论

| 观察 | 含义 |
| :-- | :-- |
| SRS 大幅改善短请求延迟（-50%~-69%） | 符合设计预期 |
| 长请求只轻微变差（+4%~+5%） | 因为长请求本来就要等 |
| TPOT 变差（14.98→20.74） | 短请求快速结束后，decode batch 变小 |
| makespan 完全不变 | 策略只重新分配延迟 |
| 老化是二值开关 | 同批到达时无法精细调节 |

**对 VA 的意义**：`short_request_first` 在"短请求多、长请求少"的负载下收益明显；
`long_max_wait_ms` 更适合作为"防饿死开关"而不是"调参旋钮"。

## 15. 在线模式：HTTP server（2026-10-28 追加）

前面全是离线 `LLM.generate()`。这一节验证 `vllm serve` 路径。

### 15.1 启动

```bash
python -m vllm.entrypoints.openai.api_server   --model /models/Qwen_Qwen3-0.6B   --served-model-name qwen   --simulate-forward   --kv-cache-memory-bytes 2147483648   --enforce-eager   --max-model-len 2048   --host 0.0.0.0 --port 8000
```

脚本：`assets/simulate-forward/server/run_server.sh`（容器内跑，映射到宿主 18000）。

启动耗时 **约 24 秒**（离线 init 约 12s，多出来的是 API server 前端）。

### 15.2 请求必须带 trace

`#47922` 给 OpenAI 协议加了字段（completion 和 chat 都有）：

```json
{
  "model": "qwen",
  "prompt": "Hello",
  "max_tokens": 4,
  "return_token_ids": true,
  "trace_decode_token_ids": [100, 101, 102, 103]
}
```

返回：

```json
{
  "choices": [{
    "token_ids": [100, 101, 102, 103],
    "finish_reason": "length",
    "text": ""
  }],
  "usage": {"prompt_tokens": 1, "completion_tokens": 4, "total_tokens": 5}
}
```

`text` 为空是因为 100~103 是特殊/空 token；换成真实文本 token 就有内容。

> 默认不返回 `token_ids`，需要显式 `"return_token_ids": true`。

### 15.3 不带 trace 会静默返回 0

这是**必须注意的行为**：请求不带 `trace_decode_token_ids` 时，服务端**不报错**，
返回 200，但 token 全是 0：

```json
{"token_ids": [0, 0, 0, 0], "finish_reason": "length", "text": "!!!!"}
```

原因：模拟 runner 用 `trace_replay_state.apply_trace(...)` 覆盖采样结果，
请求没有 trace 时被写成 0。

**所以在线模式下每个请求都必须带 trace**，否则拿到的是无意义输出。

### 15.4 并发隔离

同时发 4 个不同 trace 的请求：

```text
[100, 101, 102, 103]
[200, 201, 202, 203]
[300, 301, 302, 303]
[400, 401, 402, 403]
```

每个请求都拿到自己的 trace，没有串扰——说明 trace replay 按 request 索引隔离正确。

### 15.5 能用它测什么

| 能测 | 不能测 |
| :-- | :-- |
| HTTP 前端、请求生命周期、并发接入 | 真实推理延迟 |
| 多请求下的调度/批处理行为 | 流式输出的真实节奏（没有计算，几乎是瞬间返回） |
| OpenAI 协议兼容性、chat template | tokenizer 之后的质量 |

### 15.6 脚本

- `assets/simulate-forward/server/run_server.sh` —— 起服务
- `assets/simulate-forward/server/smoke_client.sh` —— 健康检查 + 带/不带 trace 的请求

## 16. MLA 模型：官方限制 vs 实测（2026-10-28 追加）

### 16.1 官方说法

PR #47922 的 Notes 里写着：

```text
- Doesn't support MLA yet (deepseekv4)
```

### 16.2 代码里没有强制检查

```text
$ grep -rn "simulate_forward" vllm/model_executor/ vllm/v1/worker/
（无输出）
```

也就是说这是一个**已知限制的标注**，不是 hard block——不会在启动时拒绝 MLA 模型。

### 16.3 实测：V2 风格 MLA 可以跑

DeepSeek-V2-Lite（MLA + MoE）。注意：这个目录的 config 在**实验A**里被截断成了
**3 层**（原始 27 层），所以 block 数才这么夸张：

```bash
SIM_MODEL=/models/deepseek-ai_DeepSeek-V2-Lite ./run_in_container_030.sh sim_mla.py
```

```text
CPU KV cache size: 621,376 tokens, Maximum concurrency for 2,048 tokens per request: 303.41x
Initialized virtual KV cache with 1 groups and 38836 blocks; skipped KV tensor allocation.
TOKENS [100, 101, 102, 103]
```

- 38,836 blocks / 621,376 tokens（16 token/block）—— 每 token 仅约 3.4KB，
  是 3 层 MLA（`(512+64)×2B×3`）的结果；完整 27 层会是约 9 倍
- trace token 正确返回

### 16.4 那"不支持 MLA"指的是什么

更可能指 **DeepSeek V4 风格的 MLA**。代码里靠配置字段区分：

```python
# vllm/model_executor/layers/attention/mla_attention.py
if hasattr(hf_text_config, "compress_ratios"):
    # DeepseekV4 style: unified head_dim + rope_head_dim
```

V2/V3 走另一条分支。考虑到空跑跳过了 forward（attention 内核根本不执行），
限制只可能来自 **config 解析 / KV spec / runner 记账** 这一层——
V4 的 `compress_ratios` + sparse indexer 路径可能依赖只有真实权重才有的信息。

> 本地没有 V4 的 config，无法进一步确认。

### 16.5 实践建议

| 模型 | 建议 |
| :-- | :-- |
| Qwen / Llama 等 dense | 直接用 |
| DeepSeek-V2 / V3（MLA） | 可以用，先跑一次 `sim_mla.py` 冒烟 |
| DeepSeek-V4（`compress_ratios`） | 官方标注不支持，需要自己验证，可能卡在 config/KV spec |

脚本：`assets/simulate-forward/sim_mla.py`（`SIM_MODEL` 可换任意模型）。

## 17. GLM-5.3 空跑（2026-10-28 追加）

GLM-5.3 是 `glm_moe_dsa` 架构（78 层、MLA + 稀疏注意力 + MoE），比 Qwen3-0.6B 复杂得多。

### 17.1 准备 config（不需要权重）

```bash
BASE=https://hf-mirror.com/zai-org/GLM-5.3/resolve/main
for f in config.json generation_config.json tokenizer.json tokenizer_config.json chat_template.jinja; do
  curl -sL -o "models/zai-org_GLM-5.3/$f" "$BASE/$f"
done
```

关键字段：

```
num_hidden_layers = 78
hidden_size       = 6144
num_attention_heads = 64
head_dim          = 192
first_k_dense_replace = 3      # 前 3 层 dense，其余 MoE（256 experts）
index_topk        = 2048       # 稀疏注意力（DSA）
```

> `models/` 在 `.gitignore` 里，config 不入库；`glm53/run_glm53.sh` 检测到缺失会自动下载。

### 17.2 直接跑会被 CPU 拦住

```text
NotImplementedError: Sparse Attention is not supported on CPU.
```

来自 `vllm/platforms/cpu.py：get_attn_backend_cls` 里的 `if attn_selector_config.use_sparse: raise`。
这就是**实验A 的坑 1**，在 0.30 上依然存在。

### 17.3 解法：关掉 `is_v32`（复用实验A 的办法）

```python
# vllm/model_executor/models/deepseek_v2.py（两处：1134 / 1435）
self.is_v32 = False   # 原本是 hasattr(config, "index_topk")
```

镜像 `sim030:glm53` = `sim030:dry-run` + 这个补丁：

```bash
docker run -d --name glm53img --platform linux/arm64 sim030:dry-run bash -c '
  sed -i "s/self.is_v32 = hasattr(config, \"index_topk\")/self.is_v32 = False/g" \
    /work030/vllm/model_executor/models/deepseek_v2.py'
docker commit glm53img sim030:glm53
```

（`is_v32` 是纯 Python 改动，不需要重新编译。）

### 17.4 结果

```text
CPU KV cache size: 23,888 tokens, Maximum concurrency for 2,048 tokens per request: 11.66x
Initialized virtual KV cache with 1 groups and 1493 blocks; skipped KV tensor allocation.
[sim] engine init: 13.49s
[sim] generate: 0.37s
[sim] token_ids: [100, 101, 102, 103, 104, 105, 106, 107]
```

- **1,493 blocks**（block_size 16），2 GiB 对应 23,888 tokens ≈ 88 KB/token
- 与手算一致：`78 层 × (512 + 64) × 2B ≈ 88 KB/token`
- 78 层完整 config，**没有下载任何权重**，init 只用了 13.5s

同样 2 GiB 虚拟 KV 下三个模型的对比：

| 模型 | 层数 | tokens | blocks | block 大小 |
| :-- | :-- | :-- | :-- | :-- |
| Qwen3-0.6B（GQA） | 28 | 18,688 | 146 | 128 |
| **GLM-5.3（MLA）** | 78 | 23,888 | 1,493 | 16 |
| DeepSeek-V2-Lite（3 层截断 MLA） | 3 | 621,376 | 38,836 | 16 |

MLA 的每 token KV 远小于 GQA，所以同样显存能装更多 token——这也是抢占阈值完全不同的原因。

### 17.5 重要 caveat

`is_v32 = False` 关掉的不只是 CPU 检查，还有 **DSA 稀疏注意力的 indexer**。
所以这个实验模拟的是 GLM-5.3 的 **dense MLA 变体**：

| 项 | 是否真实 |
| :-- | :-- |
| 78 层 / hidden 6144 / 64 heads 的 KV 形状 | ✅ |
| MLA 压缩（kv_lora_rank 512 + rope 64） | ✅ |
| MoE 层结构（256 experts） | ✅（meta 构建，不执行） |
| **DSA indexer 的额外 KV cache** | ❌ 未建模 |
| 稀疏注意力对 prefill 的影响 | ❌ |

所以 KV 容量/块数可以信，**但 GLM-5.3 真正省 KV 的那一半（indexer 压缩）没体现**。

### 17.6 main 与 0.30 的对比

同一份 config、同样关掉 `is_v32`，在两个镜像上各跑一次：

| 版本 | tokens | blocks | 并发度 | init | generate |
| :-- | :-- | :-- | :-- | :-- | :-- |
| main（`0.31.1rc1`，`sim-main:glm53`） | 23,888 | 1,493 | 11.66x | 13.96s | 0.31s |
| v0.30.0（`sim030:glm53`） | 23,888 | 1,493 | 11.66x | 13.49s | 0.37s |

**调度指标逐位一致**，只有墙钟时间有噪声。说明这条"78 层 MLA + MoE"路径在
两个版本间也没有行为差异——把之前四组对照（dense / 策略 / 抢占 / 前缀缓存）
扩展到了"大模型 + MLA + MoE"的 config 上。

### 17.7 脚本

```bash
./wiki/vllm架构笔记/assets/simulate-forward/glm53/run_glm53.sh
```

## 18. 待办

1. ✅ 多请求 + step 级观测（`assets/simulate-forward/sim_steps.py`）
2. ✅ 多轮实验 + KV block 观测（`assets/simulate-forward/sim_rounds.py`）
3. ✅ 参数扫描（`assets/simulate-forward/sim_sweep.py`）：预算/并发 ↑ → 步数 50→10，chunk 21→2，avg_reqs 1.7→6.6
4. ✅ KV 压力实验：调小 `kv_cache_memory_bytes` + 长输出，触发排队与抢占（`assets/simulate-forward/sim_kv_stress.py`）
5. ✅ 前缀缓存实验（`assets/simulate-forward/sim_prefix.py`）：prefill token 2968→1176，窄预算下步数 4→2
6. ✅ 时间模型初版（`assets/simulate-forward/sim_timing.py`）：step 定价 + TTFT/TPOT，扫成本比例
7. ✅ 策略对比框架（`sim_policy.py`）：三种策略、makespan 相同、TTFT 分布差异显著
8. ✅ 复刻 VA 短请求优先 + 老化（`sim_srs.py` / `sim_srs_arrivals.py`）
9. ✅ 在线模式（HTTP server）验证：trace 必带、并发隔离正确
10. ✅ MLA 模型实测（V2-Lite 可用；V4 官方标注不支持，待验证）
11. ✅ GLM-5.3 空跑（78 层、1,493 blocks，需关 `is_v32` 绕开稀疏注意力）
12. 用真机数据标定 `c_prefill / c_decode / c_overhead`，或等 #61305 的 `TimingProvider`
13. 关注 #47922 的合并进度；合并后可以去掉本地 patch

---

## 19. 参考

- PR #47922: https://github.com/vllm-project/vllm/pull/47922
- RFC #61305: https://github.com/vllm-project/vllm/issues/61305
- trace replay 前置 PR #46701（2026-08-20 合入 main）
- 相关外部工作：Vidur、Frontier、BLIS（llm-d）、SimAI
