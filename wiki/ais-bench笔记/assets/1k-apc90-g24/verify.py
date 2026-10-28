"""独立复核：不走插件的 theory 模拟，直接用 tokenizer 重编码 prompt 验证。"""
import json
import sys
from collections import defaultdict, Counter
from transformers import AutoTokenizer

out_dir = sys.argv[1]
tok = AutoTokenizer.from_pretrained("/data/tokenizer")

full = [json.loads(line) for line in open(f"{out_dir}.full.jsonl")]
reqs = [json.loads(line) for line in open(f"{out_dir}.requests.jsonl")]
print(f"full rows={len(full)} requests rows={len(reqs)}")
print("fields(full):", sorted(full[0].keys()))

groups = defaultdict(list)
for row in full:
    groups[row["group_id"]].append(row)
print(f"groups={len(groups)} per-group={Counter(len(v) for v in groups.values())}")

# 1) token 数是否等于 1024
lens = [len(tok.encode(r["question"], add_special_tokens=False)) for r in full]
print(f"token lens: min={min(lens)} max={max(lens)} set={sorted(set(lens))}")

# 2) 每组内部的公共前缀长度（两条 prompt 的 LCP）
lcp_ok = 0
for g, rows in sorted(groups.items()):
    ids = [tok.encode(r["question"], add_special_tokens=False) for r in rows]
    lcp = 0
    for a, b in zip(*ids):
        if a != b:
            break
        lcp += 1
    declared = min(r["shared_prefix_tokens"] for r in rows)
    # LCP 至少覆盖声明的共享前缀；LCP 超出的部分只可能是块内巧合，seed 保证不会继续共享
    if lcp >= declared:
        lcp_ok += 1
    else:
        print(f"  [!] {g}: lcp={lcp} declared={declared}")
print(f"groups with LCP >= declared prefix: {lcp_ok}/{len(groups)}")

# 3) 24 个前缀的首 block 互不相同？
first_blocks = {g: tuple(tok.encode(v[0]["question"], add_special_tokens=False)[:16]) for g, v in groups.items()}
print(f"distinct first blocks: {len(set(first_blocks.values()))}/{len(first_blocks)}")

# 4) 独立算理论命中率：warmup 下每条请求命中自己组内的 max 前缀
total_in = sum(r["actual_input_tokens"] for r in full)
total_hit = sum(r["shared_prefix_tokens"] for r in full)
print(f"independent hit rate = {total_hit}/{total_in} = {total_hit/total_in:.6f}")
print("manifest theoretical =", json.load(open(f"{out_dir}.analysis.json"))["theoretical_hit_rate"])

# 5) 命中量是否 block 对齐
print("prefix multiples of 16:", sorted({r["shared_prefix_tokens"] % 16 for r in full}))
print("prefix distribution:", Counter(r["shared_prefix_tokens"] for r in full))

# 6) 展示一条 prompt 的头尾
sample = full[0]
ids = tok.encode(sample["question"], add_special_tokens=False)
print("\n--- head 60 tokens decd ---")
print(tok.decode(ids[:60]))
print("--- tail 60 tokens ---")
print(tok.decode(ids[-60:]))
print("--- seed/prefix layout:", {k: sample[k] for k in
      ("group_id", "occurrence_index_within_group", "shared_prefix_tokens",
       "seed_tokens", "natural_suffix_tokens", "theoretical_hit_tokens", "theoretical_hit_rate")})
