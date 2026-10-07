#!/bin/bash
# 从 hf-mirror 下载模型的"非权重"文件（config + tokenizer），用于 dummy 模式
# 用法: ./dl_model.sh Qwen/Qwen2.5-0.5B-Instruct
# 输出: models/Qwen__Qwen2.5-0.5B-Instruct/ （可直接作为 vllm 的 --model 本地路径）
#
# 背景: huggingface.co 直连不通；huggingface_hub 1.28 + hf-mirror 的 HEAD 校验失败，
#       所以绕开 hub，用 curl 直接拉小文件。权重文件（.safetensors 等）不下载。
set -euo pipefail

MODEL="$1"
OUT="models/$(echo "$MODEL" | tr '/' '__')"
mkdir -p "$OUT"

echo "==> 下载 $MODEL 的配置文件到 $OUT"
FILES=$(curl -s --max-time 20 "https://hf-mirror.com/api/models/$MODEL" | python3 -c "
import sys, json
d = json.load(sys.stdin)
skip = ('.safetensors', '.bin', '.gguf', '.pt', '.pth', '.onnx', '.sft', '.npy', '.npz', '.msgpack')
for s in d.get('siblings', []):
    n = s['rfilename']
    if not n.endswith(skip):
        print(n)
")

for f in $FILES; do
    mkdir -p "$OUT/$(dirname "$f")"
    curl -sL --max-time 60 -o "$OUT/$f" "https://hf-mirror.com/$MODEL/resolve/main/$f" \
        && echo "  ✓ $f" || echo "  ✗ $f"
done
echo "==> 完成: $OUT"
