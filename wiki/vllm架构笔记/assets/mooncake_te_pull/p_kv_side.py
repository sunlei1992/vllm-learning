import ctypes
import json
import os
import socket
import sys

sys.path.insert(0, "/app")
from patterns import make_pattern
from pull_transport import MooncakeTransport, host_ptr

HOST = "pull-p"
CONTROL_PORT = 29501
NUM_BLOCKS = int(os.getenv("NUM_BLOCKS", "2"))
K_BLOCK = int(os.getenv("K_BLOCK", str(1 << 20)))
V_BLOCK = int(os.getenv("V_BLOCK", str(1 << 20)))


def main() -> None:
    transport = MooncakeTransport(HOST, protocol="tcp", metadata="http://pull-meta:8080/metadata")
    k_buf = ctypes.create_string_buffer(K_BLOCK * NUM_BLOCKS)
    v_buf = ctypes.create_string_buffer(V_BLOCK * NUM_BLOCKS)
    for b in range(NUM_BLOCKS):
        k_buf.raw = k_buf.raw[: b * K_BLOCK] + make_pattern(1, b, K_BLOCK) + k_buf.raw[(b + 1) * K_BLOCK :]
        v_buf.raw = v_buf.raw[: b * V_BLOCK] + make_pattern(2, b, V_BLOCK) + v_buf.raw[(b + 1) * V_BLOCK :]
    transport.register([host_ptr(k_buf), host_ptr(v_buf)], [K_BLOCK * NUM_BLOCKS, V_BLOCK * NUM_BLOCKS])

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", CONTROL_PORT))
    srv.listen(1)
    print("P kv ready", flush=True)
    conn, _ = srv.accept()
    conn.makefile("r").readline()
    meta = {"host": HOST, "k_base": host_ptr(k_buf), "v_base": host_ptr(v_buf),
            "k_block": K_BLOCK, "v_block": V_BLOCK, "num_blocks": NUM_BLOCKS}
    conn.sendall((json.dumps(meta) + "\n").encode())
    print("P sent kv meta", flush=True)
    print("P got", conn.recv(64).decode(errors="replace").strip(), flush=True)
    conn.close()
    srv.close()


if __name__ == "__main__":
    main()
