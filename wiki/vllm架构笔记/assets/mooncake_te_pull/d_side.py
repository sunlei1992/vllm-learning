import ctypes
import json
import socket
import sys
import time

sys.path.insert(0, "/app")
from pull_transport import MooncakeTransport, host_ptr

PEER = "pull-p"
CONTROL_PORT = 29500


def make_pattern(buf_index: int, size: int) -> bytes:
    cycle = bytes(((j * 31 + buf_index * 131) & 0xFF) for j in range(256))
    return (cycle * (size // 256 + 1))[:size]


def main() -> None:
    transport = MooncakeTransport("pull-d", protocol="tcp", metadata="http://pull-meta:8080/metadata")

    sock = socket.create_connection((PEER, CONTROL_PORT))
    sock.sendall((json.dumps({"hello": "d"}) + "\n").encode())
    info = json.loads(sock.makefile("r").readline())
    peer_host = info["host"]
    peer_buffers = info["buffers"]
    print("D got peer", peer_host, "buffers", [b["size"] for b in peer_buffers], flush=True)

    local = []
    for b in peer_buffers:
        local.append(ctypes.create_string_buffer(b["size"]))
    transport.register([host_ptr(t) for t in local], [b["size"] for b in peer_buffers])

    ranges = [(0, 0, 1 << 20), (1, 2 << 20, 1 << 20), (2, 0, 4 << 20)]
    t0 = time.perf_counter()
    transport.read(
        peer_host,
        [host_ptr(local[i]) for i, _, _ in ranges],
        [peer_buffers[i]["addr"] + off for i, off, _ in ranges],
        [ln for _, _, ln in ranges],
    )
    dt = time.perf_counter() - t0

    ok = True
    for i, off, ln in ranges:
        expect = make_pattern(i, 4 << 20)[off : off + ln]
        same = local[i].raw[:ln] == expect
        ok &= same
        print(f"range buf={i} off={off} len={ln} match={same}", flush=True)

    total = sum(ln for _, _, ln in ranges)
    print(f"RESULT {'PASS' if ok else 'FAIL'} bytes={total} time={dt*1e3:.2f}ms", flush=True)
    sock.sendall(b"READ_DONE\n")
    sock.close()


if __name__ == "__main__":
    main()
