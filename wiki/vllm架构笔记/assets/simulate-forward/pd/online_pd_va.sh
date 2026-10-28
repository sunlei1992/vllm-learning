#!/bin/bash
set -uo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
cd "$ROOT"
docker rm -f pd_va >/dev/null 2>&1
docker run -d --name pd_va --platform linux/arm64 --shm-size=16g \
  -p 18001:8000 -p 18002:8001 \
  -v $PWD/vllm-ascend-src:/ascend:ro \
  -v "$PWD/wiki/vllm架构笔记/assets/simulate-forward/va/torch_npu_stub":/stub:ro \
  -v $PWD/models:/models:ro -v $PWD/tmp/simlogs:/logs sim-int:dry-run bash -c '
    set -e
    cp -a /ascend /va
    echo "__device_type__ = '\''A2'\''" > /va/vllm_ascend/_build_info.py
    python - <<PY
p = "/va/vllm_ascend/__init__.py"
s = open(p).read()
s = s.replace("import importlib.util\nimport sys", "import importlib.util\nimport os\nimport sys", 1)
s = s.replace(
    "def register():\n    \"\"\"Register the NPU platform.\"\"\"\n\n    return \"vllm_ascend.platform.NPUPlatform\"",
    "def register():\n    \"\"\"Register the NPU platform.\"\"\"\n    if os.getenv(\"VA_DRY_RUN\") == \"1\":\n        return None\n\n    return \"vllm_ascend.platform.NPUPlatform\"",
)
open(p, "w").write(s)
PY
    cat > /va/va_plugins.py <<PY
def _safe(name, attr):
    import vllm_ascend
    getattr(vllm_ascend, attr)()

def register_connector(): _safe("connector", "register_connector")
def register_model_loader(): _safe("model_loader", "register_model_loader")
def register_service_profiling(): _safe("service_profiling", "register_service_profiling")
def register_model(): _safe("model", "register_model")
PY
    mkdir -p /va/vllm_ascend-0.0.0.dist-info
    printf "Metadata-Version: 2.1\nName: vllm-ascend\nVersion: 0.0.0\n" > /va/vllm_ascend-0.0.0.dist-info/METADATA
    printf "[vllm.platform_plugins]\nascend = vllm_ascend:register\n\n[vllm.general_plugins]\nascend_kv_connector = va_plugins:register_connector\nascend_model_loader = va_plugins:register_model_loader\nascend_service_profiling = va_plugins:register_service_profiling\nascend_model = va_plugins:register_model\n" > /va/vllm_ascend-0.0.0.dist-info/entry_points.txt
    export PYTHONPATH=/va:/stub VA_DRY_RUN=1
    cd /work
    export VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/logs/triton-cache
    export SIMCFG="{\"simulate_forward\":true,\"kv_transfer_timing\":{\"load_gbps\":10}}"
    common="--model /models/Qwen_Qwen3-0.6B --served-model-name qwen --simulate-forward \
      --kv-cache-memory-bytes 2147483648 --enforce-eager --max-model-len 2048 \
      --host 0.0.0.0 --simulation-config $SIMCFG"
    VLLM_NIXL_SIDE_CHANNEL_PORT=5600 python -m vllm.entrypoints.openai.api_server $common --port 8000 \
      --kv-transfer-config "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"kv_producer\"}" > /logs/va_pd_pre.log 2>&1 &
    VLLM_NIXL_SIDE_CHANNEL_PORT=5601 python -m vllm.entrypoints.openai.api_server $common --port 8001 \
      --kv-transfer-config "{\"kv_connector\":\"NixlConnector\",\"kv_role\":\"kv_consumer\"}" > /logs/va_pd_dec.log 2>&1 &
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
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=180))
r = post("http://127.0.0.1:18001/v1/completions",
         {"model": "qwen", "prompt": "Hello", "max_tokens": 1, "temperature": 0, "return_token_ids": True,
          "kv_transfer_params": {"do_remote_decode": True, "do_remote_prefill": False}})
kv = r["kv_transfer_params"]
print("prefill tokens:", [c["token_ids"] for c in r["choices"]], "blocks:", kv.get("remote_block_ids"))
d = post("http://127.0.0.1:18002/v1/completions",
         {"model": "qwen", "prompt": "Hello", "max_tokens": 8, "temperature": 0,
          "return_token_ids": True, "kv_transfer_params": kv})
print("decode tokens:", [c["token_ids"] for c in d["choices"]], "finish:", d["choices"][0]["finish_reason"])
PY
echo "=== VA 痕迹 ==="
docker exec pd_va sh -c "grep -c vllm-ascend /logs/va_pd_pre.log; grep -c vllm-ascend /logs/va_pd_dec.log" 2>/dev/null
docker rm -f pd_va >/dev/null 2>&1
