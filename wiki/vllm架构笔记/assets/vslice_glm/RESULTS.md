# GLM-5.3 128K / 24 前缀 / 90% APC 空跑结果

> **2026-10-31 重要修正**：真实 P 每个 DP rank 只有 **760,832 tokens KV（~34 GiB C8）**，
> 是本文 320 GiB 仿真（3.82M tokens）的 **约 1/5**。因此下面的 320 GiB 结果只能说明“suffix 累积
> 会驱逐前缀、grouped 更稳”的趋势，**不能代表真实容量**。按真实容量，24 个 128K 前缀 = 2.76M tokens
> = 3.63× 容量，90% APC 物理上不成立；即使 grouped，24 组×40 条的首条冷启动上限也只有 87.75%。
> 详见 `实验F` §7。

日期：2026-10-31 ｜ 镜像：`sim030:glm53`（vLLM 0.30.0 仿真器）｜ 模型：`zai-org_GLM-5.3`（仅 config，无权重）

## 目的

在真实 950 拓扑（P: TP8×DP2，D: TP1×DP16，util 0.85）拿不到日志前，先用仿真比较三种调度方式的优劣：

- `baseline`：两个 P rank 都缓存全部 24 个前缀，请求轮询（round-robin）；
- `affinity`：按 prefix 固定到某个 P rank（每个 rank 12 个前缀）；
- `grouped`：按 prefix 分组，一组 40 条跑完再切下一组。

只测 prefill（`max_tokens=1`），所以**不看墙钟性能**，只看 APC 命中率、抢占、稳定性。

## 仿真限制（很重要）

1. **CPU MLA 默认强制关闭 APC + chunked prefill**（`cpu.py`）。这里把 `cpu.py` 挂载进容器，并用
   `VLLM_SIM_MLA_ALLOW=1` 跳过这个限制；`simulate_forward` 不跑 MLA kernel，所以只影响调度/KV 管理。
2. **block_size=128** 已生效（否则会被 CPU MLA 强制成 16）。
3. 仿真 KV 是 **BF16**，约 90 KiB/token；真实是 C8，约 46.6 KiB/token。因此：
   **320 GiB 仿真 KV ≈ 160 GiB C8**；250 GiB 仿真 ≈ 125 GiB C8。
4. `is_v32=False` 会关闭 DSA indexer；indexer 的 KV 未单独建模。
5. 两个 P rank 用两个 TP1 仿真 server 表示，KV 按 TP8 rank 聚合设置；不是真实 TP8。
6. zero timing；`measured_s` 只代表 CPU 调度/哈希开销，不是 950 性能。
7. 没有起 D 侧（prefill-only）。

## Workload

- 24 个公共前缀 × 115,200 token（90% of 128K）；
- 每个前缀 40 条请求，每条 128,000 token（前缀 + 12,800 唯一 suffix），共 **960 条**；
- 64 并发；每 rank `max_num_seqs=32`、`max_num_batched_tokens=32768`、`block_size=128`；
- 输出 1 token；APC 开；KV 虚拟 320 GiB/rank（≈160 GiB C8）。

## 结果

### 960 请求，320 GiB/rank（≈160 GiB C8）

| mode | hit rate | preemptions | p50 wall | 说明 |
|---|---:|---:|---:|---|
| baseline（两端都缓存 24 前缀，轮询） | **86.5%** | 0 | 2.41 s | 960 个唯一 suffix 的块把前缀挤出 |
| affinity（每 rank 12 前缀） | **88.8%** | 0 | 2.65 s | 前缀压力减半，但仍被 suffix 挤出 |
| grouped（同前缀 40 条跑完再切） | **90.0%** | 0 | 2.26 s | 当前前缀常驻，旧 suffix 可被回收 |

`measured_s` 在 affinity/grouped 里被一个 ~300s 的离群请求拉高（`wall_max=300.47`），**不能用于比较总耗时**；p50 都在 2.3–2.7s，差异主要是噪声。命中率是可靠指标。

### 96 请求容量敏感性（24 前缀 × 4）

| KV 仿真 / ≈C8 | baseline | affinity |
|---|---:|---:|
| 250 GiB / 125 GiB | **71.0%** | **90.0%** |
| 300 GiB / 150 GiB | 90.0% | 90.0% |
| 320 GiB / 160 GiB | 90.0% | 90.0% |

250 GiB 时 baseline 装不下 24 个前缀（24×5.8 GiB ≈139 GiB C8 + 并发唯一 KV），命中率掉到 71%；affinity 每 rank 12 个前缀，稳在 90%。

