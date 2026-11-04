"""Create a 4-layer Qwen2.5-shaped model for the shared-buffer e2e."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SRC = ROOT / "models/Qwen_Qwen2.5-0.5B-Instruct"
DST = ROOT / "models/Qwen2.5-tiny4"

DST.mkdir(parents=True, exist_ok=True)
for name in ("tokenizer.json", "tokenizer_config.json", "generation_config.json", "merges.txt", "vocab.json"):
    source = SRC / name
    if source.exists():
        shutil.copy2(source, DST / name)

config = json.loads((SRC / "config.json").read_text())
config.update(
    {
        "num_hidden_layers": 4,
        "hidden_size": 256,
        "intermediate_size": 512,
        "num_attention_heads": 4,
        "num_key_value_heads": 2,
        "head_dim": 64,
        "max_position_embeddings": 512,
        "tie_word_embeddings": True,
    }
)
(DST / "config.json").write_text(json.dumps(config, indent=2))
print("created", DST)
