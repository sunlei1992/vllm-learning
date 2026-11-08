#!/usr/bin/env bash
# Bring up a real Mooncake master + a sim container that can use it.
#
#   ./setup_mooncake_sim.sh [sim-image] [sim-container]
#
# Result: mc-master (mooncake-tcp-p2p:latest) and <sim-container> on network mcnet,
# Mooncake client installed into the sim container's site-packages.
set -euo pipefail

SIM_IMAGE="${1:-sim030:int3}"
SIM_NAME="${2:-lab3}"
ROOT="${VLLM_LAB_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
DEPS_DIR=/tmp/mcdeps

docker network create mcnet >/dev/null 2>&1 || true

docker rm -f mc-master >/dev/null 2>&1 || true
docker run -d --name mc-master --network mcnet mooncake-tcp-p2p:latest \
  mooncake_master -rpc_port=50051 >/dev/null
sleep 3
docker logs mc-master 2>&1 | grep -q "Serving" && echo "master: ok"

# Client deps: copy the wheel payload + the few system libs the sim image lacks.
rm -rf "$DEPS_DIR" && mkdir -p "$DEPS_DIR/lib"
docker rm -f mc-src >/dev/null 2>&1 || true
docker create --name mc-src mooncake-tcp-p2p:latest >/dev/null
docker cp mc-src:/usr/local/lib/python3.12/site-packages/mooncake "$DEPS_DIR/"
docker cp mc-src:/usr/local/lib/python3.12/site-packages/mooncake_transfer_engine_non_cuda.libs "$DEPS_DIR/"
docker rm -f mc-src >/dev/null
docker run --rm -v "$DEPS_DIR/lib:/out" mooncake-tcp-p2p:latest bash -c \
  'cp -L /lib/aarch64-linux-gnu/libibverbs.so.1 \
        /lib/aarch64-linux-gnu/libnl-route-3.so.200 \
        /lib/aarch64-linux-gnu/libnl-3.so.200 \
        /lib/aarch64-linux-gnu/libmlx5.so.1 \
        /lib/aarch64-linux-gnu/librdmacm.so.1 /out/'

docker rm -f "$SIM_NAME" >/dev/null 2>&1 || true
docker run -d --name "$SIM_NAME" --network mcnet --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp/trace-e2e:/out" \
  -v "$ROOT/tmp:/wheels:ro" \
  -v "$ROOT/models:/models:ro" \
  -v "$ROOT/tmp/triton-cache:/triton-cache" \
  -v "$DEPS_DIR:/mcdeps:ro" \
  "$SIM_IMAGE" bash -c 'sleep 7200' >/dev/null

docker exec "$SIM_NAME" bash -c '
cp -r /mcdeps/mooncake /mcdeps/mooncake_transfer_engine_non_cuda.libs \
      /usr/local/lib/python3.12/site-packages/
cp /mcdeps/lib/*.so* /usr/local/lib/ && ldconfig
python -c "from mooncake.store import MooncakeDistributedStore; print(\"client: ok\")"
'

echo "done: mc-master + $SIM_NAME on mcnet"
