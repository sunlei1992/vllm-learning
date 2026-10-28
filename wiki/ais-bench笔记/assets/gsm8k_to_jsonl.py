#!/usr/bin/env python3
"""把 GSM8K 转成 AISBench PrefixCache 插件要求的 JSONL。

插件只要求：每行一个 JSON 对象，含 `corpus.field` 指定的文本字段（默认 `question`）。
这里保留 answer 字段，方便人工核对；插件本身不读它。

用法：
    # 从 HuggingFace 拉（需要联网 + datasets）
    python gsm8k_to_jsonl.py -o GSM8K.jsonl
    python gsm8k_to_jsonl.py -o GSM8K.jsonl --split test

    # 用 AISBench 已下载到本地的数据集目录（parquet / jsonl 都行）
    python gsm8k_to_jsonl.py -o GSM8K.jsonl --dir ais_bench/datasets/gsm8k

    # 用本地已有的 parquet
    python gsm8k_to_jsonl.py -o GSM8K.jsonl --parquet ./gsm8k/train-00000-of-00001.parquet

输出示例：
    {"question": "Janet's ducks lay 16 eggs per day...", "answer": "..."}

依赖：pip install datasets
"""
import argparse
import glob
import json
import os
import sys


def load_rows(args):
    """统一返回一个可迭代的 {question, answer} 行集合。"""
    from datasets import load_dataset

    if args.parquet:
        return load_dataset("parquet", data_files=args.parquet, split="train")

    if args.dir:
        if not os.path.isdir(args.dir):
            sys.exit(f"[error] 目录不存在: {args.dir}")
        parquets = sorted(glob.glob(os.path.join(args.dir, "**", "*.parquet"), recursive=True))
        if parquets:
            return load_dataset("parquet", data_files=parquets, split="train")
        jsonls = sorted(glob.glob(os.path.join(args.dir, "**", "*.jsonl"), recursive=True))
        if jsonls:
            return load_dataset("json", data_files=jsonls, split="train")
        arrows = sorted(glob.glob(os.path.join(args.dir, "**", "*.arrow"), recursive=True))
        if arrows:
            return load_dataset("arrow", data_files=arrows, split="train")
        sys.exit(f"[error] {args.dir} 下没找到 parquet/jsonl/arrow")

    return load_dataset(args.dataset, args.config, split=args.split)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-o", "--output", default="GSM8K.jsonl", help="输出路径（默认 GSM8K.jsonl）")
    p.add_argument("--dataset", default="openai/gsm8k", help="HF 数据集名")
    p.add_argument("--config", default="main", help="HF 配置名（gsm8k 是 main / socratic）")
    p.add_argument("--split", default="train", help="train / test")
    p.add_argument("--dir", help="本地数据集目录（优先 parquet）")
    p.add_argument("--parquet", help="直接指定 parquet 文件")
    p.add_argument("--dedup", action="store_true", help="按 question 去重")
    p.add_argument("--limit", type=int, default=0, help="最多写多少条（0 = 全部）")
    args = p.parse_args()

    ds = load_rows(args)
    seen = set()
    written = 0

    with open(args.output, "w", encoding="utf-8") as f:
        for row in ds:
            q = (row.get("question") or "").strip()
            if not q:
                continue
            if args.dedup:
                if q in seen:
                    continue
                seen.add(q)
            f.write(json.dumps({"question": q, "answer": row.get("answer", "")},
                               ensure_ascii=False) + "\n")
            written += 1
            if args.limit and written >= args.limit:
                break

    print(f"[ok] 写入 {written} 条 -> {os.path.abspath(args.output)}", file=sys.stderr)


if __name__ == "__main__":
    main()
