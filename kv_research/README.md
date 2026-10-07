# LLM KV Cache 压缩：算法层研究综述（截至 2026 年 9 月）

> **方法/证据说明**：本文所有条目均通过 arXiv 检索页与摘要页实时抓取核验（截至 2026-09-15），链接在文末统一列出。凡标注「作者自述」的数字，均直接取自论文摘要原文，**未做第三方复现**；凡标注「arXiv 预印本」的条目表示抓取时未见正式会议/期刊页信息（arXiv 的 `Comments` / `Journal ref` 字段）。评审状态以论文自己声明为准，可能存在与官方 proceedings 的出入。
>
> **覆盖范围**：约 120 个方法/系统 + 12 项评测与基准工作，按 6 个家族组织，最后给出「生产环境实际有效」的判断。来源共 154 个 arXiv 条目及官方工程博客/模型卡。

---

## 0. 全景判断（先说结论）

1. **2024–2025 的主线是"在固定 KV 预算下怎么选 token"（eviction/selection）**；2026 年的主线已经转向 **"选 token 这件事本身值不值"**——多篇 2026 论文用受控实验证明注意力打分作为重要性信号非常弱（`TwinKV` 测得 Spearman ρ=−0.004；`Random Attention` 证明在推理负载下纯随机驱逐可匹配最强打分器；`Trust the Mass` 证明最优子集只再补上 2–5% 的差距）。这条"打脸线"是本年度最重要的算法层进展。
2. **真正在生产里稳定落地的是三件事**：FP8/INT8 KV 量化（单指令级、零算法风险）、稀疏注意力 + 分层 KV 缓存（DSA/NSA/Quest 系列 + 显存分层 offload）、以及**架构级**的 KV 削减（MLA / GQA / 线性-全注意力混合）。纯"驱逐式"算法在生产里基本只在**解码阶段**、且**预算不太激进**时才敢用。
3. **推理（long-CoT）负载是对驱逐类方法最不利的场景**：`Hold Onto That Thought` (2512.12008) 指出主流策略多在 prefill 阶段设计，很少在长解码上评估；后续 2026 年一整批工作（`R-KV`、`ThinKV`、`BeaconKV`、`ReasonAlloc`、`Crystal-KV`、`KV-Rescue`）都在补这个洞，且普遍发现**低预算下驱逐会让模型生成更长的思维链**，反而抵消吞吐收益——这是 2026 年最被低估的发现。

---

## 1. KV Cache 驱逐 / Token Dropping

### 1.1 奠基基线（2023–2024）

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **H2O** (Heavy-Hitter Oracle) | NeurIPS 2023 | 用累计注意力质量打分，保留 "heavy hitters" + 近期 token 的平衡；把驱逐表述为动态子模问题并给出理论保证 | 20% 保留率（5×） | 作者自述：OPT-6.7B/30B 上吞吐较 DeepSpeed Zero-Inference / HF Accelerate 提升最高 29×，同等 batch 下时延降低最高 1.9×；仍是所有后续工作的默认基线 |
| **StreamingLLM** | ICLR 2024 | 发现 attention sink：保留最初若干 token + 滑动窗口即可让有限窗口训练的模型外推到无限长度 | 固定窗口（常数内存） | 作者自述：Llama-2/MPT/Falcon/Pythia 上稳定处理 4M+ token，较滑窗重算基线最高 22.2× 加速 |
| **Keyformer** | MLSys 2024 | 观察到 ~90% 注意力权重集中在少数 "key tokens"，设计 score 函数在 KV cache 中只保留这些 token | 未给单一比率 | 作者自述：GPT-J/Cerebras-GPT/MPT 上时延降低 2.1×、token 生成吞吐提升 2.4×，同时保持精度 |
| **SnapKV** | 2024（arXiv，广泛复现） | 用 prompt 末尾的 "observation window" 投票，为每个 head 选出聚簇的重要 KV 位置；training-free | 保留约 1/8 缓存 | 作者自述：16K 输入下生成加速 3.6×、内存效率提升 8.2×；单张 A100-80GB 处理 380K token 上下文，NIAH 近乎无损下降 |
| **RoCo / EasyKV** | arXiv 2024 | 从"重要性打分"和"驱逐范围构造"两个维度审视既有策略，提出基于时序注意力分数 + 鲁棒性度量的驱逐策略 | 未给统一比率 | 作者自述：在 prefill 与自回归解码两个阶段均优于先前策略；同时开源 EasyKV 包 |
| **PyramidKV** | arXiv 2024（v4 2025） | 发现 "Pyramidal Information Funneling"：低层注意力分散、高层聚焦；据此给低层多分配缓存、高层少分配 | 12% 保留率 | 作者自述：LongBench 上 12% 缓存匹配全缓存；0.7% 缓存时 TREC 上较基线 +20.5 分；Llama-3-70B 仅留 128 条即达 NIAH 100.0 |
| **Ada-KV** | **NeurIPS 2025** | 首个 head 级自适应预算分配，给出驱逐前后注意力输出的理论误差上界，可作为插件套在任何 eviction 上 | 预算自适应 | 作者自述：RULER 13 数据集 + LongBench 16 数据集，question-aware 与 agnostic 两种设定下均显著优于均匀预算基线 |
| **SqueezeAttention** | arXiv 2024 | 2D 管理：用自注意力层前后 prompt 表示的余弦相似度衡量层重要性，把层分成两组分配不同 KV 预算，再叠加序列维压缩 | 内存降 30–70% | 作者自述：吞吐最高提升 2.2× |
| **RazorAttention** | arXiv 2024 | 识别 "retrieval heads"（少数需要全上下文的 head）保留完整缓存，其余 head 丢弃远端 token，并引入 "compensation token" 找回被丢信息 | >70% 削减 | 作者自述：性能无可感下降，兼容 FlashAttention，无需训练 |
| **CAKE**（常被称作 "cascading KV eviction"） | ICLR 2025 | 把 KV 驱逐形式化为 "切蛋糕问题"：按空间+时间维度评估层偏好，级联式分配各层缓存，并提出考虑 token 重要性随时间漂移的驱逐指标 | 仅保留 3.2% | 作者自述：LongBench/NeedleBench 上一致优于基线，128K 上下文下解码时延较全缓存加速 >10×（FA2） |
| **DuoAttention** | 2024（arXiv） | 区分 Retrieval Heads（全注意力）与 Streaming Heads（只关注近期+sink），后者用常数长度轻量缓存；用合成数据优化识别 head 类型 | MHA 2.55× / GQA 1.67× | 作者自述：解码加速 2.18×/1.50×，prefill 加速 1.73×/1.63×；与量化结合可在单张 A100 上跑 330 万 token 上下文 |
| **CompressKV** | arXiv 2025 | 不再用全部 GQA head 投票，而是先识别"语义检索头"来决定重要 token；再按层驱逐误差做层自适应预算 | 层自适应 | 作者自述：LongBench 与 NIAH 各预算下一致优于 SOTA |
| **LazyEviction** | arXiv 2025 | 发现 "Token Importance Recurrence"：大量 token 在多个解码步之后重新获得高注意力；用观测窗口 + 延迟驱逐保留这些周期性关键 token | 50%–70% 削减 | 作者自述：长推理任务上精度可比，优于已有压缩基线 |
| **LServe** | **MLSys 2025** | 统一 prefill 与 decode 的结构化稀疏：把一半 head 转成近乎免费的 streaming head，decode 侧用分层 KV page 选择动态裁剪 | 保留常数个 KV page | 作者自述：相对 vLLM prefill 加速最高 2.9×，decode 1.3–2.1×，长上下文精度保持 |
| **CacheCraft / FRC** | arXiv 2026 | 用 LLM 引导的程序演化自动搜索驱逐策略，发现三信号打分器（局部注意力、邻域注意力密度、KV-head 最大显著性）+ chunk 级 top-k | r ≥ 0.75（≥88% 压缩） | 作者自述：RULER 4k/8k 上在单遍 KVPress 基线中每个格子都第一；Llama-4k +15.4 分、Qwen-8k +13.9 分；打分函数贡献 +67.2 分而 chunk 结构只贡献 ~0.1 |

### 1.2 2026 年新方法（及"驱逐是否值得"的质疑）

