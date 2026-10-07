#!/bin/bash
# vLLM 本地开发环境变量（macOS / M3 / CPU backend）
# 用法: source env.sh
#
# 说明: 把 uv / HuggingFace / vLLM 的缓存都放在仓库目录内，
#       避免写入 ~/.cache（在本机沙箱环境下必须，普通终端下也无害）。
#       删除 .uv-cache .hf-cache .vllm-cache 即可清理所有缓存。

export PATH="/opt/homebrew/bin:$PATH"          # brew 装的 uv / cmake / ninja
# 注意: 不要定义 VLLM_ 前缀的自定义变量，vLLM 启动时会警告 Unknown vLLM environment variable
export UV_CACHE_DIR="$PWD/.uv-cache"           # uv 包缓存
export HF_HOME="$PWD/.hf-cache"                # HuggingFace 模型/配置缓存
export HF_ENDPOINT="https://hf-mirror.com"     # ★ HF 镜像（huggingface.co 直连不通，必须配）
export VLLM_CACHE_ROOT="$PWD/.vllm-cache"      # vLLM 元数据缓存

# CPU 后端在 macOS 上自动生效 (VLLM_TARGET_DEVICE=cpu)
# 内存要点: --gpu-memory-utilization 在 CPU 后端控制保留的 CPU 内存比例，
#           本机 24GB 且常有其他进程占用，建议 0.4~0.5

alias vllm-run=".venv/bin/python -m vllm.entrypoints.openai.api_server"
