"""真 Scheduler 联调：用离线 Scheduler 的真实 batch 形状驱动 ShardQ 适配器。

不是手搓 metadata，而是让 vLLM 的 v1 Scheduler 真的跑起来（无前向、fake KV），
把每步 `SchedulerOutput` 的 num_scheduled_tokens 变成 query_lens/seq_lens，
再喂给 `split_from_common_attn_metadata`，检查分片在所有真实形状下都自洽。

跑法（本机，CPU 版 vLLM）：
    /Users/sunlei/code/dsh/vllm/.venv-va030/bin/python sched_integration.py
"""

import os
import pathlib
import sys

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

import torch  # noqa: E402
import vllm  # noqa: E402

_ROOT = pathlib.Path(vllm.__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from tests.v1.attention.utils import BatchSpec, create_common_attn_metadata  # noqa: E402
from tests.v1.core.utils import create_requests, create_scheduler  # noqa: E402
from vllm.v1.outputs import ModelRunnerOutput  # noqa: E402

import shardq_vllm as sv  # noqa: E402

MODEL = str(pathlib.Path(__file__).resolve().parents[4] / "models" / "Qwen_Qwen3-0.6B")
WORLD = 4
MIN_TOKENS = 1024
INDEX_TOPK = 2048
MAX_MODEL_LEN = 32768
BATCH_BUDGET = 4096
NUM_REQS = 3
PROMPT_TOKENS = 6000


def run() -> dict:
    scheduler = create_scheduler(
        model=MODEL,
        max_num_seqs=4,
        max_num_batched_tokens=BATCH_BUDGET,
        max_model_len=MAX_MODEL_LEN,
        num_blocks=20000,
        block_size=16,
        enable_chunked_prefill=True,
        skip_tokenizer_init=True,
    )
    requests = create_requests(
        NUM_REQS,
        num_tokens=PROMPT_TOKENS,
        max_tokens=4,
        ignore_eos=True,
        req_ids=[f"r{i}" for i in range(NUM_REQS)],
    )
    for req in requests:
        scheduler.add_request(req)

    stats = {
        "steps": 0,
        "prefill_steps": 0,
        "shardq_steps": 0,
        "fallback_steps": 0,
        "fallback_after_threshold": 0,
        "max_split_tokens": 0,
        "max_seq_len": 0,
    }
    for _ in range(200):
        if not scheduler.has_requests():
            break
        out = scheduler.schedule()
        rids = [rid for rid, n in out.num_scheduled_tokens.items() if n > 0]
        if not rids or out.total_num_scheduled_tokens == 0:
            break

        query_lens = [int(out.num_scheduled_tokens[rid]) for rid in rids]
        # 注意：这个版本的 schedule() 已经把本步 token 记进 num_computed_tokens，
        # 所以 seq_len 就是它本身，写成 base + n 会重复计数（实测 seq 会虚高到 9811）。
        seq_lens = [
            int(scheduler.requests[rid].num_computed_tokens) for rid in rids
        ]
        assert all(s >= n for s, n in zip(seq_lens, query_lens)), (seq_lens, query_lens)
        prefill_tokens = sum(n for n in query_lens if n > 1)
        decode_tokens = sum(n for n in query_lens if n <= 1)

        cam = create_common_attn_metadata(
            BatchSpec(seq_lens=seq_lens, query_lens=query_lens),
            block_size=16,
            device=torch.device("cpu"),
        )
        split = sv.split_from_common_attn_metadata(
            cam, world=WORLD, min_tokens=MIN_TOKENS, index_topk=INDEX_TOPK
        )

        stats["steps"] += 1
        stats["prefill_steps"] += int(prefill_tokens > 0)
        stats["max_seq_len"] = max(stats["max_seq_len"], max(seq_lens))

        if split is None:
            stats["fallback_steps"] += 1
            if prefill_tokens >= MIN_TOKENS and max(seq_lens) > INDEX_TOPK:
                # 只可能是空 rank 或计数对不上；两者都不该在正常 batch 出现
                stats["fallback_after_threshold"] += 1
                print(
                    f"  [warn] step {stats['steps']}: fallback despite "
                    f"prefill={prefill_tokens} max_seq={max(seq_lens)} "
                    f"lens={query_lens}"
                )
        else:
            stats["shardq_steps"] += 1
            assert split.num_split_tokens == prefill_tokens, (
                split.num_split_tokens,
                prefill_tokens,
            )
            assert split.num_decode_tokens == decode_tokens, (
                split.num_decode_tokens,
                decode_tokens,
            )
            assert split.num_tokens_per_rank.min() > 0
            assert split.token_ids.max() < prefill_tokens
            assert len(set(split.token_ids.tolist())) == prefill_tokens
            stats["max_split_tokens"] = max(stats["max_split_tokens"], split.num_split_tokens)

        scheduler.update_from_output(
            out,
            ModelRunnerOutput(
                req_ids=rids,
                req_id_to_index={rid: i for i, rid in enumerate(rids)},
                sampled_token_ids=[[0] for _ in rids],
            ),
        )

    return stats


if __name__ == "__main__":
    s = run()
    print("scheduler integration stats:")
    for k, v in s.items():
        print(f"  {k:>22}: {v}")
    assert s["steps"] > 0, "scheduler produced no steps"
    assert s["shardq_steps"] > 0, "no step crossed the ShardQ threshold"
    assert s["fallback_after_threshold"] == 0, "unexpected fallback above threshold"
    print("OK")
