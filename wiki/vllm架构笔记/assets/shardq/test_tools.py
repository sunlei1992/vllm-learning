"""收益模型与 golden trace 的单测（纯函数，不需要 Scheduler）。"""

import numpy as np
import pytest

import cost_model as cm
import golden_trace as gt


# ---------------------------------------------------------------- cost model


def test_exchange_bytes_shrink_with_tp():
    w = cm.Workload()
    assert cm.exchange_bytes_per_rank(w, 8) < cm.exchange_bytes_per_rank(w, 4)


def test_saved_bytes_grow_with_context():
    w = cm.Workload()
    saved = [cm.saved_indexer_bytes_per_rank(w, 8, ctx) for ctx in (8192, 32768, 131072)]
    assert saved[0] < saved[1] < saved[2]


def test_bandwidth_view_break_even_is_early():
    """带宽账下，小上下文就已经回本（说明瓶颈不在交换）。"""
    w = cm.Workload()
    added, saved = cm.bandwidth_view(w, 8, 8192)
    assert added > 0 and saved > 0
    assert saved / added > 1.0


def test_amdahl_monotonic_in_indexer_share():
    prev = 1.0
    for f in (0.1, 0.2, 0.3, 0.4, 0.5):
        cur = cm.amdahl_speedup(f, tp=8, exchange_ratio=0.02)
        assert cur > prev
        prev = cur


def test_break_even_f_is_a_probability():
    for tp in (4, 8):
        for target in (1.10, 1.25):
            f = cm.break_even_f(tp, exchange_ratio=0.02, target_speedup=target)
            assert 0.0 < f < 1.0
    # 目标越高，要求的 indexer 占比越大
    assert cm.break_even_f(8, 0.02, 1.25) > cm.break_even_f(8, 0.02, 1.10)


# ---------------------------------------------------------------- golden trace


class _Split:
    def __init__(self, nd, per_rank, ids):
        self.num_decode_tokens = nd
        self.num_tokens_per_rank = np.array(per_rank, dtype=np.int64)
        self.token_ids = np.array(ids, dtype=np.int64)


def _records():
    s1 = _Split(0, [2, 2], [0, 3, 1, 2])
    s2 = _Split(2, [1, 1], [0, 2])
    return [
        gt.step_record([4], [4], s1),
        gt.step_record([1, 1, 2], [9, 9, 10], s2),
        gt.step_record([1], [11], None),
    ]


def test_step_record_shape():
    rec = _records()[1]
    assert rec["split"]["num_decode_tokens"] == 2
    assert rec["split"]["num_tokens_per_rank"] == [1, 1]
    assert len(rec["split"]["token_ids_sha256"]) == 16


def test_compare_identical():
    assert gt.compare(_records(), _records()) == []


def test_compare_detects_token_ids_change():
    left, right = _records(), _records()
    right[0]["split"]["token_ids_sha256"] = "0" * 16
    diffs = gt.compare(left, right)
    assert any("token_ids_sha256" in d for d in diffs)


def test_compare_detects_length_change():
    diffs = gt.compare(_records(), _records()[:-1])
    assert any("step count" in d for d in diffs)


def test_compare_detects_nullsplit_flip():
    left, right = _records(), _records()
    right[2]["split"] = _records()[0]["split"]
    diffs = gt.compare(left, right)
    assert any("split" in d for d in diffs)


def test_hash_is_dtype_insensitive():
    assert gt._hash(np.array([1, 2], dtype=np.int32)) == gt._hash(
        np.array([1, 2], dtype=np.int64)
    )
