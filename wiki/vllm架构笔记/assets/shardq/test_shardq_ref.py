"""ShardQ 布局层单测（本机可跑，无 NPU / 无 vLLM 依赖）。

跑法：
    cd wiki/vllm架构笔记/assets/shardq
    ../../../.venv/bin/python -m pytest -q
"""

import numpy as np
import pytest
import torch

import shardq_ref as sq

WORLD_CASES = [2, 4, 8]
LENS_CASES = [
    [4096],
    [65, 300, 7000],
    [1000, 64, 64, 129],
]


# ---------------------------------------------------------------- 切分


@pytest.mark.parametrize("world", WORLD_CASES)
@pytest.mark.parametrize("lens", LENS_CASES)
def test_zigzag_partitions_all_tokens(world, lens):
    lens = np.array(lens, dtype=np.int64)
    ids, counts = sq.zigzag_split(lens, world)

    # 每个 token 恰好属于一个 rank
    assert sorted(ids.tolist()) == list(range(int(lens.sum())))
    assert counts.sum() == lens.sum()
    assert counts.min() >= 1

    # 组内升序（stable sort 保证）
    for chunk in np.split(ids, np.cumsum(counts)[:-1]):
        assert np.all(np.diff(chunk) > 0)


def test_zigzag_matches_known_layout():
    """把算法钉在纸上：长度 8、4 个 rank 时，切分必须长这样。"""
    ids, counts = sq.zigzag_split(np.array([8]), 4)
    assert ids.tolist() == [0, 7, 1, 6, 2, 5, 3, 4]
    assert counts.tolist() == [2, 2, 2, 2]


@pytest.mark.parametrize("world", WORLD_CASES)
def test_zigzag_balances_token_count(world):
    lens = np.array([7000], dtype=np.int64)
    _, counts = sq.zigzag_split(lens, world)
    assert counts.max() - counts.min() <= 1


def test_zigzag_balances_causal_work():
    """单请求下，各 rank 的因果位置之和应几乎相等（zigzag 的核心收益）。"""
    world = 4
    ids, counts = sq.zigzag_split(np.array([7000]), world)
    per_rank = np.split(ids, np.cumsum(counts)[:-1])
    work = [int(chunk.sum()) for chunk in per_rank]
    assert max(work) / min(work) < 1.01, work


# ---------------------------------------------------------------- 触发条件


def test_split_respects_min_tokens():
    topk = 2048
    seq = np.array([topk + 1], dtype=np.int64)

    assert (
        sq.build_shardq_split(
            np.array([1023]), seq, 4, min_tokens=1024, index_topk=topk
        )
        is None
    )
    assert (
        sq.build_shardq_split(
            np.array([1024]), seq, 4, min_tokens=1024, index_topk=topk
        )
        is not None
    )


def test_split_declines_when_not_sparse():
    """seq_len 不超过 top-k 时没必要稀疏。"""
    lens = np.array([4096], dtype=np.int64)
    assert sq.build_shardq_split(lens, lens, 4, index_topk=4096) is None
    assert sq.build_shardq_split(lens, lens, 4, index_topk=4095) is not None


def test_split_declines_when_a_rank_is_empty():
    lens = np.array([4], dtype=np.int64)
    assert sq.build_shardq_split(lens, lens, 8, min_tokens=1, index_topk=0) is None


def test_split_keeps_decode_tokens():
    query_lens = np.array([1, 1, 65, 300, 7000], dtype=np.int64)
    seq_lens = query_lens + 500
    split = sq.build_shardq_split(
        query_lens, seq_lens, 4, num_decodes=2, min_tokens=1024, index_topk=2048
    )
    assert split is not None
    assert split.num_decode_tokens == 2
    # token id 相对 split 起点，不会把 decode 区间卷进来
    assert split.token_ids.min() >= 0
    assert split.token_ids.max() < split.num_split_tokens


def test_split_declines_without_prefill():
    query_lens = np.array([1, 1], dtype=np.int64)
    assert (
        sq.build_shardq_split(query_lens, query_lens, 4, num_decodes=2, min_tokens=1)
        is None
    )


# ---------------------------------------------------------------- 元数据


def test_local_runs_cover_tokens_and_stay_per_request():
    query_lens = np.array([65, 300, 7000], dtype=np.int64)
    split = sq.build_shardq_split(query_lens, query_lens, 4, min_tokens=1, index_topk=0)
    assert split is not None

    for rank in range(split.world):
        ids = split.local_token_ids(rank)
        runs = sq.local_runs(split, rank, query_lens)
        assert sum(r.length for r in runs) == ids.size

        covered = np.concatenate([np.arange(r.start, r.stop) for r in runs])
        assert np.array_equal(covered, ids)

        # 每个请求最多两段（zigzag 的早晚两截）
        per_req = np.bincount([r.req for r in runs], minlength=query_lens.size)
        assert per_req.max() <= 2


def test_positions_match_absolute_offsets():
    query_lens = np.array([65, 300, 7000], dtype=np.int64)
    context = 200
    seq_lens = query_lens + context
    split = sq.build_shardq_split(
        query_lens, seq_lens, 4, min_tokens=1, index_topk=0
    )
    assert split is not None

    starts = np.concatenate(([0], np.cumsum(query_lens)[:-1]))
    req_of = np.repeat(np.arange(query_lens.size), query_lens)
    for rank in range(split.world):
        ids = split.local_token_ids(rank)
        pos = sq.compute_positions(split, rank, query_lens, seq_lens)
        # 未做 chunked prefill 时：position = 上下文长度 + token 在 query 内的偏移
        assert np.array_equal(pos, ids - starts[req_of[ids]] + context)


