"""Golden trace：记录每步调度形状与分片摘要，供真机对拍。

本机生成 golden（CPU 参考实现），真机录一份，用 compare() 找差异。
也可以直接当回归测试用：同一 workload 两次录制必须逐位一致。

跑法：
    python golden_trace.py record out.json
    python golden_trace.py record out_apc.json --scenario apc
    python golden_trace.py compare out.json out_2.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

import numpy as np


def _hash(arr) -> str:
    data = np.ascontiguousarray(np.asarray(arr, dtype=np.int64))
    return hashlib.sha256(data.tobytes()).hexdigest()[:16]


def step_record(query_lens, seq_lens, split) -> dict:
    """一步的紧凑摘要：形状 + 分片指纹（不存原始数组，便于跨机比较）。"""
    record = {
        "query_lens": [int(x) for x in query_lens],
        "seq_lens": [int(x) for x in seq_lens],
        "split": None,
    }
    if split is not None:
        record["split"] = {
            "num_decode_tokens": int(split.num_decode_tokens),
            "num_tokens_per_rank": [int(x) for x in split.num_tokens_per_rank],
            "token_ids_sha256": _hash(split.token_ids),
        }
    return record


def compare(left: list[dict], right: list[dict]) -> list[str]:
    """返回差异描述；空列表表示一致。"""
    diffs: list[str] = []
    if len(left) != len(right):
        diffs.append(f"step count: {len(left)} != {len(right)}")
    for i, (a, b) in enumerate(zip(left, right)):
        if a == b:
            continue
        if a.get("query_lens") != b.get("query_lens"):
            diffs.append(f"step {i}: query_lens {a['query_lens']} != {b['query_lens']}")
        if a.get("seq_lens") != b.get("seq_lens"):
            diffs.append(f"step {i}: seq_lens {a['seq_lens']} != {b['seq_lens']}")
        sa, sb = a.get("split"), b.get("split")
        if (sa is None) != (sb is None):
            diffs.append(f"step {i}: split {sa} != {sb}")
        elif sa is not None:
            for key in sa:
                if sa[key] != sb[key]:
                    diffs.append(f"step {i}: split.{key} {sa[key]} != {sb[key]}")
    return diffs


def record(scenario_name: str = "baseline") -> list[dict]:
    """跑一遍离线 Scheduler，录制每步摘要。"""
    from sched_integration import SCENARIOS, run

    scenario = next((s for s in SCENARIOS if s.name == scenario_name), None)
    if scenario is None:
        raise SystemExit(f"unknown scenario {scenario_name!r}")
    _, records = run(scenario, collect_records=True)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("out")
    rec.add_argument("--scenario", default="baseline")

    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("left")
    cmp_.add_argument("right")

    args = parser.parse_args(argv)
    if args.cmd == "record":
        records = record(args.scenario)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=1)
        print(f"recorded {len(records)} steps -> {args.out}")
        return 0

    with open(args.left, encoding="utf-8") as fh:
        left = json.load(fh)
    with open(args.right, encoding="utf-8") as fh:
        right = json.load(fh)
    diffs = compare(left, right)
    if diffs:
        print(f"{len(diffs)} differences:")
        for line in diffs[:20]:
            print("  " + line)
        return 1
    print("identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
