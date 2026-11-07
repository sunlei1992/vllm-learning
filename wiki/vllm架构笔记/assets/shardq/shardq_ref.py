"""ShardQ 布局层参考实现（纯 CPU，无设备依赖）。

对应 vLLM 上游 `vllm/v1/attention/ops/shardq.py` 的
`zigzag_split` / `shard_q` / `unshard_out`，去掉了 Triton 与对称内存，
只保留可移植的布局语义。目标是：

1. 本机可单测、可证明与上游等价；
2. 结构上可以整体拷进 `vllm_ascend/attention/shardq.py`，
   把 `reference_*` 换成 HCCL 实现即可。

名词：
- split token：prefill 步里分给各 rank 的 token（decode token 不参与分片）
- token_ids：按 rank 分组、组内升序的 token id（相对第一个 split token）
- positions：token 在其请求内的绝对位置（chunked prefill 下不是简单下标）
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch


# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ShardQSplit:
    """一步 ShardQ 的分片结果。"""

    num_decode_tokens: int
    """本步保持 head 分片的 decode token 数（分片前的前缀）。"""

    token_ids: np.ndarray
    """[num_split_tokens] 按 rank 分组、组内升序的 token id（相对 split 起点）。"""

    num_tokens_per_rank: np.ndarray
    """[world] 每个 rank 分到多少 token。"""

    @property
    def world(self) -> int:
        return int(self.num_tokens_per_rank.size)

    @property
    def num_split_tokens(self) -> int:
        return int(self.num_tokens_per_rank.sum())

    def rank_offset(self, rank: int) -> int:
        return int(self.num_tokens_per_rank[:rank].sum())

    def local_token_ids(self, rank: int) -> np.ndarray:
        start = self.rank_offset(rank)
        stop = start + int(self.num_tokens_per_rank[rank])
        return self.token_ids[start:stop]


@dataclass(frozen=True)
class LocalRun:
    """本 rank 在某个请求内的一段连续 token。"""

    req: int
    """prefill 请求下标（不含 decode）。"""
    start: int
    """起始 token id（含）。"""
    stop: int
    """结束 token id（不含）。"""

    @property
    def length(self) -> int:
        return self.stop - self.start


# --------------------------------------------------------------------------
# 切分
# --------------------------------------------------------------------------


def zigzag_split(query_lens: np.ndarray, world: int) -> tuple[np.ndarray, np.ndarray]:
    """把每个请求切成 2*world 段，rank r 拿第 r 段和倒数第 r 段。

    这样每个 rank 都同时拿到「靠前的短因果」和「靠后的长因果」，
    因果工作量接近均衡（见模块测试）。
    """
    query_lens = np.asarray(query_lens, dtype=np.int64)
    if query_lens.ndim != 1 or query_lens.size == 0:
        raise ValueError("query_lens must be a non-empty 1-D array")
    if (query_lens < 0).any():
        raise ValueError("query_lens must be non-negative")
    if world < 1:
        raise ValueError("world must be >= 1")

    total = int(query_lens.sum())
    num_chunks = 2 * world
    starts = np.cumsum(query_lens) - query_lens
    pos = np.arange(total) - np.repeat(starts, query_lens)
    denom = np.repeat(query_lens, query_lens)
    chunk = ((pos + 1) * num_chunks - 1) // denom
    owner = np.minimum(chunk, num_chunks - 1 - chunk).astype(np.uint8)
    # owner 只有 2*world 种取值，stable sort 等价于按 rank 分桶且组内保序。
    order = np.argsort(owner, kind="stable")
    counts = np.bincount(owner, minlength=world).astype(np.int64)
    return order, counts


def build_shardq_split(
    query_lens: np.ndarray,
    seq_lens: np.ndarray,
    world: int,
    *,
    num_decodes: int = 0,
    min_tokens: int = 1024,
    index_topk: int = 2048,
) -> ShardQSplit | None:
    """判断本步是否触发 ShardQ，并给出分片。

    触发条件（对齐上游 `build_shardq_split`）：
    1. split token 数 >= min_tokens；
    2. 至少一个 prefill 请求的 seq_len > index_topk（否则不稀疏）；
    3. 每个 rank 至少分到一个 token。

    返回 None 表示回退到 head 分片。
    """
    query_lens = np.asarray(query_lens, dtype=np.int64)
    seq_lens = np.asarray(seq_lens, dtype=np.int64)
    if query_lens.shape != seq_lens.shape:
        raise ValueError("query_lens and seq_lens must have the same shape")
    if not 0 <= num_decodes <= query_lens.size:
        raise ValueError("num_decodes out of range")

    num_decode_tokens = int(query_lens[:num_decodes].sum())
    prefill_lens = query_lens[num_decodes:]
    num_prefill_tokens = int(prefill_lens.sum())
    if num_prefill_tokens == 0 or num_prefill_tokens < min_tokens:
        return None
    if int(seq_lens[num_decodes:].max()) <= index_topk:
        return None

    token_ids, counts = zigzag_split(prefill_lens, world)
    if int(counts.min()) == 0:
        # 空 rank 会让 kernel 收到空 batch，直接回退。
        return None
    return ShardQSplit(num_decode_tokens, token_ids, counts)


# --------------------------------------------------------------------------
# 元数据：run 划分 / positions / query_start_loc 重编号
# --------------------------------------------------------------------------


def _req_of_prefill_token(query_lens: np.ndarray, num_decodes: int) -> np.ndarray:
    prefill = np.asarray(query_lens, dtype=np.int64)[num_decodes:]
    return np.repeat(np.arange(prefill.size), prefill)


def local_runs(
    split: ShardQSplit, rank: int, query_lens: np.ndarray, *, num_decodes: int = 0
) -> list[LocalRun]:
    """本 rank 的 token 按「同一请求内的连续段」切分成 run。

    zigzag 会把一个请求切成早晚两段，所以每个请求最多产生 2 个 run。
    真机上就是把这些 run 表达成「伪请求」喂给 metadata builder。
    """
    req_of = _req_of_prefill_token(query_lens, num_decodes)
    ids = split.local_token_ids(rank)
    if ids.size == 0:
        return []
    reqs = req_of[ids]
    breaks = np.nonzero((np.diff(ids) != 1) | (np.diff(reqs) != 0))[0] + 1
    bounds = np.concatenate(([0], breaks, [ids.size]))
    return [
        LocalRun(req=int(reqs[a]), start=int(ids[a]), stop=int(ids[b - 1]) + 1)
        for a, b in zip(bounds[:-1], bounds[1:])
    ]


def compute_positions(
    split: ShardQSplit,
    rank: int,
    query_lens: np.ndarray,
    seq_lens: np.ndarray,
    *,
    num_decodes: int = 0,
) -> np.ndarray:
    """本 rank 每个 split token 在其请求内的绝对位置。

    上游公式：`gather_ids + seq_lens[req] - query_start_loc[req + 1]`。
    在 chunked prefill 下，`query_start_loc[req + 1]` 指向当前 chunk 末尾，
    所以 `seq_lens - 该值` 就是 chunk 之前的上下文长度，不能简单用下标代替。
    """
    query_lens = np.asarray(query_lens, dtype=np.int64)
    seq_lens = np.asarray(seq_lens, dtype=np.int64)
    ids = split.local_token_ids(rank)
    req_of = _req_of_prefill_token(query_lens, num_decodes)
    local_req = req_of[ids]
    global_req = local_req + num_decodes

    starts = np.cumsum(query_lens) - query_lens
    query_end = starts[global_req] + query_lens[global_req]
    return (split.num_decode_tokens + ids) + seq_lens[global_req] - query_end


def renumber_query_start_loc(
    split: ShardQSplit, rank: int, query_start_loc_cpu: np.ndarray
) -> np.ndarray:
    """把全局 query_start_loc 重新编号成本 rank 的紧凑布局。

    decode token 保持原位，split token 紧跟其后、按 token id 升序。
    """
    indices = np.concatenate(
        (
            np.arange(split.num_decode_tokens),
            split.local_token_ids(rank) + split.num_decode_tokens,
        )
    )
    indices.sort()
    return np.searchsorted(indices, np.asarray(query_start_loc_cpu), side="left")


# --------------------------------------------------------------------------
# 参考实现：交换（单进程语义，替代 all-to-all）
# --------------------------------------------------------------------------


def reference_shard_q(
    q_all: torch.Tensor, split: ShardQSplit, rank: int
) -> tuple[torch.Tensor, torch.Tensor]:
    """模拟 `shard_q` 在 rank 上的结果。

    Args:
        q_all: [T, world * H, D]，**全部 head** 的 Q（单进程测试时由调用方提供）。
            真机上每个 rank 只有自己那 H 个 head，由 all-to-all 补齐。
        split: 分片。
        rank: 目标 rank。

    Returns:
        (decode_q [Nd, H, D], local [T_rank, world * H, D])
        其中 local 的第 r 个 head 块来自 rank r，token 顺序即本 rank 的 local ids。
    """
    world = split.world
    nd = split.num_decode_tokens
    total, world_heads, dim = q_all.shape
    if world_heads % world != 0:
        raise ValueError("head count must be divisible by world")
    heads = world_heads // world
    if total != nd + split.num_split_tokens:
        raise ValueError("q_all token count does not match the split")

    decode_q = q_all[:nd, rank * heads : (rank + 1) * heads].contiguous()
    ids = torch.from_numpy(split.local_token_ids(rank)).long()
    local = q_all[nd + ids]  # [T_rank, world*H, D]，每个 head 块来自对应 rank
    return decode_q, local.contiguous()


def reference_unshard_out(
    local: torch.Tensor, split: ShardQSplit, owner: int
) -> dict[int, tuple[np.ndarray, torch.Tensor]]:
    """模拟 `unshard_out`：owner 把输出按 head 块寄回各 peer。

    返回 `{peer: (全局行号, peer 的 head 块)}`。peer 收到后直接写到自己缓冲区的
    这些行上。每个 token 行恰好被一个 owner 写一次——这一点由往返测试验证。

    Args:
        local: [T_owner, world * H, D]，owner 跑完 attention 的输出。
        split: 分片。
        owner: 产出这份输出的 rank。
    """
    world = split.world
    nd = split.num_decode_tokens
    if local.shape[1] % world != 0:
        raise ValueError("head count must be divisible by world")
    if local.shape[0] != int(split.num_tokens_per_rank[owner]):
        raise ValueError("local rows do not match this owner's token count")

    heads = local.shape[1] // world
    rows = nd + split.local_token_ids(owner)
    return {
        peer: (rows, local[:, peer * heads : (peer + 1) * heads])
        for peer in range(world)
    }


def pad_to_static(local: torch.Tensor, max_local: int) -> torch.Tensor:
    """把本 rank 的 token 数 pad 到固定长度（ACL graph 友好 / 等长 all-to-all）。"""
    if local.shape[0] > max_local:
        raise ValueError(f"local tokens {local.shape[0]} exceed static capacity {max_local}")
    padded = local.new_zeros((max_local, *local.shape[1:]))
    padded[: local.shape[0]] = local
    return padded


# --------------------------------------------------------------------------
# 参考实现：最小 sparse MLA（用于上机对拍 / 契约检查）
# --------------------------------------------------------------------------


class RefSparseMla:
    """单请求的 sparse MLA 参考实现。

    只求语义正确，不求性能：按 top-k 索引取 KV，做因果加权的 softmax 聚合。
    上机时用同一个输入跑真 kernel，逐元素对拍。
    """

    def __init__(self, scale: float | None = None) -> None:
        self.scale = scale

    def prefill(
        self,
        q: torch.Tensor,
        kv: torch.Tensor,
        topk_idx: torch.Tensor,
        causal_lens: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            q: [T, H, D]
            kv: [S, D]（MLA latent，单 head）
            topk_idx: [T, K] long，-1 表示 padding
            causal_lens: [T] long，第 i 个 token 可见的 KV 上界（不含）
        """
        if q.dim() != 3 or kv.dim() != 2:
            raise ValueError("q must be [T,H,D] and kv must be [S,D]")
        if topk_idx.shape[0] != q.shape[0] or causal_lens.shape[0] != q.shape[0]:
            raise ValueError("topk_idx / causal_lens must match q's token count")
        if int(causal_lens.max()) > kv.shape[0]:
            raise ValueError("causal_lens exceed kv length (contract violation)")

        scale = self.scale if self.scale is not None else q.shape[-1] ** -0.5
        out = q.new_zeros(q.shape)
        for i in range(q.shape[0]):
            idx = topk_idx[i]
            valid = (idx >= 0) & (idx < causal_lens[i])
            if not bool(valid.any()):
                continue
            sel = kv[idx[valid]]  # [K, D]
            logits = (q[i] @ sel.T).float() * scale  # [H, K]
            probs = torch.softmax(logits, dim=-1)
            out[i] = (probs.to(sel.dtype) @ sel).to(q.dtype)
        return out
