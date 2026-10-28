#!/bin/bash
# Load vllm-ascend releases/v0.30.0 into the vLLM 0.30 dry-run image.
set -euo pipefail
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp/va030":/ascend:ro \
  -v "$ROOT/tmp/torch_npu_stub":/stub:ro \
  -v "$ROOT/models":/models:ro \
  -e SIM_MODEL=/models/zai-org_GLM-5.3 \
  -e VA_SKIP_MODEL=1 \
  -e VA_INIT_CONFIG=1 \
  -v "$ROOT/tmp":/out:ro \
  -v "$ROOT/tmp/simlogs":/logs \
  sim030:glm53 bash -c '
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
    import os

    if os.getenv("VA_SKIP_MODEL") == "1":
        print("[va-plugin] model: SKIPPED", flush=True)
        return
    _safe("model", "register_model")


def _install_ascend_config_hook():
    import os

    if os.getenv("VA_INIT_CONFIG") != "1":
        return
    try:
        from vllm.config import VllmConfig

        _orig = getattr(VllmConfig, "__post_init__", None)

        def _post(self, *args, **kwargs):
            if _orig is not None:
                _orig(self, *args, **kwargs)
            try:
                from vllm_ascend.ascend_config import init_ascend_config

                init_ascend_config(self)
            except Exception as exc:
                print(f"[va-plugin] init_ascend_config failed: {exc}", flush=True)

        VllmConfig.__post_init__ = _post
    except Exception as exc:
        print(f"[va-plugin] hook install failed: {exc}", flush=True)

    try:
        from vllm.v1.worker.gpu_worker import Worker

        _orig_load_model = Worker.load_model

        def _load_model(self, *args, **kwargs):
            try:
                from vllm_ascend.ascend_config import init_ascend_config

                init_ascend_config(self.vllm_config)
                print("[va-plugin] init_ascend_config: OK (worker)", flush=True)
            except Exception as exc:
                print(f"[va-plugin] init_ascend_config failed: {exc}", flush=True)
            return _orig_load_model(self, *args, **kwargs)

        Worker.load_model = _load_model
    except Exception as exc:
        print(f"[va-plugin] worker hook failed: {exc}", flush=True)

    try:
        from vllm.model_executor.layers.fused_moe.routed_experts import RoutedExperts

        _orig_re_init = RoutedExperts.__init__

        def _re_init(self, *args, **kwargs):
            kwargs.pop("n_shared_experts", None)
            return _orig_re_init(self, *args, **kwargs)

        RoutedExperts.__init__ = _re_init
        print("[va-plugin] RoutedExperts.n_shared_experts shim: OK", flush=True)
    except Exception as exc:
        print(f"[va-plugin] routed-experts shim failed: {exc}", flush=True)


_install_ascend_config_hook()
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