| 方法 | 状态 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **Hold Onto That Thought**（评测，非方法） | arXiv 2512.12008 (2025-12) | 在长推理任务上系统评测主流压缩策略；提出 decoding-enabled 版 SnapKV | — | 作者自述：非推理模型上**没有单一策略通吃**，性能强依赖数据集类型；推理模型上 **H2O 与 decoding 版 SnapKV 占优**，说明 heavy-hitter 追踪对推理轨迹有用；**低预算驱逐会产出更长的推理链**，形成"省缓存 vs. 增生成"的权衡 |
| **Random Attention** | arXiv 2609.03430 (2026-09) | 保留 prompt，在每个 head 内**均匀随机**驱逐，完全不计算分数 | 无分数、预算驱动 | 作者自述：4 个模型 6 个推理任务上匹配最强先驱逐器，vLLM 部署下吞吐高 32–43%。机理解释：**prompt 是缓存中最脆弱的部分**，多数打分器的差距只是"恰好保住了 prompt"；推理轨迹自身在文本层与 head 层都有冗余可以自我保护 |
| **Trust the Mass / ContourKV** | arXiv 2608.25230 (2026-08) | 在 168,192 条注意力行上穷举约束下的最优子集；用"被丢弃质量"统计构造 training-free 分配器 | 按字节对齐 | 作者自述：**最优子集只弥补到全注意力差距的中位数 2–5%**；且发现强 query-agnostic 方法实际把整份缓存都留在显存里（按 head 掩码存储），只有 ragged per-head 存储才真正省内存；强制单一固定选择的标称预算会掉 14–62 个基准分；ContourKV 在 160 组配对比较中赢 93 输 22 |
| **InertiaKV / Score-Free**（What Matters for Aggressive Decoding-Time KV Eviction?） | **EMNLP 2026 Main** | 指出跨解码步的分数聚合规则（EMA）比打分函数本身更关键；Score-Free 模式只在第一个解码步打一次分然后冻结排序 | — | 作者自述：6 个开源骨干 + LongBench/LongBench-v2/RULER；InertiaKV-Lazy 较全刷新版提升 decode 吞吐 1.34–1.46×；Score-Free 平均质量变化 +0.03 |
| **TwinKV** | arXiv 2608.27128 (2026-08) | 完全不依赖注意力：用"key 是否在上下文中有近重复"作为冗余信号，作为**可组合修复 pass** 与既有策略互换 orphan/redundant donor | 预算不变（提升同预算质量） | 作者自述：留一法探针显示注意力幅度与 token 的因果贡献**无关（ρ=−0.004）**；在 LongBench/LooGLE/RULER + MMLU-Pro 无害对照上与 4 种策略组合，多数配置改善，但对已达天花板的策略帮助有限，few-shot 分类样例上无效 |
| **VaSE** | arXiv 2606.03928 (2026-06) | 两点发现：少数 value 状态幅度异常大，驱逐会触发"重复推理循环"灾难；引入随机性可提升缓存多样性 | 4× | 作者自述：Qwen3 上 6 个推理任务，4× 压缩下平均精度高于同稀疏度的 SOTA 选择式稀疏注意力，比最强驱逐方法高 >4%；支持 FA2、静态内存占用 |
| **BeaconKV** | **ICML 2026** | 发现长时程推理中存在 "Thought Revisiting Tokens"（会回看远处的早期计划）；这些 query 在嵌入空间聚成少数簇，用 "beacon queries" 作为簇代表来预判会被回看的 KV | 最高 5.8× 内存削减 | 作者自述：4 个开源 LRM 上普遍优于已有压缩方法，接近全缓存精度，吞吐提升 >4.3× |
| **ReasonAlloc** | arXiv 2606.11164 (2026-06) | 把解码期 KV 压缩重构为**层级预算分配**：离线层间预分配（作者称 "Reasoning Wave"）+ 在线 head 间实时再分配 | 自适应 | 作者自述：MATH-500/AIME 2024，DeepSeek-R1-Distill-Llama-8B / Qwen-14B / AceReason-14B；小预算（128–512 token）下增益最大，优于 uniform-budget 的 R-KV、SnapKV、Pyramid-RKV；可插拔、开销可忽略 |
| **Crystal-KV** | arXiv 2601.16986 (2026-01) | "answer-first" 原则：把答案偏好映射回 think 阶段注意力图，区分 SlipKV（维持推理流但可能引入误导）与 CrystalKV（真正贡献答案正确性），用 LRU/LFU 变体精确判定失效时机 | 自适应 | 作者自述：达到 SOTA 压缩、显著提升吞吐与响应速度，并在 CoT 上保持甚至提升答案精度 |
| **KV-Rescue** | arXiv 2608.15797 (2026-08) | 把驱逐损失刻画为"信息缺口"而非能力缺口：被驱逐的 7B 与全上下文 1.5B 犯互补错误；用一个轻量全上下文 helper 与主模型**逐步交错**推理，在线熵/可压缩性检测器提前终止退化 | 预算 B=64 | 作者自述：oracle 选择二者答案可恢复 79% 精度差；Qwen2.5-Math 7B/72B 五个数学基准上平均恢复 87% 被驱逐损失的精度，并把基础模型生成 token 减少 43%（抑制 runaway degeneration） |
| **ThinKV** | **ICLR 2026 (Oral)** | 注意力稀疏度揭示 CoT 中不同 "thought" 的重要性差异；按 thought 重要性分配精度（量化）并渐进驱逐次要 thought；扩展 PagedAttention 内核复用被驱逐槽位 | <5% 缓存 | 作者自述：DeepSeek-R1-Distill / GPT-OSS / NVIDIA AceReason 上数学与代码基准近乎无损，吞吐较 SOTA 基线最高 5.8× |
| **R-KV** | arXiv 2025（v4 2026） | 专门针对推理模型中的**冗余 token**；保留约 10% 缓存 | 10%（16% 时自述 105% 全缓存性能） | 作者自述：两个数学推理数据集上持续优于基线，内存节省 90%、吞吐 6.6×。**注意**：`Not All Thoughts Need HBM`（2605.09490）在自己的复现中报告 R-KV 在可比预算下只有 0–32% 精度——生产采用前必须自行验证 |
| **RLKV** | arXiv 2025（v3 2026） | 用 RL 作为探针，直接以真实生成结果为目标发现"对推理一致性至关重要的 head"，这些 head 保留全缓存，其余用常数缓存 | 20–60% 削减 | 作者自述：跨任务/模型近乎无损，60% 削减下端到端加速最高 2.06× |
| **KVP (Learning to Evict)** | **ICML 2026** | 把驱逐重构为 RL 问题：为每个 head 训练轻量 agent，用"未来效用"导出的整体奖励评价排序质量 | 自适应 | 作者自述：两个模型家族，RULER（至 128K）与 OASST2-4k 上显著优于强基线；zero-shot 泛化到 BoolQ/LongBench 段落检索/GovReport，且能外推到更长序列 |
| **Not All Thoughts Need HBM** | arXiv 2605.09490 (2026-05) | 反对"永久驱逐"：把 token 分四层（HBM / DDR / 压缩 / 驱逐），低重要度 token **搬到 CPU 而非销毁**，注意力步前全精度预取回来 | 驱逐率 3% | 作者自述：**精度只取决于永久丢弃的 token 数（驱逐率），而与多少留在 HBM 无关**；GSM8K 保留 91%、MATH-500 71%（仅 3% 驱逐）；14B 规模下与未压缩基线持平（90% vs 86%）同时 HBM 占用减半；传输开销仅 5–7% |
> **其余 2026 年驱逐类工作（同族，未单列）**：`SkipKV`（2512.07993，发现多 batch 设定下 SOTA 驱逐方法因打分不稳 + padding 侵蚀有效预算而失效，改为选择性跳过 KV 生成与存储）、`KARA`（2607.01237，滑窗式压缩解决阈值触发的吞吐反降与"整块被清空"问题）、`ReCo`（2608.04771，用过程奖励协调压缩与生成：高奖励步压缩更狠、低奖励步更松，生成 token 降 37–65%、端到端 2.08–2.35×）、`TAM`（2608.12331，按 CoT 的 thought 分段做自适应预算）、`Neural Garbage Collection`（2604.18002，端到端从结果奖励中学会"忘记"）、`AgentKV`（2609.14872，agentic 负载下未来 query 是 think/act/tool 等阶段的混合，recency 代表会系统性低估未来阶段需要的 key）、`Jacap`（2609.08131，用 Jacobian Information Capacity 刻画非线性 softmax 下的 token 效用）、`ECOKV`（2609.06663，指出余弦相似度多样性度量因各向异性而失效）、`Probabilistic Interpretation of KV Eviction`（2608.28293，证明该问题计算困难并给出概率框架）、`MaskKV`（2510.09309，面向 dLLM 的双向注意力缓存驱逐）。

---

## 2. KV Cache 量化与低位压缩

### 2.1 奠基基线

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **KIVI** | **ICML 2024** | 关键结论：**key cache 应按 channel 量化（per-channel），value cache 应按 token 量化（per-token）**；tuning-free 2-bit | 峰值内存 2.6× 少 | 作者自述：Llama/Falcon/Mistral 上质量几乎不变；batch 可增大 4×，吞吐 2.35–3.47× |
| **KVQuant** | **NeurIPS 2024** | 四件套：(i) per-channel key 量化；(ii) **Pre-RoPE** key 量化以规避 RoPE 对分布的影响；(iii) 逐层敏感度加权的非均匀数据类型；(iv) per-vector dense-and-sparse 离群值处理 | 3-bit | 作者自述：Wikitext-2/C4 上 PPL 退化 <0.1；LLaMA-7B 单张 A100-80GB 支持 1M 上下文、8 卡 10M；自研 CUDA kernel 相对 fp16 最高 ~1.7× |
| **QAQ** | arXiv 2024 | 理论证明 key 与 value 对量化的敏感度不同，分别设计非均匀量化策略 + 专用离群值处理 + attention-aware 方案 | 最高 10× | 作者自述：模型性能影响可忽略。（该工作另有 ICCV 2025 Workshop 版本） |
| **MiKV** | arXiv 2024 | 关键观察：**把被驱逐的 KV 以低精度保留下来，能大幅恢复"驱逐造成"的退化**；重要 KV 保留高精度，被驱逐 KV 存低精度 | 高压缩率 | 作者自述：压缩率-性能折衷 SOTA；同时揭示纯驱逐会导致安全越狱、幻觉与上下文丢失 |
| **SKVQ** | arXiv 2024 | 重排 KV channel 提升量化组内相似度 + 组级裁剪动态量化；最近窗口 token 保持高精度 | 2-bit K / 1.5-bit V | 作者自述：精度损失极小；7B 模型在 80GB GPU 上支持 1M 上下文，解码最高 7× |
| **PolarQuant** | arXiv 2025 | 随机预条件 + 极坐标变换后量化角度；角度分布紧致且有解析形式，**免去显式归一化**从而省掉 per-block 量化参数开销 | >4.2× | 作者自述：长上下文评测中质量优于 SOTA |
| **TaDA** | ACL 2025 (industry) | 量化精度按层误差敏感度自适应 + mean-centering 消除离群值特殊处理 | 内存降至基线 27% | 作者自述：多模型多上下文长度上精度大幅优于常规方法，且无需单独处理离群元素 |
| **SVDq** | arXiv 2025 | 对 K cache 做 SVD 转潜在通道（值衰减快）+ 重要性感知的混合精度量化 | 1.25-bit / 410× key cache | 作者自述：极高 key cache 压缩率下保持可用质量 |
| **MiniKV** | arXiv 2024（v3 2025） | 2-bit 层差异化 KV 缓存 + 与 FlashAttention 兼容的专用 CUDA kernel | 86% 压缩 | 作者自述：恢复 >98.5% 精度，系统性能优于 SOTA |
| **TurboQuant** | arXiv 2025 | 随机旋转 → 坐标服从集中 Beta 分布 → 逐坐标最优标量量化；两阶段（MSE 量化 + 残差 1-bit QJL）得到无偏内积估计 | 3.5 bit 质量中性 | 作者自述：**3.5 bit/channel 绝对质量中性，2.5 bit 轻微退化**；并给出信息论下界证明（差距 ≈2.7 常数因子）。这是目前被 2026 年多个工作（PIVOT/UltraQuant/Self-Indexing Attention）当作事实锚点的量化方案 |
| **AQUA-KV** ("Cache Me If You Must") | **ICML 2025** | 利用层间 K/V 的相互依赖，用紧凑 adapter 预测可预测部分，"最优地"压缩不可预测的残差 | 2–2.5 bit/value | 作者自述：Llama 3.2 上近无损，PPL 与 LongBench 相对误差 <1%；one-shot，单卡 1–6 小时标定（70B 亦可） |
| **PM-KVQ** | **ICLR 2026** | 面向 long-CoT：(1) 渐进降位宽 + block 级内存分配以降低累积量化误差；(2) 位置插值标定，用短标定数据逼近长上下文分布 | 混合精度 | 作者自述：7B–70B long-CoT 上同内存预算下推理基准最多 +8%，吞吐 2.73–5.18× |
| **MixKVQ** | arXiv 2025-12 | 指出低位 KV 量化在复杂推理上退化严重：需同时考虑 key channel 的**内在量化难度**与**与 query 的相关性**；用轻量 query-aware 算法挑出需高精度的关键 channel | 混合精度 | 作者自述：显著优于已有低位方法，在内存大幅下降时达到全精度基线水平 |

