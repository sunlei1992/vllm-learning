#!/bin/bash
set -uo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
docker rm -f pd_va >/dev/null 2>&1
docker run --rm --platform linux/arm64 --shm-size=16g \
  -e TIERS -e BWS -e SESSIONS -e TURNS -e BASE -e NEW -e HBM_GB -e OUT \
  -v $ROOT/vllm-ascend-src:/ascend:ro \
  -v "$ROOT/wiki/vllm架构笔记/assets/simulate-forward/va/torch_npu_stub":/stub:ro \
  -v $ROOT/models:/models:ro -v $ROOT/tmp:/out:ro -v $ROOT/tmp/simlogs:/logs \
  sim-int:dry-run bash -c '
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
    export PYTHONPATH=/va:/stub VA_DRY_RUN=1 VLLM_TARGET_DEVICE=cpu TRITON_CACHE_DIR=/logs/triton-cache
    cd /work && python /out/sim_multiturn.py
  ' 2>&1
