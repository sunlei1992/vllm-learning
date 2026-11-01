# 实验F：GLM-5.3 128K / 24 前缀 / 90% APC 空跑

> 日期：2026-10-31 ｜ 目标：在真实 950 日志缺失时，用仿真比较 **轮询 / prefix-affinity / prefix-grouped** 三种调度方式。
> 资产：[`assets/vslice_glm/`](assets/vslice_glm/RESULTS.md) ｜ 前置：[实验C](实验C-移植PR61506仿真器.md)、[10-调度优化测试工作流](10-调度优化测试工作流.md)

## 1. 真实拓扑与 case

- P：2 台 × 8 卡，`TP8 × DP2`（2 个 P rank，每个 8 卡）；
- D：2 台 × 8 卡，`TP1 × DP16`（EP16 放下 MoE 权重）；
- GLM-5.3，W4A4C8；C8 = 主 KV 8-bit + indexer 8-bit；
- case：128K 输入、1 token 输出、90% APC、24 个公共前缀、960 请求、64 并发；
- 每 rank `max_num_batched_tokens=32768`、`block_size=128`、`gpu_memory_utilization=0.85`；
- 只测 prefill，D 不参与。

## 2. 仿真做了什么

镜像 `sim030:glm53`（vLLM 0.30.0 仿真器），模型只读 config，无权重。三个关键适配：

1. **CPU MLA 默认强制关闭 APC + chunked prefill**。把 `cpu.py` 挂进容器，用
   `VLLM_SIM_MLA_ALLOW=1` 跳过该限制（`simulate_forward` 不跑 MLA kernel，安全）。
2. **block_size=128** 生效（否则被 CPU MLA 强制成 16）。
3. 仿真 KV 是 BF16（~90 KiB/token），真实是 C8（~46.6 KiB/token）：
   **320 GiB 仿真 KV ≈ 160 GiB C8**；250 GiB ≈ 125 GiB C8。

P 的 TP8×DP2 用 **2 个 TP1 仿真 server** 表示，每个 server 的 KV 按 TP8 rank 聚合设置；
不是真实 TP8，也没有 D 侧。timing=zero，所以**不看墙钟性能**，只看 APC/驱逐/抢占。

Workload：24 个前缀 × 115,200 token；每个前缀 40 条、每条 128,000 token（90% 前缀 + 10% 唯一 suffix），共 960 条；64 并发。

## 3. 结果（960 请求，320 GiB/rank ≈ 160 GiB C8）

| mode | APC hit | preemptions | p50 wall |
|---|---:|---:|---:|
| baseline（两端都缓存 24 前缀，轮询） | **86.5%** | 0 | 2.41 s |
| affinity（按 prefix 固定 rank，每 rank 12 前缀） | **88.8%** | 0 | 2.65 s |
| grouped（同前缀 40 条跑完再切） | **90.0%** | 0 | 2.26 s |

`measured_s` 受一个 ~300s 离群请求影响，不能比较总耗时；p50 都在 2.3–2.7s，主要是噪声。

容量敏感性（96 请求 = 24 前缀 × 4）：

| KV 仿真 / ≈C8 | baseline | affinity |
|---|---:|---:|
| 250 GiB / 125 GiB | **71.0%** | **90.0%** |
| 300 GiB / 150 GiB | 90.0% | 90.0% |
| 320 GiB / 160 GiB | 90.0% | 90.0% |

## 4. 解读

1. **24 个前缀不是瓶颈，960 个唯一 suffix 才是**。前缀缓存会保留已完成请求的 suffix 块；
   960 × 0.58 GiB（C8）≈ 557 GiB，远超 160 GiB/rank，LRU 会把前缀挤掉。
2. **affinity 必要但不充分**：它把每 rank 的前缀数减半（139→70 GiB），容量紧时能把 71% 拉回 90%；
   但 960 条 unique suffix 仍会累积，命中率只到 88.8%。
3. **grouped 才稳**：同前缀的 40 条连续跑完，当前前缀常驻，旧 suffix 可回收；90.0%。
   代价是牺牲跨前缀公平性/尾延迟。
4. **不要只看 `num_preemptions`**：这里是 prefix cache 驱逐，抢占计数为 0，但命中率已经掉了。
5. 真实 P rank 估算 159–179 GiB C8，比 160 GiB 略高；baseline 可能在 86–90% 之间，grouped 更稳。

## 5. 下一步

- 真实 950 日志回来后，先验证 `Available KV cache memory` 是否 ≥160 GiB C8；
- 在真实系统上试 **prefix-grouped**（或 prefix 感知的准入/路由），观察 960 条下的 APC 与 TTFT；
- 如果 group 导致尾延迟不可接受，用“分组 + 老化”折中：组内连续、组间按等待时间提权；
- D 侧 EP16 不参与 prefill case；要做 P/D 时另测 5.8 GiB/请求的 KV 传输。

## 6. 文件

