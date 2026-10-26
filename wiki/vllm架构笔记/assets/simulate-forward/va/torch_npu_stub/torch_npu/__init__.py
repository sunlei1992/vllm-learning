"""Minimal torch_npu stub for import-only experiments (no NPU)."""
from unittest.mock import MagicMock

__version__ = "0.0.0-stub"
npu = MagicMock()
_C = MagicMock()
npu_fusion_attention = MagicMock()
npu_format_cast = MagicMock(side_effect=lambda weight, fmt, **kw: weight)
npu_rotary_mul = MagicMock()
npu_rms_norm = MagicMock()
npu_swiglu = MagicMock()
npu_scaled_masked_softmax = MagicMock()


def __getattr__(name):
    return MagicMock()
