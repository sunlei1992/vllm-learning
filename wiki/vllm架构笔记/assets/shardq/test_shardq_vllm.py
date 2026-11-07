"""接真实 `CommonAttentionMetadata` 的适配器测试。

需要装好的 vLLM（vllm-ascend 锁定的 `a98247ab` 最好），以及同版本的
`tests/v1/attention/utils.py`。缺任意一个就 skip。

跑法：
    /Users/sunlei/code/dsh/vllm/.venv-va030/bin/python -m pytest -q test_shardq_vllm.py
"""

import pathlib
import sys

import numpy as np
import pytest

import shardq_ref as sq
import shardq_vllm as sv

vllm = pytest.importorskip("vllm")


def _load_vllm_test_utils():
    """从已安装 vllm 的位置推导仓库根，再导入它的测试工具。"""
    root = pathlib.Path(vllm.__file__).resolve().parent.parent
    if not (root / "tests" / "v1" / "attention" / "utils.py").exists():
        pytest.skip(f"vllm test utils not found under {root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tests.v1.attention.utils import BatchSpec, create_common_attn_metadata

    return BatchSpec, create_common_attn_metadata


def _make_metadata(seq_lens, query_lens, block_size=16):
    import torch

    BatchSpec, create = _load_vllm_test_utils()
    return create(
        BatchSpec(seq_lens=list(seq_lens), query_lens=list(query_lens)),
        block_size=block_size,
        device=torch.device("cpu"),
    )


def test_adapter_matches_pure_function():
    query_lens = [1, 1, 65, 300, 7000]
    seq_lens = [q + 500 for q in query_lens]
    cam = _make_metadata(seq_lens, query_lens)

    split = sv.split_from_common_attn_metadata(
        cam, world=4, min_tokens=1024, index_topk=2048
    )
    expected = sq.build_shardq_split(
        np.array(query_lens),
        np.array(seq_lens),
        world=4,
        num_decodes=2,
        min_tokens=1024,
        index_topk=2048,
    )

    assert split is not None and expected is not None
    assert split.num_decode_tokens == expected.num_decode_tokens == 2
    assert np.array_equal(split.token_ids, expected.token_ids)
    assert np.array_equal(split.num_tokens_per_rank, expected.num_tokens_per_rank)


def test_adapter_declines_without_prefill():
    cam = _make_metadata([501, 501], [1, 1])
    assert sv.split_from_common_attn_metadata(cam, world=4) is None


def test_adapter_respects_min_tokens():
    cam_short = _make_metadata([1512], [512])
    assert sv.split_from_common_attn_metadata(cam_short, world=4, min_tokens=1024) is None

    cam_ok = _make_metadata([3024], [1024])
    assert sv.split_from_common_attn_metadata(cam_ok, world=4, min_tokens=1024) is not None


def test_adapter_declines_when_not_sparse():
    cam = _make_metadata([4096], [4096])
    assert sv.split_from_common_attn_metadata(cam, world=4, index_topk=4096) is None
    assert sv.split_from_common_attn_metadata(cam, world=4, index_topk=4095) is not None


def test_adapter_honours_speculative_decode_threshold():
    """query_len <= 1 + num_spec 的请求算 decode，不参与分片。"""
    query_lens = [3, 3, 2000]
    seq_lens = [303, 303, 2300]
    cam = _make_metadata(seq_lens, query_lens)

    split = sv.split_from_common_attn_metadata(
        cam, world=4, min_tokens=1024, index_topk=2048, num_speculative_tokens=2
    )
    assert split is not None
    assert split.num_decode_tokens == 6
