# ShardQ vs PCP：140K prefill TTFT 解析模型结果

运行：`python3 shardq_sim.py`（每行一个假设，不是实测）

## 主表（baseline T0 = 14s，tp=8）

| indexer 占比 | ShardQ tp=2 | ShardQ tp=4 | ShardQ tp=8 | PCP=2 (eff 0.85) |
| :-- | :-- | :-- | :-- | :-- |
| 10% | 13.53s | 13.18s | 13.00s | 8.49s |
| 20% | 12.83s | 12.13s | 11.77s | 8.49s |
| 30% | 12.13s | 11.08s | 10.55s | 8.49s |
| 40% | 11.43s | 10.03s | 9.32s | 8.49s |

## ShardQ 加速比（tp=8）

| indexer 占比 | 加速比 |
| :-- | :-- |
| 10% | 1.10× |
| 20% | 1.21× |
| 30% | 1.36× |
| 40% | 1.54× |

## PCP（无效率损失）

| 配置 | TTFT | 卡数 | 加速比 |
| :-- | :-- | :-- | :-- |
| PCP=2 @200GB/s | 7.25s | ×2 | 1.93× |
| PCP=4 @200GB/s | 3.77s | ×4 | 3.72× |

## 关键敏感性

- **indexer 是否已在 TP 上冗余**：若 VA 已按 head 切分 indexer，ShardQ 收益接近 0
  （30% 档：10.33s → 14.00s）
- PCP 的 KV 交换量 12.6 GiB，200GB/s 下仅 ~0.03s，**不是瓶颈**
- ShardQ 的 Q/输出交换仅 ~0.4GB/rank，可忽略
- 组合（PCP=2 × ShardQ，需 VA 额外工作）：indexer 30% → 6.32s，40% → 5.59s
