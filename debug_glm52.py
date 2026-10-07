"""GLM-5.2 截断调试脚本（进程内模式，配合 VSCode 断点）

用法:
    # 默认: 3 层 dense（前 3 层）
    source env.sh && VLLM_ENABLE_V1_MULTIPROCESSING=0 .venv/bin/python debug_glm52.py

    # MoE 模式: 3 层全部 MoE（8 专家/层，保留真实形状）
    .venv/bin/python debug_glm52.py --moe

说明:
    - 模型: models/zai-org_GLM-5.2（78 层截断为 3 层，config 已改）
    - 权重: dummy（随机值，输出乱码正常），不下载权重
    - 依赖本地补丁: deepseek_v2.py is_v32=False（稀疏注意力）+ PR#51471 的 cpu_sdpa.py
    - 进程内模式: 单进程运行，VSCode 调试器可跟到引擎内部
"""
import argparse

from vllm import LLM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moe", action="store_true",
                        help="3 层全部改为 MoE（默认是前 3 层 dense）")
    parser.add_argument("--prompt", default="Debug this GLM-5.2 on M3")
    args = parser.parse_args()

    hf_overrides = {}
    if args.moe:
        # 让 3 个截断层全部是 MoE 层，并缩小专家数以适配 24GB 内存
        # （保留真实形状: hidden=6144, MLA, moe_intermediate_size=2048）
        hf_overrides = {
            "first_k_dense_replace": 0,  # 层 0-2 全部 MoE（原 256 专家/层 ≈ 19GB/层，放不下）
            "n_routed_experts": 8,       # 256 -> 8
            "num_experts_per_tok": 2,    # 8 -> 2 (top-2)
        }

    llm = LLM(
        model="models/zai-org_GLM-5.2",
        load_format="dummy",
        enforce_eager=True,
        max_model_len=512,           # GLM-5.2 原始 context 是 1M，必须限制
        dtype="float16",
        gpu_memory_utilization=0.3,  # 内存校验: 可用内存 >= 24G * 比例
        hf_overrides=hf_overrides,
    )

    # 断点推荐位置:
    # ── 模型层 ──
    # - vllm/model_executor/models/deepseek_v2.py:279  ← DeepseekV2MoE 类
    #   （router 线性层 + topk + 专家分发，forward 在 393 行）
    # - vllm/model_executor/models/deepseek_v2.py       ← GlmMoeDsaForCausalLM MLA 注意力
    # ── MoE 执行（--moe 模式）──
    # - vllm/model_executor/layers/fused_moe/experts/cpu_moe.py   ← CPU 专家计算
    # - vllm/model_executor/layers/fused_moe/oracle/unquantized.py ← MoE 后端选择
    # ── 注意力 ──
    # - vllm/v1/attention/backends/mla/cpu_mla.py        ← CPU MLA decode
    # - vllm/v1/attention/backends/mla/prefill/cpu_sdpa.py ← CPU MLA prefill (PR#51471)
    # ── 引擎 ──
    # - vllm/v1/core/sched/scheduler.py:476  ← 连续批处理
    # - vllm/v1/worker/cpu_worker.py:146     ← 模型执行

    out = llm.generate([args.prompt])
    print("=== GENERATED ===")
    print(repr(out[0].outputs[0].text[:60]))


if __name__ == "__main__":
    main()
