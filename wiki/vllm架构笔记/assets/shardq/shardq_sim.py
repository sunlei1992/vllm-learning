"""ShardQ vs PCP: prefill TTFT model for GLM-5.3 @ 140K (analytic dry run).

Strategies
  baseline : TP head-sharded prefill; the DSA indexer runs on every TP rank
  shardq   : tokens sharded inside the TP group; the indexer runs once per
             token (per-rank indexer work / tp); Q and output all-to-all
  pcp      : one extra context-parallel axis; compute / pcp with an
             efficiency factor, KV ring-exchanged

Every number is an assumption, not a measurement.
"""

TOKENS = 140_000
KV_BYTES_PER_TOKEN = 89_856      # GLM-5.3: 78 layers x (512 + 64) x 2 B
H, DQ = 64, 192                  # Q heads / head dim, for the Q exchange
Q_BYTES = H * DQ * 2
LOAD_S = 0.22                    # 90% APC: load 126K tokens x 87.8 KiB at 50 GB/s


def shardq_time(t0, f_index, tp, bw_gbps, indexer_replicated=True):
    t_index = t0 * f_index
    sharded = t_index / tp if indexer_replicated else t_index
    comm = (tp - 1) / tp * (TOKENS * Q_BYTES / tp) / (bw_gbps * 1e9)
    return t0 - t_index + sharded + 2 * comm + LOAD_S


def pcp_time(t0, pcp, bw_gbps, eff=0.85):
    comm = (pcp - 1) / pcp * (TOKENS * KV_BYTES_PER_TOKEN) / (bw_gbps * 1e9)
    return t0 / (pcp * eff) + comm + LOAD_S


def main():
    print(f"L={TOKENS} tokens, kv={KV_BYTES_PER_TOKEN/1024:.1f} KiB/token "
          f"({TOKENS*KV_BYTES_PER_TOKEN/1024**3:.1f} GiB/request), tp=8, "
          f"load={LOAD_S*1000:.0f}ms\n")

    for t0 in (10.0, 14.0, 18.0):
        print(f"=== baseline prefill T0={t0:.0f}s (target TTFT <= 10s) ===")
        print(f"{'indexer%':>8} | {'ShardQ tp=2':>11} | {'ShardQ tp=4':>11} | "
              f"{'ShardQ tp=8':>11} | {'PCP=2(eff.85)':>13}")
        for f in (0.10, 0.20, 0.30, 0.40):
            print(f"{f*100:7.0f}% | "
                  f"{shardq_time(t0, f, 2, 200):10.2f}s | "
                  f"{shardq_time(t0, f, 4, 200):10.2f}s | "
                  f"{shardq_time(t0, f, 8, 200):10.2f}s | "
                  f"{pcp_time(t0, 2, 200, 0.85):12.2f}s")
        print()

    print("=== ShardQ speedup = 1 / ((1-f) + f/tp), tp=8 ===")
    for f in (0.10, 0.20, 0.30, 0.40):
        print(f"  indexer {f*100:2.0f}% -> {1/((1-f)+f/8):.2f}x")

    print("\n=== sensitivity: if VA already shards the indexer (no replication) ===")
    for f in (0.30, 0.40):
        rep = shardq_time(14.0, f, 8, 200) - LOAD_S
        norep = shardq_time(14.0, f, 8, 200, indexer_replicated=False) - LOAD_S
        print(f"  indexer {f*100:2.0f}%: replicated {rep:.2f}s vs already-sharded {norep:.2f}s")

    print("\n=== PCP: speedup vs extra cards (no efficiency loss) ===")
    for pcp in (2, 4):
        for bw in (200, 400):
            t = pcp_time(14.0, pcp, bw, 1.0)
            print(f"  PCP={pcp} @{bw}GB/s: {t:.2f}s, cards x{pcp}, speedup {14/t:.2f}x")

    print("\n=== hypothetical: PCP x ShardQ combined (needs VA work) ===")
    for f in (0.30, 0.40):
        combined = pcp_time(14.0, 2, 200, 0.85) - LOAD_S
        combined = combined * ((1 - f) + f / 8) + LOAD_S
        print(f"  indexer {f*100:2.0f}%, PCP=2 x TP8: {combined:.2f}s")


if __name__ == "__main__":
    main()
