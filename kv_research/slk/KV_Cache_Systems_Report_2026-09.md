# LLM KV Cache 管理与以 KV Cache 为中心的推理服务：2023–2026 学术系统论文综述

> 检索截止：2026-09-15（UTC）。所有条目均基于本次会话中的实际网络检索与一手页面（USENIX/ACM/arXiv/OpenReview/NeurIPS/ICML 官网）核验；
> 凡未能一手核验或存在不确定性的信息，均以「⚠️不确定」显式标注。
> 主要一手来源：USENIX FAST'26 / NSDI'26 / OSDI'26 会议程序页、arXiv abs 页与 arXiv 检索页、NeurIPS/ICML/ACL 论文页、
> 以及两个公开的论文索引仓库（`mental2008/awesome-papers` 会议 reading notes、`byungsoo-oh/ml-systems-papers`）。

---

## 0. 最有影响力 / 最常被引用的 Shortlist

| # | 论文 | 会议+年份 | 链接 | 一句话结论 |
|---|------|-----------|------|-----------|
| 1 | **Efficient Memory Management for LLM Serving with PagedAttention**（vLLM） | SOSP 2023 | [arXiv:2309.06180](https://arxiv.org/abs/2309.06180) | 把 KV cache 分页化，几乎消除碎片与冗余复制，吞吐比当时 SOTA 高 2–4×。整个方向的奠基工作。 |
| 2 | **Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving** | FAST 2025（**最佳论文**） | [arXiv:2407.00079](https://arxiv.org/abs/2407.00079) · [USENIX](https://www.usenix.org/conference/fast25/presentation/qin) | 首个把 KV cache 当作一等公民的 PD 解耦架构 + KVCache 中心调度器；模拟场景吞吐最高 +525%，Kimi 生产环境多承载 75% 请求。 |
| 3 | **DistServe: Disaggregating Prefill and Decoding for Goodput-optimized LLM Serving** | OSDI 2024 | [arXiv:2401.09670](https://arxiv.org/abs/2401.09670) · [USENIX](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) | 把 prefill/decode 拆到不同 GPU 并按 TTFT/TPOT 联合优化并行策略；同 SLO 下可服务请求数 7.4×，或 SLO 收紧 12.6×。 |
| 4 | **Splitwise: Efficient Generative LLM Inference Using Phase Splitting** | ISCA 2024 | [arXiv:2311.18677](https://arxiv.org/abs/2311.18677) | 按"算力密集 prompt 阶段 vs 访存密集 token 生成阶段"拆分到异构机器；1.4× 吞吐 @ 成本降 20%，或同成本 2.35× 吞吐。 |
| 5 | **SGLang: Efficient Execution of Structured Language Model Programs**（RadixAttention） | NeurIPS 2024 | [arXiv:2312.07104](https://arxiv.org/abs/2312.07104) · [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/724be4472168f31ba1c9ac630f15dec8-Abstract-Conference.html) | 基数树（radix tree）前缀 KV 复用 + 结构化输出 FSM；相比当时 SOTA 最高 6.4× 吞吐。 |
| 6 | **CacheBlend: Fast LLM Serving for RAG with Cached Knowledge Fusion** | EuroSys 2025 | [arXiv:2405.16444](https://arxiv.org/abs/2405.16444) | 非前缀位置的 chunk KV 复用 + 选择性重算少量 token；TTFT 降低 2.2–3.3×，吞吐提升 2.8–5×，质量无损。 |
| 7 | **CacheGen: KV Cache Compression and Streaming** | SIGCOMM 2024 | [arXiv:2310.07240](https://arxiv.org/abs/2310.07240) · [ACM](https://dl.acm.org/doi/abs/10.1145/3651890.3672274) | KV cache 张量编码 + 带宽自适应流式加载；KV 体积降 3.5–4.3×，上下文获取+处理总延迟降 3.2–3.7×。 |
| 8 | **Preble: Efficient Distributed Prompt Scheduling for LLM Serving** | ICLR 2025 | [arXiv:2407.00023](https://arxiv.org/abs/2407.00023) · [ICLR](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5bc342f48de8264779952fac378f96dc-Abstract-Conference.html) | 首个**面向 prompt 共享的分布式调度**：KV 复用与负载均衡协同优化 + 两级调度；平均延迟优于 SOTA 1.5–14.5×，p99 优 2–10×。 |
| 9 | **Pensieve: Stateful Large Language Model Serving** | EuroSys 2025 | [arXiv:2312.05516](https://arxiv.org/abs/2312.05516) · [ACM](https://dl.acm.org/doi/abs/10.1145/3689031.3696086) | 多轮对话的场景状态缓存（GPU+CPU 多层）+ 非连续 KV 的 PagedAttention 扩展；吞吐为 vLLM/TensorRT-LLM 的 1.14–3.0×。 |
| 10 | **EPIC: Efficient Position-Independent Caching for Serving LLMs**（LegoLink） | ICML 2025 | [arXiv:2410.15332](https://arxiv.org/abs/2410.15332) · [ICML](https://icml.cc/virtual/2025/poster/43926) | 形式化"位置无关缓存（PIC）"，用 LegoLink 修正文档开头的 attention sink；TTFT 最高 8×、吞吐 7× 提升，精度几乎无损。 |
| 11 | **A Survey on LLM Acceleration based on KV Cache Management** | TMLR 2025 | [arXiv:2412.19442](https://arxiv.org/abs/2412.19442) · [TMLR](https://mlanthology.org/tmlr/2025/li2025tmlr-survey/) | 目前最系统的 KV cache 管理综述：token 级 / 模型级 / 系统级三层分类。引用量最高的入门综述。 |
| 12 | **LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Inference** | arXiv 2025（工业界事实标准） | [arXiv:2510.09665](https://arxiv.org/abs/2510.09665) | 把 KV cache 从 GPU 抽出并跨引擎/跨查询共享（offload + PD 传输）；与 vLLM 组合在多轮问答等负载吞吐最高 15×。 |

**2026 年最值得关注的新工作**：`Strata`（OSDI'26，分层上下文缓存，5×）、`LMetric`（OSDI'26，乘法式 KV$-aware 调度）、`CacheSlide`（FAST'26，相对位置相关缓存）、`DroidSpeak`（NSDI'26，跨模型 KV 共享）、`KVServe`（SIGCOMM'26，KV 通信压缩）、`CacheRoute`/`DualMap`（2026 前缀亲和路由）。

---

## 主题 1：以 KV Cache 为中心的服务架构与调度器

### 1.1 架构 / 系统

- **Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving**
  - 会议+年份：**FAST 2025（最佳论文）**；[arXiv:2407.00079](https://arxiv.org/abs/2407.00079) · [USENIX](https://www.usenix.org/conference/fast25/presentation/qin) · [清华获奖新闻](https://www.tsinghua.edu.cn/en/info/1245/14138.htm)
  - 问题：Kimi 生产负载高度过载、长上下文多，传统"假设所有请求都会被处理"的调度假设失效。
  - 技术：prefill 集群 / decode 集群解耦；把 GPU 集群闲置的 CPU/DRAM/SSD 组成 **KVCache 分布式缓存**；KVCache 中心调度器在有效吞吐与延迟 SLO 间平衡；基于预测的**提前拒绝（early rejection）**策略。
  - 结果：模拟场景吞吐最高 **+525%**（满足 SLO）；真实负载下 Kimi 可多承载 **75%** 请求。

- **MemServe: Context Caching for Disaggregated LLM Serving with Elastic Memory Pool**
  - 年份/venue：arXiv 2406.17565（2024-06），⚠️ 我未检索到正式会议收录信息，暂标为**预印本**。
  - 链接：[arXiv:2406.17565](https://arxiv.org/abs/2406.17565)
  - 问题：KV cache 生命周期与作用域被 context caching + 解耦推理拉长，缺少统一架构。
  - 技术：**MemPool** 弹性内存池统一管理跨实例分布式内存与 KV；首次把 context caching 与 disaggregated inference 结合；全局调度器用 **global prompt tree** 做局部性感知的复用策略。
  - 结果：显著改善 JCT（作业完成时间）与 TTFT（论文原文以定性+曲线为主）。

- **Pensieve: Stateful Large Language Model Serving**（EuroSys 2025）
  - [arXiv:2312.05516](https://arxiv.org/abs/2312.05516) · [ACM DOI](https://dl.acm.org/doi/abs/10.1145/3689031.3696086)
  - 问题：多轮对话中，无状态服务每轮重复 prefill 全部历史（论文称冗余极高）。
  - 技术：跨请求维护会话状态；GPU+CPU **多层缓存**；把 PagedAttention 内核泛化以支持"多输入 token、KV 分散在非连续显存"的注意力。
  - 结果：吞吐为 vLLM / TensorRT-LLM 的 **1.14–3.0×**，延迟显著下降。

- **InferCept: Efficient Intercept Support for Augmented LLM Inference**
  - 年份/venue：arXiv 2402.01869（2024-02），⚠️ 未确认正式会议。
  - 链接：[arXiv:2402.01869](https://arxiv.org/abs/2402.01869)
  - 问题：工具调用/agent 拦截把一次生成切成多个新请求，重复计算占模型前向时间 **37–40%**。
  - 技术：首个支持"生成过程拦截"的推理框架；拦截时保留 KV/generation 状态，把省下的显存用于更多请求。
  - 结果：整体服务吞吐 **1.6–2×**，每秒完成请求数 **2×**。

- **Parrot: Efficient Serving of LLM-based Applications with Semantic Variable**
  - **OSDI 2024** · [arXiv:2405.19888](https://arxiv.org/abs/2405.19888) · [USENIX](https://www.usenix.org/conference/osdi24/presentation/lin-chaofan)
  - 问题：公共 LLM 服务只有 request 级 API，丢失应用级信息（多请求间的数据流关系）。
  - 技术：**Semantic Variable** 抽象暴露应用级依赖，服务端做数据流分析，从而共享前缀/上下文并优化端到端性能（KV 复用是其关键收益来源之一）。
  - 结果：典型应用场景端到端性能最高提升一个数量级。

- **SGLang: Efficient Execution of Structured Language Model Programs**（NeurIPS 2024）
  - [arXiv:2312.07104](https://arxiv.org/abs/2312.07104)
  - 核心技术：**RadixAttention**——用基数树管理 KV cache，使任意共享前缀（而非仅整段前缀）都能命中复用，并按 LRU 驱逐叶子。
  - 结果：多类任务（agent 控制、RAG、JSON 解码、多轮对话）比当时 SOTA 最高 **6.4×** 吞吐。

### 1.2 调度器（2025–2026）

- **Strata: Hierarchical Context Caching for Long Context Language Model Serving** — **OSDI 2026**（Session: *KV Cache and Long Context*）
  - [USENIX 程序页](https://www.usenix.org/conference/osdi26/technical-sessions) · [论文 PDF](https://www.usenix.org/system/files/osdi26-xie-zhiqiang.pdf)
  - 问题：长上下文服务中分层缓存（HBM/CPU/SSD）"朴素实现"会变成 I/O bound：KV 布局碎片化导致小传输、缓存加载阻塞 prefill、调度器忽略加载延迟与 **delay hits**（同一上下文的并发请求同时 miss）。
  - 技术：GPU 辅助 I/O 机制解耦 GPU/host 布局以支持大块传输；cache-aware 调度器缓解 delay hits、平衡 batch 以隐藏加载延迟、机会式重叠互补工作。
  - 结果：已集成进 SGLang 并在生产部署；吞吐比 vLLM-LMCache 高 **5×**、比 NVIDIA TensorRT-LLM 高 **3.75×**，短上下文性能不退化。

- **Simple Is Better: Multiplication May Be All You Need for LLM Request Scheduling（LMetric）** — **OSDI 2026**
  - [USENIX 程序页](https://www.usenix.org/conference/osdi26/technical-sessions) · [论文 PDF](https://www.usenix.org/system/files/osdi26-zhang-dingyan.pdf)
  - 问题：调度需同时满足"路由到的实例有 KV$"与"负载均衡"，现有线性组合打分需大量逐负载调参/simulator 建模。
  - 技术：**直接把两个指标相乘**作为调度分数——KV$-aware 指标（若路由到该实例的"新 prefill token 数"）× 负载指标（该实例当前 batch size）。超参在比较时自动约掉，**无需调参**；论文还推导了乘法可能失效的数学条件（实践中极罕见且可提前检测）。
  - 结果：相比 vLLM-v1 与某生产调度器，TTFT 降低 **92% / 39%**，TPOT 降低 **24% / 51%**；已在生产部署并通过灰度验证。

- **Prism: Cost-Efficient Multi-LLM Serving via GPU Memory Ballooning** — **OSDI 2026**
  - [USENIX 程序页](https://www.usenix.org/conference/osdi26/technical-sessions) · [kvcached 开源](https://github.com/ovg-project/kvcached)
  - 问题：推理服务商要同时保活大量（含低频）模型，需要更细粒度的显存共享。
  - 技术：**显存 ballooning**——用可回收的 KV 显存统一空间共享与时间共享；balloon 驱动 **kvcached** 已开源。
  - 结果：已在 **10K+ GPU** 生产环境部署（论文以生产部署与 SLO/效率权衡为主）。

- **Prism/Niyama（QoServe）: Breaking the Silos of LLM Inference Serving** — **ASPLOS 2026**
  - 注意：arXiv 题目为 *Niyama*，ASPLOS'26 收录题目为 *QoServe*（同一工作）。链接：[ASPLOS'26 DOI](https://dl.acm.org/doi/10.1145/3779212.3790206) · [arXiv:2503.22562](https://arxiv.org/abs/2503.22562)
  - 技术：细粒度 QoS 分级 + 利用 LLM 推理可预测性做**动态 chunking**，在严格 QoS 下提升整体吞吐；混合优先级策略平衡公平与效率。

- **eLLM: High Throughput and Low Latency LLM Serving via Adaptive KV Caching** — **EuroSys 2026**
  - [ACM DOI](https://dl.acm.org/doi/abs/10.1145/3767295.3803570) · [作者页（含摘要）](https://cds-macau.github.io/publication/conference-paper/ellm/)
  - 问题：现有"KV offload 到 host 再整块恢复"过于粗粒度，GPU 算力与存储能力未联合利用。
  - 技术：**细粒度部分 token 缓存**——只缓存部分 token 的 KV，其余 token 在解码同时并行重算；请求级（token-wise caching 动态调整 batch 与未缓存比例）+ 层间（通信计算重叠、kernel 融合）。
  - 结果：在满足每条输出 token 延迟 SLO 前提下吞吐 **3.03×**；首 token 延迟降低 **2.63×**。

- **FastServe: Iteration-Level Preemptive Scheduling for LLM Inference** — **NSDI 2026**
  - [USENIX](https://www.usenix.org/conference/nsdi26/presentation/wu-bingyang) · [arXiv:2305.05920](https://arxiv.org/abs/2305.05920)（原 2023 预印本，2026 年正式发表于 NSDI）
  - 技术：token 粒度的抢占式调度 + **skip-join MLFQ**；GPU 与 host 之间主动换入换出中间状态（KV）以支持抢占。
  - 结果：相比 vLLM 吞吐最高 **6.1×**。

- **JITServe: SLO-aware LLM Serving with Imprecise Request Information** — **NSDI 2026**
  - [USENIX](https://www.usenix.org/conference/nsdi26/presentation/zhang-wei) · [arXiv:2504.20068](https://arxiv.org/abs/2504.20068)
  - 技术：用**不精确的请求信息**（输出长度/依赖未知）先做保守调度，随生成推进逐步放松估计；grouped margin 机制保证应用级 SLO。
  - 结果：最大化"满足 SLO 的 token 数"意义上的 goodput（论文以 goodput 曲线为主）。

- **KunServe: Parameter-centric Memory Management for Efficient Memory Overloading Handling in LLM Serving** — **EuroSys 2026**
  - [ACM/arXiv:2412.18169](https://arxiv.org/abs/2412.18169)
  - 问题：负载尖峰时 KVCache 挤爆显存，排队导致延迟数量级上升；已有 KV-centric 方案（丢弃/迁移/换出 KV）释放内存不够快。
  - 技术：**参数中心**的新视角——利用"模型参数在 GPU 间普遍存在副本"这一观察，选择性丢弃参数副本以瞬间释放内存，让所有请求以更大 batch 无排队地服务。

- **DiffKV: Differentiated Memory Management for LLMs with Parallel KV Compaction** — **SOSP 2025**
  - [ACM DOI](https://dl.acm.org/doi/abs/10.1145/3731569.3764810) · [arXiv:2412.03131](https://arxiv.org/abs/2412.03131)
  - 技术：KV 三级差异化（K 与 V 影响不同、token 重要性不同、各 head 动态稀疏模式不同）+ **片上并行 KV compaction** 内存管理器处理碎片化。
  - 结果：论文报告在压缩率与精度/吞吐上均优于统一量化/剪枝方案。

- **Aegaeon: Effective GPU Pooling for Concurrent LLM Serving on the Market** — **SOSP 2025**
  - [ACM DOI](https://dl.acm.org/doi/10.1145/3731569.3764815)
  - 技术：面向"模型市场上大量并发低负载 LLM 服务"的 **GPU 池化**，用显存/KV 与参数的统一调度减少所需 GPU 数。
  - 结果：公开报道称可将硬件用量减少约 **82%**（Alibaba Cloud + 北大；⚠️ 该 82% 数字来自媒体报道与厂商新闻，非本次会话一手核验的论文正文，请以论文为准）。参考：[SDxCentral 报道](https://www.sdxcentral.com/news/alibaba-cloud-claims-it-can-reduce-gpu-use-by-82-with-pooling-system/)。

- **IC-Cache: Efficient Large Language Model Serving via In-context Caching** — **SOSP 2025**
  - [ACM DOI](https://dl.acm.org/doi/abs/10.1145/3731569.3764829)
  - 问题：>70% 用户请求存在语义相似的历史请求；精确匹配 KV 命中率低，纯相似度匹配质量会崩。
  - 技术：把历史 request-response 对作为 **in-context 示例**缓存，让**小模型模仿大模型**；两阶段示例选择（相关性预筛 + 离线聚类 + 轻量代理模型估计端到端效用）+ 按请求复杂度/示例效用/当前负载做**跨模型选择性卸载** + 离线成本感知缓存精炼。
  - 结果：论文报告显著降低服务成本与延迟（提高小模型流量占比而不降质）。⚠️ 具体倍数未在本次检索中拿到一手数字。

- **NanoFlow: Towards Optimal Large Language Model Serving Throughput** — **OSDI 2025**
  - [USENIX](https://www.usenix.org/conference/osdi25/presentation/zhu-kan) · [arXiv:2408.12757](https://arxiv.org/abs/2408.12757)
  - 关键论断：端到端 LLM 服务在常见工作负载下其实是**计算受限**而非访存受限，瓶颈在于同设备内 compute/memory/network 串行。
  - 技术：**intra-device parallelism**——把输入切成 nano-batch 并复制算子，使异构资源并行重叠。

- **Cache-aware / SLO 调度补充（供参考）**：`Past-Future Scheduler`（ASPLOS 2025，[ACM](https://dl.acm.org/doi/abs/10.1145/3676641.3716011)）、`Apt-Serve`（SIGMOD 2025，[arXiv:2504.07494](https://arxiv.org/abs/2504.07494)，KV+hidden state **hybrid cache** 扩大 batch）、`SOLA`（MLSys 2025，[MLSys](https://mlsys.org/virtual/2025/poster/3231)，state-aware 调度）、`ThunderServe`（MLSys 2025，[arXiv:2502.09334](https://arxiv.org/abs/2502.09334)）、`HCache`（EuroSys 2025，[arXiv:2410.05004](https://arxiv.org/abs/2410.05004)，用中间激活而非重算/换出恢复 LLM 状态）。

---

## 主题 2：Prefill/Decode 解耦（PD Disaggregation）与 KV Cache 传输

### 2.1 奠基工作（2024）

- **DistServe** — **OSDI 2024** · [arXiv:2401.09670](https://arxiv.org/abs/2401.09670) · [USENIX](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)
  - 问题：colocate 时 prefill/decode 相互干扰（prefill-decoding interference），且两阶段的资源分配与并行策略被耦合。
  - 技术：两阶段分派到不同 GPU；按 TTFT/TPOT 需求**联合优化各阶段并行策略**；按集群带宽决定放置以最小化解耦通信。
  - 结果：在 TTFT/TPOT 约束下，每 GPU 可服务请求数 **7.4×**，或 SLO 收紧 **12.6×**，>90% 请求满足约束。

- **Splitwise** — **ISCA 2024** · [arXiv:2311.18677](https://arxiv.org/abs/2311.18677)
  - 技术：prompt 计算阶段与 token 生成阶段拆到**不同（可异构）机器**，用 GPU 集群的高速背板互联做状态（KV）传输。
  - 结果：同等条件下 **1.4× 吞吐 @ 成本降 20%**，或同成本同功耗下 **2.35× 吞吐**。

- **Arrow: Adaptive Scheduling Mechanisms for Disaggregated LLM Inference Architecture**
  - arXiv 2505.11916（2025-05），⚠️ 未确认正式会议。 [arXiv:2505.11916](https://arxiv.org/abs/2505.11916)
  - 问题：PD 解耦下静态节点分配在输入/输出长度剧烈波动时 P/D 负载失衡。
  - 技术：利用无状态实例 + P/D 任务延迟特征，**按实时集群指标动态调整 P/D 实例数量**。
  - 结果：真实负载下请求服务率最高 **2.55×**。

### 2.2 2025–2026 新进展

- **Libra: Flexible Request Partitioning and Scheduling for Serving Unbalanced and Dynamic LLM Workloads** — **NSDI 2026**
  - [USENIX](https://www.usenix.org/conference/nsdi26/presentation/ruan-libra)
  - 问题：真实负载下 prompt/response 长度差异大，colocate（含 chunked prefill）与完全解耦都无法同时满足低尾延迟与高吞吐。
  - 技术：**micro-request 拆分框架**——全局调度器决定每请求的切分点，各 GPU 本地调度器组 SLO-aware batch；用 **chunked KV cache 传输**支持跨实例执行 micro-request。
  - 结果：真实 trace 上 goodput 最高 **1.91× / 1.61×**，服务容量 **1.15–3.07×**。

- **SYMPHONY: Enabling Compute-Memory Disaggregation in LLM Serving Systems** — **NSDI 2026**
  - [USENIX](https://www.usenix.org/conference/nsdi26/presentation/agarwal) · [arXiv:2412.16434](https://arxiv.org/abs/2412.16434)
  - 问题：多轮会话 KV 绑定到具体机器 → 负载不均或被迫重算（论文称重算可致 **>99% 已处理 token 冗余**）。
  - 技术：用负载自带的**提示（advisory requests）**把 KV 迁移移出关键路径；由于提示常不可靠，引入**优先级化 KV 管理**（按网络结构与请求优先级分配内存）+ **协作式内存管理**（与 serving 框架协同管理 GPU 内存）。
  - 结果：相比 vLLM 端到端延迟降低 **2.4×**，可多服务 **4×** 请求而延迟基本不增（USENIX 摘要口径；arXiv 摘要称"比 SOTA 多处理 8× 请求"——⚠️ 两处口径不同，以官方会议摘要为准）。

- **Bidaw: Enhancing Key-Value Caching for Interactive LLM Serving via Bidirectional Computation–Storage Awareness** — **FAST 2026**
  - [USENIX](https://www.usenix.org/conference/fast26/presentation/hu-shipeng)
  - 问题：两级存储（host DRAM + SSD）加载历史 KV 使延迟最高 **+3.8×**、吞吐最多 **−2.0×**（相比理想大内存）。
  - 技术：**计算-存储双向感知**——计算引擎按 KV 加载延迟感知调度（按 KV 所在层分离请求并按 KV 大小重排以减少阻塞）；存储侧用 LLM 生成的回复**预测用户访问模式**以提升 host 命中率；并选择性缓存"存储效率高"的历史张量。
  - 结果：延迟降低最多 **3.58×**，吞吐提升最多 **1.83×**，接近"全 KV 驻留 host 内存"的理论上界。

- **KVServe: Service-Aware KV Cache Compression for Communication-Efficient Disaggregated LLM Serving** — **SIGCOMM 2026**
  - [arXiv:2605.13734](https://arxiv.org/abs/2605.13734)
  - 问题：PD/KV 状态解耦后 KV 成为显式网络负载并主导端到端瓶颈；现有 KV 压缩多是**静态运行时配置**，与服务上下文（工作负载混合、带宽、SLO/质量预算）随时间变化不匹配。
  - 技术：(1) 模块化压缩**策略空间**并支持跨方法重组；(2) **Bayesian Profiling Engine** 高效搜索并蒸馏出 3D Pareto 候选集，离线搜索开销降低 **50×**；(3) 在线 **Service-Aware Controller**（解析延迟模型 + 轻量控制器）。
  - 结果：在变化的服务上下文中自适应选择压缩策略，避免固定配置导致的次优甚至延迟上升。

- **Not All Prefills Are Equal: PPD Disaggregation for Multi-turn LLM Serving** — **ICML 2026**
  - [arXiv:2603.13358](https://arxiv.org/abs/2603.13358)
  - 洞察：多轮场景下每轮需 prefill 上轮 prompt+response，且 P↔D 反复传 KV 打满带宽；**append-prefill**（只算新增 token 并复用缓存 KV）对 decode 的扰动比 full prefill 小一个数量级。
  - 技术：**PPD（Prefill-capable Decode）**——把 append-prefill 就近放在 decode 节点执行，并按 SLO 动态路由（论文论证无任何固定路由策略能同时满足所有 SLO）。

- **MuxWise: Towards High-Goodput LLM Serving with Prefill-decode Multiplexing** — **ASPLOS 2026**
  - [ACM DOI](https://dl.acm.org/doi/10.1145/3779212.3790236) · [arXiv:2504.14489](https://arxiv.org/abs/2504.14489)
  - 技术：**GPU 内（intra-GPU）prefill-decode 复用**新范式：bubble-less 复用引擎 + 抗竞争估计器 + SLO-aware dispatcher；把计算分配与显存管理解耦，P/D 独立执行。
  - 结果：SLO 保证下峰值吞吐平均提升 **2.20×**（最高 **3.06×**）。

- **Bullet: Boosting GPU Utilization for LLM Serving via Dynamic Spatial-Temporal Orchestration** — **ASPLOS 2026**
  - [ACM DOI](https://dl.acm.org/doi/10.1145/3779212.3790135) · [arXiv:2504.19516](https://arxiv.org/abs/2504.19516) · [代码](https://github.com/zejia-lin/Bullet)
  - 技术：prefill 与 decode **并发执行** + 基于实时性能建模的动态资源划分 + SLO-aware 调度。

- **DuetServe: Harmonizing Prefill and Decode via Adaptive GPU Multiplexing** — arXiv 2511.04791
  - [arXiv:2511.04791](https://arxiv.org/abs/2511.04791)
  - 技术：默认聚合模式；当预测到 TBT（Time-Between-Tokens）要退化时，动态启用 **SM 级空间复用**做相位隔离。包含 attention-aware roofline 延迟预测 + 分区优化器。

- **RAPID-Serve: Resource-efficient and Accelerated P/D Intra-GPU Disaggregation** — arXiv 2601.11822
  - [arXiv:2601.11822](https://arxiv.org/abs/2601.11822)
  - 技术：同 GPU 上并发执行 P/D + 运行时算力自适应分配（可选 AMD Instinct 的 CU masking）。
  - 结果：无约束吞吐最高 **4.1×**（平均 1.7×），尾延迟改善 32×+（平均 4.9×）。

- **FlowKV: Disaggregated Inference with Low-Latency KV Cache Transfer and Load-Aware Scheduling** — arXiv 2504.03775
  - [arXiv:2504.03775](https://arxiv.org/abs/2504.03775)
  - 技术：优化 KV 传输（块式调用 + 非连续显存导致 kernel 调用过多）并引入 **Load-Aware Scheduler** 动态分配 P/D 节点角色。
  - 结果：平均 KV 传输延迟从 **0.944s 降到 0.053s（−96%）**。

- **semi-PD: Phase-Wise Disaggregated Computation and Unified Storage** — arXiv 2504.19867
  - [arXiv:2504.19867](https://arxiv.org/abs/2504.19867)
  - 洞察：解耦的真正收益来自"计算解耦"，存储不必解耦。技术：分相位解耦计算 + **统一存储**，消除权重副本、KV 传输、存储不均衡与 KV 迁移难题。

- **SplitZip: Ultra Fast Lossless KV Compression for Disaggregated LLM Serving** — arXiv 2605.01708
  - [arXiv:2605.01708](https://arxiv.org/abs/2605.01708)
  - 技术：GPU 友好的**无损** KV 传输压缩器，利用 KV 浮点指数冗余（高频指数用定长码 + 稀疏 escape 流），可直接集成进现有框架、不改模型执行。

- **SpectrumKV: Per-Token Mixed-Precision KV Cache Transfer for PD-Disaggregated Serving** — arXiv 2606.08635
  - [arXiv:2606.08635](https://arxiv.org/abs/2606.08635)
  - 技术：把"传/不传"的二元选择升级为**逐 token 精度分配**（attention sink 等高重要性 FP16、中等 INT8、低重要性可 INT4）；因 INT4 容忍度依模型而异（Qwen2.5-7B 会崩、Mistral-7B/Gemma-2-9B 稳定），引入轻量部署期探针（3 次激进 NIAH 尝试）决定是否启用 INT4。

- **SmartGen: Seamless Disaggregated LLM Inference with Selective KV Cache Transfer** — arXiv 2607.28150
  - [arXiv:2607.28150](https://arxiv.org/abs/2607.28150)
  - 技术：三条传输路径——profile 驱动的**主动推送**关键 KV、**并行按需拉取**、以及兜底路径，以缓解租用云实例间带宽饱和。

- **Prefill-as-a-Service (PrfaaS): KVCache of Next-Generation Models Could Go Cross-Datacenter** — arXiv 2604.15039
  - [arXiv:2604.15039](https://arxiv.org/abs/2604.15039)
  - 洞察：混合注意力架构大幅缩小 KV 体积，使**跨数据中心** PD 服务开始可行；但突发流量、长度偏斜、前缀缓存分布不均、跨集群带宽波动仍会引发拥塞。
  - 技术：选择性把**长上下文 prefill** 卸载到独立的算力密集 prefill 集群（Prefill-as-a-Service）。

- **PDD: Cross-Datacenter Prefill-Decode Disaggregation** — arXiv 2609.13161（2026-07/09）
  - [arXiv:2609.13161](https://arxiv.org/abs/2609.13161)
  - 定位：异构、跨数据中心的经济型 PD 解耦（⚠️ 仅预印本）。

- **其他值得留意**：`BanaServe`（统一 KV 与模块迁移做解耦负载均衡，[arXiv:2510.13223](https://arxiv.org/abs/2510.13223)，亦见 *SPE* DOI 10.1002/spe.70054）、`Observation, Not Prediction`（把调度单元从 turn 提到 conversation，使放置决策只需可观测的首轮输入长度与 KV 占用，[arXiv:2606.01839](https://arxiv.org/abs/2606.01839)）、`Towards Load-Aware Prefill Deflection`（[arXiv:2607.02043](https://arxiv.org/abs/2607.02043)，2P2D 集群上 prefill 执行仅占 P95 TTFT 的 2–23%，其余是排队与 KV 传输）、`Stream2LLM`（MLSys 2026，[arXiv:2604.16395](https://arxiv.org/abs/2604.16395)，上下文流式到达与 prefill 重叠）、`DualPath`（[arXiv:2602.21548](https://arxiv.org/abs/2602.21548)，打破 storage→prefill 单路径的存储带宽瓶颈）、`LLM microserving`（[arXiv:2412.12488](https://arxiv.org/abs/2412.12488)，统一 KV 接口 + 可编程路由支持任意 PD/迁移模式）。

---

## 主题 3：KV Cache 感知的请求路由 / 缓存感知负载均衡

- **Preble: Efficient Distributed Prompt Scheduling for LLM Serving** — **ICLR 2025**（本主题的开创性工作）
  - [arXiv:2407.00023](https://arxiv.org/abs/2407.00023) · [ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5bc342f48de8264779952fac378f96dc-Abstract-Conference.html)
  - 问题：先前 KV 复用工作都局限在**单 GPU**，而生产服务本质是分布式的，prompt 复用与负载均衡会互相冲突。
  - 技术：首个面向 prompt 共享的**分布式 serving 平台**；分布式调度系统联合优化 KV 状态复用与计算负载均衡；引入**层次化调度**（全局放置 + 每实例分组调度）。
  - 结果：真实工作负载与到达模式下，相比 SOTA 平均延迟优 **1.5–14.5×**，p99 延迟优 **2–10×**。

- **Simple Is Better / LMetric**（乘法调度分数）— **OSDI 2026** → 见主题 1.2。**这是 2026 年 KV$-aware 路由最重要的"极简主义"结果**：TTFT −92% / −39%。

- **CacheRoute: Planned Prefix-Affinity Routing for Large-Scale LLM Serving** — arXiv 2608.19677（2026-08）
  - [arXiv:2608.19677](https://arxiv.org/abs/2608.19677)
  - 问题：前缀缓存只有在重复请求回到**仍持有该前缀 KV** 的服务器时才省 prefill；cache-blind 均衡会打散复用，固定亲和又会压垮单机。
  - 技术：**周期性路由计划**——把高频 key 纳入稳定的 warm set 并按期望负载放置其归属；热点 key 可允许多目的地（论文主实验中每个 key 恰一个目的地）。
  - 结果：Llama-3.3-70B fp8 / 60×H100，3.5s p99 SLO 下维持 **176±11 QPS**（最强基线的 **2.3×**）；服务侧 KV 命中率从 **64.1±1.3% → 93.2±0.5%**。论文同时给出**反例**：当亲和恢复的 KV 工作量太少时，残余负载倾斜会抵消甚至抹平收益，因此建议部署前用 shadow replay 评估而非凭工作负载统计直接开启。

- **DualMap: Enabling Both Cache Affinity and Load Balancing for Distributed LLM Serving** — arXiv 2602.06502（2026-02）
  - [arXiv:2602.06502](https://arxiv.org/abs/2602.06502)
  - 技术：用**两个独立哈希函数**把每个请求映射到两个候选实例，再依当前系统状态择优。相比"部分请求走亲和、其余走均衡"的单映射空间方案，统一地同时获得亲和与均衡。

- **Lodestar: An Online-Learning LLM Inference Router** — arXiv 2606.00946（2026-05/06）
  - [arXiv:2606.00946](https://arxiv.org/abs/2606.00946)
  - 技术：持续采集**请求级**集群快照（实例实时状态、请求特征、观测性能），在线训练 **reward predictor**，把请求路由到期望奖励最优（如最小 TTFT）的实例；cloud-native，可与现有引擎配合。

- **NetKV: Network-Aware Decode Instance Selection for Disaggregated LLM Inference** — arXiv 2606.03910（2026-06）
  - [arXiv:2606.03910](https://arxiv.org/abs/2606.03910)
  - 问题：解耦后 KV 必须先穿越数据中心网络，传输时间直接进入 TTFT 预算；现有调度只看算力负载与前缀局部性，忽略拓扑距离与动态拥塞。
  - 技术：引入 **network cost oracle** 的轻量 operator→scheduler 接口；**证明**忽略网络项会使仅 cache-aware 的调度随上下文变长而任意次优；给出 O(|D|) 贪心 NetKV，且其分层排序对**过期遥测**具可证鲁棒性。
  - 结果：64-GPU 四级 fat-tree 模拟 + Mooncake trace 下，平均 TTFT 相比 round-robin 降低最多 **21.2%**、相比调优过的 cache+load-aware 调度器降低 **17.6%**，SLO 达成率最多 **+20.1 个百分点**，TBT 开销 <0.5ms。

- **KVCache Cache in the Wild: Characterizing and Optimizing KVCache Cache at a Large Cloud Provider** — **USENIX ATC 2025**
  - [arXiv:2506.02634](https://arxiv.org/abs/2506.02634)
  - 价值：**首个大规模生产 KV$ 工作负载刻画**。关键发现：KV$ 复用高度倾斜，**单轮请求之间的复用与多轮同等重要**；复用时间与概率总体多样，但按请求类别**可预测**；达到理想命中率所需缓存规模其实不大。据此提出 workload-aware 驱逐策略。

- **Towards a solution to the management scaling paradox in distributed LLM inference** — **EuroMLSys 2026**（第 6 届 ML and Systems Workshop，与 EuroSys 2026 同期，2026-04-27，Edinburgh）
  - [Edinburgh 页面（含摘要/venue）](https://www.research.ed.ac.uk/en/publications/towards-a-solution-to-the-management-scaling-paradox-in-distribut/) · [ACM DOI 10.1145/3805621.3807658](https://dl.acm.org/doi/10.1145/3805621.3807658)
  - 作者：Amir Noohi, Bita Asoodeh, Antonio Barbalace（University of Edinburgh）
  - 问题：解耦推理依赖跨节点 KV 复用（前缀缓存），但现有系统把缓存完全放在**用户态**、叠在内核之上——内核本已负责内存映射、页表与 RDMA 注册。作者提出**"管理扩展性悖论"**：缓存越热，用户态的协调 RPC、逐 chunk 加锁、冗余内存拷贝与 RDMA 传输碎片化开销越大，可占可达 TTFT 的 **79%**，在"最该受益"时反而几乎让延迟翻倍。
  - 技术：先把悖论形式化为 TTFT 分解模型（在 **LMCache + Mooncake atop vLLM** 这一 SOTA 栈上验证）；然后提出 **RMC（Remote Memory for Cache）**——把内核提供的 `/dev/shm` 共享内存扩展到**集群范围**，用**内容寻址的虚拟内存区域（content-addressed VMR）**，任何节点通过对 chunk 的 token 内容做哈希即可算出其地址，**无需任何协调**。
  - 结果：4 类工作负载上相比 LMCache+Mooncake 降低 TTFT **1.1–1.3×**，相比完全重算最多 **2.1×**。

- **ELDR: Expert-Locality-Aware Decode Routing for PD-Disaggregated MoE Serving** — arXiv 2607.00466（2026-07）
  - [arXiv:2607.00466](https://arxiv.org/abs/2607.00466)
  - 洞察：MoE 下"负载相同"的 decode worker 延迟可以不同，因为每步解码要加载该 batch 激活的所有专家权重。
  - 技术：由 prefill 阶段的专家激活构建 **expert signature** 预测生成期专家；离线用 balanced K-means 把 signature 空间划分给 decode worker；在线用 locality-band 路由；signature cache 与 KV cache 按 **KV-block 粒度共同索引**以保证前缀缓存下签名仍精确。
  - 结果：≤40 GPU 部署上，相对最强基线中位 TPOT 降低 **5.9–13.9%**，输出不变。

- **HW-Router: Hardware-Aware Routing for Scalable Multi-LLM Serving** — arXiv 2608.14575（2026-08，预印本）
  - [arXiv:2608.14575](https://arxiv.org/abs/2608.14575)
  - 问题：多模型路由常用静态属性（参数量/FLOPs）估成本，忽略硬件型号（H100 vs V100）、队列长度、KV 占用与 GPU 利用率。
  - 技术：把模型特征与**实时硬件信号**联合输入延迟预测，做 SLO-aware 路由。

- **MISA-T: Scheduling Mixed RL Rollouts Beyond Prefix Locality** — arXiv 2608.11152（2026-08）
  - [arXiv:2608.11152](https://arxiv.org/abs/2608.11152)
  - 问题：前缀亲和路由能提升复用与均衡，但**不控制异构 rollout 会话如何竞争 KV 容量**（RLVR/RLHF/agentic 三类序列结构与 KV 驻留时间差异巨大）。
  - 技术：路由层准入策略 = 自适应会话准入 + 工作负载感知 KV 容量分配 + **驻留时间感知的 KV 记账**；不对 trainer 指定的负载配比造成失真。

- **其他**：`BanaServe`（指出前缀缓存感知路由会让高命中率 prefill 节点吸引过多请求，进一步破坏均衡，[arXiv:2510.13223](https://arxiv.org/abs/2510.13223)）、`RequestRouter`（LOCO 2026 workshop，单 GPU 请求边界模式选择，[arXiv:2605.23057](https://arxiv.org/abs/2605.23057)，⚠️ 非主线会议）、`PlanetServe`（去中心化 LLM 服务 overlay，NSDI 2026）、`Seshat/ServeGen`（NSDI 2026，生产 LLM 服务负载刻画与生成框架，[arXiv:2505.09999](https://arxiv.org/abs/2505.09999)）。

---

## 主题 4：KV Cache 存储分层 / 池化系统（3FS、TokenLake、Cache-as-a-Service、RDMA/CXL）

- **LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Inference** — arXiv 2510.09665（2025-10）
  - [arXiv:2510.09665](https://arxiv.org/abs/2510.09665)
  - 问题：真实用户累积的 KV 总量已远超 GPU 显存，但缺少高效的 offload/transfer 方案。
  - 技术：把 vLLM/SGLang 生成的 KV 抽出 GPU 并**跨引擎、跨查询共享**；支持 prefix reuse（offload）与 **PD 解耦的跨引擎/跨 GPU 传输**；三大支柱 = 批量化数据搬运与计算/IO 流水线、模块化 KV connector（与引擎解耦）、面向 GPU/CPU/存储/网络各层的**一等控制 API**。
  - 结果：与 vLLM 组合在多轮问答/文档分析等负载上吞吐最高 **15×**。生产洞察：从远端存储取 KV 对 prefill 延迟确有收益；而工业界广泛使用的 **context truncation 会把前缀缓存命中率砍掉约一半**。

- **TokenLake: A Unified Segment-level Prefix Cache Pool for Fine-grained Elastic Long-Context LLM Serving** — arXiv 2508.17219（2025-08），⚠️ 未确认正式会议
  - [arXiv:2508.17219](https://arxiv.org/abs/2508.17219)
  - 问题：集群级前缀缓存系统与请求调度**紧耦合**，导致实例间负载不均、数据冗余、内存碎片；而现有系统只在实例间搬"越来越长的前缀缓存"，无法做到低延迟内存池化。
  - 技术：**声明式缓存接口**把 query tensor、前缀缓存与 cache-aware 操作暴露给 TokenLake；以**段（segment）为粒度**管理前缀缓存；heavy-hitter-aware 负载均衡算法改善缓存均衡、去重与碎片整理；透明地最小化 query tensor 与新缓存的通信量；调度器由此可"无视底层缓存管理"地弹性调度。
  - 结果：真实负载下吞吐最高提升 **2.6× / 2.0×**，命中率提升 **2.0× / 2.1×**（分别对比 SOTA cache-aware routing 与 cache-centric PD-disaggregation）。

- **KVDrive: A Holistic Multi-Tier KV Cache Management System for Long-Context LLM Inference** — **SIGMOD 2026**（PACMMOD）
  - [ACM DOI 10.1145/3802077](https://dl.acm.org/doi/abs/10.1145/3802077)
  - 定位：面向长上下文推理的**整体多级 KV 缓存管理**（⚠️ 具体指标本次未取得一手数字）。

- **OrbitFlow: SLO-Aware Long-Context LLM Serving with Fine-Grained KV Cache Reconfiguration** — **VLDB 2026**
  - [arXiv:2601.10729](https://arxiv.org/abs/2601.10729) · [PVLDB DOI](https://dlnext.acm.org/doi/abs/10.14778/3796195.3796214)
  - 问题：长上下文服务中长度与 batch 组成持续变化，显存占用动态波动；静态/预定的 offload 策略无法适配，导致过多 CPU↔GPU KV 传输 → 延迟尖刺与 SLO 违例。
  - 技术：用**轻量 ILP solver** 逐请求决定"哪些层的 KV 留在 GPU"；生成过程中依据运行时反馈持续修正放置；重载时启用 fallback（临时推迟大内存占用的 in-flight 请求）以保整体 SLO。

- **Rack-scale / CXL 相关（2025–2026）**
  - **TraCT: Disaggregated LLM Serving with CXL Shared Memory KV Cache at Rack-Scale** — [arXiv:2512.18194](https://arxiv.org/abs/2512.18194)。把 **CXL 共享内存**同时作为 KV 传输载体与机架级前缀感知 KV 缓存：GPU 通过 CXL load/store 与 DMA 直接读写 KV 块，**消除现有解耦流水线中的 NIC 跳**；并处理非一致 CXL 内存上的同步、一致性与数据管理难题。
  - **SAC: Disaggregated KV Cache System for Sparse Attention LLMs with CXL** — [arXiv:2606.19746](https://arxiv.org/abs/2606.19746)。指出 RDMA 内存池对**稀疏注意力**是结构性浪费（只激活少量 KV 却要整段前缀搬本地）；用 CXL 的 cache-line 粒度 load/store **按需只取 top-k KV**。DeepSeek-V3.2 + SGLang 上相比 RDMA 基线吞吐 **2.1×**、TTFT **9.7× 更低**、TBT **1.8× 更低**。
  - **CXL-SpecKV: A Disaggregated FPGA Speculative KV-Cache for Datacenter LLM Serving** — **FPGA 2026（Oral）**，[arXiv:2512.11920](https://arxiv.org/abs/2512.11920)。CXL 内存解耦把 KV 下放到远端 FPGA 内存 + 推测式 KV 预取 + FPGA 加速的 KV 压缩/解压引擎（内存带宽需求最多降 **4×**）；端到端最高 **3.2×**（⚠️ 摘要中该数字在截断处，建议核对原文）。
  - **ITME: Inference Tiered Memory Expansion with Disaggregated CXL-Hybrid Memories** — [arXiv:2606.12556](https://arxiv.org/abs/2606.12556)
  - **Reducing Data Transfer Overhead with CXL-Based Near-Data Processing for LLM Inference** — IEEE Xplore [文档 11329799](https://ieeexplore.ieee.org/document/11329799)（⚠️ venue 未确认）
  - **Evaluating CXL Memory Pooling for Scalable LLM Inference** — IEEE Xplore [文档 11459268](https://ieeexplore.ieee.org/document/11459268)（⚠️ venue 未确认）

- **SSD / 本地存储侧**
  - **SolidAttention: Low-Latency SSD-based Serving on Memory-Constrained PCs** — **FAST 2026**，[USENIX](https://www.usenix.org/conference/fast26/presentation/zheng)。AI PC 上 KV 显存受限；把多个 KV pair 聚成粗粒度块 + 利用稀疏注意力时间局部性的**推测预取** + 计算/IO 细粒度编排。128k 上下文下速度最高 **3.1×**，KV 显存占用最多降 **98%**，精度不降。
  - **ObjectCache: Layerwise Object-Storage Retrieval for KV Cache Reuse** — [arXiv:2605.22850](https://arxiv.org/abs/2605.22850)。把 KV 放到 S3 兼容对象存储以解除容量约束；**协同设计存储协议与传输调度**，让存储服务器按 GPU 消费顺序交付 KV，并与并发请求的计算重叠。原型：100 Gbps RoCE + NIXL + Ceph RGW + DAOS；64K 上下文下 TTFT 增加很小。

- **Tiering 配置与经济学**
  - **Kareto: Adaptive Multi-Objective Tiered Storage Configuration for KV Cache in LLM Service** — [arXiv:2603.08739](https://arxiv.org/abs/2603.08739)。把"异构存储层如何配置"形式化为多目标优化（成本/吞吐/延迟的 Pareto 前沿），用**递减收益引导的剪枝**高效逼近前沿 + 细粒度自适应调参器。
  - **Can I Buy Your KV Cache?** — [arXiv:2606.13361](https://arxiv.org/abs/2606.13361)（2026）。position/实证型：让发布者预计算文档 KV，agent **付费加载**以跳过 prefill。验证为 **token-exact**（24/24 greedy token，logits 级一致），Qwen3-4B 上复用比 prefill 便宜 **9–50×** 且随长度拉大差距（prefill attention 随 L² 增长）；核心难点在**KV 放哪里**——传输失败因为 KV 近乎不可压缩，按次 egress 成本会超过其节省的 prefill。
  - **Adaptive KV Cache Reuse for Fast Long-Context LLM Serving** — [arXiv:2605.24022](https://arxiv.org/abs/2605.24022)（⚠️ venue 未确认）

- **关于 3FS**：DeepSeek 的 **Fire-Flyer File System (3FS)** 是 2025-02 在 `deepseek-ai/open-infra-index` 开源的并行文件系统（[仓库](https://github.com/deepseek-ai/open-infra-index)），被生产用于 KV cache 等 AI 负载的高吞吐读取。⚠️ **本次检索未发现对应的同行评审学术论文**，因此不计入论文清单，仅作为工业系统背景列出。学术侧与之最接近的是 FAST'26 的 **AITURBO**（华为云 AI 作业云存储，明确把 KV-cache reads 作为目标负载之一，并与 Mooncake 等对比；[FAST'26 程序页](https://www.usenix.org/conference/fast26/technical-sessions)）。

---

## 主题 5：KV Cache 复用 / 前缀共享 / 检索增强复用

### 5.1 缓存复用（非精确前缀）

- **CacheBlend: Fast LLM Serving for RAG with Cached Knowledge Fusion** — **EuroSys 2025**
  - [arXiv:2405.16444](https://arxiv.org/abs/2405.16444)
  - 问题：RAG 中被检索文本块通常**不是输入前缀**，预计算 KV 忽略了与前面文本的 cross-attention，因而无法直接使用。
  - 技术：不管前缀与否直接复用预计算 KV，并**选择性重算极少数 token 的 KV**做部分更新；重算的少量延迟可与同 job 内的 KV 检索**流水线重叠**，因此允许把 KV 放在更慢但更大的存储上。
  - 结果：3 个开源 LLM × 4 个数据集上，TTFT 降低 **2.2–3.3×**，吞吐提升 **2.8–5×**，生成质量不降。

- **EPIC: Efficient Position-Independent Caching**（LegoLink） — **ICML 2025**
  - [arXiv:2410.15332](https://arxiv.org/abs/2410.15332) · [PMLR](https://proceedings.mlr.press/v267/hu25j.html)
  - 技术：**形式化 PIC**（位置无关缓存：与前后缀无关的模块化 KV 复用）；**LegoLink** 专治每个文档开头的 **attention sink** 误配，以极小计算维持精度。
  - 结果：TTFT 最高 **8×**、吞吐 **7×** 提升，精度几乎无损失。

- **CacheSlide: Unlocking Cross Position-Aware KV Cache Reuse for Accelerating LLM Serving** — **FAST 2026**
  - [USENIX](https://www.usenix.org/conference/fast26/presentation/liu-yang) · [论文 PDF](https://www.usenix.org/system/files/fast26-liu-yang.pdf)
  - 问题：agent 应用的 prompt 由"不变段 + 动态段"构成。既有 PDC（位置相关）与 PIC（位置无关）都不合适：前者有严格位置约束，后者因 **Positionally Misaligned KV Drift (PMKD)** 与窗口 padding 带来大量额外计算。
  - 洞察/技术：识别出 agent 工作流中的第三类模式 **RPDC（相对位置相关缓存）**——可复用段在绝对位置变化时仍保持一致的**相对顺序**。CacheSlide 增强固定段的**位置编码相似性**、只对极少数 token 算注意力、用**学习到的权重**融合新/旧 KV，并加入层级与 spill-aware 的 KV 优化（实现为 vLLM 扩展：Chunked Contextual Position Encoding + Weighted Correction Attention）。
  - 结果：多个 LLM 与 agent benchmark 上延迟降低 **3.11–4.3×**，吞吐提升 **3.5–5.8×**。

- **DroidSpeak: KV Cache Sharing Across Fine-tuned Model Variants（Cross-LLM Communication and Multi-LLM Serving）** — **NSDI 2026**
  - [USENIX](https://www.usenix.org/conference/nsdi26/presentation/liu-yuhan) · [arXiv:2411.02820](https://arxiv.org/abs/2411.02820)
  - 问题：企业复合 AI 系统中多个同架构 LLM 处理相同上下文前缀，但"一个模型复用另一个模型的 KV"仍是开放问题。
  - 技术：首次系统研究**跨模型 KV 共享的质量影响**；只**选择性重算少数层**、复用其余层；并把逐层重算与复用 KV 的加载流水线化。
  - 结果：吞吐最高 **4×**，prefill（TTFT）约 **3.1×** 加速，F1/Rouge-L/代码相似度几乎无损。

- **KVLink: Accelerating Large Language Models via Efficient KV Cache Reuse** — **NeurIPS 2025**
  - [NeurIPS 页面](https://neurips.cc/virtual/2025/loc/san-diego/poster/116061) · [arXiv:2502.16002](https://arxiv.org/abs/2502.16002)
  - 定位：独立预计算多个文档的 KV 后高效拼接复用（KV 链接/拼接类工作的代表）。

- **Cache-Craft: Managing Chunk-Caches for Efficient Retrieval-Augmented Generation** — **SIGMOD 2025**
  - [arXiv:2502.15734](https://arxiv.org/abs/2502.15734) · [Adobe Research](https://research.adobe.com/publication/cache-craft-managing-chunk-caches-for-efficient-retrieval-augmented-generation/)
  - 技术：管理并复用与文本 chunk 对应的预计算 KV（**chunk-cache**）：识别哪些 chunk-cache 可复用、做**少量重算修复**以保质量、并高效存储/驱逐以最大化复用而掩盖开销。
  - 结果：冗余计算比 SOTA 前缀缓存减少 **51%**、比完全重算减少 **75%**；真实生产负载 + 连续批处理下吞吐 **1.6×**、端到端响应延迟 **2×** 改善（LLaMA-3-8B 与 70B 均有效）。

- **RAGCache: Efficient Knowledge Caching for Retrieval-Augmented Generation**
  - [arXiv:2404.12457](https://arxiv.org/abs/2404.12457)（⚠️ 未确认正式会议；被广泛引用为 RAG KV 缓存早期代表）
  - 技术：把被检索知识的中间状态组织成**知识树**并在 GPU/host 内存层级缓存；替换策略同时感知 LLM 推理特征与 RAG 检索模式；并把检索与推理步骤**动态重叠**。

- **SpecCache: Speculative KV Cache Reuse for Efficient RAG Serving** — **ACL 2026**
  - [ACL Anthology](https://aclanthology.org/2026.acl-long.859/)
  - 定位：检索增强服务的**推测式** KV 复用（⚠️ 具体机制与数字未在本次会话中取到一手摘要）。

- **HYPIC: Accelerating Hybrid-Attention LLM Serving with Position-Independent Caching** — arXiv 2607.01299（2026-07）
  - [arXiv:2607.01299](https://arxiv.org/abs/2607.01299)
  - 问题：PIC 与混合注意力（多数全注意力层被线性注意力替代）**无法共存**——逐 token KV 复用原语不能迁移到"按请求维护的递归状态"。
  - 技术：对线性注意力层，识别出缺失的代数原语 **segment-cumulative transition operator**，与每个段的 zero-start end-state 一起缓存，从而对独立缓存的段实现**近精确、常数时间的组合**；对剩余全注意力层另行修复 PIC 失效问题。

- **SparseX: Efficient Segment-Level KV Cache Sharing for Interleaved LLM Serving** — arXiv 2606.01751（2026-06）
  - [arXiv:2606.01751](https://arxiv.org/abs/2606.01751)
  - 技术：以连续 token 段为复用单位；利用 KV 复用负载中自然出现的 **Sparse-Q 索引**估计需修正的关键 token，在**单次前向**内做 Sparse-KV 重算以恢复跨段上下文交互（无需额外模型或独立预处理）；并实现按层阈值的 full+sparse 混合注意力。

- **A Universal Context-Reuse Layer for Cross-Model KV Sharing** — arXiv 2608.30963（2026-08）
  - [arXiv:2608.30963](https://arxiv.org/abs/2608.30963)
  - 技术：把源模型的 KV 状态**翻译**成目标模型可消费的表示，覆盖不同规模、架构、注意力配置、tokenizer 甚至模型族。
  - 结果：Qwen2.5-7B → Qwen2.5-1.5B 上 LongBench2 从 **27.59% → 34.48%**（+6.89 个百分点），同时移交成本低于目标模型原生 prefill；跨族（Qwen2.5-1.5B → Gemma-2-2B）也能降低目标侧开销。

- **KVShareArena: KV-Cache Reuse Across Contexts and Model Checkpoints** — arXiv 2609.10266（2026-09）
  - [arXiv:2609.10266](https://arxiv.org/abs/2609.10266)（⚠️ 新预印本）

- **RedKnot: Efficient Long-Context LLM Serving with Head-Aware KV Reuse and SegPagedAttention** — arXiv 2606.06256（2026-06）
  - [arXiv:2606.06256](https://arxiv.org/abs/2606.06256)
  - 洞察：KV 效用**跨 KV head 高度结构化**（不同 head 的功能角色、注意力距离、运行时重要性不同），因此不该对整条 KV 用同质策略。RedKnot 打破单体 KV 抽象，把位置无关缓存、前缀压缩、冷热分离、分布式管理等统一到 head-aware 表示上。

- **SemShareKV: Efficient KVCache Sharing for Semantically Similar Prompts via Token-Level LSH Matching** — IJCNLP-AACL 2025 Findings
  - [ACL Anthology](https://aclanthology.org/2025.findings-ijcnlp.25/) · [arXiv:2509.24832](https://arxiv.org/abs/2509.24832)
  - 技术：面向**语义相似但字面不同**的 prompt（多文档摘要、对话 agent 常见）；用 token embedding 上的 **LSH 模糊匹配**替代精确 token 匹配，并结合 RoPE 保留位置信息。

- **Prompt/Cache 的其他 2026 代表**：`SPECTRA`/`StitchLLM`（ACL 2025，[StitchLLM](https://aclanthology.org/2025.acl-long.1305.pdf)，按块服务 LLM）、`LazyAttention`（**ICML 2026**，[arXiv:2606.04302](https://arxiv.org/abs/2606.04302)，延迟位置编码的 RAG）、`PCR`（[arXiv:2603.23049](https://arxiv.org/abs/2603.23049)，预取增强的 RAG 缓存复用，直击命中率低、CPU-GPU 传输开销与 SSD I/O 慢三个痛点）、`C2KV`（压缩且可组合的 KV 复用，⚠️ arXiv ID 未确认）、`TokenDance`（[arXiv:2604.03143](https://arxiv.org/abs/2604.03143)，多 agent 集体 KV 共享）、`AAFLOW+`（[arXiv:2607.10987](https://arxiv.org/abs/2607.10987)，把 KV cache 变成一等分布式对象：materialize/transfer/fork/compose/evict 算子；TTFT 最多降 **50.2×**、多 agent 算力成本降 **7.63×**）、`GraniKV`（[arXiv:2608.15584](https://arxiv.org/abs/2608.15584)，长共享前缀多 agent 的非对称粒度 KV 分页，⚠️ 作者声明吞吐测量方法有误、待更正）。

### 5.2 KV 压缩 / 量化 / 驱逐（与复用互补）

- **CacheGen** — SIGCOMM 2024（见 Shortlist）：KV 体积降 **3.5–4.3×**，上下文获取+处理延迟降 **3.2–3.7×**。
- **Oaken: Online-Offline Hybrid KV Cache Quantization** — **ISCA 2025** · [arXiv:2503.18599](https://arxiv.org/abs/2503.18599)，把离群值处理拆成在线/离线两段以消除在线检测开销。
- **MiniKV: Pushing the Limits of 2-Bit KV Cache** — ACL 2025 Findings · [ACL](https://aclanthology.org/2025.findings-acl.952.pdf)
- **Kitty**（MLSys 2026，2-bit KV 量化 + 动态通道级精度增强，[OpenReview](https://openreview.net/forum?id=r3mQiuYKIN)）、**FlexiCache**（MLSys 2026，利用跨 KV head 的**时间稳定性**差异做 per-head 缓存策略，[OpenReview](https://openreview.net/forum?id=GgX6dPJx9M)）、**OPKV**（MLSys 2026，可分页 KV 中**可召回稀疏**的插件框架，[OpenReview](https://openreview.net/forum?id=EB5bgzv4qA)）、**SkipKV**（MLSys 2026，跳过 reasoning 模型 thinking token 的 KV 生成与存储，[OpenReview](https://openreview.net/forum?id=cJcZKzdwkP)）
- **Lethe: Layer- and Time-Adaptive KV Cache Pruning for Reasoning-Intensive LLM Serving** — **AAAI 2026** · [arXiv:2511.06029](https://arxiv.org/abs/2511.06029)
- **InfiniGen**（OSDI 2024，动态 KV 管理 + 预取，[USENIX](https://www.usenix.org/conference/osdi24/presentation/lee)）作为背景。

---

## 主题 6：综述与 Position Paper

- **A Survey on Large Language Model Acceleration based on KV Cache Management** — **TMLR 2025**
  - [arXiv:2412.19442](https://arxiv.org/abs/2412.19442) · [TMLR 页面](https://mlanthology.org/tmlr/2025/li2025tmlr-survey/) · [配套论文库](https://github.com/TreeAI-Lab/Awesome-KV-Cache-Management)
  - 分类法：**token 级**（选择、预算分配、合并、量化、低秩分解）、**模型级**（架构与注意力创新以增强 KV 复用）、**系统级**（内存管理、调度、硬件感知设计）。目前该方向引用量最高的综述。

- **Towards Efficient Large Language Model Serving: A Survey on System-Aware KV Cache Optimization (sKis)** — **ACL 2026 Findings**
  - [arXiv:2607.08057](https://arxiv.org/abs/2607.08057) · DOI [10.18653/v1/2026.findings-acl.1916](https://doi.org/10.18653/v1/2026.findings-acl.1916)
  - 三维度组织：**执行与调度（时间）**、**放置与迁移（空间）**、**表示与保留（结构）**；并分析跨行为协同设计亲和性与"行为—目标"映射。

- **From Tensor Buffer to Distributed Memory Hierarchy: A Survey of KV Cache Management for LLM Serving** — arXiv 2607.02574（2026-07）
  - [arXiv:2607.02574](https://arxiv.org/abs/2607.02574)
  - 用**四个轴**（locality、lifetime、ownership、substrate）分类 30+ 个 KV 管理系统，归纳出五种架构原型：**local-paged / disaggregated-pipeline / shared-store / memory-pool / hybrid-tier**；核心论断：在负载与硬件固定的前提下，**ownership（谁拥有 KV）**解释了分布式系统间剩余设计差异的很大部分。并审计现有评测，指出 **7 项缺失的 KV 专项度量**，关联到容错、隔离、分层驱逐、推测解码、MoE 服务与共享缓存语义等开放问题。

- **Benchmarking KV-Cache Optimizations across Task Quality and System Performance for Long-Context Serving** — arXiv 2607.05399（2026-07）
  - [arXiv:2607.05399](https://arxiv.org/abs/2607.05399)
  - 内容：对量化/剪枝/合并三类代表性机制（KIVI、TurboQuant、SnapKV、CaM）在 LongBench 风格任务上做负载感知基准，模型为 Llama-3.1-8B-Instruct 与 Mistral-7B-Instruct-v0.3。
  - 结论：**压缩率本身是端到端性能的糟糕预测器**；KIVI4 跨模型质量最稳，SnapKV 长上下文吞吐最强，CaM 在部分 QA 上收益大但工作负载敏感性强。

- **KVCache Cache in the Wild** — **USENIX ATC 2025**（既是主题 3 的路由依据，也是最有价值的生产工作负载刻画论文）。
- **Seshat/ServeGen** — **NSDI 2026**（全球云推理服务的生产 LLM 服务负载刻画与生成框架，[arXiv:2505.09999](https://arxiv.org/abs/2505.09999)）。
- **Towards Efficient Generative LLM Serving: A Survey from Algorithms to Systems** — **ACM CSUR 2025** · [ACM](https://dl.acm.org/doi/full/10.1145/3754448)（更上层的 LLM 服务综述，KV 管理是其中一节）。
- **Rethinking Key-Value Cache Compression Techniques for LLM Serving** — MLSys 2025 · [arXiv:2503.24000](https://arxiv.org/abs/2503.24000)（对 KV 压缩在真实 serving 下的再评估）。
- **Toward Sustainable Distributed LLM Inference: A Systems Synthesis and Research Agenda** — [arXiv:2609.05565](https://arxiv.org/abs/2609.05565)（2026-09，含能耗/碳排视角的系统综述与议程）。
- **安全侧 position 工作**：`Characterizing Contention-Induced Reliability Collapse in KV-Cache Timing Side Channels for Multi-Tenant LLM Serving` — [arXiv:2609.06853](https://arxiv.org/abs/2609.06853)（2026-09）；另有 "KV Cache Hijacking" 类位置无关复用攻击的讨论（⚠️ 后者未取得一手来源）。

---

## 附：不确定性与核验说明

1. **SYMPHONY 的倍数口径不一致**：USENIX NSDI'26 官方摘要为"相比 vLLM 端到端延迟降 2.4×，多服务 4× 请求"；arXiv 摘要与第三方 reading notes 出现"8×"说法。**以官方会议摘要为准**。
2. **Aegaeon 的"GPU 用量减少 82%"** 来自媒体报道，本次会话未在论文正文中一手核验。
3. **IC-Cache（SOSP'25）** 的定量结果未取得一手数字，仅按官方页面与作者主页给出机制描述。
4. **MemServe / Arrow / InferCept / TokenLake / HYPIC / DualPath 等** 目前检索到的是 arXiv 预印本，**未确认正式会议收录**，已在正文标注。
5. **CXL 类论文的 venue**（`Reducing Data Transfer Overhead with CXL-Based NDP`、`Evaluating CXL Memory Pooling`）仅取得 IEEE Xplore 文档号，**会议/年份不确定**。
6. **KVLink 的 arXiv 编号为 2502.16002**（经 arXiv 检索确认），但该编号对应关系未在 abs 页面正文中二次核验，请以 NeurIPS 2025 官方页面为准。
7. 所有 arXiv 编号形如 `26xx.xxxxx` 的条目均为 **2026 年**投稿（arXiv 编号规则：YYMM）；标注为"2026-0X"的月份来自其 announced 日期。
8. 本次检索中，**arXiv 官方 API（export.arxiv.org）在该网络环境下不可达**，因此全部 arXiv 元数据改由 `arxiv.org/abs/*` 与 `arxiv.org/search` 页面抓取核验；ACM DL 正文受 Cloudflare 拦截（HTTP 403），ACM 条目均以 DOI 页面与官方会议程序页核对标题/venue。

---

## 全部来源 URL

**会议程序 / 官方页面**
- https://www.usenix.org/conference/osdi26/technical-sessions
- https://www.usenix.org/conference/fast26/technical-sessions
- https://www.usenix.org/conference/nsdi26/technical-sessions
- https://www.usenix.org/conference/fast25/presentation/qin
- https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin
- https://www.usenix.org/conference/osdi24/presentation/lin-chaofan
- https://www.usenix.org/conference/osdi24/presentation/lee
- https://www.usenix.org/conference/osdi25/presentation/zhu-kan
- https://www.usenix.org/conference/nsdi26/presentation/ruan-libra
- https://www.usenix.org/conference/nsdi26/presentation/agarwal
- https://www.usenix.org/conference/nsdi26/presentation/liu-yuhan
- https://www.usenix.org/conference/nsdi26/presentation/zhang-wei
- https://www.usenix.org/conference/nsdi26/presentation/wu-bingyang
- https://www.usenix.org/conference/fast26/presentation/liu-yang
- https://www.usenix.org/conference/fast26/presentation/hu-shipeng
- https://www.usenix.org/conference/fast26/presentation/zheng
- https://www.usenix.org/system/files/osdi26-xie-zhiqiang.pdf
- https://www.usenix.org/system/files/osdi26-zhang-dingyan.pdf
- https://www.tsinghua.edu.cn/en/info/1245/14138.htm （Mooncake FAST'25 最佳论文）

**arXiv（标题 / 摘要一手核验）**
- https://arxiv.org/abs/2309.06180 · https://arxiv.org/abs/2407.00079 · https://arxiv.org/abs/2407.00023
- https://arxiv.org/abs/2406.17565 · https://arxiv.org/abs/2312.05516 · https://arxiv.org/abs/2402.01869
- https://arxiv.org/abs/2312.07104 · https://arxiv.org/abs/2401.09670 · https://arxiv.org/abs/2311.18677
- https://arxiv.org/abs/2405.19888 · https://arxiv.org/abs/2405.16444 · https://arxiv.org/abs/2310.07240
- https://arxiv.org/abs/2410.15332 · https://arxiv.org/abs/2505.11916 · https://arxiv.org/abs/2510.09665
- https://arxiv.org/abs/2508.17219 · https://arxiv.org/abs/2411.02820 · https://arxiv.org/abs/2412.16434
- https://arxiv.org/abs/2504.20068 · https://arxiv.org/abs/2305.05920 · https://arxiv.org/abs/2504.19516
- https://arxiv.org/abs/2504.14489 · https://arxiv.org/abs/2503.22562 · https://arxiv.org/abs/2509.16495
- https://arxiv.org/abs/2504.07494 · https://arxiv.org/abs/2608.19677 · https://arxiv.org/abs/2601.10729
- https://arxiv.org/abs/2605.13734 · https://arxiv.org/abs/2512.11920 · https://arxiv.org/abs/2511.06029
- https://arxiv.org/abs/2503.18599 · https://arxiv.org/abs/2412.19442 · https://arxiv.org/abs/2506.02634
- https://arxiv.org/abs/2507.07400 · https://arxiv.org/abs/2502.15734 · https://arxiv.org/abs/2404.12457
- https://arxiv.org/abs/2602.06502 · https://arxiv.org/abs/2606.00946 · https://arxiv.org/abs/2605.23057
- https://arxiv.org/abs/2607.08057 · https://arxiv.org/abs/2607.02574 · https://arxiv.org/abs/2607.05399
- https://arxiv.org/abs/2512.18194 · https://arxiv.org/abs/2606.19746 · https://arxiv.org/abs/2605.22850
- https://arxiv.org/abs/2608.30963 · https://arxiv.org/abs/2607.01299 · https://arxiv.org/abs/2504.03775
- https://arxiv.org/abs/2504.19867 · https://arxiv.org/abs/2603.13358 · https://arxiv.org/abs/2604.15039
- https://arxiv.org/abs/2607.02043 · https://arxiv.org/abs/2606.03910 · https://arxiv.org/abs/2603.08739
- https://arxiv.org/abs/2602.21548 · https://arxiv.org/abs/2606.01839 · https://arxiv.org/abs/2601.11822
- https://arxiv.org/abs/2511.04791 · https://arxiv.org/abs/2605.01708 · https://arxiv.org/abs/2604.16395
- https://arxiv.org/abs/2603.23049 · https://arxiv.org/abs/2408.12757 · https://arxiv.org/abs/2605.23389
- https://arxiv.org/abs/2510.13223 · https://arxiv.org/abs/2606.08635 · https://arxiv.org/abs/2608.14575
- https://arxiv.org/abs/2607.00466 · https://arxiv.org/abs/2607.28150 · https://arxiv.org/abs/2608.08097
- https://arxiv.org/abs/2412.03131 · https://arxiv.org/abs/2606.13361 · https://arxiv.org/abs/2606.01751
- https://arxiv.org/abs/2607.10987 · https://arxiv.org/abs/2606.06256 · https://arxiv.org/abs/2609.13161
- https://arxiv.org/abs/2609.10266 · https://arxiv.org/abs/2608.11152 · https://arxiv.org/abs/2609.05565
- https://arxiv.org/abs/2609.06853 · https://arxiv.org/abs/2605.24022 · https://arxiv.org/abs/2603.24000
- https://arxiv.org/abs/2606.12556 · https://arxiv.org/abs/2606.04302 · https://arxiv.org/abs/2604.03143
- https://arxiv.org/abs/2608.15584 · https://arxiv.org/abs/2605.09999 · https://arxiv.org/abs/2412.12488
- https://arxiv.org/abs/2609.16495 · https://arxiv.org/abs/2509.24832 · https://arxiv.org/abs/2410.05004
- https://arxiv.org/abs/2502.09334 · https://arxiv.org/abs/2412.18169

**ACM / IEEE / PMLR / ACL / OpenReview / NeurIPS / ICML**
- https://dl.acm.org/doi/abs/10.1145/3689031.3696086 （Pensieve, EuroSys'25）
- https://dl.acm.org/doi/abs/10.1145/3651890.3672274 （CacheGen, SIGCOMM'24）
- https://dl.acm.org/doi/abs/10.1145/3731569.3764810 （DiffKV, SOSP'25）
- https://dl.acm.org/doi/abs/10.1145/3731569.3764829 （IC-Cache, SOSP'25）
- https://dl.acm.org/doi/10.1145/3731569.3764815 （Aegaeon, SOSP'25）
- https://dl.acm.org/doi/abs/10.1145/3767295.3803570 （eLLM, EuroSys'26）
- https://dl.acm.org/doi/10.1145/3779212.3790236 （MuxWise, ASPLOS'26）
- https://dl.acm.org/doi/10.1145/3779212.3790135 （Bullet, ASPLOS'26）
- https://dl.acm.org/doi/10.1145/3779212.3790206 （QoServe/Niyama, ASPLOS'26）
- https://dl.acm.org/doi/abs/10.1145/3802009 （AlignedServe, SIGMOD'26）
- https://dl.acm.org/doi/abs/10.1145/3802077 （KVDrive, SIGMOD'26）
- https://dl.acm.org/doi/abs/10.1145/3805621.3807658 （管理扩展性悖论, EuroMLSys'26）
- https://dlnext.acm.org/doi/abs/10.14778/3796195.3796214 （OrbitFlow, VLDB'26）
- https://dl.acm.org/doi/full/10.1145/3754448 （ACM CSUR'25 服务综述）
- https://dl.acm.org/doi/abs/10.1145/3676641.3716011 （Past-Future Scheduler, ASPLOS'25）
- https://ieeexplore.ieee.org/document/11329799 · https://ieeexplore.ieee.org/document/11459268 （CXL 相关）
- https://ieeexplore.ieee.org/abstract/document/11408492 （ELORA, HPCA'26）
- https://proceedings.iclr.cc/paper_files/paper/2025/hash/5bc342f48de8264779952fac378f96dc-Abstract-Conference.html （Preble, ICLR'25）
- https://proceedings.neurips.cc/paper_files/paper/2024/hash/724be4472168f31ba1c9ac630f15dec8-Abstract-Conference.html （SGLang, NeurIPS'24）
- https://papers.nips.cc/paper_files/paper/2025/hash/b7971d31a7d5eb0f1eed2f8f6f368195-Abstract-Conference.html （KVFlow, NeurIPS'25）
- https://neurips.cc/virtual/2025/loc/san-diego/poster/116061 （KVLink, NeurIPS'25）
- https://proceedings.mlr.press/v267/hu25j.html · https://icml.cc/virtual/2025/poster/43926 （EPIC, ICML'25）
- https://aclanthology.org/2026.acl-long.859/ （SpecCache, ACL'26）
- https://aclanthology.org/2025.findings-acl.952.pdf （MiniKV, ACL'25）
- https://aclanthology.org/2025.acl-long.1305.pdf （StitchLLM, ACL'25）
- https://aclanthology.org/2025.findings-ijcnlp.25/ （SemShareKV）
- https://openreview.net/forum?id=r3mQiuYKIN · https://openreview.net/forum?id=GgX6dPJx9M · https://openreview.net/forum?id=EB5bgzv4qA · https://openreview.net/forum?id=cJcZKzdwkP （MLSys'26 KV 相关）
- https://mlanthology.org/tmlr/2025/li2025tmlr-survey/ （TMLR'25 综述）

**其他（工业界 / 索引仓库 / 媒体报道）**
- https://github.com/ovg-project/kvcached （Prism 的 balloon 驱动）
- https://github.com/deepseek-ai/open-infra-index （3FS 开源）
- https://github.com/TreeAI-Lab/Awesome-KV-Cache-Management
- https://github.com/byungsoo-oh/ml-systems-papers
- https://github.com/mental2008/awesome-papers
- https://research.adobe.com/publication/cache-craft-managing-chunk-caches-for-efficient-retrieval-augmented-generation/
- https://cds-macau.github.io/publication/conference-paper/ellm/
- https://www.research.ed.ac.uk/en/publications/towards-a-solution-to-the-management-scaling-paradox-in-distribut/
- https://5ujinkang.github.io/IC-Cache/ （IC-Cache 作者主页）
- https://vllm.ai/blog/2026-05-18-pegaflow （vLLM × Novita AI 外部 KV cache，工业实践）
- https://www.sdxcentral.com/news/alibaba-cloud-claims-it-can-reduce-gpu-use-by-82-with-pooling-system/ （Aegaeon 报道）
- https://uchi-jcl.github.io/group-website/publication/cachegen/