### 2.2 2025–2026 新一代（通用量化 / 极致低位 / 系统级）

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **OSCAR** | arXiv 2026-05 | 离线估计 attention-aware 协方差，导出固定旋转与裁剪阈值，使 INT2 对齐"注意力真正消费的结构"；配可部署 INT2 attention kernel，兼容 paged KV | ~8× 内存 | 作者自述：Qwen3-4B-Thinking-2507 / Qwen3-8B 上把 BF16 差距压到 3.78 / 1.42 分（朴素旋转 INT2 直接崩塌到接近 0）；可扩到 Qwen3-32B 与 GLM-4.7 (358B)；RULER-NIAH 到 128K 稳健；吞吐最高 7×、batch=1 解码最高 3× |
| **SPECTRA** | arXiv 2026-08 | 把缓存旋转到由其自身统计导出的坐标系以去相关，然后把比特预算集中到少数承载信息的通道，突破 "2-bit 悬崖" | 4× 近无损 / 8× 有竞争力 / 最高 12× | 作者自述：Llama-3.1-8B、Qwen2.5-7B 长上下文基准 |
| **NOVA-KV** (Spend Bits Where Queries Look) | arXiv 2026-08 | 把 KV 量化形式化为**变换编码**问题，失真定义为注意力乘积误差；推导 key/value 的闭式最优变换（key 最优变换非正交，满足广义 Parseval） | 2 bit/element | 作者自述：在同吞吐下恢复了标量量化方法丢失的大部分长上下文检索精度 |
| **OptR** | arXiv 2026-08 | 指出既有旋转法只优化缓存统计或 pre-readout 代理误差；改为最小化 **post-W_O** 注意力输出误差，分解为 key/value 两项并学习 per-head 正交修正 | INT2 | 作者自述：3 模型 5 个推理/代码基准上同时提升 QuaRot 与 OSCAR，并增强长上下文检索；保持 paged 格式 |
| **Codec-Gauge** | arXiv 2026-07 | 训练后的"缓存坐标层"：学习小的正交 channel 变换，用 DCT 谱心 + 平滑码率代理把 KV 能量集中到低频布局 | 受后端决定 | 作者自述：用实测字节数与滚动压缩指标评价 |
| **JoLT** | arXiv 2026-07 | 把某层缓存视为三阶张量（heads × tokens × features），用 Tucker 秩 + 旋转残差的联合 Lagrangian 分配 | 近无损 | 作者自述：long context 下缓存（而非权重）决定吞吐上限 |
| **eOptShrinkQ** | arXiv 2026-05 | 把 KV 分解为低秩"共享上下文" + 满秩 per-token 残差（尖峰随机矩阵模型）；最优奇异值收缩抽取共享结构，残差用 TurboQuant 量化 | — | 作者自述：恢复标量量化所需的各向同性 |
| **HyperQuant** | arXiv 2026-06 | Hadamard + 最优 packing + 熵 Rice 编码的统一 PTQ 流水线（权重与 KV） | KV ~3.79× @4bps | 作者自述：优于 TurboQuant、OCTOPUS 直到 1.7 bps；H100 上近无损 |
| **RaBitQCache** | **ICML 2026** | 用随机旋转二值量化 + 高吞吐 binary-INT4 算术来估算注意力权重；代理分是无偏估计且有误差界，据此做**自适应 Top-p** 检索而非固定 Top-k | 自适应 token 预算 | 作者自述：显著加速并减少内存 I/O，质量保持 |
| **UltraQuant** | EMNLP 2026 Industry | 面向 context-heavy agent 的 4-bit KV：TurboQuant 式旋转+码本、非对称 K/V、Walsh-Hadamard 旋转、去 QJL、block-scale；AMD CDNA4 上用 FP8 query + FP4 KV + UE8M0 group scale 与原生 scaled-MFMA | 半字节（相对 BF16） | 作者自述：生产 Claude Code trace 的 adaptive-SLO 重放下，合格请求吞吐达 BF16 的 2.71×（MiniMax-M2.5）/ 4.38×（Qwen3-235B），匹配或超过硬件 FP8 KV 而只用一半字节 |
| **WitCert** | arXiv 2026-07 | 给已部署系统一个**可证明可靠的运行时"KV 量化 DTrace"**：逐 (layer, head, step) 的 attention 全变差上界（确定性 band-norm-witness + 概率证书，Lean 4 机检）；风险驱动的门控修复 | 运行时 | 作者自述：raw-cast fp8 在困难 RULER 任务上从 22.8 恢复到 79.7 且与未压缩差距被配对检验界定在 [+0.0,+0.8]；28 层扫描显示**没有单层的污染能单独造成损失（0/28）**，激进方案靠跨层误差抵消存活；同内存下 INT8 缓存可多服务 1.88× KV token |
| **RoPE-Aware Bit Allocation (Block-GTQ)** | arXiv 2026-06 | 在 RoPE 下 key 对注意力 logit 的贡献分解为二维频率块之和，把 key 量化变成**块级比特分配**问题，按边际收益贪心分配整数位宽 | 匹配 K/V 比特预算 | 作者自述：同预算下优于平坦比特分配 |
| **Don't Waste Bits!** | **CVPR 2026** | 借鉴 Huffman 变长编码：用 token 频次/质量分/注意力方差/熵不确定性等轻量特征训练控制器，在 {2,4,8,FP16} 间动态选择精度 | 自适应 | 作者自述：SmolLM-360M @HellaSwag，相对静态 KV 量化解码时延降低 17.75%、精度 +7.60 分，距 FP16 仅 0.30 分 |
| **Interface-Aware KV Quantization** | **ICCAD 2026** | 面向片上 NVM：随机旋转 + per-vector 归一化让所有坐标同范围，全缓存共享一套 key/value 码本；码本阈值一次烧录进读出转换器 | 4-bit | 作者自述：**KIVI 与 KVQuant 在软件上更准**；本文优势在内存接口——KV 读能耗比二者低 3.1–3.6×，元数据开销比 KIVI 低 8×（KIVI 的 per-group 元数据会让缓存变大 ~25%） |
| **Lynx** | arXiv 2026-07 | 面向 PD 分离的 KV 传输：**渐进式投机量化**——不同比特对精度贡献不均，不等整份 KV 到齐即可开始解码 | 传输量降低 | 作者自述：同时压低网络暴露时延与保持精度 |
| **Alignment Collapse Under KV Quantization**（评测） | arXiv 2026-06 | 11 个指令模型、5 个基准、1,894 prompt 上评估量化对**安全对齐**的影响 | — | 作者自述：Mistral-7B 在仅 1.03× PPL 时丢失 15.2% 的拒答；**不存在通用的安全位宽**，存在标准指标看不见的模型特异相变；根因是几何性的（安全特征占据特定子空间） |
| **Quality Recovery for Quantized KV Caches** | arXiv 2026-09 | 固定量化器，把全精度缓存模型的行为蒸馏进低秩 Q/K/V 投影更新，学生模型执行真实打包的增量缓存 | 4-bit | 作者自述：三 seed 下 TinyLlama-1.1B 恢复 54.24%±2.47% 的 PPL 差距，Gemma-4-12B 恢复 75.96%±4.04%；同 Llama-3.1-8B 冻结基座上 KIVI K2V2 恢复 60.42%、KVarN K4V2 恢复 37.61%，并保持 180 例联想检索 |
| **KV Cache Quantization for Self-Forcing Video**（评测） | arXiv 2026-03 | 33 种量化/缓存策略、610 条 prompt 级观测、63 条基准级摘要的实证研究 | 5.42–5.49× | 作者自述：最强实用区间是 FlowCache 式 soft-prune INT4，峰值 VRAM 从 19.28 GB 降到 ~11.7 GB；**保真度最高的方法（PRQ_INT4、QUAROT_KV_INT4）反而不是最佳部署选择**；**标称压缩率不足以说明问题**——部分方法缩小了 KV 存储但仍超过 BF16 峰值显存 |

---

## 3. 注意力层结构性削减（架构级）

### 3.1 KV 头共享与潜在压缩

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **MQA / GQA** | 2019 / 2023（EMNLP） | 多个 query head 共享一个 KV head，直接削减 head 维度上的缓存 | GQA 常见 4–8× | 事实标准：GQA 已是主流开源模型默认配置 |
| **MLA** (Multi-head Latent Attention) | **DeepSeek-V2**，arXiv 2024 | 把 K/V 压成低维 latent 向量并缓存 latent，推理时再投影展开 | KV cache 减少 **93.3%** | 作者自述：相对 DeepSeek 67B，训练成本省 42.5%，最大生成吞吐提升 5.76×。是现代高性价比长上下文模型的架构基线 |
| **CLA** (Cross-Layer Attention) | arXiv 2024 | 把 MQA 再推一步：**相邻层之间也共享 KV head** | 相对 MQA 再 2× | 作者自述：从零训练 1B/3B，精度与未改动的 MQA 几乎相同，形成对 MQA 内存/精度折衷的 Pareto 改进 |
| **MLKV** | arXiv 2024 | 跨 transformer 层共享 KV（比 MQA/GQA 更激进的多层共享） | 相对 MQA 最多 6× | 作者自述：Pythia-160M uptrain 变体上内存显著下降、性能损失极小 |
| **YOCO** | arXiv 2024 | decoder-decoder 架构：self-decoder 编码全局 KV **只缓存一次**，cross-decoder 通过 cross-attention 复用；prefill 可提前退出而不改输出 | 只缓存一次（近似常数层数） | 作者自述：扩展模型规模/训练 token 均优于同规模 Transformer；扩展到 1M 上下文近乎完美的针检索；内存、prefill 延迟、吞吐改善数个数量级 |
| **Layer-Condensed KV Cache** | **ACL 2024** | 只计算并缓存少数层的 K/V | 吞吐最高 26× | 作者自述：语言建模与下游任务性能有竞争力，且与其它显存节省技术正交 |
| **TransMLA** | arXiv 2025 | 把已有 GQA 模型**事后转换**为 MLA 结构 | 依 GQA→MLA 比例 | 作者自述：让 MLA 可应用于任何 Transformer LLM |
| **Thin Keys, Full Values** | arXiv 2026-03 | 主张 selection（Q·K 产生标量权重）只需 O(log N) 维度而 value transfer 需要高维；对 W_K 做截断 SVD，把 B^T 吸收进 W_Q（query 从不缓存，故零成本） | key cache 75% 节省 / 组合最高 16× | 作者自述：7B 从零训练 r=d/4 时 PPL 9.24 vs 9.25、参数少 12%、训练快 8%；已有模型 SVD + QK 微调（3 epoch，<1% 预训练数据）达 75% key cache 节省、约 2% 质量代价；128K 上下文每用户省 25 GB，同硬件并发用户多约 60% |
| **Variable-Width Transformers** | arXiv 2026-06 | 非均匀宽度分配（×-shape：首尾宽、中间窄），参数自由的残差重缩放 | KV 缓存/IO 降 15% | 作者自述：200M–3B 上优于参数匹配的均匀基线；FLOPs 减 22% |

