#!/bin/bash
# Load vllm-ascend (main) into the dry-run container, with no NPU, and run a smoke test.
#
# This is a LOCAL EXPERIMENT harness. It stubs torch_npu / torch.npu /
# triton-ascend ops, disables the NPU platform plugin, and fabricates the
# package entry points so vLLM's plugin discovery picks them up without a
# real `pip install vllm-ascend`.
set -euo pipefail

ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/tmp/simlogs"

docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp":/wheels:ro \
  -v "$HERE/torch_npu_stub":/stub:ro \
  -v "$ROOT/vllm-ascend-src":/ascend:ro \
  -v "$ROOT/models":/models:ro \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  sim-int:dry-run bash -c '
    set -e

    cp -a /ascend /va
    echo "__device_type__ = '\''A2'\''" > /va/vllm_ascend/_build_info.py

    # Make the platform plugin decline when there is no NPU.
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

    # General plugins, each guarded so one failure does not abort startup.
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

    export PYTHONPATH=/va:/stub
    export VA_DRY_RUN=1
    export VLLM_TARGET_DEVICE=cpu
    export TRITON_CACHE_DIR=/logs/triton-cache

    echo "=== patches applied? ==="
    python - <<PY
import vllm_ascend
vllm_ascend.register_connector()
from vllm.v1.engine.core import EngineCoreProc
import vllm.v1.core.kv_cache_utils as k
print("EngineCoreProc.run_engine_core:", EngineCoreProc.run_engine_core.__module__)
print("kv_cache_utils.get_kv_cache_groups:", k.get_kv_cache_groups.__module__)
PY

    echo "=== smoke ==="
    cd /work && python /out/sim_pd2.py > /logs/va_pd.log 2>&1 || true
    grep -E "\[va-plugin\]" /logs/va_pd.log | sort | uniq -c
    grep -E "^\[sim\]" /logs/va_pd.log
  '
