#!/bin/bash
set -uo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
cd "$ROOT"
docker rm -f pd_both >/dev/null 2>&1
docker run -d --name pd_both --platform linux/arm64 --shm-size=16g \
  -p 18001:8000 -p 18002:8001 \
  -v $PWD/models:/models:ro -v $PWD/tmp/simlogs:/logs sim-int:dry-run bash -c '
    cd /work
    export VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/logs/triton-cache
    export SIMCFG="{\"simulate_forward\":true,\"kv_transfer_timing\":{\"load_gbps\":10}}"
    common="--model /models/Qwen_Qwen3-0.6B --served-model-name qwen --simulate-forward \
      --kv-cache-memory-bytes 2147483648 --enforce-eager --max-model-len 2048 \
      --host 0.0.0.0 --simulation-config $SIMCFG"
    VLLM_NIXL_SIDE_CHANNEL_PORT=5600 python -m vllm.entrypoints.openai.api_server \
      $common --port 8000 \
      --kv-transfer-config "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"kv_producer\"}" \
      > /logs/pd_online_prefill.log 2>&1 &
    VLLM_NIXL_SIDE_CHANNEL_PORT=5601 python -m vllm.entrypoints.openai.api_server \
      $common --port 8001 \
      --kv-transfer-config "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"kv_consumer\"}" \
      > /logs/pd_online_decode.log 2>&1 &
    wait
  ' >/dev/null
for i in $(seq 1 60); do
  a=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18001/health)
  b=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18002/health)
  [ "$a" = "200" ] && [ "$b" = "200" ] && { echo "both healthy after ${i}x2s"; break; }
  sleep 2
done
echo "prefill=$a decode=$b"
python3 - <<'PY'
import json, urllib.request

def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=180))

r = post("http://127.0.0.1:18001/v1/completions",
         {"model": "qwen", "prompt": "Hello", "max_tokens": 1, "temperature": 0,
          "return_token_ids": True,
          "kv_transfer_params": {"do_remote_decode": True, "do_remote_prefill": False}})
kv = r["kv_transfer_params"]
print("prefill tokens:", [c["token_ids"] for c in r["choices"]])
print("kv blocks:", kv.get("remote_block_ids"), "engine:", kv.get("remote_engine_id")[:8])
d = post("http://127.0.0.1:18002/v1/completions",
         {"model": "qwen", "prompt": "Hello", "max_tokens": 8, "temperature": 0,
          "return_token_ids": True, "kv_transfer_params": kv})
print("decode tokens:", [c["token_ids"] for c in d["choices"]],
      "finish:", d["choices"][0]["finish_reason"])
PY
echo "=== 传输日志 ==="
docker exec pd_both grep -hiE "nixl|transfer|kv.?load" /logs/pd_online_*.log 2>/dev/null | tail -6
docker rm -f pd_both >/dev/null 2>&1