### 3.2 Attention Sink / 分层预算

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **Attention Sink 机制研究** | **ICLR 2025 Spotlight** | 系统研究 sink 的成因：在充分数据上有效优化后出现；sink 位置与损失函数和数据分布高度相关；sink 更像 **key bias**，存储额外注意力分数，不贡献 value 计算 | — | 作者自述：把 softmax 换成 sigmoid 等非归一化注意力后，1B 规模内不再出现 attention sink。**这直接决定了后续 eviction 方法"必须保住 sink token"的工程做法** |
| **StreamingLLM** | ICLR 2024 | 见 §1.1 | 常数内存 | 见 §1.1 |
| **DuoAttention** | arXiv 2024 | 见 §1.1；本质是"分层预算"最成功的落地形态 | MHA 2.55× / GQA 1.67× | 见 §1.1 |
| **CAKE / SqueezeAttention / PyramidKV / Ada-KV** | 见 §1.1 | 层/头维度的非均匀预算分配 | 见 §1.1 | 见 §1.1 |
| **RippleKV** | arXiv 2026-08 | 质疑"层深/注意力统计/表示变化"这些代理：改为**独立注入 norm-adaptive 扰动到每层 value cache，测量输出端 KL 散度**，得到不随深度单调的敏感度剖面，再经指数映射转为层预算乘子 | 同预算更优 | 作者自述：LongBench 上在匹配缓存预算下取得最高平均表现 |
| **PolyKV** | arXiv 2026-06 | 层内**同时**做"策略选择 + 预算分配"：按层信号把每层路由到合适的压缩策略，并在总预算下做非均匀分配 | 平均 512 token | 作者自述：LLaMA-3.1-8B / Qwen3-8B 上恢复 54.5% / 25.7% 的 FullKV 差距；128–1024 预算扫描中较最强单策略基线一致提升 1.7%–6.4% |
| **HeadWiseKV** | arXiv 2026-09 | 针对**混合模型**：只压缩残余的 global attention KV，保留原生 local/recurrent/linear 路径；给每个物理 KV head 静态多级历史窗口（可预测的缓存需求）；建模为受限 operational rate-distortion | 峰值显存 −8.59% @112K | 作者自述：4 个混合长上下文模型上 RULER 与 LoCoMo 接近 Full-KV；Qwen3.6-27B 上把最大已验证成功上下文从 114K 扩到 161K |
| **GraceKV** | arXiv 2026-08 | 把压缩当作**全局资源分配**：每 (layer, KV head, slot) 是原子单元，构建 prototype 树，叶=token 级 KV、内部节点=单 prototype 覆盖子树；所有候选动作全局竞争同一个缓存预算，在"分辨率"与"覆盖度"之间权衡 | 最高 128× | 作者自述：32 个设定中 24 个排第一，无需额外训练，全流程在 GPU 上 |
| **MoE-nD** | arXiv 2026-04 | 指出既有压缩方法各自只作用于四维 KV 张量的一个轴（序列/精度/head 维/层），且对所有层用同一配方；改为 per-layer MoE 路由到各自的 (eviction-ratio, K-bits, V-bits) 三元组 | 全局内存预算 | 作者自述：不同层对每种压缩操作的响应差异很大，逐层最优组合远离均匀配方 |

### 3.3 混合 / 线性注意力

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **Mamba** | arXiv 2023 | 选择性 SSM，无注意力、线性时间；把上下文压进固定大小的递归状态 | 常数状态 | 作者自述：推理吞吐比 Transformer 高 5×，序列长度线性扩展；Mamba-3B 超过同规模 Transformer 并匹配 2× 规模 |
| **Mamba-2 / SSD** | **ICML 2024** | 提出 state space duality 框架，把 SSM 与注意力变体通过半可分矩阵分解联系起来；核心层比 Mamba 快 2–8× | 常数状态 | 作者自述：语言建模上持续与 Transformer 有竞争力 |
| **Jamba** | arXiv 2024 | Transformer 层与 Mamba 层交错 + 部分层加 MoE | 大幅小于纯 Transformer | 作者自述：单张 80GB GPU 可容纳；256K 上下文；在标准基准与长上下文评测上 SOTA |
| **Infini-attention** | arXiv 2024 | 在单个 Transformer block 内同时做 masked local attention 与 long-term linear attention（压缩记忆） | 有界内存 | 作者自述：1B/8B 上通过 1M 序列 passkey 检索与 500K 书籍摘要任务 |
| **Qwen3-Next 式混合注意力** | 模型/工程（2025–2026） | Gated DeltaNet（线性注意力）与 Full Attention 逐层交错，配合高稀疏 MoE 与多 token 预测；vLLM 用 hybrid KV cache manager（Jenga 式两级分配器）自动调"逻辑 block size"让线性层状态与全注意力 KV 占用相同物理显存，避免碎片 | 大幅度（全注意力层占比很低） | 工程侧事实：vLLM 官方博客描述 80B-A3B 每 token 仅激活 3B 参数、支持 65K+ 上下文；Triton kernel 来自 Flash Linear Attention，默认开启 CUDA graph 以抵消 kernel 启动开销 |
| **GLIDE** | arXiv 2026-06 | 层间异构：**浅层对移除 softmax 高度敏感，深层冗余可被线性替代**；每层在高效线性递归与可变大小 softmax 窗口之间自适应平衡 | 非均匀压缩 softmax 足迹 | 作者自述：在长上下文生成上取得更优的性能-效率折衷而不损质量 |
| **DeltaLog** | arXiv 2026-08 | 线性注意力解码时不必每步物化并写回完整递归状态：表示为 dense base state + 有界近期更新日志，多数步只追加紧凑因子，周期性合并 | 语义不变 | 作者自述：GDN/KDA/RWKV6 上递归状态更新 kernel 加速最高 1.86×，写流量降最高 7.83×，端到端 1.05–1.20× |
| **DASC** | arXiv 2026-08 | 分析 GDN 与 KDA 的衰减结构，发现不同 head/channel 的"**retention horizon**"差异巨大；据此挑出长时程状态单元打包成 ragged checkpoint 布局，并在 TP rank 间均衡 | KDA 递归状态 checkpoint 2.63× | 作者自述：Kimi-Linear 上保守配置接近全缓存；固定 checkpoint 内存预算下平均 TTFT 降 42.6%、输入吞吐 +68.4%；更大压缩率下用 suffix refresh 找回精度（代价是额外重算）。Qwen+GDN 呈类似趋势 |
| **Tail-Replay / Jenga 系列工程** | arXiv 2026-08 / 2025-03 | 解决混合模型 prefix caching 的"线性注意力诅咒"（递归状态无法像 KV 一样按前缀切分复用）；Jenga 用 LCM 两级分配器管理异构 embedding 尺寸 | — | Jenga 作者自述：GPU 内存利用率最高 +79.6%，服务吞吐最高 4.92×（平均 1.80×） |

---

## 4. 稀疏 / 动态注意力（减少 KV cache 读取）

> **这一族对内存故事的改变**：驱逐类方法改的是 **KV 缓存占多少显存（capacity）**；稀疏注意力改的是 **每个解码步读多少字节（bandwidth）**，但**通常不改变缓存本身的 O(N) 容量**——全历史仍必须留在可寻址的存储里。这正是 2026 年一批系统工作（HiSparse / OasisKV / SAC / ESS）出现的根本原因：**把 top-k 稀疏与分层存储（HBM + host + CXL/远端）组合，才能同时拿到带宽与容量**。

