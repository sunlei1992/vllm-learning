"""真 Scheduler 联调 + 场景矩阵。

让 vLLM 的 v1 Scheduler 真的跑起来（无前向、fake KV），把每步
`SchedulerOutput` 的 num_scheduled_tokens 变成 query_lens/seq_lens，再喂给
`split_from_common_attn_metadata`，检查分片在所有真实形状下都自洽。

跑法（本机，CPU 版 vLLM）：
    python sched_integration.py            # 只跑 baseline
    python sched_integration.py --matrix   # 跑全部场景
"""

import os
import pathlib
import sys
from dataclasses import dataclass, field

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


@dataclass(frozen=True)
class Scenario:
    name: str
    num_reqs: int = 3
    prompt_tokens: int = 6000
    max_tokens: int = 4
    batch_budget: int = BATCH_BUDGET
    num_blocks: int = 20000
    enable_prefix_caching: bool = False
    same_prompt: bool = False
    long_prefill_token_threshold: int = 0
    num_speculative_tokens: int | None = None
    speculative_method: str | None = None


SCENARIOS = [
    Scenario("baseline"),
    Scenario("apc", enable_prefix_caching=True, same_prompt=True),
    Scenario("chunked", long_prefill_token_threshold=2048),
    Scenario(
        "preempt",
        num_blocks=16,
        num_reqs=8,
        prompt_tokens=64,
        max_tokens=256,
        batch_budget=512,
    ),
    Scenario(
        "spec",
        num_speculative_tokens=2,
        speculative_method="ngram",
        prompt_tokens=4000,
        max_tokens=8,
    ),
]


def _step_record(query_lens, seq_lens, split) -> dict:
    from golden_trace import step_record

    return step_record(query_lens, seq_lens, split)


def run(scenario: Scenario | None = None, *, collect_records: bool = False):
    scenario = scenario or Scenario("baseline")
    scheduler = create_scheduler(
        model=MODEL,
        max_num_seqs=8,
        max_num_batched_tokens=scenario.batch_budget,
        max_model_len=MAX_MODEL_LEN,
        num_blocks=scenario.num_blocks,
        block_size=16,
        enable_chunked_prefill=True,
        enable_prefix_caching=scenario.enable_prefix_caching,
        long_prefill_token_threshold=scenario.long_prefill_token_threshold,
        num_speculative_tokens=scenario.num_speculative_tokens,
        speculative_method=scenario.speculative_method,
        skip_tokenizer_init=True,
    )
    requests = create_requests(
        scenario.num_reqs,
        num_tokens=scenario.prompt_tokens,
        max_tokens=scenario.max_tokens,
        ignore_eos=True,
        same_prompt=scenario.same_prompt,
        req_ids=[f"{scenario.name}-{i}" for i in range(scenario.num_reqs)],
    )
    for req in requests:
        scheduler.add_request(req)

    stats = {
        "steps": 0,
        "prefill_steps": 0,
        "shardq_steps": 0,
        "fallback_steps": 0,
        "fallback_after_threshold": 0,
        "preemptions": 0,
        "max_split_tokens": 0,
        "max_seq_len": 0,
    }
    records: list[dict] = []

    for _ in range(400):
        if not scheduler.has_requests():
            break
        out = scheduler.schedule()
        rids = [rid for rid, n in out.num_scheduled_tokens.items() if n > 0]
        if not rids or out.total_num_scheduled_tokens == 0:
            break

        query_lens = [int(out.num_scheduled_tokens[rid]) for rid in rids]
        # 这个版本的 schedule() 已把本步 token 记进 num_computed_tokens，
        # 所以 seq_len 就是它本身；写成 base + n 会重复计数。
        seq_lens = [int(scheduler.requests[rid].num_computed_tokens) for rid in rids]
        assert all(s >= n for s, n in zip(seq_lens, query_lens)), (seq_lens, query_lens)

        prefill_tokens = sum(n for n in query_lens if n > 1)
        decode_tokens = sum(n for n in query_lens if n <= 1)

        cam = create_common_attn_metadata(
            BatchSpec(seq_lens=seq_lens, query_lens=query_lens),
            block_size=16,
            device=torch.device("cpu"),
        )
        split = sv.split_from_common_attn_metadata(
            cam,
            world=WORLD,
            min_tokens=MIN_TOKENS,
            index_topk=INDEX_TOPK,
            num_speculative_tokens=scenario.num_speculative_tokens or 0,
        )

        stats["steps"] += 1
        stats["prefill_steps"] += int(prefill_tokens > 0)
        stats["preemptions"] += len(out.preempted_req_ids or ())
        stats["max_seq_len"] = max(stats["max_seq_len"], max(seq_lens))

        if split is None:
            stats["fallback_steps"] += 1
            if prefill_tokens >= MIN_TOKENS and max(seq_lens) > INDEX_TOPK:
                stats["fallback_after_threshold"] += 1
                print(
                    f"  [warn] {scenario.name} step {stats['steps']}: fallback "
                    f"despite prefill={prefill_tokens} max_seq={max(seq_lens)} "
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
            stats["max_split_tokens"] = max(
                stats["max_split_tokens"], split.num_split_tokens
            )

        if collect_records:
            records.append(_step_record(query_lens, seq_lens, split))

        scheduler.update_from_output(
            out,
            ModelRunnerOutput(
                req_ids=rids,
                req_id_to_index={rid: i for i, rid in enumerate(rids)},
                sampled_token_ids=[[0] for _ in rids],
            ),
        )

    return stats, records


def main() -> None:
    matrix = "--matrix" in sys.argv
    scenarios = SCENARIOS if matrix else SCENARIOS[:1]
    results = {}
    for scenario in scenarios:
        try:
            stats, _ = run(scenario)
            results[scenario.name] = stats
        except Exception as exc:  # noqa: BLE001 - 场景矩阵允许"该版本不支持"
            results[scenario.name] = {"error": f"{type(exc).__name__}: {exc}"}

    print(f"\n{'scenario':>10} {'steps':>6} {'prefill':>8} {'shardq':>7} "
          f"{'fallback':>9} {'preempt':>8} {'max_split':>10} {'note':>24}")
    for name, s in results.items():
        if "error" in s:
            print(f"{name:>10} {'-':>6} {'-':>8} {'-':>7} {'-':>9} {'-':>8} {'-':>10} "
                  f"{s['error'][:24]:>24}")
            continue
        print(
            f"{name:>10} {s['steps']:>6} {s['prefill_steps']:>8} {s['shardq_steps']:>7} "
            f"{s['fallback_steps']:>9} {s['preemptions']:>8} {s['max_split_tokens']:>10} "
            f"{'':>24}"
        )

    baseline = results.get("baseline", {})
    assert baseline.get("steps", 0) > 0, "baseline produced no steps"
    assert baseline.get("shardq_steps", 0) > 0, "baseline never crossed the threshold"
    assert baseline.get("fallback_after_threshold", 0) == 0


if __name__ == "__main__":
    main()
