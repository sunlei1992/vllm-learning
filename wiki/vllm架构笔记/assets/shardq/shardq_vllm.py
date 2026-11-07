"""把 vLLM 的 `CommonAttentionMetadata` 接到 `shardq_ref`。

这一层只做「取字段 + 调纯函数」，不碰任何设备，因此可以在 Mac 上跑。
目标版本是 vllm-ascend 锁定的 vLLM commit（`a98247ab`），
但字段在 0.28 上同样存在，两个环境都能测。
"""

from __future__ import annotations

import numpy as np

from shardq_ref import ShardQSplit, build_shardq_split


def split_from_common_attn_metadata(
    common_attn_metadata,
    *,
    world: int,
    min_tokens: int = 1024,
    index_topk: int = 2048,
    num_speculative_tokens: int = 0,
) -> ShardQSplit | None:
    """从真实 metadata 算本步的 ShardQ 分片；None 表示回退到 head 分片。

    与上游 `build_shardq_split` 对齐：
    - decode 请求的判定用 `split_decodes_and_prefills(decode_threshold=1+num_spec)`；
    - 阈值与稀疏性判定都只看 **prefill 部分**；
    - 任何一步对不上（token 计数、空 rank）都返回 None，不抛异常。
    """
    from vllm.v1.attention.backends.utils import split_decodes_and_prefills

    num_decodes, num_prefills, num_decode_tokens, num_prefill_tokens = (
        split_decodes_and_prefills(
            common_attn_metadata,
            decode_threshold=1 + num_speculative_tokens,
        )
    )
    if num_prefills == 0:
        return None

    seq_lens_cpu = common_attn_metadata.seq_lens_cpu_upper_bound
    if seq_lens_cpu is None:
        raise ValueError("seq_lens_cpu_upper_bound is required for ShardQ")
    seq_lens = np.asarray(seq_lens_cpu, dtype=np.int64)
    query_lens = np.asarray(
        common_attn_metadata.query_start_loc_cpu.diff(), dtype=np.int64
    )
    if seq_lens.size != query_lens.size:
        raise ValueError("seq_lens and query_lens disagree on the request count")

    # 防御：prefill token 数必须和 split_decodes_and_prefills 的说法一致
    prefill_lens = query_lens[num_decodes:]
    if int(prefill_lens.sum()) != int(num_prefill_tokens):
        return None

    split = build_shardq_split(
        query_lens,
        seq_lens,
        world,
        num_decodes=num_decodes,
        min_tokens=min_tokens,
        index_topk=index_topk,
    )
    if split is None:
        return None
    # 双保险：decode token 数必须与 metadata 的判定一致
    if split.num_decode_tokens != int(num_decode_tokens):
        raise ValueError(
            f"decode token mismatch: split={split.num_decode_tokens}, "
            f"metadata={num_decode_tokens}"
        )
    return split