| 方法 | 会议/年份 | 核心机制 | 压缩/加速 | 报告的效果与代价 |
|---|---|---|---|---|
| **Quest** | **ICML 2024** | query-aware 的 page 选择：为每个 KV page 维护 K 的最小/最大值，用当前 query 估计 page 重要度，只加载 Top-K page | — | 作者自述：自注意力最高 2.23× 加速，推理时延降低 7.03×，长依赖任务精度损失可忽略 |
| **SeerAttention** | arXiv 2024（v4 2025） | 受 MoE gating 启发，给注意力加可学习 gate：对 Q/K 沿序列维池化后经线性层相乘得到 block 级门控分数；配合 block-sparse FlashAttention kernel，用轻量自蒸馏训练 | 块级稀疏 | 作者自述：长上下文 prefill 上精度与延迟均优于先前方法 |
| **NSA** (Native Sparse Attention) | arXiv 2025（DeepSeek × 北大，**ACL 2025 最佳论文**） | 动态分层稀疏：粗粒度 token 压缩 + 细粒度 token 选择，兼顾全局感知与局部精度；算法与硬件对齐（算术强度平衡），支持端到端训练 | 64K 序列大幅加速 | 作者自述：NSA 预训练模型在通用基准、长上下文任务、指令推理上**维持或超过全注意力**；在 64K 上 decoding/forward/backward 均有大幅加速 |
| **MoBA** (Mixture of Block Attention) | arXiv 2025（Moonshot） | 把 MoE 原则用到注意力：不预设 sink/窗口等结构偏置，让模型自己决定关注哪些 block；可在全注意力与稀疏注意力之间无缝切换 | 稀疏可调 | 作者自述：已部署用于支持 Kimi 的长上下文请求 |
| **DSA** (DeepSeek Sparse Attention) | DeepSeek-V3.2-Exp，2025-09 | 在 MLA 之上加 **Lightning Indexer**（学习式打分投影over compressed keys），每 query 选 top-k，稀疏注意力 kernel 只读这些位置 | 依 top-k 设定 | 生产事实：MLA 保留，KV 读取量由 top-k 决定。**新的瓶颈转移到 indexer 本身**——它仍要为单位置打分，带来 O(L²) per layer 的开销（见 `PIVOT`、`StreamIndex`）。第三方复现研究（2512.03494）报告精确 Top-k Decoding 在 HELMET / LongBench v2 上可媲美甚至超过全注意力，且训练-推理一致性很关键 |
| **CSA / HCA（DeepSeek-V4 混合注意力）** | DeepSeek-V4 技术报告，arXiv 2606.19348 (2026-04) | **Compressed Sparse Attention (CSA) + Heavily Compressed Attention (HCA)** 的混合注意力架构，配合 Manifold-Constrained Hyper-Connections 与 Muon 优化器 | 10% KV cache | 作者自述：百万 token 设定下，DeepSeek-V4-Pro 只需 DeepSeek-V3.2 的 27% 单 token 推理 FLOPs 与 **10% KV cache**；Pro 1.6T(49B激活) / Flash 284B(13B激活)，均支持 1M 上下文，32T+ token 预训练 |
| **MiniMax Sparse Attention (MSA)** | arXiv 2606.13392 (2026-06) | 建在 GQA 上的 blockwise 稀疏：轻量 Index Branch 给 KV block 打分并**为每个 GQA group 独立选 Top-k**，Main Branch 只对选中 block 做精确块稀疏注意力；配套 exp-free Top-k 与 KV-outer 稀疏注意力 kernel | 1M 上下文每 token 注意力计算降 28.4× | 作者自述：109B 原生多模态模型上与 GQA 表现持平；H800 上 prefill 14.2× / decoding 7.6× 墙钟加速；kernel 已开源，生产级模型已发布 |
| **GLM-5 / GLM-5.1 式索引** | 模型（2026） | 模型卡显示为 `GlmMoeDsaModel`，即 DSA 式稀疏注意力 + MoE，配 IndexCache | 依 top-k | 第三方系统工作（`PIVOT` 2607.24593）报告：在 DeepSeek-V3.2 与 **GLM-5.1** 上，训练-free 的 PIVOT 在 LongBench/RULER 上匹配 dense indexer 精度，同时 indexer 加速最高 4×、长上下文端到端时延降最高 1.6× |
| **PIVOT** | arXiv 2026-07 | 观察到相邻 query 的 top-k 高度重叠、indexer 分数沿 key 轴长尾；用**一次共享的全前缀扫描**（proxy query）为整组 query 生成候选集，再各选 top-k（Reuse / Refine 两变体） | indexer 4× | 见上 |
| **StreamIndex** | arXiv 2026-05 | CSA 的 Triton 实现：分块 partition-merge top-k 驱动，**永不物化** [B,S,H_I,T] 的 FP32 分数张量 | 峰值 HBM 6.21 GB | 作者自述：V4-Flash 维度 S=65,536 时物化路径 OOM，StreamIndex 可跑到 S=1,048,576（32× 区间扩展）；recall 与物化真值位精确，三个设计空间扫描中最小 recall ≥0.9980；与 TileLang 注意力 kernel 组合在 S=262,144 时 1.97 s / 18.56 GB |
| **HiSparse** | arXiv 2026-08 | 精确、indexer-agnostic 的分层 KV：全历史放 host memory，GPU 只保留固定大小缓存；融合 CUDA kernel 在 decode graph 内做命中检测/LRU 替换/H2D 取数 | 峰值吞吐最高 4.7× | 作者自述：**已合入上游 SGLang**；在 DSA、NSA、Quest 三个稀疏族上于 H200/B200/GH200 验证；no-IO oracle 显示解析机制本身无额外 per-token 成本，代价只在 host-device IO |
| **OasisKV** | arXiv 2026-08 | 用投机解码 draft 出的 lookahead token 提前预测下一步需要哪些 KV block，把它们从更高容量层预取到 HBM | 2,048 token KV 预算 | 作者自述：lookahead 预测足够准，2,048 预算下精度在 full attention 的 0.7 分以内；推理负载上较 dense vLLM 1.69×（精度损失 0.1 分），多卡长上下文最高 2.1×；PD 分离下每请求少 6.5–9.7× KV |
| **SAC** | arXiv 2026-06 | 首个面向**稀疏注意力模型**的分层 KV 服务系统（用 CXL）：传统 RDMA 方案会把整个 prefix 拉回本地，而稀疏模型解码时只有一小部分 KV 活跃 | — | 作者自述：解决"只活跃一小部分却传全量"的严重传输瓶颈 |
| **ESS** | arXiv 2025-12 | 针对 DeepSeek-V3.2-Exp 的 offload 中心化 Latent-Cache 管理：选择性把 latent cache 卸载到 CPU，只保留延迟关键部分在 GPU | — | 作者自述：高保真模拟下 32K 上下文吞吐 +69.4%，128K 最高 +123% |
| **Self-Indexing Attention** | arXiv 2026-08 | 共享"变换域符号-幅度"表示：**key 的符号位即 1-bit 索引**，可用于 prefill 分组选择与 decode 检索，且与外部 KV 压缩兼容、无需额外 indexer 元数据 | 5% 注意力密度 | 作者自述：LongBench/RULER 上接近 dense；prefill 加速最高 6.1×、decode 注意力算子 10.3×；与 TurboQuant 及 DeepSeekV4-Flash 兼容 |
| **Declarative Attention (DA)** | arXiv 2026-09 | 让模型在 CoT 里**声明**它要看哪里（`<global>`/`<focus>`/`<local>`），推理引擎把这些声明当 tool call 解析并跳过大部分 KV 读取 | decode 期被读 token 减少 52.0% / 31.1% | 作者自述：zero-shot，15 个长上下文任务，Gemma-4-31B / Qwen-3.6-27B 上精度仅降 1.27pp / 2.75pp，且随规模增大而缩小 |
| **SpotAttention** | arXiv 2026-06 | 给冻结的预训练 transformer 挂一个轻量选择器，用 KL 蒸馏学习其注意力分布；因是标定好的分布，可用 dual top-p 直接读出每 query 每层的预算 | — | 作者自述：Qwen3(4B–32B) 与 Qwen3.5(混合，4B–9B) 上 128K（训练长度 8×）仍匹配 dense 精度；L=128K decode 比 FlashAttention 快 3.9×、比最强 training-free 基线 Twilight 快 1.8×；选择器 K 缓存量化为 INT4/FP4 可再缩 3.5× 且零精度损失 |
| **Augmenting Attention with Exponentially Decaying Memory** | arXiv 2026-05 | 在注意力上加指数衰减记忆（RAT+），使推理期可以灵活做 dilated attention，从而改善 query-aware 稀疏推断 | — | 作者自述：Quest、MoBA、SnapKV 在 8 个 NIAH 任务、各稀疏预算下一致受益；在 OLMo2-7B 上继续预训练 10B token 验证 |
| **NOVA / FlashMemory-LSA 等第三方变体** | arXiv 2026-06 | 用 Neural Memory Indexer 主动预测未来上下文需求，只保留 query-critical KV chunk 在 GPU | — | 作者自述：backbone-free 解耦训练策略 |

---

## 5. KV Cache 合并 / 结构压缩 / 低秩

| 方法 | 会议/年份 | 核心机制 | 压缩率 | 报告的效果与代价 |
|---|---|---|---|---|
| **MiniCache** | arXiv 2024 | 观察到中深层相邻层 KV 状态高度相似；把状态解耦为幅度与方向，方向做插值而长度保持不变；对高度不同的状态对用 token retention 策略不合并 | 4-bit 下最高 5.02× | 作者自述：ShareGPT 上 LLaMA-2-7B，吞吐提升约 5×，显存较 FP16 全缓存降 41%，近无损；training-free，与量化/稀疏互补 |
| **KeepKV** | arXiv 2025（v2 2025-11） | 指出合并策略会引入注意力分布不一致；用 Electoral Votes 机制记录合并历史并自适应调整注意力分数，配合 **Zero Inference-Perturbation Merging** 补偿注意力损失，给出单步无损与多步误差界 | 10% 预算 | 作者自述：>2× 推理吞吐提升，10% KV 预算下仍保持优越生成质量 |
| **DMC / KVMerger** | arXiv 2025 | 基于 key 相似度做 token 合并的代表工作；KVMerger 用高斯核权重 `w_j = exp(−‖k_j−k_c‖²/2σ²)/Σ` 对合并组做加权 | — | 该方向在 2026 年被大量后续工作引用（KVSculpt、SemantiCache、SelKV 都以其为对照基线）。**注**：本轮检索未能抓到 DMC/KVMerger 的原始条目页，故此处只给出机制层面的转述，比率与精度数字请以原文为准 |
| **KVCompose** | arXiv 2025-09 | 用 attention-guided、layer-adaptive 的 **composite token**：按 head 独立选 token 后对齐成尊重统一缓存结构的复合 token；全局分配机制跨层调整保留预算 | — | 作者自述：与标准推理管线完全兼容（这是它相对于 per-head 可变布局方案的核心优势），一致优于结构化与半结构化方法 |
| **KVSculpt** | arXiv 2026-03 | 跳出"选择或合并原始 pair"的谱系：直接在连续嵌入空间**优化一组更少的、无约束的 KV pair** 去保持每层注意力行为；keys 用 L-BFGS 优化，values 闭式最小二乘求解，交替进行；另加自适应预算分配（用一次廉价 pilot 压缩按难度重分配） | r ∈ {0.3,0.5,0.7} | 作者自述：Qwen2.5-1.5B-Instruct / 2048 上下文下，KL 散度比 Select+Fit 低 3.5–4.1×；自适应分配再带来 1.3× KL 降低且无额外推理成本；分析显示压缩难度极不均匀——层间 pilot MSE 差 100×，同层两个 KV head 差 467× |
| **SelKV** | arXiv 2026-07 | 两个组件：(1) soft cosine gate 按 value 相似度自适应决定合并/丢弃；(2) **attention-ratio 补偿**——用 prefill 注意力统计导出解码期 logit bias，修正合并导致的 softmax 质量错配（作者称为 "attention sag"） | 25% 保留 | 作者自述：LongBench 16 个英文数据集上表现强；在 GQA 模型上近乎无损；在多文档 QA 上甚至超过全缓存基线；100k 上下文下解码加速 3.3× |
| **SemantiCache** | arXiv 2026-03 | 按分隔符切成语义连贯 chunk，chunk 内用 Greedy Seed-Based Clustering 聚成语义核心，再用 Proportional Attention 重新平衡被合并 token 的注意力贡献 | — | 作者自述：解码阶段加速最高 2.61×，内存大幅下降，性能与原模型可比 |
| **ResKV** | arXiv 2026-07 | 观察到被驱逐 token 的信息可表述为 **softmax 分子与分母上的残差统计**；把固定预算分为"精确主缓存" + "紧凑残差缓存"，让残差与主缓存参与同一次 softmax 归一化（而非事后修正） | 固定预算 | 作者自述：LongBench 与 RULER、query-aware 与 agnostic、多骨干多预算下广泛优于同预算基线，并保持峰值内存与长上下文 decode 吞吐 |
| **PuzzleKV** | arXiv 2026-08 | 把每个 head 的 KV 缓存切成定长逻辑 page，发现**单个 page 内部有显著低秩结构**；以 page 为独立压缩单元做分解，注意力可直接在 dense 与 factorized page 上计算，解码时增量压缩新成熟的 page | ~60% 存储 → >96% 性能；18.7% 存储 → >93% | 作者自述：训练与标定无关（training-free & calibration-free）；RULER 上显著优于 Global SVD，LongBench 上具竞争力；可与量化叠加 |
| **STAR-KV** | arXiv 2026-06 | 自适应低秩：可微阈值机制在 head 与 block 级做最优秩选择；按 K/V 投影敏感度采用混合分解策略；再加低秩感知的混合精度 | 激进压缩 | 作者自述：此前方法依赖固定或启发式秩选择，难以在激进压缩下保持精度 |
| **S⁴R** | arXiv 2026-08 | 用选择性采样 token 构造低秩子空间 + 稀疏重建 KV 表示；prompt-aware 初始化构建初始 K/V 基 | — | 作者自述：规避了离线方法依赖外部标定数据、在线方法需全 prompt 分解重建的两难 |
| **DepthWeave-KV / FreqDepthKV** | arXiv 2026-07 | 把相邻层 KV 状态分解为共享的低频深度成分 + 稀疏高频残差；在线探针按对重建敏感注意力 logit 的贡献把 head 分配到 shared-depth / residual-depth / exact 三种模式 | — | FreqDepthKV 作者自述：跨长上下文 QA 任务，在不重训的前提下自适应 prompt 结构 |
| **Sigmoid Attention 作为学习式驱逐底座** | ICML 2026 Workshop (AdaptFM) | 质疑学习式驱逐的 soft-to-hard 落差问题（训练时软门控衰减贡献，推理时只有物理删除才省内存）；用 2×2×2 受控实验比较注意力类型、学习门控、位置编码 | — | 作者自述：sigmoid 注意力作为 dense LM 更差，但**学习式硬驱逐改变了可用工作点**——sigmoid-gated 模型删除 KV 后 PPL 变化相对其自身无驱逐参考可忽略；在匹配 live-cache 协议下优于作者实现的 H2O 与 KeyDiff |
| **PagedAttention 与后续变体** | **SOSP 2023** → 2026 | 把 KV 缓存分成固定大小 block 并用页表管理，消除碎片、支持共享；2026 年的直接后继是 **Minima-KV**（混合格式分页）与 **ThinKV**（扩展 PagedAttention 复用被驱逐槽位） | Minima-KV：相对 BF16 **3.50×**，相对 FP8 1.75× | Minima-KV 作者自述：近期与受保护 Anchor page 保持 FP8、较旧非 anchor page 转 packed TQ3，所有活跃请求 page 仍可寻址；格式特定 kernel 通过全局归一化 online-softmax 合并部分注意力状态，**无需 cache 大小的 dense shadow**。单张 96GB RTX PRO 6000 Blackwell 上 Qwen3.6-27B：每活跃 token 18.3 KiB attention KV；16K RULER-NIAH 与 dense 对照持平；同一 503 题 LongBench v2 上 16K/32K/64K 分别 −0.80 / −0.60 / −0.40 个百分点。另一组两个 59,008-token 请求的直接解码金丝雀测得 3.625× 活跃 KV 压缩、吞吐 0.9821×，且不掉入 fallback |
| **Fractal KV-Cache Archives** | arXiv 2026-07 | 互补问题：一旦 KV 被量化成 codebook 索引，**这串符号流该怎么存**——用收缩迭代映射码把符号序列序列化成低维实向量序列，形成支持增量访问的归档格式 | 无损（存储层） | 作者自述：提供增长型缓存所需的访问模式，代码已开源 |

