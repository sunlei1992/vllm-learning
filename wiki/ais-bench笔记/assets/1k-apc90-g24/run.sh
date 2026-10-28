#!/usr/bin/env bash
# 复现 1K / 90% APC / 24 组 × 2 条 的测试数据（纯离线，不需要推理服务）。
#
# 用法：
#   AIS_DATA=/abs/data AIS_REPO=/abs/ais-bench ./run.sh inspect
#   AIS_DATA=/abs/data AIS_REPO=/abs/ais-bench ./run.sh prepare
#   AIS_DATA=/abs/data AIS_REPO=/abs/ais-bench ./run.sh validate <manifest>
#
# AIS_DATA 目录里要有：
#   GSM8K.jsonl         # 每行 {"question": ...}，gsm8k train.jsonl 原样即可
#   tokenizer/          # AutoTokenizer.from_pretrained 的本地目录（与服务端一致）
#   outputs/            # 产物落地处
# AIS_REPO 是 AISBench/benchmark 的 clone（只用 plugins/prefix_cache，不装本体）。
set -euo pipefail

: "${AIS_DATA:?set AIS_DATA to the directory holding GSM8K.jsonl/tokenizer/}"
: "${AIS_REPO:?set AIS_REPO to the AISBench/benchmark clone}"
IMAGE=${IMAGE:-python:3.12-slim}
ACTION=${1:?usage: run.sh inspect|prepare|validate [manifest]}

mounts=(-v "$AIS_DATA":/data -v "$AIS_REPO":/work -w /work)
common=(-e PYTHONPATH=/work/plugins/prefix_cache -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1)

case "$ACTION" in
  inspect)
    # inspect 只接 --scenario（prepare 才要 --mode）
    docker run --rm "${mounts[@]}" "${common[@]}" --entrypoint python "$IMAGE" \
      -m ais_bench_prefix_cache.cli inspect --scenario /data/scenario.json
    ;;
  prepare)
    docker run --rm "${mounts[@]}" "${common[@]}" --entrypoint python "$IMAGE" \
      -m ais_bench_prefix_cache.cli prepare --mode text --scenario /data/scenario.json
    ;;
  validate)
    docker run --rm "${mounts[@]}" "${common[@]}" --entrypoint python "$IMAGE" \
      -m ais_bench_prefix_cache.cli validate --manifest "/data/${2:?manifest path under /data}"
    ;;
  *) echo "unknown action: $ACTION" >&2; exit 2 ;;
esac
