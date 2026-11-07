"""Send one streamed completion request (with simulated trace tokens)."""

import json
import urllib.request

payload = {
    "model": "qwen",
    "request_id": "95953438d507582e",
    "prompt": "Hello",
    "max_tokens": 4,
    "temperature": 0,
    "stream": True,
    "return_token_ids": True,
    "trace_decode_token_ids": [100, 101, 102, 103],
}
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=180) as resp:
    for line in resp:
        text = line.decode(errors="replace").strip()
        if text:
            print(text[:160])