---

## 6. 长上下文 / 推理模型专属 KV 管理与质量评测

### 6.1 基准与评测

| 工作 | 会议/年份 | 考察什么 | 关键结论（作者自述） |
|---|---|---|---|
| **SCBench (SharedContextBench)** | **ICLR 2025** | KV 缓存全生命周期：生成 → 压缩 → 检索 → 加载；12 个任务 × 2 种共享上下文模式；覆盖 Gated Linear RNN、Mamba-Attention 混合、稀疏注意力、KV dropping、量化、检索、加载、prompt compression 共 8 类 | ① **sub-O(n) 内存的方法在多轮场景下表现差**；② 具 O(n) 内存 + sub-O(n²) prefill 的稀疏编码表现稳健；③ 动态稀疏比静态模式产生更有表达力的 KV 缓存；④ 混合架构的层级稀疏能在强性能下降低内存；⑤ 发现长生成场景下的**注意力分布漂移**问题 |
| **Hold Onto That Thought** | arXiv 2512.12008 (2025-12) | 主流压缩策略在长推理上的表现 | 见 §1.2 |
| **Benchmarking KV-Cache Optimizations…** | arXiv 2607.05399 (2026-05) | 在同一 serving stack 上横向量化/剪枝/合并三类机制（KIVI、TurboQuant、SnapKV、CaM），测任务质量、平均输出吞吐、平均 TTFT、**实测压缩率** | **压缩率本身是端到端性能的糟糕预测器**；KIVI4 跨模型质量最稳，SnapKV 长上下文吞吐最强，CaM 在部分 QA 上增益大但工作负载敏感性强。结论：应按负载选机制而非"一招通吃" |
| **MoEXBench** | arXiv 2026-08 | MoE 模型上**压缩技术可组合性**：10 个 30B–235B 模型 × 专家剪枝 × 权重量化 × KV 精度，覆盖标准/混合线性/滑窗三种注意力架构 | 组合压缩的效果**无法从单项技术预测**；压缩率不能可靠预测质量损失或运行时收益；专家剪枝是主导退化源；平均质量会掩盖工作负载与架构特异的失败 |
| **Compression-Aware Abstention** | EMNLP 2026 Workshop (GroundLM) | 首次把"压缩感知的拒答"形式化为学习问题：用压缩器存活掩码 + 答案承载 span 构造监督 | 10.1M 参数 LoRA（~2.6K MuSiQue 2-hop）在 prompt 式截断下把幻觉降低 97%，同时保留可答样例的正确率；在真实压缩缓存解码下多压缩器训练带来 6–22× 相对提升；受控删除实验表明行为由证据内容驱动而非长度 |
| **LOCA-bench** | arXiv 2602.07962 (2026-02) | 用可自动化控制的环境状态**可控地把 agent 上下文推到近乎无限**，同时保持任务语义不变；评测"模型 + scaffold"组合 | agent 性能随环境状态增长普遍下降，但**先进上下文管理技术能显著改善整体成功率** |
| **Diagnosing and Mitigating Context Rot in Long-horizon Search** | arXiv 2606.29718 (2026-06) | 4 个旗舰模型 × 3 个基准，研究 deep search 下的失败模式；对比 7 种上下文管理方法与并行采样 | 发现 **premature termination（过早终止）**：模型在远未耗尽窗口时就放弃或给出不确定的错误答案，且发生率与上下文长度正相关；上下文管理方法本质上是降低过早终止率的 test-time scaling 策略；行为感知过滤的并行采样带来 2.6%–4.9% 提升 |
| **Benchmarking the Residual** | arXiv 2607.27283 (2026-07) | 立场论文：主张长时程基准必须把整任务成功率与"由各短阶段单独表现预测的基线"对比，其对数比称为 **horizon residual** | 没有这个对照就不能声称"长时程失败"；上下文腐烂（context rot）只是轨迹诱导退化的一种特例 |
| **Semantic Integrity Matters** | **ICML 2026** (poster) | 面向高密度推理的 KV 压缩基准与保持方法 | 见 ICML 2026 poster 页（见文末链接） |
| **KV Cache Quantization for Self-Forcing Video** | arXiv 2026-03 | 33 种量化/缓存策略在自回放视频生成上的峰值 VRAM、运行时、实测压缩率、VBench、SSIM/LPIPS/PSNR、终端漂移 | 见 §2.2 |
| **Alignment Collapse Under KV Quantization** | arXiv 2026-06 | 量化对安全对齐的影响（11 模型 × 5 基准 × 1,894 prompt） | 见 §2.2 |

### 6.2 生产 / 系统层的 KV 管理（与本报告"生产有效性"直接相关）

| 工作 | 机制 | 报告的效果（作者/维护者自述） |
|---|---|---|
| **vLLM FP8 KV-Cache 验证** | `--kv-cache-dtype fp8`（e4m3），QK 与 ScoreV 全在 FP8 中计算；混合注意力模型推荐 `--kv-cache-dtype-skip-layers sliding_window` | 官方博客：修复 FA3 的 FP32 累加精度问题后，128k NIAH 精度从 **13% 恢复到 91%**（BF16 基线 91%）；内存受限解码下 per-token KV 成本可降至 BF16 的 **54%**；head_dim=64/128 时 prefill 与 decode 均有加速；**已知限制**：head_dim=256 时 prefill 仍可能回退；小滑窗层建议跳过 |
| **SGLang HiCache + 稀疏分层调度** | 面向 DeepSeek-V3.2 的分层稀疏 KV 缓存管理与调度；HiSparse 已合入上游 | 第三方论文（HiSparse）报告在 H200/B200/GH200 上峰值生成吞吐最高 4.7× |
| **Jenga（vLLM 异构内存分配器）** | 用 embedding 尺寸的最小公倍数（LCM）做两级分配，提供表达层特异缓存逻辑的 API | 作者自述：GPU 内存利用率最高 +79.6%，服务吞吐最高 4.92×（平均 1.80×）。这是 Qwen3-Next 类混合架构能高效跑起来的基础设施之一 |
| **CacheScout** | 多 agent 服务中在线学习 agent 执行转移，用学到的执行模型指导缓存驱逐与主动预取 | arXiv 2026-07：KV 命中率 +10–18 个百分点，平均 TTFT 降 18–45%，每轮时延降 29–38%，峰值吞吐最高 +57%；更大模型上 TTFT 降最高 54% |
| **Leyline** | 给服务系统加"KV 指令"原语：声明式四元组分离"改什么"与"如何保持位置正确"，用闭式 RoPE 旋转修正恢复注意力数学 | arXiv 2026-05：splice kernel 把 replay cache-hit 提升 +11.2pp、时延最多降低 241ms；一个十行截断规则经同一接口使 debug-gym 上 agentic solve rate +14.3pp |
| **KVBoost** | chunk 级 KV 复用，双哈希键分离位置身份与前缀身份，支持任意位置的（近似）复用 | arXiv 2026-05：突破"必须共享连续前缀"的限制 |
| **More GPUs or a Smaller Cache?** | 把张量并行度（1–8）与 KV 压缩配置（16/8/4-bit 等）放到**同一条成本轴上**比较 | arXiv 2026-08：指出压缩论文报内存比、并行论文报吞吐曲线，几乎没人把二者放到同一成本轴——这是部署决策最缺的一类研究 |

---

## 7. 生产环境实际有效的是什么

> 这一节的判断综合了：官方工程博客（vLLM/SGLang）、论文中的系统实现描述（是否合入上游）、以及 2026 年多篇评测类论文的负面结论。凡属推断的部分均已标明。

### 7.1 已经稳定落地（可以直接开）

