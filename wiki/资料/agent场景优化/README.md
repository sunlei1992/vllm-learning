# agent 场景优化 · 资料索引

> **主题**：AI 编程 / Coding Agent 场景的推理优化 —— **超长输入、短输出**（prefill 主导、前缀高共享、KV Cache 巨大）。
> **覆盖范围**：负载画像、前缀/KV 缓存与调度、稀疏注意力、PD 分离、投机解码、跨文件代码补全上下文。
> **归档时间**：2026-09-04（本目录为检索会话整理的资料索引；如需精读/译文可另建文件放本目录）。
> **排序规则**：大类按**来源**分类；类内按时间**新 → 老**；无明确日期的条目排在类内末尾（标"时间未标注"）。
> **日期依据**：arXiv 编号 YYMM、GitHub API（issue/PR/release/仓库）、博客 URL 自带日期。

---

## 0. 30 秒总览（最值得先看的 4 项）

| 想看什么 | 去这里 |
|---|---|
| 为什么 coding agent = 长输入短输出（数据） | [TraceLab（论文）](https://arxiv.org/abs/2606.30560) / [CacheWise（论文）](https://arxiv.org/abs/2606.16824) |
| 算法侧怎么省（稀疏注意力，已进 vLLM/SGLang） | [DeepSeek-V3.2-Exp in vLLM 官方博客](https://vllm.ai/blog/2025-09-29-deepseek-v3-2) |
| 系统侧怎么省（前缀缓存的单机/分布式方案） | [vLLM Automatic Prefix Caching 文档](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching.html) / [Preble（论文）](https://arxiv.org/abs/2407.00023) |

---

## 1. 学术论文（arXiv / 顶会）

| 时间 | 论文 | 出处 | 一句话要点 |
|---|---|---|---|
| 2026-07 | [Load-Aware Prefill Deflection for Disaggregated LLM Serving](https://arxiv.org/abs/2607.02043) | arXiv:2607.02043 | PD 分离架构下按负载感知把 prefill 请求转移调度，长输入主导负载的调度优化 |
| 2026-06 | [TraceLab: Characterizing Coding Agent Workloads for LLM Serving](https://arxiv.org/abs/2606.30560)（[HF Papers 页](https://huggingface.co/papers/2606.30560)） | arXiv:2606.30560 | **真实 coding agent trace 负载画像**：请求/会话结构、输入输出比、可缓存前缀占比 |
| 2026-06 | [CacheWise: Optimizing KVCache Management for Efficiently Serving LLM Coding Agents](https://arxiv.org/abs/2606.16824)（[HF Papers 页](https://huggingface.co/papers/2606.16824)、[全文](https://arxiv-org.ezproxy.obspm.fr/html/2606.16824v1)） | arXiv:2606.16824 | coding agent 的 KV Cache 调度 + 预测淘汰；token goodput 相对 vLLM/InferCept 提升 **1.64x–2x** |
| 2026-03 | [Coding Agents are Effective Long-Context Processors](https://bytez.com/docs/arxiv/2603.20432/paper) | arXiv:2603.20432 | 实证 coding agent 是高效的长上下文处理器 |
| 2025 | [Aligning LLMs to Fully Utilize the Cross-file Context in Repository-level Code Completion](https://conf.researchr.org/details/ase-2025/ase-2025-papers/174/Aligner-LLMs-to-Fully-Utilize-the-Cross-file-Context-in-Repository-level-Code-Comple)（[ACM 版](https://dl.acm.org/doi/10.1109/ASE63991.2025.00125)） | ASE 2025 | 让模型真正用上跨文件上下文，而不是简单堆满长窗口 |
| 2025 | [RepoFusion-in-Decoder: Efficient Cross-File Code Completion via Lightweight Encoder Fusion](https://ieeexplore.ieee.org/document/11257694) | IEEE 2025 | 轻量 encoder 融合多文件表示，避免把整个仓库塞进 decoder 长上下文 |
| 2025 | [Graph-MoE: Graph-Based LLM Framework for Scalable Code Completion in IDE](https://ieeexplore.ieee.org/document/11139956) | IEEE 2025 | 图结构 + MoE 的 IDE 内代码补全（次要参考） |
| 2025 | [LongSpec: Long-Context Lossless Speculative Decoding](https://icml.cc/virtual/2025/51846) | ICML 2025 | 长上下文**无损**投机解码（drafting + verification 针对长序列优化） |
| 2025 | [RAPID: Long-Context Inference with Retrieval-Augmented Speculative Decoding](https://proceedings.mlr.press/v267/chen25s.html) | PMLR v267 | 用检索/短上下文 draft 加速长上下文投机解码 |
| 2025 | [PRISM: Efficient Long-Range Reasoning With Short-Context LLMs](https://aclanthology.org/2025.emnlp-main.517/) | EMNLP 2025 | "不给超长输入"路线：短上下文模型做长程推理/任务分解 |
| 2025（月份未标注） | [Lethe: Layer- and Time-Adaptive KV Cache Pruning for Reasoning-Intensive LLM Serving](https://www.semanticscholar.org/paper/ce7628e9428ec7a94005d237f06a814c45a5f9ee) | Semantic Scholar | 面向 reasoning/agentic serving 的分层、时间自适应 KV 剪枝 |
| 2025-02 | [NSA: Native Sparse Attention](https://arxiv.org/abs/2502.11089)（[全文](https://arxiv-org.ezproxy.obspm.fr/html/2502.11089v2)） | arXiv:2502.11089 | 硬件对齐、可训练稀疏注意力 —— DeepSeek DSA 的理论基础 |
| 2025-02 | [MutaGReP: Execution-Free Repository-Grounded Plan Search for Code-Use](https://arxiv.org/abs/2502.15872) | arXiv:2502.15872 | 免执行的仓库级计划搜索（code-use agent 的上下文选择） |
| 2024-07（ICLR 2025） | [Preble: Efficient Distributed Prompt Scheduling for LLM Serving](https://arxiv.org/abs/2407.00023)（[ICLR 页](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5bc342f48de8264779952fac378f96dc-Abstract-Conference.html)、[OpenReview](https://openreview.net/forum?id=meKEKDhdnx)、[全文 ar5iv](https://ar5iv.labs.arxiv.org/html/2407.00023v2)、[代码](https://github.com/WukLab/preble)、[中文速览](https://chatpaper.com/zh-CN/paper/112999)） | arXiv:2407.00023 | **分布式前缀共享调度（E2）**：全局 radix tree + 利用/探索两级决策，协调缓存复用与负载均衡；负载画像显示 prompt:output 达 37x–2494x、共享 token 85%–97%；平均延迟相对 SGLang 分布式基线好 1.5x–14.5x、p99 好 2x–10x；支持 vLLM / SGLang 后端 |
| 2024-07（FAST 2025） | [Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving](https://arxiv.org/abs/2407.00079)（[FAST'25 PDF](https://www.usenix.org/system/files/fast25-qin.pdf)） | arXiv:2407.00079 | KVCache 为中心的分离式架构（Kimi 的 serving 平台），以存代算解决长输入 + agent 多轮负载 |
| 时间未标注 | [KVComp: LLM-Aware Lossy KV Cache Compression](https://www.semanticscholar.org/paper/3901ed44294e31f906a94c2a107d2cc28c155768) | Semantic Scholar | 面向长上下文的 KV Cache 有损压缩框架 |
| 时间未标注 | [Efficient Context Scaling with LongCat ZigZag Attention](https://arxivlens.com/paperview/details/efficient-context-scaling-with-longcat-zigzag-attention-6559-a96c1406) | ArxivLens | 上下文扩展的新型 ZigZag 注意力 |

---

## 2. vLLM 官方（blog / docs / GitHub issue & PR / Release / 论坛）

| 时间 | 条目 | 类型 | 一句话要点 |
|---|---|---|---|
| 2026-08-28 | [Issue #54179: FlashMLA sparse prefill assertion failed（DeepSeek-V4-Flash + DSpark + 长上下文，H20）](https://github.com/vllm-project/vllm/issues/54179) | Bug | 稀疏 prefill 内核在长上下文下的回归/踩坑记录（open） |
| 2026-06-29 | [PR #46995: [Spec Decode] DSpark](https://github.com/vllm-project/vllm/pull/46995) | PR | vLLM 接入 DSpark 稀疏投机解码 |
| 2026-05-12 | [Issue #42400: GLM-5.1 tool call parsing（作 Claude Code 后端时偶发失败）](https://github.com/vllm-project/vllm/issues/42400) | Bug | coding agent 工具调用链路的解析踩坑（closed） |
| 2026-03-18 | [Issue #37435: MTP draft 配置丢弃 --hf-overrides（破坏长上下文 YaRN/RoPE）](https://github.com/vllm-project/vllm/issues/37435) | Bug | 投机解码 MTP 与长上下文扩展配置冲突（open） |
| 2026-02-13 | [vLLM 论坛：长公共前缀在 v0.11.0 → v0.12.0 间显著提速](https://discuss.vllm.ai/t/significant-speedup-observed-with-long-common-prefix-between-v0-11-0-and-v0-12-0/2379) | 论坛 | 前缀缓存命中优化在真实负载上的提速实证 |
| 2025-12-03 | [Release v0.12.0](https://github.com/vllm-project/vllm/releases/tag/v0.12.0) | Release | 474 commits / 213 贡献者；PyTorch 2.9 升级等 |
| 2025-09-29 | [DeepSeek-V3.2-Exp in vLLM: Fine-Grained Sparse Attention in Action](https://vllm.ai/blog/2025-09-29-deepseek-v3-2) | Blog | vLLM 对 DeepSeek 稀疏注意力（DSA）的接入实践 —— 长输入短输出场景的算法侧降本 |
| 2025-09-05 | [Inside vLLM: Anatomy of a High-Throughput LLM Inference System](https://vllm.ai/blog/2025-09-05-anatomy-of-vllm) | Blog | 架构解剖；含**块边界对齐影响长前缀缓存命中**的分析（agent 长输入场景关键） |
| 2025-06-02 | [RFC #19038: Prefill-only optimizations for PD disaggregation](https://github.com/vllm-project/vllm/issues/19038) | RFC | PD 分离下 prefill-only 优化方向的社区 RFC（open） |
| 持续更新 | [Automatic Prefix Caching（官方文档）](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching.html) | Docs | 哈希前缀缓存，coding agent 多轮重复长输入的核心特性 |
| 持续更新 | [Disaggregated Prefill（Production Stack 文档 vllm-stack-0.1.7）](https://docs.vllm.ai/projects/production-stack/en/vllm-stack-0.1.7/use_cases/disaggregated-prefill.html) | Docs | 生产栈的 prefill/decode 分离部署指南 |
| 持续更新 | [API 文档：vllm.models.deepseek_v4.nvidia.dspark](https://docs.vllm.ai/en/latest/api/vllm/models/deepseek_v4/nvidia/dspark/) | Docs | DeepSeek V4 + NVIDIA DSpark 稀疏注意力模块（对应 2026-06 PR） |

---

## 3. SGLang / LMSYS 官方

| 时间 | 条目 | 一句话要点 |
|---|---|---|
| 2025-09-29 | [SGLang Day 0 Support for DeepSeek-V3.2 with Sparse Attention（LMSYS）](https://lmsys.org/blog/2025-09-29-deepseek-V32/) | SGLang 首发支持 DeepSeek V3.2 稀疏注意力 |
| 2025-09-10 | [SGLang HiCache: Fast Hierarchical KV Caching with Your Favorite Storage Backends（LMSYS）](https://www.lmsys.org/blog/2025-09-10-sglang-hicache/) | 分层 KV 缓存（显存 → 本地盘 → 远端存储），冷启动长会话免全量重算 |
| 随代码更新 | [HiCache System Design and Optimization（设计文档）](https://raw.githubusercontent.com/sgl-project/sglang/d0fb24ee7bf5d024d23dbb829d9abd7766489489/docs/advanced_features/hicache_design.md) | HiCache 系统设计细节（对应 2025-09 发布） |

---

## 4. 其他框架与平台官方（GitHub 仓库 / 厂商博客）

| 时间 | 条目 | 一句话要点 |
|---|---|---|
| 2026-03（仓库创建） | [THUDM/IndexCache（GitHub）](https://github.com/THUDM/IndexCache) | 稀疏注意力**跨层索引复用**（清华&智谱）；报道对 DeepSeek 稀疏注意力提速约 1.8x |
| 2025-09-29（仓库创建） | [deepseek-ai/DeepSeek-V3.2-Exp（GitHub）](https://github.com/deepseek-ai/DeepSeek-V3.2-Exp) | DeepSeek V3.2-Exp 权重/代码发布（稀疏注意力模型） |
| 2025-05-16 | [LMCache: How LMCache Turbocharges Enterprise LLM Inference Frameworks](https://blog.lmcache.ai/en/2025/05/16/how-lmcache-turbocharges-enterprise-llm-inference-frameworks/) | 通用 KV 缓存层，跨框架前缀缓存提速（vLLM/SGLang 皆可挂） |
| 2025-02（仓库创建，2026-07 更新） | [deepseek-ai/FlashMLA（GitHub）](https://github.com/deepseek-ai/FlashMLA) | MLA 高效解码内核（12.9k★）；KV 占用远小于 MHA，长上下文显存友好 |
| 2024-10 | [Chain of Agents（Google Research Blog）](https://research.google/blog/chain-of-agents-large-language-models-collaborating-on-long-context-tasks/) | 多 worker 协作处理长上下文，每个 worker 只读一部分（论文发表于 2024-06） |
| 2024-06（仓库创建，2026-09 持续更新） | [kvcache-ai/Mooncake（GitHub）](https://github.com/kvcache-ai/Mooncake) | Kimi 的 serving 平台开源版；含 [SGLang HiCache 集成示例](https://github.com/kvcache-ai/Mooncake/blob/c251eefa/docs/source/getting_started/examples/sglang-integration/hicache-integration-v1.md) |
| 2024-03（仓库创建，2025-03 更新） | [WukLab/preble（GitHub）](https://github.com/WukLab/preble) | Preble 实现；⚠️ 默认分支已演进为 `multi_modal_main`（描述改为 "Stateful LLM Serving"），当前形态为挂 SGLang fork 的 load balancer，对接现代 vLLM 需自行适配 |
| 时间未标注 | [OpenAI 官方指南：Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) / [Prompt Caching 201 Cookbook](https://developers.openai.com/cookbook/examples/prompt_caching_201) | API 侧自动缓存长公共前缀（适合超长固定系统提示）；缓存命中输入 token 仅 10% 价格 |
| 时间未标注 | [NVIDIA 开发者博客（中文）：借助 NVIDIA Dynamo 实现代理式推理的全栈优化](https://developer.nvidia.cn/blog/full-stack-optimizations-for-agentic-inference-with-nvidia-dynamo/) | Dynamo 面向 agentic 推理的 KV 缓存/调度/分离式全栈优化 |

---

## 5. 中文解读 / 第三方文章

| 时间 | 条目 | 一句话要点 |
|---|---|---|
| 2026-07-12 | [CacheWise 论文详解：面向 LLM Coding Agent 的 KV Cache 调度与预测淘汰（gentlecold）](https://gentlecold.top/20260712/cachewise-paper-analysis/) | 第 1 节论文的中文精读 |
| 2026-05-06 | [vLLM x Mooncake 大规模服务 agentic 工作负载（vllm.com.cn 中译）](https://blog.vllm.com.cn/2026/05/06/mooncake-store.html) | Mooncake 官方博客中文版 |
| 2025-09-29 | [DeepSeek-V3.2-Exp in vLLM 实践（vllm.com.cn 中译）](https://blog.vllm.com.cn/2025/09/29/deepseek-v3-2.html) | vLLM 稀疏注意力博客中文版 |
| 2025-09-05 | [Inside vLLM 解剖（vllm.com.cn 中译）](https://blog.vllm.com.cn/2025/09/05/anatomy-of-vllm.html) | vLLM 架构博客中文版 |
| 2025-09（V3.2 发布前后） | [DeepSeek V3.2 稀疏注意力发布报道：163](https://www.163.com/dy/article/KALC22QA0511ABV6.html) / [36kr](https://eu.36kr.com/zh/p/3488379156487046) / [BAAI hub](https://hub.baai.ac.cn/view/49320) | 稀疏注意力机制（源自北大 ACL 最佳论文）的通俗报道 |
| 2026-03（随仓库发布） | [IndexCache 报道：DeepSeek 稀疏注意力提速 1.8 倍（清华&智谱）（BAAI hub）](https://hub.baai.ac.cn/view/53293) | IndexCache 的通俗报道 |
| 2026-06（镜像） | [TraceLab 中文页面（sinoxiv）](https://sinoxiv.napstic.cn/article/26026796) | 第 1 节论文的中文镜像 |

---

## 附：使用建议

1. **想快速落地**：vLLM [Automatic Prefix Caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching.html) + 升级新版（[v0.11→v0.12 长公共前缀提速讨论](https://discuss.vllm.ai/t/significant-speedup-observed-with-long-common-prefix-between-v0-11-0-and-v0-12-0/2379)）；长冷启动会话看 [SGLang HiCache](https://www.lmsys.org/blog/2025-09-10-sglang-hicache/) / [LMCache](https://blog.lmcache.ai/en/2025/05/16/how-lmcache-turbocharges-enterprise-llm-inference-frameworks/)；算法侧换 DeepSeek-V3.2 类稀疏注意力模型（[vLLM 接入博客](https://vllm.ai/blog/2025-09-29-deepseek-v3-2)）。
2. **想读论文找设计点**：负载画像（[TraceLab](https://arxiv.org/abs/2606.30560) → [CacheWise](https://arxiv.org/abs/2606.16824)）→ 分布式调度（[Preble](https://arxiv.org/abs/2407.00023)）→ KV 池化（[Mooncake](https://arxiv.org/abs/2407.00079)）→ 稀疏索引复用（[IndexCache](https://github.com/THUDM/IndexCache)）。
3. **时效性提醒**：Preble 论文基于 2024 年的 vLLM/SGLang 老版本（当时 vLLM 前缀缓存为 beta）；WukLab/preble 仓库已转向 "Stateful LLM Serving"。引用系统类论文结论前，请对照当前 vLLM（V1 引擎 / PD 分离）实现确认是否仍成立。
