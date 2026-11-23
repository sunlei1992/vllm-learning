"""Class-level check: MembPullReadThread._do_read_batch with MooncakeTransport."""

import ctypes
import json
import socket
import sys

sys.path.insert(0, "/app")
from patterns import make_pattern
from pull_transport import MooncakeTransport, host_ptr

from vllm_ascend.distributed.kv_transfer.kv_p2p.sfa_pd_rd2h.read_thread import (
    ConsumerReadState,
    MembPullReadThread,
)

PEER = "pull-p"
CONTROL_PORT = 29501


def main() -> None:
    sock = socket.create_connection((PEER, CONTROL_PORT))
    sock.sendall(b'{"hello": "d"}\n')
    info = json.loads(sock.makefile("r").readline())
    num_blocks = info["num_blocks"]
    k_block, v_block = info["k_block"], info["v_block"]

    transport = MooncakeTransport("pull-d", protocol="tcp", metadata="http://pull-meta:8080/metadata")
    local_k = ctypes.create_string_buffer(k_block * num_blocks)
    local_v = ctypes.create_string_buffer(v_block * num_blocks)
    transport.register([host_ptr(local_k), host_ptr(local_v)], [k_block * num_blocks, v_block * num_blocks])

    state = ConsumerReadState(
        num_blocks=num_blocks,
        tp_size=1,
        layer_metadata={},
        main_name_to_idx={"layer0": 0},
        cpu_pools=[None],
        main_gva_bases=[(host_ptr(local_k), host_ptr(local_v))],
        main_block_lens=[(k_block, v_block)],
        indexer_tensors=[None],
        indexer_scale_tensors=[None],
        dest_blocks_by_req={"req0": (list(range(num_blocks)), [])},
        get_offload_layer_id=lambda name: 0,
    )
    thread = MembPullReadThread(tp_rank=0, side_channel_port=0, engine=transport, state=state)
    p_meta = {
        "layer0": {
            "base_addrs": [info["k_base"], info["v_base"]],
            "block_len": [k_block, v_block],
            "main_tensor_count": 2,
            "has_indexer": False,
        }
    }
    thread._do_read_batch(
        "layer0",
        [("req0", list(range(num_blocks)), [], 0, 0)],
        p_session=PEER,
        p_layer_meta=p_meta,
    )

    ok = True
    for b in range(num_blocks):
        k_ok = local_k.raw[b * k_block : (b + 1) * k_block] == make_pattern(1, b, k_block)
        v_ok = local_v.raw[b * v_block : (b + 1) * v_block] == make_pattern(2, b, v_block)
        ok &= k_ok and v_ok
        print(f"block={b} k_match={k_ok} v_match={v_ok}", flush=True)
    print("RESULT", "PASS" if ok else "FAIL", flush=True)
    sock.sendall(b"READ_DONE\n")
    sock.close()
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