1. **FP8 / INT8 KV 量化**——唯一"零算法风险"的选项。vLLM 的 `--kv-cache-dtype fp8` 已经把 128k NIAH 精度修复到与 BF16 持平，内存受限解码下 per-token 成本降到 BF16 的 54%。**坑点已被官方点明**：混合注意力模型请跳过小滑窗层；head_dim=256 时 prefill 可能回退。
2. **架构级削减（GQA / MLA / 线性-全注意力混合）**——收益最大且不依赖运行时猜测。DeepSeek-V2 的 MLA 自述减少 93.3% KV；DeepSeek-V4 的 CSA+HCA 在 1M 上下文下只需 V3.2 的 10% KV cache 与 27% 单 token FLOPs。Qwen3-Next 式混合注意力已在 vLLM 官方支持（含 hybrid KV cache manager），支持 65K+ 上下文。
3. **稀疏注意力 + 分层 KV 存储（DSA/NSA/Quest 族 + HiSparse/OasisKV）**——**这是 2026 年真正的工程主线**。关键在于：稀疏注意力只省"每步读多少"，不省"缓存占多少"；只有把 top-k 稀疏与 HBM/host/CXL 分层结合才能同时拿到带宽与容量。HiSparse 已合入上游 SGLang，在 DSA/NSA/Quest 三族、H200/B200/GH300 上验证。
4. **Prefix caching / KV 复用（含多 agent 场景）**——按 `CacheScout` 与 `KVBoost` 的报告，命中率提升直接转化为 TTFT 与吞吐收益，且不触碰模型质量。这是当前性价比最高的优化之一。

### 7.2 谨慎使用（有条件有效）

5. **解码期驱逐（H2O / SnapKV / Ada-KV / PyramidKV 等）**——**只在预算不激进时有效**。2026 年的受控研究给出了三条硬约束：
   - 注意力分数作为重要性信号非常弱（`TwinKV` ρ=−0.004；`Trust the Mass` 显示最优子集只补 2–5% 差距；`Random Attention` 显示随机驱逐可匹配最强打分器）。这意味着**不同驱逐方法之间的"论文差距"很可能大部分来自评测协议差异（例如排序时答案是否可见、是否真的按字节释放内存）**，而不是算法优越性。
   - **很多"query-agnostic"方法实际上把整份缓存留在显存里**，只是按 head 存了掩码；只有 ragged per-head 存储才真正省内存（`Trust the Mass` 自述）。标称预算与实际字节数是两件事。
   - `Not All Thoughts Need HBM` 自述：推理任务上**精度只取决于永久丢弃的 token 数（驱逐率），与多少留在 HBM 无关**；他们的复现显示 R-KV 在可比预算下只有 0–32%。所以对推理负载，**优先考虑"搬到 CPU/更低层"而不是"删掉"**（其原型报告传输开销仅 5–7%）。
6. **INT2 / 2-bit 量化**——2026 年确实有突破（`OSCAR` 报告 Qwen3-8B 上距 BF16 仅 1.42 分、`SPECTRA` 报告 4× 近无损/最高 12×），但都需要配套自研 kernel 且仍属研究前沿。生产上 4-bit 是更稳的边界；`UltraQuant` 的 4-bit 路径（EMNLP 2026 Industry Track）是目前少见的、直接以"生产 Claude Code trace + vLLM FP8 锚点"来评估的方案。
7. **合并类方法（KVMerger / MiniCache / SelKV / ResKV 等）**——理论上比驱逐信息保留更好（`ResKV` 把被丢贡献形式化为 softmax 分子/分母残差；`KeepKV` 给出单步无损与多步误差界），但**合并会扰动本应保持精确的 retained K/V**，且实现复杂度高于量化。适合作为驱逐之上的"第二级"叠加，不建议作为主压缩手段。

### 7.3 目前不要指望

8. **"更聪明的打分函数"**——`Random Attention`、`Trust the Mass`、`InertiaKV` 三篇 2026 论文从不同角度得出一致结论：在激进预算下，**跨解码步的分数聚合规则（EMA vs 全刷新）比打分函数本身更关键**；打分信号本身的贡献接近可忽略。投资"更好的重要性估计"回报率很低。
9. **低预算 + 长推理**——`Hold Onto That Thought` 明确指出低预算驱逐会**让模型生成更长的推理链**，反而推高总成本；`KV-Rescue` 报告激进预算下会出现 runaway degeneration（重复/不连贯直到长度上限）。如果必须用，请把"生成 token 数"和"缓存大小"放在同一个指标里衡量（`Fewer Tokens, Smaller Cache` 的 ReCo 就是按这个思路做的：生成 token 降 37–65%，端到端时延 2.08–2.35×）。
10. **把压缩率当性能指标**——`Benchmarking KV-Cache Optimizations`（2026-05）与 MoEXBench 独立得出同一结论：**压缩率本身是端到端性能的糟糕预测器**；`KV Cache Quantization for Self-Forcing Video` 甚至发现有些方法缩小了 KV 存储却仍超过 BF16 峰值显存，因为实现在 attention/refresh 阶段重建或保留了大的 BF16 缓冲。
11. **KV 量化的安全对齐风险**——`Alignment Collapse` 报告 Mistral-7B 在仅 1.03× PPL 时丢失 15.2% 拒答，且**不存在通用安全位宽**。对面向用户的模型，这必须单独立项评测。

### 7.4 部署决策清单（建议）

| 你的约束 | 首选 | 次选 | 避免 |
|---|---|---|---|
| 显存紧张、要最简单 | FP8 KV（跳过滑窗层） | INT4（KIVI 式 per-channel K / per-token V） | INT2（除非有自研 kernel 与验证） |
| 上下文极长、延迟敏感 | MLA/GQA 架构 + 稀疏注意力（DSA/NSA 式）+ 分层 offload | Quest / SnapKV 做 page 级选择 | 纯驱逐到极低预算 |
| 长推理（thinking）负载 | 分层存储（HBM→DDR）而非删除 | ThinKV / BeaconKV / ReasonAlloc 类推理专用方法 | H2O/SnapKV 直接套用到 reasoning（需先用 2512.12008 式评测验证） |
| 多轮 / 多 agent | Prefix caching + CacheScout 式执行感知预取 | KVBoost 式任意位置 chunk 复用 | 仅按 recency 的替换策略 |
| 混合架构（Qwen3-Next 类） | vLLM hybrid KV cache manager / Jenga 式分配器 + HeadWiseKV 式 head 级驻留预算 | DASC 式递归状态 checkpoint 压缩 | 对线性层做"驱逐"（语义上不成立） |

---

## 8. 方法论说明与局限

- **本报告的检索方式**：通过 arXiv 搜索页（`searchtype=all`）与 arXiv 摘要页实时抓取标题、日期、`Comments`/`Journal ref`、摘要原文，辅以 `web_search` 定位非 arXiv 来源（会议 poster 页、官方工程博客、模型卡）。所有压缩率与精度数字均取自抓取到的摘要原文。
- **无法保证的部分**：
  1. **venue 归属**：arXiv 的 `Comments` 字段由作者自行填写，可能与官方 proceedings 有出入；标注为「arXiv 预印本」的条目在抓取时未见正式发表信息。
  2. **数字未做第三方复现**。凡是同一问题上存在矛盾说法（最典型的是 R-KV 的 10% 预算精度），本报告已并列双方并标注来源。
  3. **少数条目的原始 arXiv 页未能定位**（如 DMC、KVMerger），已在该条目内明确标注为机制转述。
  4. 2026 年的 arXiv 上存在大量**同一方法的重命名与并发投稿**（例如 CAKE 与用户所指的 "CascadingKV"；CompressKV 有两篇标题相近的 2026 条目，其中一篇 arXiv 标注为 "substantial text overlap with arXiv:2508.02401"）。引用前建议核对原始条目。
- **建议的后续动作**：对 §7.1 中的候选方案，在**你自己的负载**上跑 `Benchmarking KV-Cache Optimizations` 式的四指标测量（任务质量、输出吞吐、TTFT、**实测**压缩率），而不是依赖论文中的名义压缩率。

---

## 9. 完整来源 URL 列表

### 家族 1：驱逐 / Token Dropping
- H2O — https://arxiv.org/abs/2306.14048
- StreamingLLM — https://arxiv.org/abs/2309.17453
- Keyformer — https://arxiv.org/abs/2403.09054
- SnapKV — https://arxiv.org/abs/2404.14469
- RoCo / EasyKV — https://arxiv.org/abs/2402.06262
- PyramidKV — https://arxiv.org/abs/2406.02069
- Ada-KV — https://arxiv.org/abs/2407.11550
- SqueezeAttention — https://arxiv.org/abs/2404.04793
- RazorAttention — https://arxiv.org/abs/2407.15891
- CAKE — https://arxiv.org/abs/2503.12491
- DuoAttention — https://arxiv.org/abs/2410.10819
- CompressKV — https://arxiv.org/abs/2508.02401 ｜ 2026 重名条目 https://arxiv.org/abs/2606.24467
- LazyEviction — https://arxiv.org/abs/2506.15969
- LServe — https://arxiv.org/abs/2502.14866
- CacheCraft / FRC — https://arxiv.org/abs/2608.14555
- Hold Onto That Thought — https://arxiv.org/abs/2512.12008 ｜ HF https://huggingface.co/papers/2512.12008
- Random Attention — https://arxiv.org/abs/2609.03430
- Trust the Mass / ContourKV — https://arxiv.org/abs/2608.25230
- InertiaKV (EMNLP 2026) — https://arxiv.org/abs/2609.03515
- TwinKV — https://arxiv.org/abs/2608.27128
- VaSE — https://arxiv.org/abs/2606.03928
- BeaconKV (ICML 2026) — https://arxiv.org/abs/2609.04971
- ReasonAlloc — https://arxiv.org/abs/2606.11164
- Crystal-KV — https://arxiv.org/abs/2601.16986
- KV-Rescue — https://arxiv.org/abs/2608.15797
- ThinKV (ICLR 2026 Oral) — https://arxiv.org/abs/2510.01290
- R-KV — https://arxiv.org/abs/2505.24133
- RLKV — https://arxiv.org/abs/2510.08525
- KVP / Learning to Evict (ICML 2026) — https://arxiv.org/abs/2602.10238 ｜ 代码 https://github.com/apple/ml-learning-to-evict
- Not All Thoughts Need HBM — https://arxiv.org/abs/2605.09490
- SkipKV — https://arxiv.org/abs/2512.07993
- KARA — https://arxiv.org/abs/2607.01237
- ReCo / Fewer Tokens, Smaller Cache — https://arxiv.org/abs/2608.04771
- TAM / Thought-Aware Compaction — https://arxiv.org/abs/2608.12331
- Neural Garbage Collection — https://arxiv.org/abs/2604.18002
- Bottlenecked Transformers — https://arxiv.org/abs/2505.16950
- AgentKV — https://arxiv.org/abs/2609.14872
- Jacap — https://arxiv.org/abs/2609.08131
- ECOKV — https://arxiv.org/abs/2609.06663
- A Probabilistic Interpretation of KV Cache Eviction — https://arxiv.org/abs/2608.28293
- Sigmoid Attention 作为学习式驱逐底座 (ICML 2026 Workshop) — https://arxiv.org/abs/2608.23296
- MaskKV（dLLM） — https://arxiv.org/abs/2510.09309

