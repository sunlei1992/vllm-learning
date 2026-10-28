#!/bin/bash
# Waits for the dry-run server, then sends traced and untraced requests.
set -euo pipefail
URL=http://127.0.0.1:18000
for i in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health" || true)" = "200" ] && break
  sleep 3
done

echo "=== traced completion ==="
curl -s "$URL/v1/completions" -H 'Content-Type: application/json' \
  -d '{"model":"qwen","prompt":"Hello","max_tokens":4,"temperature":0,
       "return_token_ids":true,"trace_decode_token_ids":[100,101,102,103]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['token_ids'])"

echo "=== untraced completion (returns zeros, not an error) ==="
curl -s "$URL/v1/completions" -H 'Content-Type: application/json' \
  -d '{"model":"qwen","prompt":"Hello","max_tokens":4,"temperature":0,"return_token_ids":true}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['token_ids'])"
