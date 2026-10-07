"""vLLM 本地推理示例（macOS / M3 / CPU backend）

用法:
    source env.sh
    .venv/bin/python demo_inference.py

参数:
    --model        模型名或本地路径（默认 facebook/opt-125m，极小，验证用）
    --load-format  dummy = 随机权重不下载；auto = 下载真实权重
    --mem          CPU 后端保留内存比例，本机可用内存常被其他进程占用，建议 0.3~0.5
    --prompt       输入文本

注意:
    - dummy 权重是随机的，输出"乱码"是正常现象，目的是验证整条推理链路通不通
    - 跑真实模型: --load-format auto --model Qwen/Qwen2.5-0.5B-Instruct
"""
import argparse

from vllm import LLM


def main() -> None:
    parser = argparse.ArgumentParser(description="vLLM 离线推理示例")
    parser.add_argument("--model", default="facebook/opt-125m")
    parser.add_argument("--load-format", default="dummy", choices=["dummy", "auto"])
    parser.add_argument("--mem", type=float, default=0.25,
                        help="CPU 后端保留内存比例 (0~1)。vLLM 启动校验: 可用内存 >= 24G*比例,"
                             "本机可用内存常波动(8~15G), 报 Available memory 不足就调低")
    parser.add_argument("--prompt", default="Hello, my name is")
    args = parser.parse_args()

    llm = LLM(
        model=args.model,
        load_format=args.load_format,   # dummy=随机权重不下载; auto=下载真实权重
        enforce_eager=True,             # 跳过 CUDA Graph（CPU 后端用不上）
        max_model_len=256,              # 限制序列长度，省内存
        dtype="float16",
        gpu_memory_utilization=args.mem,
    )

    out = llm.generate([args.prompt])
    print("=== GENERATED ===")
    print(repr(out[0].outputs[0].text))


if __name__ == "__main__":
    main()