### 家族 2：量化 / 低位压缩
- KIVI (ICML 2024) — https://arxiv.org/abs/2402.02750
- KVQuant (NeurIPS 2024) — https://arxiv.org/abs/2401.18079
- QAQ — https://arxiv.org/abs/2403.04643 ｜ ICCV 2025W 版本 https://www.openaccess.thecvf.com/content/ICCV2025W/U%26ME/html/Cheng_QAQ_Quality_Adaptive_Quantization_for_LLM_KV_Cache_ICCVW_2025_paper.html
- MiKV — https://arxiv.org/abs/2402.18096
- SKVQ — https://arxiv.org/abs/2405.06219
- PolarQuant — https://arxiv.org/abs/2502.02617
- TaDA (ACL 2025) — https://arxiv.org/abs/2506.04642
- SVDq — https://arxiv.org/abs/2502.15304
- MiniKV — https://arxiv.org/abs/2411.18077
- TurboQuant — https://arxiv.org/abs/2504.19874
- AQUA-KV / Cache Me If You Must (ICML 2025) — https://arxiv.org/abs/2501.19392 ｜ ICML poster https://icml.cc/virtual/2025/poster/46067
- PM-KVQ (ICLR 2026) — https://arxiv.org/abs/2505.18610 ｜ 代码 https://github.com/thu-nics/PM-KVQ
- MixKVQ — https://arxiv.org/abs/2512.19206
- OSCAR — https://arxiv.org/abs/2605.17757
- SPECTRA — https://arxiv.org/abs/2608.07915
- NOVA-KV — https://arxiv.org/abs/2608.04074
- OptR — https://arxiv.org/abs/2608.02691
- Codec-Gauge — https://arxiv.org/abs/2607.20538
- JoLT — https://arxiv.org/abs/2607.12550
- eOptShrinkQ — https://arxiv.org/abs/2605.02905
- HyperQuant — https://arxiv.org/abs/2606.23406
- RaBitQCache (ICML 2026) — https://arxiv.org/abs/2606.31519
- UltraQuant (EMNLP 2026 Industry) — https://arxiv.org/abs/2606.20474
- WitCert — https://arxiv.org/abs/2607.28699
- Block-GTQ (RoPE-aware bit allocation) — https://arxiv.org/abs/2606.24033
- Don't Waste Bits! (CVPR 2026) — https://arxiv.org/abs/2604.04722
- Interface-Aware KV Quantization for On-Chip NVM (ICCAD 2026) — https://arxiv.org/abs/2609.05764
- Lynx — https://arxiv.org/abs/2607.01831
- Alignment Collapse Under KV Cache Quantization — https://arxiv.org/abs/2606.09864
- Quality Recovery for Quantized KV Caches — https://arxiv.org/abs/2609.04263
- Transforms for LLM Quantization（旋转/变换综述，200 篇） — https://arxiv.org/abs/2608.25188
- KV Cache Quantization for Self-Forcing Video（33 方法实证） — https://arxiv.org/abs/2603.27469

### 家族 3：注意力层结构性削减 / 混合架构
- MQA / GQA（GQA: EMNLP 2023）
- MLA / DeepSeek-V2 — https://arxiv.org/abs/2405.04434
- DeepSeek-V4（CSA + HCA） — https://arxiv.org/abs/2606.19348
- CLA - Cross-Layer Attention — https://arxiv.org/abs/2405.12981
- MLKV — https://arxiv.org/abs/2406.09297
- YOCO — https://arxiv.org/abs/2405.05254
- Layer-Condensed KV Cache (ACL 2024) — https://arxiv.org/abs/2405.10637
- TransMLA — https://arxiv.org/abs/2502.07864
- Thin Keys, Full Values — https://arxiv.org/abs/2603.04427
- Variable-Width Transformers — https://arxiv.org/abs/2606.18246
- Attention Sinks 机制研究 (ICLR 2025 Spotlight) — https://arxiv.org/abs/2410.10781
- Attention Sinks: Catch, Tag, Release — https://arxiv.org/abs/2502.00919
- RippleKV — https://arxiv.org/abs/2608.08684
- PolyKV — https://arxiv.org/abs/2606.15157
- HeadWiseKV — https://arxiv.org/abs/2609.02029
- GraceKV — https://arxiv.org/abs/2608.07001
- MoE-nD — https://arxiv.org/abs/2604.17695
- Mamba — https://arxiv.org/abs/2312.00752
- Mamba-2 / SSD (ICML 2024) — https://arxiv.org/abs/2405.21060
- Jamba — https://arxiv.org/abs/2403.19887
- Infini-attention — https://arxiv.org/abs/2404.07143
- xLSTM — https://arxiv.org/abs/2405.04517
- Qwen3-Next 在 vLLM 的支持（混合注意力 + hybrid KV cache manager） — https://raw.githubusercontent.com/vllm-project/vllm-project.github.io/main/_posts/2025-09-11-qwen3-next.md ｜ https://blog.vllm.com.cn/2025/09/11/qwen3-next.html
- Jenga（异构内存分配，vLLM） — https://arxiv.org/abs/2503.18292
- GLIDE — https://arxiv.org/abs/2607.24788
- DeltaLog — https://arxiv.org/abs/2608.15533
- DASC — https://arxiv.org/abs/2608.30386
- Tail-Replay — https://arxiv.org/abs/2608.30310
- Gated DeltaNet 量化研究 — https://arxiv.org/abs/2609.04098

### 家族 4：稀疏 / 动态注意力
- Quest (ICML 2024) — https://arxiv.org/abs/2406.10774 ｜ 项目页 https://hanlab.mit.edu/projects/quest
- SeerAttention — https://arxiv.org/abs/2410.13276
- NSA — https://arxiv.org/abs/2502.11089
- MoBA — https://arxiv.org/abs/2502.13189 ｜ 代码 https://github.com/MoonshotAI/MoBA ｜ Kimi 文档 https://platform.kimi.com/docs/changelog/moba
- DSA / DeepSeek-V3.2-Exp 生态：ESS — https://arxiv.org/abs/2512.10576
- Native Top-k Sparse Attention 研究 — https://arxiv.org/abs/2512.03494
- MiniMax Sparse Attention — https://arxiv.org/abs/2606.13392
- GLM-5 / GLM-5.1 模型卡（GlmMoeDsa） — https://huggingface.co/docs/transformers/v5.15.0/en/model_doc/glm_moe_dsa
- PIVOT — https://arxiv.org/abs/2607.24593
- StreamIndex — https://arxiv.org/abs/2605.02568
- HiSparse — https://arxiv.org/abs/2608.07009 ｜ SGLang PR https://github.com/sgl-project/sglang/pull/14619
- OasisKV — https://arxiv.org/abs/2608.08097
- SAC — https://arxiv.org/abs/2606.19746
- Self-Indexing Attention — https://arxiv.org/abs/2609.13205
- Declarative Attention — https://arxiv.org/abs/2609.02737
- SpotAttention — https://arxiv.org/abs/2606.22874
- Augmenting Attention with Exponentially Decaying Memory — https://arxiv.org/abs/2605.28640
- NOSA — https://arxiv.org/abs/2510.13602
- ReTopK — https://arxiv.org/abs/2607.27692
- ATFlash — https://arxiv.org/abs/2608.02947
- PRR（Predict, Reuse, Repair） — https://arxiv.org/abs/2606.30389
- OmniSparse (AAAI 2026) — https://arxiv.org/abs/2511.12201

### 家族 5：合并 / 结构压缩 / 低秩
- MiniCache — https://arxiv.org/abs/2405.14366 ｜ 项目页 https://minicache.vmv.re/
- KeepKV — https://arxiv.org/abs/2504.09936
- KVCompose — https://arxiv.org/abs/2509.05165
- KVSculpt — https://arxiv.org/abs/2603.27819
- SelKV — https://arxiv.org/abs/2607.16213
- SemantiCache — https://arxiv.org/abs/2603.14303
- ResKV — https://arxiv.org/abs/2607.29591
- PuzzleKV — https://arxiv.org/abs/2608.23843
- STAR-KV — https://arxiv.org/abs/2606.08382
- S⁴R — https://arxiv.org/abs/2608.00528
- FreqDepthKV — https://arxiv.org/abs/2607.06519 ｜ DepthWeave-KV https://arxiv.org/abs/2607.06523
- MaskKV / PagedAttention 扩展 — https://arxiv.org/abs/2510.09309
- Minima-KV（混合格式分页） — https://arxiv.org/abs/2608.23834
- Fractal KV-Cache Archives — https://arxiv.org/abs/2607.07144 ｜ 代码 https://github.com/eighteight/fractal-kv

### 家族 6：长上下文 / 推理专属管理 + 评测
- SCBench (ICLR 2025) — https://arxiv.org/abs/2412.10319
- Benchmarking KV-Cache Optimizations — https://arxiv.org/abs/2607.05399
- MoEXBench — https://arxiv.org/abs/2608.21693
- Compression-Aware Abstention (EMNLP 2026 Workshop) — https://arxiv.org/abs/2608.29934
- LOCA-bench — https://arxiv.org/abs/2602.07962
- Diagnosing and Mitigating Context Rot in Long-horizon Search — https://arxiv.org/abs/2606.29718
- Benchmarking the Residual — https://arxiv.org/abs/2607.27283
- Semantic Integrity Matters (ICML 2026 poster) — https://icml.cc/virtual/2026/poster/66656
- KV Cache Management 综述 (TMLR 2025) — https://arxiv.org/abs/2412.19442
- CacheScout — https://arxiv.org/abs/2608.14624
- Leyline — https://arxiv.org/abs/2606.01065
- KVBoost — https://arxiv.org/abs/2608.21362
- KVLink — https://arxiv.org/abs/2502.16002
- More GPUs or a Smaller Cache? — https://arxiv.org/abs/2608.23962
- vLLM FP8 KV-Cache 官方验证博客 — https://vllm.ai/blog/2026-04-22-fp8-kvcache ｜ 源码 https://raw.githubusercontent.com/vllm-project/vllm-project.github.io/refs/heads/main/_posts/2026-04-22-fp8-kvcache.md
- vLLM 量化 KV cache 文档 — https://docs.vllm.ai/en/v0.28.0/features/quantization/quantized_kvcache/
- SGLang HiCache for Hybrid and Sparse LLMs — https://github.com/sgl-project/sglang/issues/12826
- VestigeKV — https://arxiv.org/abs/2609.03949
- KARA — https://arxiv.org/abs/2607.01237
- RedKnot-MLA — https://arxiv.org/abs/2609.07008
- FlashMemory-DeepSeek-V4 — https://arxiv.org/abs/2606.09079
- GLM-5 Serving Parameter Tuning — https://arxiv.org/abs/2607.02518