| 路径 | 说明 |
|---|---|
| `assets/vslice_glm/RESULTS.md` | 结果、限制、复现命令 |
| `assets/vslice_glm/glm_case.py` | 960 请求客户端（baseline/affinity/grouped） |
| `assets/vslice_glm/start_replicas.sh` | 起两个 P 仿真 rank（`KV_BYTES` 可调） |
| `assets/vslice_glm/cpu.py` | 允许 MLA 在仿真中开 APC/block128 的补丁版 |
| `assets/vslice_glm/results/` | 三组 960 请求 JSON |

## 7. 真实 KV 容量补充（2026-10-31）

用户提供：P 节点每个 DP 的 **NPU KV cache size = 760,832 tokens**。这有两种口径，结论完全相反：

| 口径 | 每 DP rank tokens | C8 KV | blocks@128 | 24 前缀 + 32 并发（3.17M tokens） | 结论 |
|---|---:|---:|---:|---|---|
| **per-NPU**（×8） | **6.09M** | **~270 GiB** | 47.5k | 占 52% | 装得下；前缀可常驻 |
| **per-DP-rank**（不乘） | **0.76M** | **~34 GiB** | 5.9k | 需要 4.2× 容量 | 24 前缀装不下，90% 不可持续 |

**2026-10-31 已确认：per-DP-rank（760,832 tokens / 每个 TP8 rank，约 34 GiB C8）。**
这个容量下 24 个前缀/90% APC 物理上不成立：

- 24 个前缀 = 2.76M tokens = **3.63× 容量**；只放前缀也只能放 **6.6 个**；
- 32 条活跃请求的唯一 suffix = 409.6K tokens，剩给前缀的只有 **3.05 个**；
- 3 前缀 + 32 并发 = 755.2K tokens，占 **99.3%**，没有余量；
- 2 前缀 + 32 并发 = 640K，84%，才比较安全；
- 1 个前缀 + 40 条 suffix = 627.2K，82.4%，可以放下一个 group。

即使完美 grouped，24 个前缀每个 40 条请求，**每组第一条必然冷启动**：
`hit ≈ 0.9 × (1 − 1/40) = 87.75%`，仍然到不了 90%。要 90% 必须满足其一：

1. 24 个前缀常驻（容量 3.63×，不可能）；
2. 外部 prefix store / Mooncake 预加载（HBM 只放活跃前缀）；
3. layerwise KV buffer 复用把有效容量放大；
4. 把目标改成 ~87.8%，或减少前缀数/长度、增加 HBM/KV 预算。

原“从量级看更像 per-NPU”的推断作废，保留在下面作为灵敏度参考：
从量级看更可能是 **per-NPU**：

- 760,832 × 46.6 KiB ≈ 33.8 GiB/卡；8 卡合计 270 GiB，和 96GB×0.85 − W4 权重 − 激活大致对得上；
- 如果是 per-DP-rank，每卡只有 4.2 GiB KV，W4 权重会占掉 ~77GB/卡，和 743B 模型的 EP8 权重（~48GB/卡）不太吻合。

但无论哪种口径，**960 条请求的 12.29M 唯一 suffix tokens 都超过容量**：

- per-NPU 6.09M tokens：24 前缀 2.76M + 活跃唯一 0.41M = 3.17M，能装下；但 960 条历史 suffix 12.29M，
  LRU 仍会驱逐前缀，所以 grouped/prefix 保留策略仍然必要；
- per-DP-rank 0.76M tokens：连 24 前缀都装不下，90% APC 不可能靠普通 prefix cache 实现；
  除非开了 **layerwise KV buffer 复用**（容量 ×19.5），或这个数字其实是 per-NPU。

待确认：

1. 日志里 `760,832` 是 **每张 NPU** 还是 **每个 DP rank**？
2. 对应 `Available KV cache memory` 是 ~34 GiB 还是 ~270 GiB？
3. P 侧是否开了 layerwise KV buffer 复用？如果开了，有效 KV 容量会按槽位数放大。

如果确认是 per-NPU（6.09M/rank），我们之前 320 GiB BF16 仿真（3.82M tokens）其实比真实更紧；
按真实容量应把仿真 KV 调到 **~520 GiB BF16/rank** 再跑一轮，baseline 可能会比 86.5% 更好，
但 960 条 suffix 的驱逐问题仍然存在，grouped 仍是稳妥策略。

## 8. 简单 prefix-grouped scheduler 实测（2026-11-01）

实现：[`assets/vslice_glm/prefix_sched.py`](assets/vslice_glm/prefix_sched.py)。

做法（最小版）：

- 每步 `schedule()` 前，把 `Scheduler.waiting` 按 prefix key（前 128 token 的 hash）分桶；
- `PREFIX_ACTIVE=1`：只把“当前 running 的前缀”+ 一个 waiting 桶移到队首，其余保持原顺序；
- 不改 `running`、不改 KV 管理；用 `--scheduler-cls` 挂载。

容量按真实 65 GiB BF16/rank（`kv_cache_size_tokens=776,704`，≈760,832 真实值），960 请求、64 并发：

