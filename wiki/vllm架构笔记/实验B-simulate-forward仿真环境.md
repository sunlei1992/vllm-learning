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
| 性能数字（TTFT/TPOT） | ❌ 需要 #61305 的 timing model |
| vllm-ascend 的 connector | ❌ 官方 simulator 不覆盖 |

适合：调度策略对比、chunked prefill 行为、prefix cache 命中、抢占逻辑。
不适合：算子/数值正确性、通信、显存实测。

---

## 7. 待办

1. 多请求 + step 级观测（每步调度多少 token、batch 组成、KV block 使用）
2. 参数扫描（`max_num_batched_tokens` / `max_num_seqs`）看调度差异
3. 如需时间维度，按 #61305 的 `StepDescriptor → StepCost` 自己实现一个最简 `TimingProvider`
4. 关注 #47922 的合并进度；合并后可以去掉本地 patch

---

## 8. 参考

- PR #47922: https://github.com/vllm-project/vllm/pull/47922
- RFC #61305: https://github.com/vllm-project/vllm/issues/61305
- trace replay 前置 PR #46701（2026-08-20 合入 main）
- 相关外部工作：Vidur、Frontier、BLIS（llm-d）、SimAI
