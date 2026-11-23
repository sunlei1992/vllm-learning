#!/usr/bin/env bash
# Local DRAM2DRAM pull prototype: Mooncake TE + TCP + HTTP metadata server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${IMAGE:-mooncake-tcp-p2p:latest}"
NET="${NET:-pullnet}"

docker network create "$NET" >/dev/null 2>&1 || true
docker rm -f pull-meta pull-p >/dev/null 2>&1 || true

docker run -d --name pull-meta --network "$NET" --platform linux/arm64 \
  -e MC_METADATA_HTTP_ALLOW_INSECURE=1 \
  "$IMAGE" mooncake_http_metadata_server --port 8080 >/dev/null

sleep 2
docker run -d --name pull-p --network "$NET" \
  -e MC_METADATA_HTTP_ALLOW_INSECURE=1 \
  -v "$ROOT:/app:ro" "$IMAGE" python -u /app/p_side.py >/dev/null

sleep 3
docker run --rm --network "$NET" \
  -e MC_METADATA_HTTP_ALLOW_INSECURE=1 \
  -v "$ROOT:/app:ro" "$IMAGE" python -u /app/d_side.py
