#!/usr/bin/env python3
"""Generate a mixed short/long case for the scheduling vertical slice.

Order matters: long requests first, so the stock FCFS queue front is long.
`vllm bench serve --disable-shuffle` preserves this order.
"""

import json
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parent
LAB = next(p for p in [ROOT, *ROOT.parents] if (p / "AGENTS.md").exists())
TOK = AutoTokenizer.from_pretrained(
    str(LAB / "models" / "Qwen_Qwen3-0.6B"), trust_remote_code=True
)

UNIT = "hello world. "
SHORT_REPEAT = 20   # ~60 tokens
LONG_REPEAT = 240   # ~720 tokens
N_PER_CLASS = 8
OUTPUT_TOKENS = 16


def ntok(text: str) -> int:
    return len(TOK(text, add_special_tokens=False).input_ids)


rows = []
for i in range(N_PER_CLASS):
    prompt = f"LONG-{i}: " + UNIT * LONG_REPEAT
    rows.append({"prompt": prompt, "output_tokens": OUTPUT_TOKENS})

for i in range(N_PER_CLASS):
    prompt = f"SHORT-{i}: " + UNIT * SHORT_REPEAT
    rows.append({"prompt": prompt, "output_tokens": OUTPUT_TOKENS})

out = ROOT / "case_mixed.jsonl"
with out.open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

lengths = [ntok(r["prompt"]) for r in rows]
print(f"wrote {out} rows={len(rows)}")
print(f"long  n={N_PER_CLASS} tokens={lengths[:N_PER_CLASS]}")
print(f"short n={N_PER_CLASS} tokens={lengths[N_PER_CLASS:]}")
