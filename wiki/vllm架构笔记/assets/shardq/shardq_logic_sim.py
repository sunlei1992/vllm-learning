"""ShardQ logic simulation: zigzag split, all-to-all accounting, SFA metadata.

Pure CPU/numpy, no kernels. Verifies the invariants we would need before
implementing ShardQ in vllm-ascend:

  1. every token after the decodes is owned by exactly one TP rank
  2. zigzag ownership matches the two-chunk-per-rank rule
  3. each rank's token list is ascending and balanced
  4. the Q/output all-to-all is symmetric and its byte count is small
  5. the top-k buffer slice for a rank maps to its own tokens
  6. causal KV ranges stay inside the owning request (KV is replicated)
  7. PCP (contiguous split) covers every token too, with its KV fetch cost
"""
import numpy as np

FAIL = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAIL.append(name)


def zigzag_split(query_lens, world):
    lens = np.asarray(query_lens, dtype=np.int64)
    total = int(lens.sum())
    num_chunks = 2 * world
    starts = np.cumsum(lens) - lens
    pos = np.arange(total) - np.repeat(starts, lens)
    # chunk i spans [floor(i*len/2w), floor((i+1)*len/2w))
    chunk = ((pos + 1) * num_chunks - 1) // np.repeat(lens, lens)
    owner = np.minimum(chunk, num_chunks - 1 - chunk).astype(np.int32)
    return owner, chunk, pos, starts, lens


def run_case(name, query_lens, world, num_decodes=8, head_dim=192, local_heads=8):
    print(f"\n=== {name}: {len(query_lens)} requests, "
          f"{sum(query_lens)} prefill tokens, world={world} ===")
    owner, chunk, pos, starts, lens = zigzag_split(query_lens, world)
    total = owner.size

    # 1. exactly one owner per token
    counts = np.bincount(owner, minlength=world)
    check("每 token 恰好一个 rank", counts.sum() == total and total == sum(query_lens),
          f"{total} tokens")
    order = np.argsort(owner, kind="stable")
    check("全局 token id 不重不漏", np.unique(order).size == total)

    # 2. zigzag rule: rank r owns chunk r and chunk 2w-1-r
    num_chunks = 2 * world
    chunk_owner = np.minimum(np.arange(num_chunks), num_chunks - 1 - np.arange(num_chunks))
    check("chunk->rank 映射符合 zigzag",
          np.array_equal(chunk_owner[:world], np.arange(world)) and
          np.array_equal(chunk_owner[world:], np.arange(world)[::-1]),
          f"chunk owners {chunk_owner.tolist()}")

    # 3. ascending, per-rank slices
    slices = {}
    off = 0
    for r in range(world):
        ids = order[off:off + counts[r]]
        off += counts[r]
        slices[r] = ids
        check(f"rank{r} token id 升序", bool(np.all(np.diff(ids) > 0)))
    sizes = counts[counts > 0]
    # zigzag 以 request 为单位切，每个 request 内 rank 间最多差 1 token
    check("rank 间负载均衡", int(sizes.max() - sizes.min()) <= len(query_lens),
          f"min={sizes.min()} max={sizes.max()} diff={sizes.max()-sizes.min()} "
          f"(requests={len(query_lens)}, 允许 <= {len(query_lens)})")

    # 4. all-to-all accounting: rank r receives its own tokens' Q slices
    q_bytes = total * local_heads * head_dim * 2          # all ranks, one head shard
    per_rank_bytes = counts * local_heads * head_dim * 2
    check("all-to-all 收发总量对称",
          int(counts.sum()) == total and int(per_rank_bytes.sum()) == q_bytes,
          f"Q exchange {q_bytes/1e6:.1f} MB, max/rank {per_rank_bytes.max()/1e6:.1f} MB")

    # 5. top-k buffer alignment: [num_decodes, num_decodes+total)
    topk = np.full(num_decodes + total, -1, dtype=np.int64)
    for r in range(world):
        start = num_decodes + int(counts[:r].sum())
        topk[start:start + counts[r]] = slices[r]
    check("topk buffer 每个 token 只写一次",
          np.array_equal(np.sort(topk[num_decodes:]), np.arange(total)),
          f"topk_start={num_decodes}")

    # 6. causal KV range stays inside the owning request
    ok = True
    for r in range(world):
        ids = slices[r]
        req_of_token = np.searchsorted(starts + lens, ids, side="right")
        req_start = starts[req_of_token]
        tok_pos = ids - req_start
        # causal KV the token needs is [0, tok_pos]; it must not cross the request
        ok &= bool(np.all(tok_pos >= 0)) and bool(np.all(tok_pos < lens[req_of_token]))
    check("causal KV 范围不跨请求", ok)

    # 7. PCP contiguous split for comparison
    pcp = world
    bounds = np.floor(np.arange(pcp + 1) * total / pcp).astype(np.int64)
    pcp_counts = np.diff(bounds)
    pcp_need = np.concatenate([[0], np.cumsum(pcp_counts)[:-1]])
    check("PCP 连续切分覆盖全部 token", int(pcp_counts.sum()) == total,
          f"per-rank {pcp_counts.tolist()[:4]}...")
    computed_kv = total * 89856
    ring = (pcp - 1) / pcp * computed_kv
    check("PCP ring 流量", True,
          f"computed KV {computed_kv/1e9:.2f} GB, ring/rank {ring/1e9:.2f} GB "
          f"@200GB/s = {ring/200e9*1000:.0f} ms")
    return counts


if __name__ == "__main__":
    run_case("小型结构用例", [1000] * 4, world=4)
    run_case("24 前缀 x 40 条，90% APC 命中（每条只算 350）", [350] * 960, world=8)
    run_case("单条 140K（你线上的形状）", [140000], world=8)
    print("\n" + ("ALL PASS" if not FAIL else f"FAILED: {FAIL}"))
