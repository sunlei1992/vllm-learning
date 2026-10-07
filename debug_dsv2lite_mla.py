"""DeepSeek-V2-Lite 缩层调试脚本：验证 CPU 上的 MLA 路径

用法:
    source env.sh && VLLM_ENABLE_V1_MULTIPROCESSING=0 .venv/bin/python debug_dsv2lite_mla.py
    VLLM_LOGGING_LEVEL=DEBUG .venv/bin/python debug_dsv2lite_mla.py   # 看后端选择细节

说明:
    - 模型: models/deepseek-ai_DeepSeek-V2-Lite（本地 config+tokenizer，27 层 -> 2 层）
    - 缩层方式: hf_overrides（与官方 tests/v1/attention/test_cpu_mla_backend.py 同款）
    - 权重: dummy（随机值，输出乱码正常）
    - 依赖本地补丁: PR#51471 的 cpu_sdpa.py（CPU MLA prefill 后端）
    - 目的: MLA 全链路（prefill 走 CPUSDPAMLAPrefillBackend，decode 走 CPUMLAImpl）
"""
import argparse

from vllm import LLM, SamplingParams


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layers", type=int, default=2, help="截断层数（原始 27）")
    parser.add_argument("--experts", type=int, default=4, help="路由专家数（原始 64）")
    parser.add_argument("--prompt", default="MLA on CPU")
    args = parser.parse_args()

    # 与官方 test_cpu_mla_backend_smoke 相同的缩层策略：
    #   first_k_dense_replace=0 -> 所有层都是 MoE（默认第 0 层是 dense，MoE 路径跑不到）
    #   n_routed_experts 64 -> 4（内存），num_experts_per_tok 6 -> 2
    hf_overrides = {
        "num_hidden_layers": args.layers,
        "n_routed_experts": args.experts,
        "first_k_dense_replace": 0,
        "num_experts_per_tok": 2,
    }

    llm = LLM(
        model="models/deepseek-ai_DeepSeek-V2-Lite",
        trust_remote_code=True,       # 本地目录带 modeling_deepseek.py
        load_format="dummy",
        enforce_eager=True,
        max_model_len=128,
        max_num_seqs=2,
        block_size=16,
        dtype="float16",
        gpu_memory_utilization=0.2,
        hf_overrides=hf_overrides,
    )

    # MLA 断点地图:
    # ── MLA prefill（本机补丁路径）──
    # - vllm/v1/attention/backends/mla/prefill/cpu_sdpa.py   ← CPUSDPAMLAPrefillBackend（CPU_SDPA_MLA）
    # - vllm/v1/attention/backends/mla/prefill/selector.py   ← CPU 分支选后端
    # ── MLA decode ──
    # - vllm/v1/attention/backends/mla/cpu_mla.py            ← CPUMLAImpl（mla_decode_kvcache kernel）
    # ── 模型层 ──
    # - vllm/model_executor/models/deepseek_v2.py            ← DeepseekV2Attention（MLA q/kv 投影）
    #   DeepseekV2MoE（router/topk/专家分发）
    # ── MoE 执行 ──
    # - vllm/model_executor/layers/fused_moe/experts/cpu_moe.py

    out = llm.generate([args.prompt, "Hello"], SamplingParams(max_tokens=4, temperature=0.0))
    print("=== GENERATED ===")
    for o in out:
        print(f"  {o.prompt!r} -> {o.outputs[0].text[:40]!r}  (token_ids={len(o.outputs[0].token_ids)})")


if __name__ == "__main__":
    main()
