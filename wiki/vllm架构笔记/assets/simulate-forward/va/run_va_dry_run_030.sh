#!/bin/bash
# Load vllm-ascend releases/v0.30.0 into the vLLM 0.30 dry-run image.
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp/va030":/ascend:ro \
  -v "$ROOT/tmp/torch_npu_stub":/stub:ro \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  sim030:dry-run bash -c '
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
import traceback


def _safe(name, attr):
    try:
        import vllm_ascend
        getattr(vllm_ascend, attr)()
        print(f"[va-plugin] {name}: OK", flush=True)
    except Exception:
        print(f"[va-plugin] {name}: FAILED", flush=True)
        traceback.print_exc()


def register_connector():
    _safe("connector", "register_connector")


def register_model_loader():
    _safe("model_loader", "register_model_loader")


def register_service_profiling():
    _safe("service_profiling", "register_service_profiling")


def register_model():
    _safe("model", "register_model")
PY
    mkdir -p /va/vllm_ascend-0.0.0.dist-info
    printf "Metadata-Version: 2.1\nName: vllm-ascend\nVersion: 0.0.0\n" \
      > /va/vllm_ascend-0.0.0.dist-info/METADATA
    printf "[vllm.platform_plugins]\nascend = vllm_ascend:register\n\n[vllm.general_plugins]\nascend_kv_connector = va_plugins:register_connector\nascend_model_loader = va_plugins:register_model_loader\nascend_service_profiling = va_plugins:register_service_profiling\nascend_model = va_plugins:register_model\n" \
      > /va/vllm_ascend-0.0.0.dist-info/entry_points.txt
    export PYTHONPATH=/va:/stub VA_DRY_RUN=1 VLLM_TARGET_DEVICE=cpu VLLM_USE_V2_MODEL_RUNNER=1
    export TRITON_CACHE_DIR=/logs/triton-cache-030
    echo "=== patches applied? ==="
    /opt/v030/bin/python - <<PY
import vllm_ascend
vllm_ascend.register_connector()
from vllm.v1.engine.core import EngineCoreProc
import vllm.v1.core.kv_cache_utils as k
print("EngineCoreProc.run_engine_core:", EngineCoreProc.run_engine_core.__module__)
print("kv_cache_utils.get_kv_cache_groups:", k.get_kv_cache_groups.__module__)
PY
    echo "=== smoke ==="
    cd /work030 && /opt/v030/bin/python /out/sim_smoke.py > /logs/va030.log 2>&1 || true
    grep -E "\[va-plugin\]" /logs/va030.log | sort | uniq -c
    grep -E "^\[sim\]" /logs/va030.log
    tail -4 /logs/va030.log
  '
