# simulate-forward 实验脚本

配套笔记：[实验B-simulate-forward仿真环境.md](../../实验B-simulate-forward仿真环境.md)

## 前置条件

1. Docker Desktop（`linux/arm64` 或 `linux/amd64` 均可）
2. 一个已编译好 vLLM（含 PR #47922 补丁）的镜像，默认名 `sim-built`
3. 宿主机上放置以下 wheel（用于运行时安装，避免容器内拉 GitHub）：
   - `triton-<ver>+cpu-*.whl`（`triton-cpu` release）
   - `torchvision` / `torchaudio` / `torchcodec` 的 `+cpu` 版本，需与 torch 匹配
4. 本地模型目录（默认 `/models/Qwen_Qwen3-0.6B`，可用 `SIM_MODEL` 覆盖）

这些路径与构建步骤见笔记第 3 节。

## 脚本

| 脚本 | 用途 |
| :-- | :-- |
| `sim_smoke.py` | 最小冒烟：单请求、trace replay |
| `sim_debug.py` | 2 token 的调试运行 |
| `sim_steps.py` | 多请求 + 逐 step 观测（chunked prefill） |
| `sim_rounds.py` | 多轮 generate + KV block 占用 |
| `sim_kv_stress.py` | KV 压力：排队与抢占（env 可调） |
| `sim_sweep.py` | 参数扫描：`max_num_batched_tokens` × `max_num_seqs` |
| `sim_prefix.py` | 前缀缓存 off/on 对比 |
| `sim_timing.py` | 最简时间模型：TTFT / TPOT / makespan |
| `sim_policy.py` | 策略对比：FCFS / 短请求优先 / 长请求优先 |
| `sim_srs.py` | 复刻 VA 的 short-request-first（同时到达） |
| `sim_srs_arrivals.py` | 同上 + 错峰到达 + 老化阈值 |
| `sim_va_compare.py` | VA 补丁 on/off 对比 |
| `run_in_container.sh` | 在容器里跑上述脚本（透传 `KV_MB` 等 env） |
| `server/run_server.sh` | 起干跑 OpenAI server（端口 18000） |
| `server/smoke_client.sh` | 健康检查 + 带/不带 trace 的请求 |
| `DOCKER.md` | 镜像的逐层构建命令与每个坑的解法 |

## 用法

```bash
# 在仓库根目录执行
./"wiki/vllm架构笔记/assets/simulate-forward/run_in_container.sh" sim_timing.py

# 带参数
KV_MB=128 MAX_TOKENS=300 MAX_MODEL_LEN=1024 \
  ./"wiki/vllm架构笔记/assets/simulate-forward/run_in_container.sh" sim_kv_stress.py
```

`run_in_container.sh` 默认把仓库根目录当作宿主根；若脚本被复制到别处，
用 `VLLM_LAB_ROOT` 指定。

## 注意

- 首次运行会做 Triton JIT 编译（每个 kernel 约 60s），之后命中
  `TRITON_CACHE_DIR`（脚本已挂载持久缓存）。
- 换 workload 形状可能触发新的 JIT，实验前先预热一遍。
