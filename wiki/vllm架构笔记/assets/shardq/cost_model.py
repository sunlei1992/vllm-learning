"""ShardQ 收益模型：交换成本 vs 省下的 indexer 工作。

两个视角：
1. 带宽账：交换的字节 / 省下的 K 读字节，判断"理论上限"；
2. Amdahl 账：indexer 占 prefill 时间的比例 f，判断"实际能拿多少"。

纯计算，无硬件依赖，用来在 950DT 上机前决定值不值得做。

跑法：
    python cost_model.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

BYTES_FP16 = 2


@dataclass(frozen=True)
class Hw:
    """950DT 公开规格（2026-09 超节点公布）。"""

    hbm_gbps: float = 4000.0  # 4 TB/s per die
    fabric_gbps: float = 1720.0  # 1.72 PB/s / 1024 dies ≈ 1.68 TB/s per die


@dataclass(frozen=True)
class Workload:
    prefill_tokens: int = 4096
    heads: int = 128
    qk_dim: int = 576
    out_dim: int = 512
    index_dim: int = 128  # DSA indexer 的 MQA head dim（fp8，1 byte）
    index_bytes: int = 1


def exchange_bytes_per_rank(w: Workload, tp: int, hw: Hw | None = None) -> float:
    """本 rank 在两次 all-to-all 中要发的字节数（Q + 输出）。"""
    local_tokens = w.prefill_tokens / tp
    heads_per_rank = w.heads / tp
    q_bytes = (tp - 1) * local_tokens * heads_per_rank * w.qk_dim * BYTES_FP16
    out_bytes = (tp - 1) * local_tokens * heads_per_rank * w.out_dim * BYTES_FP16
    return q_bytes + out_bytes


def saved_indexer_bytes_per_rank(w: Workload, tp: int, ctx: int) -> float:
    """不分片时每个 rank 都要为全部 token 读 ctx 的 K；分片后只读 1/tp。"""
    full = w.prefill_tokens * ctx * w.index_dim * w.index_bytes
    return full * (1 - 1 / tp)


def bandwidth_view(w: Workload, tp: int, ctx: int, hw: Hw | None = None):
    hw = hw or Hw()
    added_ms = exchange_bytes_per_rank(w, tp) / (hw.fabric_gbps * 1e9) * 1e3
    saved_ms = saved_indexer_bytes_per_rank(w, tp, ctx) / (hw.hbm_gbps * 1e9) * 1e3
    return added_ms, saved_ms


def amdahl_speedup(f_indexer: float, tp: int, exchange_ratio: float) -> float:
    """indexer 占 prefill 的 f；分片后 indexer 剩 1/tp，另加 exchange_ratio 的开销。"""
    remaining = 1.0 - f_indexer * (1 - 1 / tp) + exchange_ratio
    return 1.0 / remaining


def print_bandwidth_table(tp: int = 8) -> None:
    w = Workload()
    print(f"\n[带宽账] tp={tp}, prefill_tokens={w.prefill_tokens}")
    print(f"{'ctx':>8} {'exchange_ms':>12} {'saved_ms':>10} {'saved/exchange':>15}")
    for ctx in (8192, 32768, 131072, 524288, 1_000_000):
        added, saved = bandwidth_view(w, tp, ctx)
        print(f"{ctx:>8} {added:>12.3f} {saved:>10.2f} {saved / added:>15.1f}x")


def print_amdahl_table() -> None:
    print("\n[Amdahl 账] 需要 indexer 占 prefill 多大比例，才值得开 ShardQ")
    print(f"{'f_indexer':>10} {'tp=4':>8} {'tp=8':>8}")
    for f in (0.1, 0.2, 0.3, 0.4, 0.5):
        row = [f"{amdahl_speedup(f, tp, exchange_ratio=0.02):>8.2f}x" for tp in (4, 8)]
        print(f"{f:>10.1f} {row[0]} {row[1]}")


def break_even_f(tp: int, exchange_ratio: float, target_speedup: float) -> float:
    """要拿到 target_speedup，indexer 至少得占多少。"""
    remaining = 1.0 / target_speedup
    return (1.0 + exchange_ratio - remaining) / (1 - 1 / tp)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print_bandwidth_table(tp=8)
    print_bandwidth_table(tp=4)
    print_amdahl_table()
    print("\n[门槛] 拿到 1.10x / 1.25x 所需的 indexer 占比（exchange_ratio=0.02）")
    for tp in (4, 8):
        for target in (1.10, 1.25):
            print(f"  tp={tp} target={target:.2f}x -> f_indexer >= {break_even_f(tp, 0.02, target):.3f}")


if __name__ == "__main__":
    main()