### 65 GiB/rank（≈760k tokens，真实容量）策略对比

| 策略 | APC hit | measured_s | 说明 |
|---|---:|---:|---|
| stock + 交错到达 | **2.7%** | 41.88 | 24 前缀互相驱逐 |
| v1 重排（只看 running[0]） | **15.9%** | 41.92 | 只能重排已排队请求 |
| v2 重排（running 集合 + cap1） | **19.7%** | 43.31 | +3.8pp |
| v2 重排（running 集合 + cap2） | **19.5%** | 38.82 | 略快，命中率差不多 |
| affinity（只路由，无组首 warm） | **3.3%** | 42.78 | 容量不够，warm 也留不住 |
| 上游 grouped（组首 warm + 24 组串行） | **90.0%** | 67.26 | 命中最高，但 40 条/组 <64 并发，P 被 underfill |

**关键：高 APC ≠ 高吞吐**。grouped 90% 反而比 stock 41.88s 慢到 67.26s；v2 只有 19.5%，但 38.82s 略快。分组必须保持 2–4 个组在飞，不能一次只跑 1 组。

### 闭环 24 worker（每个前缀 1 条在飞，40 条串行）

| 策略 | makespan | throughput（CPU proxy） | APC hit |
|---|---:|---:|---:|
| stock | 49.57s | 19.37 req/s | 0.48% |
| cap5（每 rank 5 个活跃前缀） | 51.49s | 18.64 req/s | 0.31% |
| cap2（v2 默认） | 56.47s | 17.00 req/s | 0.19% |

闭环下每个前缀只有 1 条在飞，没有 40 条可攒；限制活跃前缀只会降低 `N_eff`，不会提高命中率。**grouping/cap 不是闭环 24 前缀的正确杠杆，需要 prefix pin/retention。** 详见实验F §9。

## 解读

1. **24 个前缀本身不是问题，960 个唯一 suffix 才是**。vLLM 前缀缓存会保留已完成请求的 suffix 块；960 条 × 0.58 GiB（C8）≈ 557 GiB，远超 160 GiB/rank，LRU 会把前缀挤掉。
2. **affinity 只能减半前缀压力，不能阻止 suffix 累积**；960 请求下只从 86.5% 提到 88.8%。
3. **grouped 才能稳住 90%**：同前缀的 40 条连续跑完，当前前缀常驻；旧前缀的 suffix 可以回收。代价是牺牲跨前缀的公平性/尾延迟，需要按业务取舍。
4. **真实 P rank 159–179 GiB C8** 比 160 GiB 略高，baseline 可能刚好在 86–90% 之间；grouped 是更稳的选择。
5. 无抢占（0）：这里是 **prefix cache 驱逐**，不是 KV 准入抢占；`num_preemptions` 看不出来，必须看 prefix hit 和 KV 水位。

## 结论

- 这个 case 的 90% APC **不是“有 24 个前缀”就自动成立**；960 条唯一 suffix 的缓存块会挤掉前缀。
- **prefix-grouped 调度**是最有效的策略：90.0% vs baseline 86.5%（320 GiB 仿真）。
- **DP-aware prefix affinity** 是必要但不充分：容量紧时（250 GiB）它能把 71% 拉回 90%，但在 960 请求下仍不如 grouped。
- 真实 950 上应优先验证：`Available KV cache memory` 是否 ≥160 GiB C8；以及 prefix cache 能否在 960 条 suffix 压力下保住 24 个前缀。

## 复现

```bash
cd /Users/sunlei/code/dsh/vllm
# 1) 起两个 P 仿真 rank（320 GiB 虚拟 KV）
KV_BYTES=343597383680 bash tmp/vslice_glm/start_replicas.sh

# 2) 跑 960 条
.venv/bin/python tmp/vslice_glm/glm_case.py --mode baseline --per-prefix 40
.venv/bin/python tmp/vslice_glm/glm_case.py --mode affinity --per-prefix 40
.venv/bin/python tmp/vslice_glm/glm_case.py --mode grouped  --per-prefix 40
```

每次换 mode 前重启 server，避免 prefix cache 残留。`cpu.py` 是挂载进容器的补丁版；
`start_replicas.sh` 里的 `KV_BYTES` 控制虚拟 KV。

文件：`glm_case.py`、`start_replicas.sh`、`cpu.py`、`results/*-320-960.json`。
