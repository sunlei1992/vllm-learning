import ctypes
import json
import socket
import sys

sys.path.insert(0, "/app")
from pull_transport import MooncakeTransport, host_ptr

HOST = "pull-p"
CONTROL_PORT = 29500
N_BUFS = 3
BUF_SIZE = 4 << 20


def make_pattern(buf_index: int, size: int) -> bytes:
    cycle = bytes(((j * 31 + buf_index * 131) & 0xFF) for j in range(256))
    return (cycle * (size // 256 + 1))[:size]


def main() -> None:
    transport = MooncakeTransport(HOST, protocol="tcp", metadata="http://pull-meta:8080/metadata")
    buffers = []
    meta = []
    for i in range(N_BUFS):
        data = make_pattern(i, BUF_SIZE)
        buf = ctypes.create_string_buffer(data, BUF_SIZE)
        buffers.append(buf)
        meta.append({"addr": host_ptr(buf), "size": BUF_SIZE})
    transport.register([m["addr"] for m in meta], [m["size"] for m in meta])

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", CONTROL_PORT))
    srv.listen(1)
    print(f"P ready host={HOST} control={CONTROL_PORT} buffers={len(buffers)}", flush=True)

    conn, _ = srv.accept()
    req = json.loads(conn.makefile("r").readline())
    conn.sendall((json.dumps({"host": HOST, "buffers": meta}) + "\n").encode())
    print("P sent metadata", flush=True)
    done = conn.recv(64)
    print("P got", done.decode(errors="replace").strip(), flush=True)
    conn.close()
    srv.close()


if __name__ == "__main__":
    main()
