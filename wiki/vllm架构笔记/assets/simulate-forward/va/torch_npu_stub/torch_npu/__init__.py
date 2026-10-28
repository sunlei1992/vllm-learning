"""Minimal torch_npu stub for import-only experiments (no NPU).

The NPU event/stream objects are backed by threading primitives so CPU code
paths that fence on them (layerwise KV save/load) still make progress.
"""
import threading
from unittest.mock import MagicMock

__version__ = "0.0.0-stub"


class _Event:
    """threading.Event with the torch.npu.Event surface used by vllm-ascend."""

    def __init__(self, *args, **kwargs):
        self._event = threading.Event()

    def record(self, stream=None):
        self._event.set()

    def wait(self, stream=None, timeout=None):
        return self._event.wait(timeout)

    def query(self):
        return self._event.is_set()

    def synchronize(self):
        self._event.wait()

    def elapsed_time(self, other):
        return 0.0


class _Stream:
    def __init__(self, *args, **kwargs):
        pass

    def wait_event(self, event):
        if event is not None:
            event.synchronize()

    def synchronize(self):
        pass


class _NpuModule:
    Event = _Event
    Stream = _Stream

    def current_stream(self, *args, **kwargs):
        return _Stream()

    def synchronize(self, *args, **kwargs):
        pass

    def set_device(self, *args, **kwargs):
        pass

    def device_count(self):
        return 1

    def is_available(self):
        return False

    def empty_cache(self):
        pass

    def __getattr__(self, name):
        return MagicMock(name=f"torch.npu.{name}")


npu = _NpuModule()
_C = MagicMock()
npu_fusion_attention = MagicMock()
npu_format_cast = MagicMock(side_effect=lambda weight, fmt, **kw: weight)
npu_rotary_mul = MagicMock()
npu_rms_norm = MagicMock()
npu_swiglu = MagicMock()
npu_scaled_masked_softmax = MagicMock()


def __getattr__(name):
    return MagicMock()
