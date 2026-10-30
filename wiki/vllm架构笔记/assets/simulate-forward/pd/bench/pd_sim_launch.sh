#!/bin/bash
# In-container launcher: X prefill + Y decode sim engines + the P/D proxy.
# Driven by tmp/pd_bench.sh (env: PRE, DEC, LOAD_GBPS).
set -uo pipefail

cd /work || exit 1
export VLLM_TARGET_DEVICE=cpu
export TRITON_CACHE_DIR=/logs/triton-cache

PRE=${PRE:?PRE is required}
DEC=${DEC:?DEC is required}
LOAD_GBPS=${LOAD_GBPS:-10}
# SIM_TIMING injects a timing model, e.g.
#   '"timing":"linear","timing_args":{"fixed_us":1000,"prefill_us_per_token":10,"decode_us_per_req":200}'
# Empty keeps the simulator default (timing=zero: compute is free).
SIMCFG="{\"simulate_forward\":true"
if [ -n "${SIM_TIMING:-}" ]; then
  SIMCFG="$SIMCFG,$SIM_TIMING"
fi
SIMCFG="$SIMCFG,\"kv_transfer_timing\":{\"load_gbps\":$LOAD_GBPS}}"

MAX_MODEL_LEN=${MAX_MODEL_LEN:-4096}
KV_MB=${KV_MB:-2048}
common=(--model /models/Qwen_Qwen3-0.6B --served-model-name qwen --simulate-forward
        --kv-cache-memory-bytes $((KV_MB * 1024 * 1024)) --enforce-eager --max-model-len "$MAX_MODEL_LEN"
        --host 0.0.0.0 --simulation-config "$SIMCFG")

pre=()
dec=()
for i in $(seq 0 $((PRE - 1))); do
  port=$((8000 + i))
  VLLM_NIXL_SIDE_CHANNEL_PORT=$((5600 + i)) \
    python -m vllm.entrypoints.openai.api_server "${common[@]}" --port "$port" \
    --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_producer"}' \
    > "/logs/pd_prefill_$i.log" 2>&1 &
  pre+=("127.0.0.1:$port")
done
for j in $(seq 0 $((DEC - 1))); do
  port=$((8100 + j))
  VLLM_NIXL_SIDE_CHANNEL_PORT=$((5700 + j)) \
    python -m vllm.entrypoints.openai.api_server "${common[@]}" --port "$port" \
    --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_consumer"}' \
    > "/logs/pd_decode_$j.log" 2>&1 &
  dec+=("127.0.0.1:$port")
done

echo "[launch] prefill=${pre[*]} decode=${dec[*]}"

if ! python - <<PY
import sys, time, urllib.request

targets = [f"http://127.0.0.1:{8000 + i}/health" for i in range($PRE)]
targets += [f"http://127.0.0.1:{8100 + j}/health" for j in range($DEC)]
deadline = time.time() + 300
while time.time() < deadline:
    ok = 0
    for t in targets:
        try:
            with urllib.request.urlopen(t, timeout=2) as r:
                ok += int(r.status == 200)
        except Exception:
            pass
    if ok == len(targets):
        print(f"[launch] {ok}/{len(targets)} engines healthy", flush=True)
        sys.exit(0)
    time.sleep(2)
print("[launch] TIMEOUT waiting for engines", flush=True)
for i in range($PRE):
    print(open(f"/logs/pd_prefill_{i}.log").read()[-1500:], flush=True)
for j in range($DEC):
    print(open(f"/logs/pd_decode_{j}.log").read()[-1500:], flush=True)
sys.exit(1)
PY
then
  echo "[launch] engine startup failed"
  exit 1
fi

python /tools/pd_proxy.py --prefill "${pre[@]}" --decode "${dec[@]}" \
  --host 0.0.0.0 --port 18000 --verbose &
wait
