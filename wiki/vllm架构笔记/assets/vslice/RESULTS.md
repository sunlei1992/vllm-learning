# Vertical slice 实测：FCFS vs SRS（短请求优先）

日期：2026-10-31 ｜ 环境：`sim-int:dry-run`（vLLM 0.31.1rc1 仿真器）｜ 模型：`Qwen_Qwen3-0.6B`（仅 config，无权重）

## 目的

跑通「同镜像 + 一个开关」的调度 A/B 闭环，验证：

1. `--scheduler-cls` 能在 `vllm serve` 下生效；
2. `vllm bench serve` + 每请求 metrics + step 轨迹能观察到调度行为变化；
3. 策略的收益/代价能被正确归因，而不是只看一个均值。

## 配置

| 项 | 值 |
|---|---|
| timing | `linear`：`fixed_us=6200`、`prefill_us_per_token=15`、`decode_us_per_req=2400`、`decode_us_per_kv_token=0.14` |
| clock | `real` |
| KV | 4 GiB，`block_size` 默认（仿真 32） |
| batch | `max_num_seqs=8`、`max_num_batched_tokens=512` |
| APC | 关闭 |
| 请求 | 8 长（725 token）+ 8 短（65 token），各输出 16 token，长请求排在前面 |
| 策略 | baseline `fcfs`；candidate `srs`（按 `num_prompt_tokens` 升序重排 `Scheduler.waiting`） |
| 重复 | 每组 2 次；每组先跑一整轮 warmup 丢弃 |

## 结果

### bench（聚合）

| metric | baseline | candidate | delta |
|---|---:|---:|---:|
| p99 TTFT (ms) | 694.96 | 706.41 | +1.6% |
| p50 TTFT (ms) | 390.38 | 301.91 | **-22.7%** |
| mean TTFT (ms) | 377.26 | 337.01 | -10.7% |
| p99 TPOT (ms) | 33.83 | 33.89 | +0.2% |
| mean TPOT (ms) | 32.12 | 31.88 | -0.7% |
| total token throughput | 5739.04 | 5717.73 | **-0.4%** |
| request goodput (TTFT≤200ms) | 6.55 | 6.96 | **+6.2%** |

### 每请求 metrics（collector，按类别）

| class | metric | baseline | candidate | delta |
|---|---|---:|---:|---:|
| SHORT | queue p50 (ms) | 566.33 | 14.88 | **-97.4%** |
| SHORT | queue p99 (ms) | 615.89 | 491.35 | -20.2% |
| SHORT | TTFT p50 (ms) | 37.11 | 27.97 | -24.6% |
| SHORT | wall p50 (ms) | 1113.47 | 556.87 | **-50.0%** |
| LONG | queue p50 (ms) | 43.87 | 531.85 | **+1112.4%** |
| LONG | queue p99 (ms) | 604.23 | 623.42 | +3.2% |
| LONG | TTFT p50 (ms) | 51.05 | 55.97 | +9.6% |
| LONG | wall p50 (ms) | 641.75 | 1124.66 | **+75.2%** |

### step 轨迹（第一轮 measured bench 的前 3 步）

| metric | baseline | candidate |
|---|---:|---:|
| steps（measured 全程） | 213 | 204 |
| scheduled tokens（全程） | 19680 | 19680 |
| first 3 步内 short 请求数 | 1 | 2 |
| first 3 步内 long 请求数 | 5 | 4 |

轨迹确实变了，说明策略生效，不是「代码没走到」。

## 解读

- **短请求大幅改善**：queue p50 从 566ms 降到 15ms，wall p50 减半。
- **长请求被牺牲**：queue p50 从 44ms 升到 532ms，wall p50 +75%。
- **总吞吐基本不变**（-0.4%，在 2 次运行的噪声内）：这是**延迟重分配**，不是吞吐提升。
- **聚合指标会骗人**：p50 TTFT -22.7%，但 p99 TTFT +1.6%；如果不分请求类别，会以为「全面变好」或「全面变差」，实际是短请求赢、长请求输。
- **goodput 上升 6.2%**：更多短请求满足 200ms SLO；这是业务口径下更合理的「变好」。

## 没验证 / 注意事项

- 每组只有 2 次，p99 波动未做置信区间；结论是「方向性验证」，不是统计显著。
- 无抢占（KV 充足）、APC 关闭；生产 case 需要补 KV 压力和 APC 两种场景。
- 这是玩具策略（每步全量排序），不代表真实优化；真实优化要比的是「同等复杂度」的实现。
- 还没有 UT / golden trace 回归；下一步应把「前 3 步 short/long 数量」固化成断言。
- 未接 RS / P/D；RS 只在 P/D 相关优化时使用。
- candidate 首次启动 158s（Docker/CPU 冷启动波动；baseline 为 18s），warmup 后 measured 运行正常；无论原因，实验脚本都必须保留整轮 warmup 丢弃。

## 轨迹 UT

`test_vslice_trace.py` 用离线 `Scheduler`（fake KV、不跑模型）复刻同一 case，把轨迹固化成断言：

```bash
bash run_trace_test.sh
# Ran 3 tests in 3.994s -- OK
```

| 断言 | FCFS | SRS |
|---|---:|---:|
| steps | 42 | 42 |
| total scheduled tokens | 6560 | 6560 |
| first short step | 16 | 0 |
| first long step | 0 | 16 |
| first 3 步 short 数 | 0 | 24 |
| first 3 步 long 数 | 6 | 0 |
| preemptions | 0 | 0 |

SRS 第 0 步：8 个 short，`short-7` 只分到 57 token（7×65+57=512，正好吃满预算）。
golden 值钉在 `sim-int:dry-run`（vLLM 0.31.1rc1）；换调度语义时要显式更新，而不是让它静默漂移。

注意：离线 UT 里 16 个请求在 step 0 前已全部入队，所以 FCFS 的 first short 要到第 16 步；
HTTP 实验里请求是陆续到达的，first 3 步还能看到 1 个 short。两者不矛盾：UT 固化的是
调度器本身的排序行为，server 轨迹还叠加了到达时序。

## 复现

```bash
cd /Users/sunlei/code/dsh/vllm

# 在 tmp/vslice 里跑（推荐，避免改动归档结果）
MODE=baseline  RUNS=2 bash tmp/vslice/run_vslice.sh
MODE=candidate RUNS=2 bash tmp/vslice/run_vslice.sh
.venv/bin/python tmp/vslice/compare.py
```

归档脚本也可直接从本目录跑；`run_vslice.sh` 会向上找到工作区根目录，挂载 `models/` 和 `tmp/triton-cache/`。