def test_renumber_query_start_loc_is_compact():
    query_lens = np.array([1, 1, 65, 300, 7000], dtype=np.int64)
    edge = np.concatenate(([0], np.cumsum(query_lens)))
    split = sq.build_shardq_split(
        query_lens, query_lens + 10, 4, num_decodes=2, min_tokens=1, index_topk=0
    )
    assert split is not None

    for rank in range(split.world):
        new_edge = sq.renumber_query_start_loc(split, rank, edge)
        assert new_edge[0] == 0
        assert np.all(np.diff(new_edge) >= 0)
        assert new_edge[-1] == split.num_decode_tokens + int(split.num_tokens_per_rank[rank])


# ---------------------------------------------------------------- 交换


def _make_split(world, heads=8, dim=16, dtype=torch.bfloat16, num_decodes=0):
    dtype_map = {
        0: np.array([65, 300, 7000], dtype=np.int64),
        2: np.array([1, 1, 65, 300, 7000], dtype=np.int64),
    }
    query_lens = dtype_map[num_decodes]
    seq_lens = query_lens + 100
    split = sq.build_shardq_split(
        query_lens,
        seq_lens,
        world,
        num_decodes=num_decodes,
        min_tokens=1,
        index_topk=0,
    )
    assert split is not None
    total = split.num_decode_tokens + split.num_split_tokens
    q_all = torch.randn(total, world * heads, dim).to(dtype)
    return split, q_all


@pytest.mark.parametrize("world", [2, 4])
@pytest.mark.parametrize("num_decodes", [0, 2])
def test_reference_exchange_round_trip(world, num_decodes):
    """每个 peer 的缓冲区都能被各 owner 的 unshard 恰好填满并还原。"""
    split, q_all = _make_split(world, num_decodes=num_decodes)
    heads = q_all.shape[1] // world
    total, _, dim = q_all.shape
    nd = split.num_decode_tokens

    for peer in range(world):
        full = q_all.new_zeros((total, heads, dim))
        # decode 部分是 peer 自己的块，不经过交换
        full[:nd] = q_all[:nd, peer * heads : (peer + 1) * heads]

        for owner in range(world):
            _, local = sq.reference_shard_q(q_all, split, owner)
            rows, block = sq.reference_unshard_out(local, split, owner)[peer]
            full[rows] = block

        expected = q_all[:, peer * heads : (peer + 1) * heads]
        assert torch.equal(full.view(torch.uint8), expected.contiguous().view(torch.uint8))


def test_exchange_delivers_all_head_blocks():
    """local 的第 r 个 head 块，必须正好是 rank r 对这批 token 的 Q。"""
    world = 4
    split, q_all = _make_split(world, heads=8, dim=16)
    nd = split.num_decode_tokens
    heads = 8

    for owner in range(world):
        _, local = sq.reference_shard_q(q_all, split, owner)
        ids = torch.from_numpy(split.local_token_ids(owner)).long()
        for peer in range(world):
            torch.testing.assert_close(
                local[:, peer * heads : (peer + 1) * heads],
                q_all[nd + ids, peer * heads : (peer + 1) * heads],
                rtol=0,
                atol=0,
            )


def test_exchange_preserves_decode_tokens_bitwise():
    world = 4
    split, q_all = _make_split(world, num_decodes=2)
    for rank in range(world):
        decode_q, _ = sq.reference_shard_q(q_all, split, rank)
        expected = q_all[
            : split.num_decode_tokens,
            rank * (q_all.shape[1] // world) : (rank + 1) * (q_all.shape[1] // world),
        ]
        assert torch.equal(
            decode_q.view(torch.uint8), expected.contiguous().view(torch.uint8)
        )


def test_exchange_output_shape():
    world = 4
    split, q_all = _make_split(world, heads=8, dim=16)
    for rank in range(world):
        decode_q, local = sq.reference_shard_q(q_all, split, rank)
        assert local.shape == (int(split.num_tokens_per_rank[rank]), world * 8, 16)
        assert q_all.shape[1] == world * 8


def test_pad_to_static():
    world = 4
    split, q_all = _make_split(world)
    _, local = sq.reference_shard_q(q_all, split, 0)
    max_local = int(split.num_tokens_per_rank.max()) + 7

    padded = sq.pad_to_static(local, max_local)
    assert padded.shape == (max_local, *local.shape[1:])
    assert torch.equal(padded[: local.shape[0]], local)
    assert padded[local.shape[0] :].abs().sum() == 0

    with pytest.raises(ValueError):
        sq.pad_to_static(local, local.shape[0] - 1)


# ---------------------------------------------------------------- 参考 attention


def test_ref_sparse_mla_matches_dense_when_topk_covers_all():
    torch.manual_seed(0)
    T, S, H, D = 8, 32, 4, 16
    q = torch.randn(T, H, D)
    kv = torch.randn(S, D)
    causal = torch.arange(1, T + 1)

    topk_idx = torch.full((T, S), -1, dtype=torch.long)
    for i in range(T):
        topk_idx[i, : causal[i]] = torch.arange(causal[i])

    ref = sq.RefSparseMla().prefill(q, kv, topk_idx, causal)

    # 全量 top-k 时应等价于标准因果注意力
    for i in range(T):
        sel = kv[: causal[i]]
        logits = (q[i] @ sel.T) * (D ** -0.5)
        probs = torch.softmax(logits, dim=-1)
        torch.testing.assert_close(ref[i], probs @ sel, rtol=1e-4, atol=1e-5)


def test_ref_sparse_mla_rejects_out_of_range_causal():
    q = torch.randn(2, 2, 8)
    kv = torch.randn(4, 8)
    topk = torch.zeros(2, 4, dtype=torch.long)
    with pytest.raises(ValueError):
        sq.RefSparseMla().prefill(q, kv, topk, torch.tensor([1, 99]))
