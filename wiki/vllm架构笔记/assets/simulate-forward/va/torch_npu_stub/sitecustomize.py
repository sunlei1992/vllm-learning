"""Inject stubs that must exist before vllm_ascend imports."""
import sys
import types
from unittest.mock import MagicMock

# triton-ascend extension ops
_cann = types.ModuleType("triton.language.extra.cann")
_ext = types.ModuleType("triton.language.extra.cann.extension")
for _name in ("insert_slice", "extract_slice", "get_element"):
    setattr(_ext, _name, MagicMock(name=_name))
_cann.extension = _ext
sys.modules.setdefault("triton.language.extra.cann", _cann)
sys.modules.setdefault("triton.language.extra.cann.extension", _ext)

# torch.npu is referenced in annotations at import time
try:
    import torch

    if not hasattr(torch, "npu"):
        try:
            import torch_npu

            torch.npu = torch_npu.npu
        except Exception:
            torch.npu = MagicMock(name="torch.npu")
except Exception:
    pass

# torch CPU build lacks HCCL; vllm-ascend's netloader imports this symbol.
try:
    import torch.distributed as _dist

    if not hasattr(_dist, "is_hccl_available"):
        _dist.is_hccl_available = lambda: False
except Exception:
    pass

# `from torch_npu._C._distributed_c10d import ProcessGroupHCCL` needs real
# module entries, a __getattr__ stub is not enough.
_c = types.ModuleType("torch_npu._C")
_dc = types.ModuleType("torch_npu._C._distributed_c10d")
_dc.ProcessGroupHCCL = MagicMock(name="ProcessGroupHCCL")
_c._distributed_c10d = _dc
sys.modules.setdefault("torch_npu._C", _c)
sys.modules.setdefault("torch_npu._C._distributed_c10d", _dc)
