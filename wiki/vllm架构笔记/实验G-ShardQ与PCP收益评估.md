# 实验G：ShardQ vs PCP —— 140K prefill TTFT 解析评估

> 日期：2026-11-21 ｜ 模型：GLM-5.3（78 层 MLA+DSA，`kv=87.8 KiB/token`）
> 目的：在决定是否移植 ShardQ 之前，先估算它能带来多少收益。

---

## 1. 三条路线

| 方案 | 怎么切 | 通信 | 额外卡 |
| :-- | :-- | :-- | :-- |
| **baseline** | TP 按 head 切，indexer 每 rank 都算全量 | 无 | — |
| **ShardQ** | TP group 内按 token 切；indexer 每 token 只算一次 | Q/输出 all-to-all（很小） | 0 |
| **PCP** | 新增一个并行轴，context 切分 | KV ring（12.6 GiB） | ×PCP |

## 2. 模型

```
baseline : T0
ShardQ   : T0·(1−f) + T0·f/tp + Q 交换 + load
PCP      : T0/(pcp·η) + KV 交换 + load

f    = indexer 占 prefill 的比例（未知，需 profile）
η    = PCP 效率（取 0.85）
load = 0.22s（90% APC，126K token × 87.8 KiB @ 50GB/s）
```

**关键假设**：ShardQ 只减少 indexer 的**冗余计算**（每 rank 都在算全量），
不改变 attention 的总 FLOPs（head 切 → token 切，总量相同）。

## 3. 结果（baseline T0 = 14s，tp=8）

| indexer 占比 | ShardQ tp=2 | ShardQ tp=4 | **ShardQ tp=8** | PCP=2（η=0.85） |
| :-- | :-- | :-- | :-- | :-- |
| 10% | 13.53s | 13.18s | 13.00s | 8.49s |
| 20% | 12.83s | 12.13s | 11.77s | 8.49s |
| 30% | 12.13s | 11.08s | **10.55s** | 8.49s |
| 40% | 11.43s | 10.03s | **9.32s** | 8.49s |

ShardQ 加速比（tp=8）：`1.10× / 1.21× / 1.36× / 1.54×`

## 4. 对 SLO 的判断（T0=14s，目标 TTFT < 10s）

| 方案 | 能否达标 | 代价 |
| :-- | :-- | :-- |
| ShardQ（indexer 30%） | ❌ 10.55s，差一点 | 0 额外卡 |
| ShardQ（indexer 40%） | ✅ 9.32s | 0 额外卡 |
| PCP=2 | ✅ 8.49s | +8 卡（TP8→16） |
| PCP=2 × ShardQ | ✅ 6.32s | +8 卡 + 开发 |

**要达到 1.4×（14s→10s），indexer 占比必须 ≥ 30%。**

## 5. 关键敏感性：VA 的 indexer 是否已经冗余？

上游 ShardQ 的前提是"每个 TP rank 都跑全量 indexer"。
VA 的 SFA 是否也这样**需要确认**：

```
如果 VA 已经按 head 切分 indexer：
  indexer 30% 档：10.33s → 14.00s（收益归零）
  indexer 40% 档：9.10s  → 14.00s
```

**这是决定 ShardQ 值不值得做的第一道检查。**

## 6. 其它结论

- **KV 交换不是 PCP 的瓶颈**：12.6 GiB @200GB/s ≈ 0.03s
- **Q 交换可忽略**：每 rank ~0.4GB
- PCP 的真实代价是**卡数**，不是带宽
- 组合方案（PCP+ShardQ）理论上 5.6–6.3s，但上游互斥，需要 VA 自己实现

## 7. 局限

| 项 | 说明 |
| :-- | :-- |
| f 未知 | indexer 占比必须用 profiler（msprof/Nsight）实测 |
| 未计 MoE | GLM-5.3 MoE 的 all-to-all/EP 成本没进模型 |
| 未计 PCP 开销 | LSE merge、负载不均、HCCL 小消息延迟 |
| 未计 attention 效率 | ShardQ 对稀疏 kernel padding 的改善可能额外 5–15% |

## 8. 建议

```
第 0 步：profile 一次 140K prefill，拆出 indexer / attention / MoE 占比
   ├─ indexer < 20%  → ShardQ 收益 <1.2×，不值得单独做
   ├─ indexer ≥ 30%  → ShardQ 可把 14s 压到 ~10.5s（或 40% 时 9.3s）
   └─ 卡够用          → 先上 PCP=2，收益更大且 VA 已支持

第 1 步：如果卡不够 + indexer 占比高 → ShardQ POC（2–3 周）
```

## 9. 复现

```bash
python3 assets/shardq/shardq_sim.py
```

输出存档：`assets/shardq/results.txt`
