#!/bin/bash
# In-container launcher for the RouteServer integration:
# two dry-run engines (P on 8001 / D on 8002), no local proxy -- RouteServer
# in the neighbouring container (shared netns) acts as the P/D proxy.
set -uo pipefail

cd /work || exit 1
export VLLM_TARGET_DEVICE=cpu
export TRITON_CACHE_DIR=/logs/triton-cache

PRE_PORT=${PRE_PORT:-8001}
DEC_PORT=${DEC_PORT:-8002}
LOAD_GBPS=${LOAD_GBPS:-10}
KV_MB=${KV_MB:-2048}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-4096}

SIMCFG="{\"simulate_forward\":true"
if [ -n "${SIM_TIMING:-}" ]; then
  SIMCFG="$SIMCFG,$SIM_TIMING"
fi
SIMCFG="$SIMCFG,\"kv_transfer_timing\":{\"load_gbps\":$LOAD_GBPS}}"

common=(--model /models/Qwen_Qwen3-0.6B --served-model-name qwen --simulate-forward
        --kv-cache-memory-bytes $((KV_MB * 1024 * 1024)) --enforce-eager
        --max-model-len "$MAX_MODEL_LEN" --host 0.0.0.0
        --simulation-config "$SIMCFG")

echo "[sim] P:$PRE_PORT D:$DEC_PORT simcfg=$SIMCFG"

VLLM_NIXL_SIDE_CHANNEL_PORT=5600 \
  python -m vllm.entrypoints.openai.api_server "${common[@]}" --port "$PRE_PORT" \
  --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_producer"}' \
  > /logs/rs_prefill.log 2>&1 &

VLLM_NIXL_SIDE_CHANNEL_PORT=5601 \
  python -m vllm.entrypoints.openai.api_server "${common[@]}" --port "$DEC_PORT" \
  --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_consumer"}' \
  > /logs/rs_decode.log 2>&1 &

wait