| 到达顺序 | scheduler | APC hit | p50 wall |
|---|---|---:|---:|
| grouped（40 条/前缀连续） | stock | **85.5%** | 2.67 s |
| grouped | prefix-grouped | **85.5%** | 2.67 s |
| interleaved（24 前缀交错） | stock | **2.7%** | 2.73 s |
| interleaved | prefix-grouped v1（只看 running[0]） | **15.9%** | 2.75 s |
| interleaved | prefix-grouped v2（running 集合 + cap1） | **19.7%** | 2.74 s |
| interleaved | prefix-grouped v2（running 集合 + cap2） | **19.5%** | 2.48 s |
| interleaved | affinity（只按 prefix 路由，无组首 warm） | **3.3%** | 2.78 s |
| grouped | 上游 grouped（组首 warm + 24 组串行） | **90.0%** | 2.57 s |

结论：

1. **重排 waiting 确实有效**：interleaved 下 2.7% → 15.9%（v1）→ **19.7%（v2，考虑 running 前缀）**；
2. **但远不到 87.8%**：请求交错到达时，waiting 里同 prefix 只有少数几条，scheduler 无法凭空
   凑出 32 条同前缀的 batch；它只能重排“已经排队”的请求；
3. **如果上游已经按 prefix 连续发送**，stock 就能到 85.5%，重排没有额外收益；
4. **prefix 块还会被 LRU 驱逐**：suffix 块比 prefix 新，prefix 可能先被淘汰；仅重排不能保证
   当前前缀常驻，需要 prefix pin / 组首预取 / cache retention；
5. **考虑 running 前缀只带来 ~3–4 个百分点**（15.9% → 19.5–19.7%）：它能避免在活跃前缀还有
   等待请求时开新前缀，但**无法凭空生成 waiting 里不存在的请求**，也挡不住 LRU 驱逐 prefix；
6. 要接近 87.8%，需要 **prefix-aware 准入/排队**（按 prefix 攒批、hold 到够一组或超时）+
   prefix pin/预取，而不是只在 `schedule()` 前排序；
7. **高 APC ≠ 高吞吐**：上游 grouped 拿到 90% 命中，但实测 `measured_s=67.26s`，
   比 stock 的 41.88s 还慢——因为它一次只放 40 条（<64 并发）、24 组串行，P 侧被 underfill。
   v2 虽然只有 19.5%，但 `measured_s=38.82s`，反而略快。优化目标应该是“保持 2–4 个组在飞”，
   而不是“一次只跑一个组”。

这个结果把优化点从“scheduler 内部排序”推到了“**上游路由/准入 + prefix 缓存策略**”：
- 路由/排队层：按 prefix 分桶、限制活跃前缀、攒批/超时；
- 缓存层：pin 当前前缀、优先淘汰 suffix、或组首预取；
- scheduler 内部重排只能作为最后一道微调。

## 9. 闭环 24 worker 实测（2026-11-01）

之前的 960 条是“同时到达”开环；真实 case 是 **24 个进程、每个进程固定一个前缀、当前请求不结束不发下一条**，即固定 24 并发、每个前缀最多 1 条在飞。补了 [`assets/vslice_glm/closed_loop.py`](assets/vslice_glm/closed_loop.py)：

- 24 个 worker，每个 worker 固定一个 prefix，40 条串行；
- 每条 128K（115.2K prefix + 12.8K unique suffix），输出 1 token；
- 65 GiB BF16/rank，block 128，`max_num_seqs=32`，`max_num_batched_tokens=32768`；
- 测 `makespan`、per-request latency（输出 1，所以 latency ≈ TTFT）、APC hit。

| 策略 | makespan | throughput（CPU proxy） | APC hit |
|---|---:|---:|---:|
| stock | **49.57s** | 19.37 req/s | 0.48% |
| cap5（每 rank 最多 5 个活跃前缀） | 51.49s | 18.64 req/s | 0.31% |
| cap2（v2 默认） | 56.47s | 17.00 req/s | 0.19% |

注意：zero timing 下 `makespan`/`throughput` 只是 CPU/HTTP proxy，不是真实吞吐；但趋势清楚：**cap2 < cap5 < stock**。

原因：

1. 闭环里每个前缀只有 **1 条在飞**，下一條要等当前请求结束才发；scheduler 无法像开环那样“攒 40 条同前缀”形成 batch；
2. 限制活跃前缀数（cap2/cap5）只会降低 `N_eff`，不会提高命中率——因为前缀没有 queued 请求可喂；
3. 没有 pin 时，前缀在本条请求结束后仍可能被其他前缀驱逐；下一条回来时 miss；
4. 因此 **闭环 24 前缀场景下，grouping/cap 不是正确杠杆；需要 prefix pin/retention**：把最近 5 个活跃前缀的块保护住，让 worker 的下一条请求直接命中。

如果按 1K 输出、TPOT=20ms 估算：

```text
throughput = N_eff / (TTFT + 1023×0.02)
```

- `N_eff` 受 HBM 限制：每 rank 5 条 → 全局 ~10；cap2 只有 4；
- TTFT 2s 时：N_eff=10 → 0.445 req/s；N_eff=4 → 0.178 req/s；
- 所以 cap2 会把总吞吐压到约 40%。

下一步不是继续调 cap，而是实现 **prefix pin/retention**，再跑同一闭环客户端对比。
