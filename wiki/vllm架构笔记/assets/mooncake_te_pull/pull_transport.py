"""Minimal PullTransport prototype over Mooncake Transfer Engine (TCP)."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Any


class PullTransport:
    def register(self, ptrs: list[int], sizes: list[int]) -> None: ...
    def read(self, peer: str, local_ptrs: list[int], peer_ptrs: list[int], lengths: list[int]) -> None: ...
    def close(self) -> None: ...


class MooncakeTransport(PullTransport):
    """Mooncake TE backend. protocol='tcp' locally, 'ascend' on NPU."""

    def __init__(self, hostname: str, protocol: str = "tcp", device: str = "",
                 metadata: str = "P2PHANDSHAKE"):
        from mooncake.engine import TransferEngine

        self.engine: Any = TransferEngine()
        rc = self.engine.initialize(hostname, metadata, protocol, device)
        if rc != 0:
            raise RuntimeError(f"TransferEngine.initialize failed rc={rc}")
        self._registered = False

    def register(self, ptrs: list[int], sizes: list[int]) -> None:
        rc = self.engine.batch_register_memory(list(ptrs), list(sizes))
        if rc != 0:
            raise RuntimeError(f"batch_register_memory failed rc={rc}")
        self._registered = True

    def read(self, peer: str, local_ptrs: list[int], peer_ptrs: list[int], lengths: list[int]) -> int:
        return self.engine.batch_transfer_sync_read(
            peer, list(local_ptrs), list(peer_ptrs), list(lengths)
        )

    def batch_transfer_sync_read(
        self, peer: str, local_ptrs: list[int], peer_ptrs: list[int], lengths: list[int]
    ) -> int:
        """read_thread's engine contract (memfabric-style)."""
        return self.read(peer, local_ptrs, peer_ptrs, lengths)

    def close(self) -> None:
        pass


@dataclass
class PeerBuffer:
    addr: int
    size: int


def host_ptr(buf: Any) -> int:
    """torch tensor or ctypes buffer -> host address."""
    if hasattr(buf, "data_ptr"):
        return buf.data_ptr()
    return ctypes.addressof(buf)
