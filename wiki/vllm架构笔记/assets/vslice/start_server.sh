#!/bin/bash
# In-container server for the vertical slice. Env: VSLICE_POLICY=fcfs|srs
set -euo pipefail

python -m vllm.entrypoints.openai.api_server \
  --model /models/Qwen_Qwen3-0.6B --served-model-name qwen \
  --simulate-forward \
  --simulation-config '{"simulate_forward":true,"timing":"linear","timing_args":{"fixed_us":6200,"prefill_us_per_token":15,"decode_us_per_req":2400,"decode_us_per_kv_token":0.14},"clock":"real","log_path":"/logs/steps.jsonl"}' \
  --kv-cache-memory-bytes 4294967296 \
  --enforce-eager --max-model-len 2048 \
  --max-num-seqs 8 --max-num-batched-tokens 512 \
  --no-enable-prefix-caching \
  --enable-per-request-metrics \
  --scheduler-cls vslice_sched.PolicyScheduler \
  --host 0.0.0.0 --port 8000
