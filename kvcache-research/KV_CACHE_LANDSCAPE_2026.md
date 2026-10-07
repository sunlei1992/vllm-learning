# 开源 LLM KV Cache 管理与 KV Cache 中心化推理服务框架全景（2026 年 9 月）

> **调研时间基准**：2026-09-15。所有 GitHub star / release / 版本号均为该日抓取值。
> **方法**：全部结论来自当日联网抓取（`web_search` + 直接 `curl` GitHub API / raw README / 官方 docs / arXiv / 厂商博客）。**未使用训练记忆作为事实来源。**
> **诚实性约定**：凡无法验证的内容一律标注 `⚠️ 未能验证` / `❌ 无法证实`。不编造 star、版本号或性能数字。
> **配套原始笔记**（同一 workspace 内，供追溯）：
> - `kvcache-research/notes_china_vendors.md`（中国厂商：阿里 Tair、腾讯 FlexKV、字节 EIC、华为 Ascend/MindIE、百度等）
> - `kvcache-research/notes_other_oss.md`（AIBrix、KServe、PegaFlow、论文综述、项目发现）
> - `kvcache-research/notes_standards.md`（标准与接口，见 §6）
> - `kvcache-research/notes_storage_cloud.md`（存储层与云厂商，见 §5）
> - `kvcache-research/raw/`（约 430 个抓取产物：README、docs 原文、HTML→text 等）

---

## 0. 核心结论（TL;DR）

1. **2026 年的分野不再是"做不做 KV Cache 复用"，而是"谁拥有 KV、走什么传输、按什么策略准入/驱逐"。** KV 已从"每请求临时张量"被重新定义为**一等持久化数据资产**（arXiv 2607.02574 综述的表述）。各家的差异集中在**所有权边界、传输介质（CUDA IPC / RDMA / NVLink / CXL）、准入与驱逐策略、以及可观测性**四点。

2. **接口事实上已经收敛到三个平面，但没有任何正式规范存在** —— 并且"标准"这个词需要非常小心：
   - **接入面（引擎侧）**：vLLM 的 `kv_transfer_config` / `KVConnectorBase_V1` 成为事实上的外部 KV Cache 集成契约。**LMCache、PegaFlow、AIBrix、Mooncake、KVBM、FlexKV、AscendStoreConnector 全部通过它接入且无需 fork vLLM。** ⚠️ **但不存在 "KV connector API 1.0"**：`KVConnectorBase_V1.__init__` **每次实例化都打印** *"This API is experimental and subject to change"*，**没有版本常量、没有 ABI**。
   - **事件面（路由侧）**：`BlockStored` / `BlockRemoved` / `AllBlocksCleared` 这一组 **KV Events** 成为事实上的缓存状态同步契约 —— **SGLang 是"刻意"采用 vLLM 的编码**（其源码原话：*"the same encoding vLLM uses… so a consumer such as Dynamo decodes both engines with one code path"*），llm-d 用两个 adapter 做归一化，Dynamo 则桥接到自己的 NATS 信封。**但分层词表已经对不上（vLLM `CPU` vs SGLang `CPU_PINNED`），且不存在任何 KV-events SIG 或共享 schema。**
   - **传输面**：**NIXL**（NVIDIA，1,256★，v1.4.1，14 个插件）成为跨框架的 KV 点对点/存储传输抽象；**Mooncake Transfer Engine** 是与之并列的另一条事实标准线（在中国生态更强，且作为 NIXL 的官方插件被嵌套进去）。⚠️ **NIXL 的治理成熟度接近为零**：`GOVERNANCE.md` 与 `VERSIONING.md` **均 404**，无基金会归属，下游只能**精确 pin 版本**。
   - 🚨 **vLLM 官方的《KV-Cache Interoperability API Standardization》RFC（#20492）已被 "Closed as not planned"，无替代品**。其**技术半部**最终以别的方式落地（PR #20511 合入，引入 `sha256_cbor` 等可复现块哈希，**但默认值仍是 `sha256`，即默认未启用跨语言可复现那一档**）；**契约半部**（版本化公开 schema + Go/Python 参考库）**没有落地**。
   - 🚨 **2026 年唯一一份写完整的 KV cache 规范 `kv-first`（openhivesai）0 star、0 fork、无任何实现者**，且无证据表明相关项目知道它的存在。**不是没人尝试写规范，而是写出来没人用** —— 这是"标准缺位"最直观的证据。

3. **五强格局（按 KV Cache 中心化程度）**：**Mooncake**（存储与传输基座，生产最久）、**LMCache**（引擎无关的 KV 层，星数最高）、**NVIDIA Dynamo**（KVBM + Router + Planner 全栈，商业化最强）、**llm-d**（K8s 控制面 + 精确路由，CNCF）、**SGLang HiCache**（引擎内置分层，后端最开放）。**vLLM 自身**的原生能力（`OffloadingConnector` + `TieringOffloadingSpec`）在 2026 年补上了多级+事件语义，正在把一部分外部 KV 层的职责收回内核。

4. **实际收益量级（均为厂商/论文自报）**：
   - Mooncake × vLLM（agentic 真实 trace）：吞吐 **3.8×**、P50 TTFT **46×**、E2E **8.6×**，命中率 1.7% → 92.2%。
   - LMCache MP（Qwen3-235B，8×H100）：TTFT 均值 3.98s → **0.29s（≈13×）**。
   - Dynamo 1.0：Blackwell 上请求数 **7×**（SemiAnalysis InferenceX）；agentic 场景 TTFT **4×↓**。
   - llm-d：前缀感知路由 vs 轮询 **3× 吞吐 / 2× TTFT**（Tesla, 4×MI300X）；分层 KV offload **13.9×** 吞吐（4×H100）。
   - SGLang HiCache：**最高 6× 吞吐 / 80% TTFT 下降**；合作方实测 56%~84% TTFT 下降。

5. **2026 年新增的重要玩家**：**AIBrix**（5.1k★，`KVCache` CRD + SGLang HiCache L3 后端）、**PegaFlow**（Novita，Rust 外部 KV 服务，跨节点 RDMA 194 GB/s）、**FlexKV**（腾讯 TACO + NVIDIA，已进 vLLM/SGLang/TRT-LLM/Dynamo 主线）、**Volcengine EIC**（字节，SGLang 内置 `eic` 后端）、**kvcached**（1.4k★，KV 虚拟内存化做 GPU 共享）、**TENT**（Mooncake 团队下一代传输调度）。

---

## 1. 调研方法与可信度说明

- **star / fork / release** 以 GitHub REST API 为准（少数因限流改用 `img.shields.io` 与 `ungh.cc` 镜像交叉核对）。**release 日期一律取自 GitHub Releases / tags 对象。**
- **性能数字**分三类明确标注：
  - **[论文]**：有 arXiv/USENIX 出处与实验设置；
  - **[公开博客+可复现脚本]**：厂商博客给出了配置与 benchmark 脚本；
  - **[厂商自报]**：仅有营销文章，无模型/硬件/脚本细节 —— 本文按此标注，不作为可比结论。
- **无法验证项**集中在 §9。

**本次调研记录到的复现陷阱（供后来者避坑）**：
1. **`curl` 对 `raw.githubusercontent.com` 超时时不会创建输出文件**，会让批量抓取**静默丢文件**（`wc -c` 报 "No such file" 而非 0）。改用 `gh api <repo>/contents/<path> -H "Accept: application/vnd.github.raw"` 或 jsDelivr/镜像更稳。
2. **GitHub REST API 未认证限额（60 req/h）很快耗尽**；`img.shields.io` 与 `ungh.cc` 可作 star/release 的交叉核对镜像。
3. **阿里云/昇腾/火山引擎/Moore Threads 的文档页是 SPA，正文以 JSON 转义形式内嵌在 `<script>` 里** —— 先"剥 script 再剥标签"的朴素管线会把正文删掉，只返回 1–5 KB 的页面框架；必须**先反转义 `\uXXXX`**。
4. **Gitee 不可抓取**（849 字节 JS 壳），**中国生态实际的代码中心是 GitCode**。
5. **arXiv API 会整段时间 429**（百度那一轮 40 分钟内 10+ 次尝试全部 429，Semantic Scholar 同）→ 无法做系统性论文普查。
6. **组织枚举型"负面结论"具有误导性**：字节最重要的三个 KV 产物里有**两个位于非字节命名的组织**（PrisKV 在 `aibrix` 组织、AIBrix 在 `vllm-project`、InfiniStore 双栖且 `bd-iaas-us` 已 404）。直接枚举 `bytedance` 组织的结论"字面为真但会误导"。
7. **一类可复用的取证方法**：闭源系统的开源源码包（shim）常常泄露其最好的设计细节 —— EIC 硬编码的 H20 GPU↔NIC 亲和表、AttentionStore 的 block/shard/layer 字段都是这样得到的。

---

## 2. 背景：为什么 KV Cache 在 2026 年成为一等公民

Agentic 负载把 KV Cache 从"优化项"变成"必需品"。vLLM × Mooncake 团队对 Codex/SWE-bench Pro 真实 trace 的分析（610 条 trace、中位数 33 轮）给出了最直观的量化（<https://vllm.ai/blog/2026-05-06-mooncake-store>）：

- **94.2% 的缓存命中率**、输入:输出 token 比 **131:1**；
- 第 30 轮时上下文约 **80K tokens**，最长超过 **180K**；每轮平均只新增约 **2,242** tokens；
- 轮间延迟中位数 5.2s、P99 81.4s。

也就是说：**每轮真正的新增计算只占极少数 token，其余全是可复用的前缀**。这直接导致两个结论：

1. **本地（单实例 CPU DRAM / 本地盘）offload 不够** —— 100K 上下文在 Kimi-2.5 FP8 下约 **3.8 GB** KV，本地容量很快被打满；
2. **必须跨实例共享** —— 负载均衡会把同一会话的下一轮打到别的实例上，没有分布式池就会全量重算。

同一结论在 EIC 的厂商文章中亦有独立表述：8K/轮、6 轮后历史 token 重算超过输入的 **80%**；LLaMA-70B 在 H20 上每 1K token 占 **1.6 GB** KV，预填充 20 分钟内即触顶。

---

## 3. 五大重点框架深度剖析

### 3.1 Mooncake（kvcache-ai/Mooncake，Moonshot AI）

| 项 | 值 |
|---|---|
| 定位 | **KVCache 中心化的分离式推理平台**（Kimi 的生产服务平台） |
| 维护方 | `kvcache-ai` 组织。`MAINTAINERS.md` 列出的贡献/合作方包括 Moonshot AI、清华大学、Approaching.AI、阿里云、**蚂蚁集团**、华为、NVIDIA、AMD、摩尔线程、腾讯、火山引擎、浪潮、海光、MetaX、Sunrise、AWS 等 |
| Stars / Forks | **6,575 / 1,221**（2026-09-15） |
| 最新版本 | **v0.3.13（2026-08-26）**；v0.3.14-rc1（2026-09-07） |
| License | Apache-2.0 |
| 论文 | **FAST'25 最佳论文**：《Mooncake: Trading More Storage for Less Computation》USENIX FAST 2025, pp.155–170；期刊版 **ACM TOS, DOI 10.1145/3773772**；arXiv 2407.00079 |

#### 核心机制

Mooncake 由三部分组成：

**(1) Transfer Engine（TE）— 数据面基座。** 统一的批量数据传输接口，面向异构存储/网络/加速器。关键特性：

- **多 RDMA 网卡带宽聚合**（multi-NIC pooling）；
- **拓扑感知路径选择**（NUMA 亲和性、源/目的位置）；
- 故障时自动切换备用路径；
- 支持协议：**TCP、RDMA、AWS EFA、NVMe-oF、NVLink、HIP、Barex、CXL、Ascend 系列传输**；
- 支持加速器：CUDA、MUSA（摩尔线程）、HIP（AMD）、MACA、寒武纪 MLU、**Ascend NPU**。

**实测带宽 [论文]**：传输 40 GB（≈LLaMA3-70B 128K token 的 KV 大小）时，4×200 Gbps RoCE 下 **87 GB/s**、8×400 Gbps 下 **190 GB/s**，分别是 TCP 的 **2.4× / 4.6×**。EFA 传输文档另给出 CPU-to-CPU 场景受 DRAM 带宽限制、约 **205–214 GB/s** 的平台值（`docs/source/design/transfer-engine/efa_transport.md`）。

**(2) Mooncake Store — 分布式 KV/权重存储引擎。** 构建在 TE 之上：

- 大对象条带化 + 并行 I/O + **端到端零拷贝**，充分吃满多网卡聚合带宽；
- **多级缓存：DRAM + SSD/NVMe**；
- **存储与推理引擎解耦**：存储节点可动态增删，缓存数据不随引擎重启/升级/调度而丢失；
- **程序化对象管理**：per-object 策略，支持**副本数、preferred segment、soft pin、hard pin** —— 让推理系统能保护重要 KV 与权重，并引导复制/放置/驱逐行为；
- Master 侧管理元数据、副本与放置、租约（lease）、驱逐。

**(3) Mooncake EP / PG（2026 新增）** — 把 Mooncake 从"数据搬运"扩展到"容错分布式执行"：EP 在 DeepEP 风格 dispatch/combine 上加入 `active_ranks` 感知，可在 rank 故障时绕行；PG 提供可注册为 `torch.distributed` backend 的进程组，支持对等状态轮询与 rank 恢复。已集成进 SGLang 做大规模 MoE 容错推理。

#### 集成面（这是 Mooncake 真正的护城河）

| 时间 | 集成 |
|---|---|
| 2024-12 | vLLM 支持 TE（PD 分离 KV 传输） |
| 2025-04 | SGLang 支持 TE（分离式预填充）；LMCache 支持 Mooncake Store 作为 remote connector |
| 2025-05 | **NIXL 把 Mooncake TE 作为官方 backend plugin** |
| 2025-06 | LMDeploy PD 分离后端 |
| 2025-09 | **SGLang HiCache 官方支持 Mooncake Store 作为 L3 后端**；vLLM-Ascend 用 Mooncake Store 作分布式 KV pool |
| 2025-11 | RBG + SGLang HiCache + Mooncake（云原生角色化部署） |
| 2025-12 | **TensorRT-LLM 集成 TE**（PD 分离）；**vLLM v1 直接集成 TE 为 KV Connector** |
| 2026-01 | FlexKV 分布式复用支持 Mooncake TE |
| 2026-02 | **Mooncake 加入 PyTorch 生态** |
| 2026-04 | SGLang 用 Mooncake TE 做 RDMA P2P 权重传输（Kimi-K2 1T 参数，**53s → 7.2s，7×**） |
| 2026-05 | **vLLM 官方博客《Serving Agentic Workloads at Scale with vLLM × Mooncake》**（见下） |
| 2026-08 | 集成进 Miles（分离式 RL 的 rollout 数据传输）、Speculators（多机在线训练 hidden-state 传输） |

#### 实测数字

**[论文 / FAST'25 原文]**
- 真实 trace 下**有效请求容量提升 59% – 498%**（在满足 SLO 的前提下）；
- Kimi 在生产中于 **A800 集群多承载 115%、H800 集群多承载 107%** 的请求；
- **全局缓存命中率最高为本地缓存的 2.36×**，带来**最高 48% 的预填充计算时间节省**；
- 论文规模：**数千节点、日均 >1000 亿 tokens**；
- 论文实测：200 ms TTFT 阈值下有效请求容量 +40%；
- 关键设计论证：1 TB 本地 DRAM 只能缓存约 **300 万 token**（LLaMA3-70B，320 KB/token），多数负载下达不到理论命中率的 50%；要接近理论上限需聚合至少 **20 个节点**的 DRAM。

**[vLLM 官方博客 2026-05-06，1P1D，12×GB200，Kimi-2.5 NVFP4]**（<https://vllm.ai/blog/2026-05-06-mooncake-store>）
- 吞吐 **3.8×**、P50 TTFT **46×↓**、E2E 延迟 **8.6×↓**；
- 命中率 **1.7% → 92.2%**；
- 12 → 60 GB200 在**轮询路由**下仍保持 **>95% 命中率**，近线性扩展；
- 数据通路要点：**GPUDirect RDMA 零拷贝、不经 SM、不落 CPU 暂存**；全部 RDMA 在专用后台 I/O 线程，对 vLLM 完全异步；通过 `MultiConnector` 与 PD 分离 connector 组合。

#### 成熟度判断

**最成熟的一个**：唯一有 FAST 最佳论文 + 期刊版 + 真实生产规模（日均千亿 token）+ 跨 5 个引擎官方集成的项目。2026 年的新方向是**从"KV 存储/传输"扩展到 MoE 容错执行（EP/PG）与下一代传输调度（TENT）**。

---

### 3.2 LMCache（LMCache/LMCache）

| 项 | 值 |
|---|---|
| 定位 | **引擎无关的 KV Cache 管理层**（"KV cache as an independent data layer"） |
| 维护方 | LMCache 社区；**2025-10 加入 PyTorch Foundation**；开发由 **Tensormesh**（UChicago 团队创立的公司）支持 |
| Stars / Forks | **11,812 / 1,887** |
| 最新版本 | **v0.5.5（2026-09-12）**；**operator-v0.5.5（2026-09-15）**；每日 nightly（cu129 / CUDA 13 / ROCm / MUSA / XPU） |
| License | Apache-2.0 |
| 论文 | **arXiv 2510.09665**（v1 2025-10-08，v2 2025-12-05） |

#### 核心机制

LMCache 的定位在 2026 年发生了**结构性变化：从"多后端 in-process 插件"转为"独立的多进程（MP）服务"**。

**MP 架构（2026-04 起为推荐模式）** —— 这是理解当前 LMCache 的关键：

```
vLLM 实例们
   │ ZMQ (tcp)
MessageQueueServer (mq.py)
   │ 按 RequestType 分发
MPCacheServer (server.py)
   ├── TokenHasher / SessionManager
   └── StorageManager (distributed/storage_manager.py)
         ├── L1Manager ──> L1MemoryManager（CPU DRAM）
         │                DevDaxL1MemoryManager（Device-DAX slab）
         │                GDSL1MemoryManager（NVMe slab via cuFile/hipFile）
         │                TTLLock（per-object 读写锁）
         ├── StoreController     ──> L2 Adapter(s)（异步 L1→L2 上推）
         ├── PrefetchController  ──> L2 Adapter(s)（异步 L2→L1 预取）
         └── EvictionController  ──> L1Manager（水位触发驱逐）
   └── EventBus + OTel providers（可观测性）
```

- **L1 = CPU DRAM / Device-DAX / NVMe(GDS)**；**L2 = 持久存储**。⚠️ **重要更正：当前 MP 模式只有两层（L1/L2），没有 L3/L4** —— 早年"16 个后端的多级"命名属于**已废弃的 in-process 模式**。
- 单节点一个 LMCache server 可服务多个 vLLM pod，提供**进程隔离**（cache 故障不拖垮引擎）、**避开 GIL 争用**、**跨 pod 共享 L1**、**资源独立扩缩**。
- L2 后端通过 `--l2-adapter` 选择，文档化矩阵含：`nixl_store` / `nixl_store_dynamic`、`fs`、`fs_native`、`raw_block`、`bigtable`、`sagemaker-hyperpod`、`s3`、`hfbucket`、**`mooncake_store`**、**`resp`（Redis/Valkey）**、`valkey`、`aerospike`、`dax`、`mock`、`fault_inject`、`plugin`/`native_plugin`。所有 adapter 均接受 `"shared": true` 表示跨实例共享同一存储域。
- **非前缀复用**：通过 `BlendModule`（CacheBlend 系）复用 prompt 中**任意位置**的 KV 块，仅对少量 token 选择性重算以恢复质量。
- **PD 分离**：通过 NIXL 等传输层做 prefill → decode 的 KV 传输（NVLink / RDMA / TCP）。
- **可插拔 KV 变换**：SERDE 接口支持压缩、token dropping、自定义序列化；2026 新增 **aesgcm 静态加密**（per `cache_salt`）。
- **多节点 P2P CPU 内存共享**：2026-01 从实验特性转为**生产特性**。

#### Operator / CRD（K8s 原生部署）

源码：`LMCache/LMCache` 仓库 `operator/DESIGN.md`。要点：

- **单一 CRD**：`apiVersion: lmcache.ai/v1alpha1`, `kind: LMCacheEngine`（Alpha，随 L2 后端稳定会演进）。未来规划 `LMCacheKeyManager`（全局 key 管理）、`LMCacheMonitor`。
- 控制器把 CR 调和为 **DaemonSet + Service + ConfigMap + ServiceMonitor**；
- **自动注入易错项**：hostPath 挂载宿主机 `/dev/shm`（CUDA IPC 必需）、`--host 0.0.0.0`；
- **稳定的服务发现契约**：创建 `internalTrafficPolicy=Local` 的 ClusterIP Service（kube-proxy 只路由到同节点 LMCache pod），并把 `kv-transfer-config` JSON 写入 `<name>-connection` ConfigMap 供 vLLM 挂载；
- **资源自动推导**：`memoryRequest = ceil(l1.sizeGB + 5) Gi`、`memoryLimit = 1.5 × request`、`cpuRequest = 4`；
- **CRD 校验**：OpenAPI schema + validating webhook（如 `l1.sizeGB > 0`、`eviction.triggerWatermark ∈ (0,1]`）；
- **L2 后端**：支持原生的 `resp`（Redis/Valkey）adapter（`numWorkers` 默认 8、`maxCapacityGB`），或 `raw` 逃逸口传任意 adapter 类型；
- **SERDE**：目前仅 `aesgcm` 有类型化字段（HKDF、128/256 bit，master key 由用户 Secret 提供，operator 不接触密钥材料）；
- **可变 webhook 注入**：默认只注入连接信息（`--kv-transfer-config`、`/dev/shm`、`PYTHONHASHSEED`）；可选 `injection.payloadImage` 把 lmcache 代码树 stage 进 vLLM 容器（emptyDir + initContainer + readOnly mount + `PYTHONPATH`），保证 client 与 engine server 用同一 build。

#### vLLM 集成点（源码级已验证）

- `vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py` → **`LMCacheConnectorV1`**
- `.../v1/lmcache_mp_connector.py` → **`LMCacheMPConnector`**
- `.../v1/lmcache_integration/`（`vllm_v1_adapter.py`、`multi_process_adapter.py`）
- 生产配置：`--kv-transfer-config '{"kv_connector":"LMCacheMPConnector","kv_role":"kv_both"}'`
- **SGLang 侧**：HiCache 文档把 LMCache 定位为"HiCache 的替代方案"，用 `--enable-lmcache` + `--lmcache-config-file` 启用。

#### 实测数字

**[论文 arXiv 2510.09665]**：与 vLLM 结合，跨多种负载**吞吐最高提升 15×**。论文强调三项贡献：高度优化的 KV 数据搬运（批量搬运、计算与 I/O 流水线重叠）、**模块化 KV connector 组件**（把 LMCache 与推理引擎的快速演进解耦）、**一等控制 API**（pin / lookup / cleanup / movement / compression）。

**[MP 架构博客 2026-04-03]** —— Qwen3-235B-A22B-Instruct-2507-FP8，单机 8×H100-80GB，vLLM 0.18.1，DP=8+EP，**两侧 host 内存预算完全相同（400 GB）**：

| 指标 | LMCache MP | In-process offload |
|---|---|---|
| TTFT 均值 | **0.29 s** | 3.98 s |
| TTFT p99 | **1.30 s** | 13.55 s |
| 解码速度均值 | **37.47 tok/s** | 9.81 tok/s |
| 解码速度 p99 | **45.14 tok/s** | 34.27 tok/s |

→ TTFT 平均 **≈13×** 改善、p99 **>10×**、解码吞吐 **≈4×**。博客自陈的归因：MP 模式把 KV 从"跨 DP rank 碎片化的进程内缓冲"变成"统一的主机层缓存"。

**[其他已核实]**：NVIDIA Dynamo 于 2025-09-18 集成 LMCache；与 CoreWeave 一起支撑 Cohere 推理（2025-10-29）；AMD MI300X 上的 agentic 负载 benchmark（2026-05-12）。

#### 成熟度判断

**生态位最宽的一个**：星数最高、引擎无关、PyTorch 基金会背书、有 K8s Operator。2026 年的关键动作是**从库变成服务**（MP + Operator + 加密 + KV 编辑 SDK），以及商业侧由 **Tensormesh** 承接（已融资：2025-10 种子 450 万美元；2026-05-27 由 AMD Ventures、CoreWeave、NVentures 参投的 **2000 万美元**）。⚠️ Tensormesh 官网的"10×"、"41× TTFT" 属其自述/客户证言，**不可作为可复现结论引用**。

---

### 3.3 NVIDIA Dynamo（ai-dynamo/dynamo）

| 项 | 值 |
|---|---|
| 定位 | **数据中心级分布式推理框架**（"inference operating system"） |
| 维护方 | NVIDIA |
| Stars / Forks | **8,083 / 1,586** |
| 最新版本 | **v1.4.2（2026-08-29）**；另有 v1.5.0 / v1.6.0 系列模型专属 dev tag（如 `v1.6.0-deepseek-v4.1-flash-dev.1`） |
| License | Apache-2.0（GitHub 标为 NOASSERTION） |
| 关键里程碑 | **Dynamo 1.0 于 2026-04-09 发布**（NVIDIA 官方博客） |

#### 1.0 发布带来的 KV 相关能力

来自 NVIDIA 官方博客（2026-04-09）：

- **KVBM 支持对象存储**：可对接 **Amazon S3 与 Azure Blob 风格 API**，无需为每个后端单独写 KV 拉取管线；
- **全局 KV 事件发射**：KVBM 在 KV 块于**GPU 内存 / CPU 内存 / 本地 SSD / 远端存储之间移动或被驱逐**时发事件，由 KV Router 的 indexer 消费，形成**全集群一致的 KV 块位置视图**；
- **KVBM 可 pip 安装**：可单独装进 vLLM / TensorRT-LLM，不需要整套 Dynamo 栈 —— 让不同框架的团队共用同一套 offload 工具。

#### 3.3.1 KVBM（KV Block Manager）机制

**分层架构（三层）**：
1. **LLM Inference Runtime 层** —— vLLM / TensorRT-LLM 通过各自的 connector 接入（SGLang ❌ 不在 KVBM 支持矩阵内）；
2. **KVBM Logic 层** —— `KvBlockManager<H,D>` 门面；`KvBlockManagerState` 统合 layouts / storage backends / pools，并持有 `OffloadManager`、metrics、events hook；负责表查找、内存分配、块布局管理、生命周期状态机、复用/驱逐策略；
3. **NIXL 层** —— 统一承担所有数据与存储事务（P2P GPU 传输、RDMA/NVLink 远端内存共享、动态块注册与元数据交换、存储后端插件）。

**四层存储池**：

| 池 | 介质 | 职责 |
|---|---|---|
| **G1 Device Pool** | GPU HBM | 分配可变块、注册不可变块、按 `sequence_hash` 查找、作为 onboard 目标 |
| **G2 Host Pool** | CPU pinned memory（page-locked） | 承接 G1 offload、向 G1 onboard、向 G3 offload |
| **G3 Disk Pool** | 本地 SSD NVMe | 承接 G2 offload、向 G1 onboard；NIXL descriptor 暴露 file offset 支持零拷贝与可选 **GDS** |
| **G4 Remote Storage** | 远端/云对象存储 | KVBM 视为**不透明 blob store**，仅通过 NIXL 访问 |

**块状态机**：`Reset → Partial →(commit) Complete →(register) Registered →(drop) Reset`。`Partial` 为序列创建者私有，`Complete` 已填满但尚不可见，`Registered` 进入全局去重缓存（`Drop of RegistrationHandle` 触发 Remove 事件）。布局默认 `FullyContiguous`：`block_stride_in_bytes = align_up(num_layers × layer_stride, alignment)`；存储后端分为 `DeviceStorage`（CUDA）、`PinnedStorage`（page-locked host）、`SystemStorage`（fallback/test）、`NixlStorage`（通过 NIXL RDMA handle 的远端内存）。

**设计说明**：KVBM 文档自陈其设计"受 SGLang 与 vLLM 的 KV block manager 启发"，并加入了通用 GPU 编程中的内存分层策略。

#### 3.3.2 KV Router（KV 感知路由）

**成本函数**（Rust worker selector，`lib/kv-router/src/scheduling/selector.rs`）：

```
overlap_credit_blocks = device_overlap_blocks       * effective_device_credit
                      + host_pinned_overlap_blocks  * 0.75  // --router-host-cache-hit-weight
                      + disk_overlap_blocks         * 0.25  // --router-disk-cache-hit-weight
                      + shared_overlap_blocks       * shared_cache_multiplier

adjusted_prefill_blocks = max(raw_prefill_blocks - overlap_credit_blocks, 0)

logit = prefill_load_scale * adjusted_prefill_blocks
      + decode_blocks
      + decode_active_request_weight * active_requests
```

其中 `effective_device_credit = overlap_score_credit / (1 + overlap_score_credit_decay * normalized_excess_prefill)` —— **下层（host/disk/shared）的 credit 不衰减，只有 device 层衰减**（避免"有缓存但排队很久"的假优势）。路由选 **logit 最小**的 worker；`router_temperature` > 0 时对归一化 logit 做 softmax 采样。

**索引（indexer）**：
- 默认 `ConcurrentRadixTree`（`--router-event-threads N>1`，默认 4 线程）：线程安全的 radix tree，采用 **sticky worker routing** 保证同 worker 事件串行；读操作 `find_matches` 与写并发。
- `--router-event-threads 1` 时用单线程 RadixTree（也支持 TTL 过期的近似模式）。
- **事件传输**：worker 维护本地 radix tree 并通过 **NATS Core 或 ZMQ**（`--event-plane`）发布事件；每个 worker 的事件 ID 单调递增；router 检测序号空洞后向该 worker 的 local indexer 直接查询恢复。
- **恢复机制**：`LocalKvIndexer` = `KvIndexer`（RadixTree，当前状态与快照源）+ `VecDeque` 循环事件缓冲。查询返回六种结果：`Events` / `TreeDump` / `TreeDumpFailed` / `TooNew` / `InvalidRange` / `Error`。**初始状态同步与游标过旧时用全量 RadixTree 快照（tree dump）事务性替换该 rank**。
  - 对比（Dynamo 官方文档 *KV Event Replay — Dynamo vs vLLM*）：vLLM 的 `ZmqEventPublisher` 只有 **buffer-only replay**（`deque`，`buffer_steps` 默认 10,000，线性扫描，无内置初始同步）；Dynamo 多一层 RadixTree，因此能做快照回退，代价是内存与复杂度。
- **多路由副本**：开启 replica sync 后交换 `AddRequest` / `MarkPrefillCompleted` 等生命周期事件（fire-and-forget，队列满时丢最新），**只改善跨副本的活跃负载估计，不保证路由决策一致**。

#### 3.3.3 Planner（KV/SLA 感知自动扩缩）

- 四个 `optimization_target`：`throughput`（默认，基于队列深度 + KV cache 利用率阈值）、`latency`、`load`（自定义 prefill 队列 token / decode KV 利用率阈值）、`sla`（用 Rust engine perf shim：native AIC 估计 + 在线 FPM 调优 + FPM 回归兜底）。
- 两种扩缩模式可叠加：**throughput-based**（默认 180s 周期，容量下限/长期规划）与 **load-based**（默认 5s 周期，用事件面 `ForwardPassMetrics`，不需要 KV Router，响应突发）。
- 流量预测模型：`arima`（默认）/ `prophet` / `kalman` / `constant`。
- 已知限制：缩容时会直接终止 worker，in-flight 请求会失败（包括等待 KV 传输的 decode worker）。
- **DynoSim**：可在无 GPU 的情况下仿真拓扑/router/Planner 行为，并对 Planner 决策做 trace 回放对比。

#### 3.3.4 与其他系统的互操作（关键）

Dynamo 官方 **Offloading Support Matrix** 明确列出跨引擎的**分层感知路由**能力：

| 框架 | 版本门槛 | GPU | CPU RAM | Disk | Shared pool |
|---|---|---|---|---|---|
| **vLLM** | vLLM v0.24.0+；Dynamo v1.3.0+ | ✅ KV events | ✅ `OffloadingConnector` + 自描述 KV events | 🚧 进行中（vLLM main 已发 FS/OBJ 事件） | 🚧 进行中 |
| **SGLang** | SGLang v0.5.11+（v0.5.13+ 配 Mooncake）；Dynamo v1.2+ | ✅ KV events | ✅ HiCache + KV events | — 无独立 disk 层 | ✅ HiCache + Mooncake + `--shared-cache-type hicache` |
| **TensorRT-LLM** | Dynamo v1.3.0+ | 🟡 `--publish-kv-events`（GPU+RAM 合并视图） | 🟡 同上 | — | — |

注意：SGLang 需 **v0.5.13+** 以避免 bundled-Mooncake 崩溃；TensorRT-LLM 的事件**不区分 GPU 与 host RAM**，因此 host-tier 权重不适用。

#### 实测数字

- **[NVIDIA 官方 / SemiAnalysis InferenceX, 2026-03-03]**：Blackwell 上 Degraded 服务 + 宽专家并行，**请求数最高 7×**（DeepSeek R1-0528 FP4, 1k/1k, ~50 tok/s/user）。
- **[NVIDIA 博客]**：Dynamo + NeMo Agent Toolkit 在 Hopper 上跑 Llama 3.1，**TTFT 最高 4× 更低、吞吐 1.5× 更高**。
- **[NVIDIA 博客]**：多模态 `Qwen3-VL-30B-A3B-Instruct-FP8` on GB200，CPU 侧 LRU **图像 embedding 缓存**使 **TTFT 改善最高 30%、吞吐最高 +25%**。
- **[NVIDIA 博客]**：ModelExpress **权重流式传输**使大 MoE（如 DeepSeek v3 on H200）**模型加载时间最高快 7×**。

#### 生产采用（NVIDIA 官方自陈）

Amazon、AstraZeneca、Baseten、**ByteDance**、CoreWeave、Crusoe、DigitalOcean、Gcore、GMI Cloud、Nebius、**美团**、Pinterest、Prime Intellect、**小红书**、SoftBank Corp.、**腾讯云**、Together AI、Vultr 等已用于生产。云厂商托管 K8s 集成：阿里云、AWS、Google Cloud、Microsoft Azure、OCI。存储厂商集成：Cloudian、DDN、Dell、Everpure（原 Pure Storage）、HPE、IBM、NetApp、VAST、WEKA。

---

### 3.4 llm-d（llm-d/llm-d）

| 项 | 值 |
|---|---|
| 定位 | **Kubernetes 上的分布式推理控制面** |
| 治理 | **CNCF Sandbox（2026-03-24 加入）**，LF Projects 系列；创始方 Red Hat、Google Cloud、IBM Research、CoreWeave、NVIDIA；支持方含 AMD、Cisco、Hugging Face、Intel、Lambda、Mistral AI、UC Berkeley、UChicago |
| Stars / Forks | **4,542 / 768** |
| 最新版本 | **v0.9.0（2026-08-17）**，发布博客 2026-08-28；**v0.10 目标为 2026 年 9 月** |
| License | Apache-2.0 |
| 子仓库 | `llm-d/llm-d-router`（338★，原 `llm-d-inference-scheduler`）、`llm-d/llm-d-kv-cache`（177★） |

#### KV Cache 管理的三大支柱 + 一条组合

llm-d 官方 KV Cache Management 文档把它拆成：

**(1) 前缀缓存感知路由（Prefix-Cache Aware Routing）** —— 由 **EPP**（Endpoint Picker）实现，**两套实现并存**：

| | 近似（Approximate） | 精确（Precise） |
|---|---|---|
| 组件 | `approx-prefix-cache-producer`（DataProducer）+ `prefix-cache-scorer`（Scorer） | `token-producer` + `precise-prefix-cache-producer` + `prefix-cache-scorer` + **KV-Cache Indexer** |
| 原理 | EPP 内无 tokenizer，用**字符→token 比例**近似；按固定块（如 16 tokens）切分并做**滚动哈希链**；EPP 维护"哪些前缀哈希最近发给了哪些 Pod"的内存 LRU 索引，路由后**假设**该 Pod 已持有该前缀 | 通过 vLLM HTTP render endpoint（`/v1/completions/render`，`vllm launch render` sidecar 或共享 render Service）拿**精确 token id**；模型服务器每次缓存变化都通过 **ZMQ 发 `KVEvents`**；indexer 维护全局一致的 `{ModelName, BlockHash} → {PodID, DeviceTier}` 视图 |
| 精度 | 启发式，可能与引擎真实状态漂移 | 100% |
| 依赖 | 无 | vLLM render endpoint + ZMQ + 引擎支持发事件 |
| P/D 支持 | 基础 | 原生（能定位需要传输的具体块） |

> ⚠️ 旧版 gRPC-over-UDS tokenizer sidecar（`udsTokenizerConfig`）**已废弃**，将在未来版本移除。

**(2) KV-Cache Indexer** —— "可观测性"层：

- Index 持有 `block key → pods` 映射。模型服务器（目前 vLLM 与 SGLang）发三类事件：**`BlockStored`**（含 chained parent hash、token chunk、LoRA ID/name、多模态 extra keys）、**`BlockRemoved`**（含 device tier / attention group）、**`AllBlocksCleared`**（如 RL 权重 rollout 场景，indexer 丢弃该 Pod 全部条目）。
- **两种投递模式**：**集中式**（所有 Pod `zmq.PUB` 连到 EPP 单端点，`zmq.SUB`，适合单 EPP 副本）与 **Pod 发现**（每个 Pod 自己 bind，EPP 通过 K8s label selector 发现并建立逐 Pod 订阅 —— **active-active 多 EPP 必须用这种**，每个副本独立订阅每个 Pod，各自收敛到相同索引）。
- **索引后端**：**In-Memory（默认，两级 LRU：外层按 block hash、内层为每块的 pod 列表；默认 1 亿 key × 10 pod entry）**、**Cost-Aware Memory**（Ristretto，带准入控制与按字节成本驱逐，适合多模态/变长 LoRA 元数据）、**Redis / Valkey**（外部服务，跨副本强一致但增加网络跳数并耦合可用性；文档明确说**通常没必要**）。
- **打分**：Scorer 找的是每个候选 Pod 上请求块序列的**最长连续前缀**（因果注意力决定块 `i` 依赖 `0..i-1`，链断即不可用）。**分层加权：默认 `gpu = 1.0`、`cpu = 0.8`；同一块在多层命中时取最大权重。** 分数归一化到 [0,1] 后与队列深度、KV 利用率等 scorer 在 **Filter → Score → Pick** 管线中组合。
- **推测索引（Speculative Indexing）**：确认事件在路由之后才到达，连续同前缀请求会破坏亲和性。开启后（**生产推荐**）在路由决策后立即向 Index 插入短生命周期的预测条目（P/D 场景下含选中的 prefill pod），直到确认的 `BlockStored` 到达或 **TTL（默认 2s）** 过期。
- **多模态 / LoRA / 混合注意力**：多模态内容哈希折进 block key 链（vLLM 在 `BlockStored` 上发 `extra_keys`）；`LoraName` 存在时替换 base model name 参与 key 派生；**混合注意力（full / sliding-window / linear）打分仍在进行中**（需要把前缀匹配分类为 full / partial / miss）。

**(3) KV Offloading** —— "容量"层，**两种集成模式**：

- **原生路径**：vLLM `OffloadingConnector` 直挂 CPU RAM，或通过 **llm-d FS backend**（`llmd_fs_backend`，作为 `SharedStorageOffloadingSpec` 插件）落共享文件系统。FS backend 特性：**文件系统无关**（标准 POSIX，可用 CephFS / Lustre / IBM Storage Scale / 本地 NVMe）、跨实例跨节点共享、重启持久化、完全异步 I/O、多线程 NUMA 感知、默认走 GPU DMA。配置项：`shared_storage_path`（默认 `/tmp/shared-kv`）、`block_size`（默认 256 tokens）、`threads_per_gpu`（默认 64）。⚠️ 该连接器**不做清理与驱逐**，需由存储系统或外部控制器负责（参考实现：`pvc_evictor`）。
- **树外连接器（out-of-tree）**：第三方 KV 引擎通过模型服务器的 KV connector API 接入，自己负责索引/内存管理/分层/驱逐/远端存储。llm-d **已发布 LMCache 与 Mooncake Store 的部署指南**，并说明 KVBM 及其他兼容引擎"在服务栈侧开箱即用"。
  - **`MooncakeStoreConnector`**（注意与 PD 用的 `MooncakeConnector` 区分，二者共用 TE 但用途不同，可通过 `MultiConnector` 组合）：Mooncake **Master** 管对象元数据/副本放置/租约/驱逐（gRPC 50051、HTTP 8080、Prometheus 9003；`eviction_high_watermark_ratio` 默认 0.95、`eviction_ratio` 0.05、`default_kv_lease_ttl` 5000ms、`default_kv_soft_pin_ttl` 1800000ms、快照 60s）；**Mooncake Client** 只在 standalone-store 模式使用，持有 CPU DRAM + 可选 SSD（写同步落 DRAM、异步持久化到 SSD；读先 DRAM 后 SSD；DRAM 到高水位时 Master 指示溢写到 SSD）。**embedded 模式**每个 vLLM rank 进程内贡献 DRAM（`global_segment_size > 0`）；**standalone-store 模式**外部 Client 拥有存储（`global_segment_size = 0`，`enable_offload: true` 开 SSD 层）。
  - **关键坑**：KV 块用 vLLM block hash 做**内容寻址键**，因此所有共享同一 Store 的 vLLM 实例**必须设置相同的 `PYTHONHASHSEED`**（例如 `PYTHONHASHSEED=0`），否则同 token 算出不同 hash、永远无法共享。
  - 调度侧统一契约：**所有树外引擎都通过 KV-Events 与 llm-d 集成** —— 无论底层缓存是哪个后端，indexer 都靠事件维护全局视图。

**(4) P2P KV Cache Sharing（2026-08 新 Well-Lit Path）** —— 组合三大支柱的"共享"层：

- 机制：EPP 从自己的前缀索引给出**源决策** —— 若某个 peer 持有的缓存 token 比被选中执行请求的 endpoint 多出 `minCachedTokenDelta` 以上（足以覆盖实测的传输交叉点），EPP 把它指定为 KV source；**平局或自匹配则保持本地**。在近乎并列的持有者间，EPP 按**等待队列深度反向加权**采样源，把并发 pull 分散到多个 producer。
- 每个 vLLM 实例可同时是 **consumer**（拉取）与 **producer**（服务），角色**按请求**选择，**没有固定 prefiller/decoder 进程**。consumer 发块哈希 → producer 回报可用块 → producer 通过 **NIXL** 完成数据面写入。**两个 GPU 都不参与这次拷贝**（CPU 到 CPU），所以服务一个 peer 只消耗 producer 的 CPU 内存带宽与网络，不占 GPU 算力。
- 默认关闭，因为交叉点与 CPU tier / fabric 容量是部署相关的。

#### 实测数字

**[README 汇总，含出处博客]**
- **3× 输出吞吐、2× TTFT ↓**：前缀缓存感知路由 vs 轮询（Llama 3.1 70B，4×AMD MI300X）—— 出处为 **Tesla + Red Hat** 博客，原文表述为"某次部署上观察到 3× 输出 tokens/s 和 2× TTFT 下降"。⚠️ 该博客**未给出绝对 tokens/s、TTFT、并发、输入输出长度或数据集**。
- **TTFT 与 ITL 各降 40%**：预测延迟调度 vs 启发式（Google，NVIDIA GPU）。
- **tokens/s 最高 +70%**：P/D 分离 vs 标准 vLLM（GPT-OSS on B200，AWS）。
- **吞吐 +10–30%**：同构基础设施上的分离式服务（GPT-OSS-120B / Llama 3.3 70B on MI300X，Oracle）。
- **50k tokens/s 集群吞吐**：宽专家并行（16×16 B200，约 **3.1k tok/s/GPU**）。
- **13.9× 吞吐**：分层 KV offloading，250 并发用户 vs 仅 GPU（4×H100）。

**[P2P 博客，2026-08-15，含可复现脚本]**
传输成本交叉点（单 pod 对，CPU-to-CPU over NIXL(UCX)，RDMA/IB 暴露给两个 pod）：

| 前缀 token | 重算 | P2P pull | 差异 |
|---|---|---|---|
| 2,048 | 78 ms | 35 ms | −56% |
| 8,192 | 250 ms | 57 ms | −77% |
| 16,384 | 510 ms | 86 ms | −83% |
| 32,768 | 1,173 ms | 165 ms | −86% |
| 49,152 | 1,988 ms | 235 ms | −88% |

753B GLM 测试台（KV footprint ≈ 93 KB/token）：8K 附近持平，12K 时 pull 快 27%，24K 时快 61%（24K 前缀 ≈ 2.1 GiB KV）；短前缀场景 pull 有 1.2–1.3 s 的下限，交叉点约 **8.7K tokens**。

GLM-5.2-FP8，32×H200 P/D 分离，AIPerf trace，并发 64（2,048-token pull 阈值）：

| 路由策略 | 成功 req/s | vs 基线 | 中位 TTFT |
|---|---|---|---|
| 近似路由（无 P2P） | 基线 | — | — |
| 近似路由 + P2P | 3.023 | +4.6% | 2.184 s（−18.9%） |
| 精确路由 | 2.927 | +1.3% | 2.899 s（+7.7%） |
| **精确路由 + P2P** | **3.210** | **+11.1%** | **2.018 s（−25.0%）** |

三次重复对比平均：**成功吞吐 +9.6%、输入 token 吞吐 +11.8%**。另外 Llama-3.1-8B 共享前缀池的纯 P2P A/B：8 req/s 下中位延迟 −43%；近饱和时机群上限 +22%、峰值 token 吞吐 +32%。

> 官方明确说明**这不是普适加速**：当路由已产生本地命中时 P2P 正确地什么都不做；当局部性与负载均衡冲突时，它把数秒的重算换成一次 peer 传输。

**[llm-d-kv-cache 的基准数字（此前未列出）]**：TTFT **p90 = 0.275 s**，对比随机路由 **84.6 s**、负载感知路由 **78.3 s**；相同 QPS 下输出吞吐 **5,650 vs 2,895 tok/s** —— 且它**使用的是更少的 KV 缓存（49.8% vs 76.5%）**，即这是**一次放置（placement）胜出，不是利用率胜出**。⚠️ 该 KV-Cache Indexer 的代码**已从 `llm-d-kv-cache` 迁移到 `llm-d-router`**。

#### v0.9（2026-08）新增的 KV 相关能力

- **Router 高可用**：多 EPP 拓扑，非 leader 副本**保持 datastore 已填充并正常路由**（而不是返回 503）；新增 `--drain-timeout` 支持优雅关闭。
- **插件稳定生命周期**：Alpha / Beta / Stable 分级；Alpha 插件必须显式 `--allow-experimental-plugins` 才能启用；启动时自动校验插件依赖。
- **流控默认值**：`defaultRequestTTL` 默认 60s、per-band `maxRequests` 默认 5000；空池返回 503、可重试背压返回 429。
- **DisaggregatedSet 版本路由**：滚动更新时 router 知道 pod 属于哪个 revision，避免 prefill pod 把 KV 发给不同 checkpoint 的 decode pod。
- **GPU 利用率感知路由**（DCGM extractor）、**session affinity（`session_id` 策略）**、**header-based profile handler**；**sticky-until-saturated 成为所有 guide 的默认策略**。
- **KEDA 取代 Prometheus Adapter** 成为自动扩缩基础；EPP 暴露队列深度、in-flight 请求数、**KV cache 压力**作为 KEDA 兼容信号。
- **端到端 OTel tracing** 贯穿 P/D 传输链（请求到达 → prefill 调度 → KV 传输 → decode 完成）。
- 新增 **P2P KV cache sharing** well-lit path；**Fast Model Actuation (FMA)** 用 ModelExpress P2P RDMA 权重传输绕开磁盘；**SGLang 新增受管 Lustre L3 offloading 与原生文件系统 offloading**；默认 vLLM 镜像升到 **v0.26.0**。

#### 该项目的公开路线（对"标准化"很重要）

v0.10（目标 2026 年 9 月）四条方向中的两条与 KV 直接相关：

1. **A standardized model server interface** —— 控制面需要一个**通用的模型服务器 API**来查询引擎能力、管理生命周期、配置运行时参数，**与底层是 vLLM / SGLang / TensorRT-LLM 无关**。
2. **KV-cache observability and intelligence** —— 分层缓存加深后，运维需要**命中率、各层利用率、驱逐模式**的可见性；目标是 **统一的 KV cache 可观测性框架**与更智能的缓存管理策略。

---

### 3.5 SGLang HiCache（sgl-project/sglang）

| 项 | 值 |
|---|---|
| 定位 | **引擎内置的三级分层 KV 缓存**，RadixAttention 的扩展 |
| 维护方 | SGLang 社区（LMSYS 系） |
| Stars（仓库） | **35,982 / 8,871** |
| 最新版本 | **v0.5.19（2026-09-05）** |
| License | Apache-2.0 |
| 原始公告 | LMSYS 博客《SGLang HiCache: Fast Hierarchical KV Caching with Your Favorite Storage Backends》，2025-09-10 |

#### 机制

**三级层次（L1/L2/L3），共享范围是设计与排障的关键**：

| 层 | 介质 | 作用域 | 跨实例共享？ |
|---|---|---|---|
| **L1** | GPU HBM | 单个推理实例 | ❌ |
| **L2** | Host DRAM | 单个推理实例（本节点） | ❌ |
| **L3** | 存储后端（`file` / `mooncake` / `hf3fs` / `nixl` / `aibrix` / 自定义 `dynamic`） | 取决于后端配置 | 仅当后端配置为共享时 |

> **官方明确纠正了一个常见误解**：**HiCache 无法把多台机器的主机内存池化成一个大 L2**。调大 `--hicache-ratio` / `--hicache-size` 只是把**每个实例自己**的 L2 变大；跨实例复用是 L3 的职责（需要 `--hicache-storage-backend`）。`file` 后端默认写 `/tmp/hicache`（`SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR` 可覆盖），除非该路径是共享挂载，否则也是节点本地的。

**HiRadixTree（元数据组织）**：RadixAttention 的 radix tree 中每个节点对应一段连续 token 的 KV，路径即请求前缀。HiRadixTree 在此基础上**记录该 KV 存在哪里**（本地 GPU / CPU / L3，或同时多层）；本地存有精确元数据（含确切地址），但**为降低开销，不为 L3 保存或持续同步元数据**，访问 L3 时**实时向后端查询**（数据是否存在、在哪个 server 的哪个位置）。

**三个关键操作**：

1. **Local Match**：从 root 遍历 HiRadixTree 匹配 token 前缀；`page_size > 1` 时按页粒度匹配；若匹配在某节点序列中间终止，**自动分裂节点**以建立精确边界。返回请求的连续前缀，前段在 L1、后段在 L2。**只遍历树、不拷数据，因此极快。**
2. **Prefetch from L3**：本地未命中的部分先查 L3 元数据；**L3 命中长度超过阈值（默认 256 tokens，可配）才触发预取**。三种终止策略：
   - `best_effort`：GPU 能开始 prefill 就立即终止（超低延迟场景）；
   - `wait_complete`：等全部预取完成（追求高命中率）；
   - `timeout`：限时终止（**生产推荐**）。超时公式 `timeout = min(prefetch_timeout_max, prefetch_timeout_base + prefetch_timeout_per_ki_token × num_token_to_fetch / 1024)`，默认 base 2 s、每 1024 token 加 0.1 s、上限 30 s。
3. **Write-back**：三种写策略 —— `write_through`（每次访问立即回写下一级，带宽充足时收益最强）、`write_through_selective`（访问频次超阈值才回写，只备份热数据）、`write_back`（仅在被上层驱逐时回写）。**跨实例共享**：L2→L3 时只传输 L3 中尚不存在的数据。

**数据搬运优化**：

- **零拷贝**：L2→L3 可直接传内存地址与大小；
- **页粒度 + 三种布局**：`layer_first`（与 GPU 计算 kernel 兼容，GPU 默认）、`page_first`（I/O 优化，一页内所有 KV 连续，可作为单个对象零拷贝传给 L3）、`page_first_direct`（一页内同一层的所有 token 聚在一起，使 L2→GPU 可按"页-层"聚合传输；**注意 GPU 计算天然是 layer-first**，page_first 从 L2 传 GPU 时须按"每 token 每层"传，page_first_direct 缓解了这一点）；
- **CPU→GPU 优化**：**按层重叠**（计算第 N 层时并发加载第 N+1 层的 KV）；在 `cudaMemcpyAsync` 之上实现了**GPU 辅助 I/O kernel，比基线最多快 3×**；
- **MLA 专用优化**：MHA 多 TP 下每个 rank 持 1/tp_size 的 KV，而 MLA 下**所有 rank 持有完整且相同的 KV**，因此 MLA 回写只由**一个 rank 发起**，避免冗余存储。

**多 rank 同步**：TP 场景下用 `all_reduce(op=min)` 保证各 rank 对"是否达到预取阈值"和"实际取回的前缀长度"认知一致。

**异构 TP 支持**：`--hicache-storage-backend-extra-config '{"tp_lcm_size": 8}'` —— 不同 TP 规模（如 tp=4 与 tp=8）的部署可共享同一 L3 命名空间；MHA + Mooncake + page_head 布局下按 `tp_lcm_size` 切分 head shard 使 key 可跨异构 TP 复用。

**运行时装配**：除启动参数外，SGLang 还支持通过 **HTTP admin endpoint 在运行时 attach/detach HiCache 存储后端，无需重启**。

**PD 分离协同**：HiCache 可在 prefill 与 decode 两侧启用。两种配置：**Prefill-only HiCache**（在 prefill 实例间共享 KV）与 **Full HiCache with async offloading**（prefill 侧开 HiCache、decode 侧开异步 offload，使 prefill 能复用 decode 产生的 KV，服务多轮对话）；后者用 `--disaggregation-decode-enable-offload-kvcache`。

#### L3 后端与开放接口

**统一接口 `HiCacheStorage(ABC)`**，后端只需实现 `get(key)` / `exist(key)` / `set(key, value)` 三个功能，其余调度与同步由中央 cache controller 负责。已内置：

| 后端 | 说明 |
|---|---|
| **Mooncake** | RDMA + 多网卡零拷贝 |
| **DeepSeek 3FS（HF3FS）** | K8s 原生分布式存储，operator 部署 |
| **NIXL** | 统一访问多种存储插件（含 3FS、GDS、S3 兼容对象存储） |
| **AIBrix KVCache** | "生产可用的 KVCache Offloading 框架"，内存分层 + 低开销跨引擎复用 |
| **HiCacheFile** | 参考实现 |
| **EIC** | 火山引擎 Elastic Instant Cache（`--hicache-storage-backend eic`） |
| **dynamic** | 通过 `--hicache-storage-backend-extra-config` 指定 `backend_name` / `module_path` / `class_name`，加载自定义后端 |
| **其他已注册后端** | 权威清单是 `arg_groups/fields/memory.py` 的 `choices` 数组：**12 个取值 = 11 个内置实现 + `dynamic`**，即 `file, sim, mooncake, npu_memcache, hf3fs, nixl, aibrix, dynamic, eic, simm, mori, shm`（`npu_memcache` 面向昇腾 NPU，`mori` 用于 AMD 侧 P/D 传输）。⚠️ **不要把 `flexkv` / `lmcache` / `mmap` 当作已注册后端** —— 它们不是 choices。⚠️ 另一个易踩的坑：**`--help` 的帮助文本从未更新，把 ByteDance 相关后端（`eic`/`simm`/`mori`/`shm`/`sim`）隐藏掉了** |
| **LMCache** | 作为 **HiCache 的替代方案**整体启用（`--enable-lmcache` + `--lmcache-config-file`） |

此外 **FlexKV** 在 SGLang 主线（PR #29701）提供 `--enable-flexkv` 的原生 CPU/SSD offload（v0.5.16+）。

#### 实测数字

**[LMSYS 官方博客，含复现脚本]**
- 官方自己测得：**最高 6× 吞吐提升、最高 80% TTFT 下降**，与社区报告的数字相近；并给出两套可复现 benchmark（long-context `bench_long_context.py` + 多轮 `bench_multiturn.py`）。
- 数据面：GPU 辅助 I/O kernel 使 CPU–GPU 传输**最高 3×**；page-first 布局 + 零拷贝使典型部署下吞吐**最高 2×**。

**[社区实测，同一博客引用]**
- **Novita AI**：Qwen3-Coder-480B 编码 agent（对话常超 25K tokens、约 8 轮/会话），**HiCache + DeepSeek 3FS KVStore** 使会话平均 **TTFT 下降 56%**、推理**吞吐翻倍**、命中率 **40% → 80%**。
- **蚂蚁集团**：DeepSeek-R1-671B，PD 分离部署，内部通用 QA 在线请求采样，**HiCache + Mooncake** 在缓存命中时**平均 TTFT 降低 84%**（vs 全量重算）。

**[Dynamo 官方文档给出的跨引擎约束]**：SGLang 需 **v0.5.11+** 才会发 host-tier（`CPU_PINNED`）事件；**v0.5.13+ 配 Mooncake** 以避免 bundled-Mooncake 崩溃。

---

## 4. vLLM 原生 KV Cache 能力（2026 年状态）

| 项 | 值 |
|---|---|
| 仓库 | `vllm-project/vllm`，**91,813★ / 22,221 forks** |
| 最新版本 | **v0.29.0（2026-09-09）** |
| License | Apache-2.0 |
| 生产栈 | `vllm-project/production-stack`，**2,571★**，最新 **vllm-stack-0.1.12（2026-07-24）** |

vLLM 在 2026 年把原本由外部 KV 层承担的很多职责**收进了内核**。这是全年最重要的结构性变化之一。

### 4.1 KV Connector API

- 抽象基类 `KVConnectorBase_V1`，通过 `--kv-transfer-config` JSON 配置：`{"kv_connector": ..., "kv_role": "kv_both"|..., "kv_connector_extra_config": {...}}`，或 `kv_connector_module_path` 加载**树外 connector**（如 PegaFlow 的 `pegaflow.connector`）。
- **`MultiConnector`**：把多个 sub-connector 串起来，各自独立；用于**同时**做 PD 分离与分布式 KV 池（Mooncake 正是这样组合 `MooncakeConnector` + `MooncakeStoreConnector`）。
- **vLLM 生产栈的 router** 目前支持 round-robin、session-ID 路由与 **prefix-aware 路由（README 标为 WIP）**。

### 4.2 原生 Offloading：`OffloadingConnector`

`vllm/v1/kv_offload/` 下的两套 spec：

- **`CPUOffloadingSpec`（默认，单层）**：完成的 GPU 块拷入 **pinned host memory**；GPU↔CPU 用 **DMA（`cudaMemcpyAsync`）**异步执行，不占 CPU/GPU 核。可用顶层便捷开关 `--kv-offloading-backend native --kv-offloading-size <GB>`。
- **`TieringOffloadingSpec`（多层）**：一个 **CPU primary tier + 一个或多个 secondary tier**。**只有 CPU primary 有直接 GPU 访问**，所有 GPU↔secondary 传输都经 CPU primary 暂存。
- 操作单位是 **chunk**（覆盖一组 token 的固定大小 KV 片段；默认一个 chunk 对应一个 accelerator block，`blocks_per_chunk` 可放大以产生更大 I/O）。

**关键参数**：

| 参数 | 默认 | 说明 |
|---|---|---|
| `spec_name` | `CPUOffloadingSpec` | 多层需 `TieringOffloadingSpec` |
| `cpu_bytes_to_use` | — | **所有 worker 合计**的 host 内存总量（非 per-worker） |
| `blocks_per_chunk` | 1 | 与 `block_size` 二选一 |
| `eviction_policy` | `lru` | 内置 `lru` / `arc`，或自定义 `CachePolicy` 名 |
| `store_threshold` | 0 | 块被 offload 前的最小 lookup 次数（多层 spec 拒绝 ≥2） |
| `max_tracker_size` | 64000 | lookup tracker 最大条目 |
| `secondary_tiers` | `[]` | 有序列表，tier 0 先于 tier 1 查询 |
| `self_describing_kv_events` | false | 见下 |

**Secondary tier 类型**：

- **`fs`（文件系统）**：把块写到目录；⚠️ 块大小是聚合后的 chunk。
- **`obj`（对象存储）**：通过 **NIXL OBJ backend** 落 **S3 兼容对象存储**；凭据留空时回退到 AWS SDK 默认凭据链（支持 K8s 上的 workload-identity）。key 沿用与 FS 相同的 run-configuration digest 方案；**共享 bucket 的实例对相同内容产生相同 key**（建议固定 `PYTHONHASHSEED`）。
- **`p2p`（RDMA 点对点）**：vLLM 实例之间通过 **NIXL** 直接交换块。**每个实例是"对称 peer"**，按请求充当 consumer 或 producer。控制 socket 由 `VLLM_P2P_SIDE_CHANNEL_HOST`（默认 `localhost` —— **跨主机必须显式设为可路由 IP/pod IP**）与 `VLLM_P2P_SIDE_CHANNEL_PORT`（默认 5710，实际端口 = base + `data_parallel_index`）。角色键：`remote_decoder`（producer）、`remote_kv_source`（consumer，带 `kv_request_id` / `remote_host` / `remote_port`）。**P2P tier 自己不决定从哪个 peer 拉 —— 那是编排层（router/EPP）的职责**，通过请求的 `kv_transfer_params` 驱动。producer 的 `unbound_store_timeout_s`（默认 60）到期后释放块以免长期 pin 住 primary tier 槽位。

**自定义 secondary tier**：实现 `SecondaryTierManager`（`vllm/v1/kv_offload/tiering/base.py`）即可，**无需 fork 或打补丁 vLLM**。

**性能要点（官方文档）**：vLLM **0.12.0** 引入的连续内存布局把同一层的所有数据聚进单个物理块，使传输吞吐提升 **4–5×**。容量参考：CPU RAM 约 **250 GB/GPU**（节点级），共享存储 TB+（集群级）。

### 4.3 KV Events（事实标准的事件面）

`vllm/distributed/kv_events.py`（源码级已验证）：

- **介质常量**：`MEDIUM_GPU = "GPU"`、`MEDIUM_CPU = "CPU"`、`MEDIUM_STORAGE = "STORAGE"`。
- **事件类型**（`KVEventBatch.events` 的联合）：
  - **`BlockStored`**：`block_hashes`、`parent_block_hash`、`token_ids`、`block_size`、`lora_id`（已废弃，保留兼容）、**`medium`**、**`lora_name`**、**`extra_keys`**（每块一项：MM 标识、LoRA name、`cache_salt`、prompt embedding hash 等，供外部消费者重建 block hash）、**`group_idx`**、**`kv_cache_spec_kind`**、**`kv_cache_spec_sliding_window`**（供消费者识别混合注意力分组）、**`locality`**（`LOCAL`/`REMOTE`，相对发布者）、**`ownership`**（若由某个 secondary offloading tier 生成）、**`session_id`**（触发该 store/reuse 的请求上下文）。
  - **`BlockRemoved`**：`block_hashes`、`medium`、`group_idx`、`locality`、`ownership`。
  - **`AllBlocksCleared`**：无字段（Pod 整体重置，如 RL 权重 rollout）。
- **批次**：`EventBatch` 含 `ts`、`events`、`data_parallel_rank`。
- **多 worker 聚合**：`KVEventAggregator` 只返回**所有 worker 都发出过**的事件（按事件哈希计数）；`KVConnectorKVEvents` 是 connector 的抽象容器（`add_events` / `aggregate` / `increment_workers` / `get_all_events` / `get_number_of_workers` / `clear_events`）。
- **发布与回放**：`ZmqEventPublisher` 在后台线程跑两个 socket —— **PUB**（默认 `tcp://*:5557`）流式发带单调序号的 `KVEventBatch`；**ROUTER**（可选，如 `tcp://*:5558`）处理消费者的回放请求。发布者保留最近 `buffer_steps`（**默认 10,000**）的**已序列化** msgpack 批次；消费者发现空洞就把缺失起始序号发给 ROUTER，发布者**线性扫描**缓冲并回放，以 sentinel（`seq=-1, payload=empty`）结束。**消费者按序号去重；若空洞早于缓冲窗口，消费者必须靠别的方式重建状态（vLLM 没有内置的初始同步）。**
- **事件里携带 token_ids** 的直接后果（RFC #20492 的原话）：外部索引可通过"token → 不同 hash → vLLM hash"的映射实现，**避免引入可复现哈希与配置同步**，但代价是**索引与查找复杂、且每个事件都要传输 32-bit token id 带来网络开销**。

### 4.4 KV offloading 的分层感知事件

`TieringOffloadingSpec` 的 secondary tier 可以 `enable_kv_events: true`（需全局开启 `--kv-events-config`）：

- **`fs` 与 `obj` 层都发 hash-only 的 `BlockStored`，medium 都用粗粒度的 `STORAGE`** —— **medium 不区分文件系统与对象存储**。要恢复位置语义，需在 tier 条目上设置可选的 **`locality`（`LOCAL` / `REMOTE`）**字段；**vLLM 不会从 tier 类型推断**（所以 `obj` tier 不隐含 REMOTE）。该元数据只描述 tier 属性，**不表示消费者已经能路由到那些块**。
- 与 Dynamo 的版本门槛：**vLLM v0.24.0+** 才会出自描述事件；更早版本会发 router 静默丢弃的占位 CPU 事件（offload 本身仍在引擎侧工作，但 router 只看得到 GPU 层）。

### 4.5 常见误解更正（会直接导致错误陈述，务必留意）

1. 🚨 **`--cpu-offload-gb` 卸载的是模型权重，不是 KV。** 它走 `UVAOffloadConfig`。真正的 KV offload 开关是 **`--kv-offloading-size` / `--kv-offloading-backend`（`native` | `lmcache`）**，或经 `--kv-transfer-config` 使用 `OffloadingConnector`。把前者当成"KV offload 参数"是最常见的错误之一。
2. **vLLM 的 v0 KVConnector API 已被完全删除**（`v0/` 目录 0 个文件，`v1/` 70 个）—— 所有连接器都必须实现 `KVConnectorBase_V1`。
3. **TensorRT-LLM 的驱逐策略是"优先级 LRU"**（priority 0–100，默认 **35**，对应 `secondary_offload_min_priority`），**不存在名为 "gen-first" 的驱逐策略** —— "gen-first" 是分离式调度工作流的名字。
4. **`llama.cpp` 的 `llama_kv_cache_*` 已不存在**，现为 **`llama_memory_*`**；**`--defrag-thold` 已废弃且无效**。
5. **HuggingFace TGI 已进入维护模式**（README 顶部横幅导向 vLLM/SGLang；最后推送 **2026-03-21**）。其 prefix caching 是 **`PREFIX_CACHING` 环境变量**，不是 CLI flag。
6. **KVarN 是 vLLM 的 fork，未合入主线**，且其 "1.3× 吞吐" 的宣传与它自己表格里的 **0.94×** 相矛盾。
7. **仓库路径已变更**：`jd-opensource/xllm` → **`xLLM-AI/xllm`**；`curvineio/curvine` → **`CurvineIO/curvine`**；`vllm-project/vllm-production-stack` → **`vllm-project/production-stack`**；`YaoJiayi/CacheGen` 已 **404**；`dphnAI/sonar` 是 `aphrodite-engine` 改名而来（**1,859★**）。
8. **已归档/停滞**：**`ray-project/ray-llm` 已 ARCHIVED**；`intel/neural-speed` 自 2024-08 停滞；`bentoml/OpenLLM` **约 17 个月无新 release**。
9. **MindSpore PD 分离的 GitHub 镜像不是权威仓库**（6★ / 0 fork，PyPI 指向 Gitee），**不要据此引用**。
10. ⚠️ **`ai-dynamo/nixl` 与 `ai-dynamo/dynamo` 的 GitHub license 字段是 NOASSERTION**（实际为 Apache-2.0，以仓库 LICENSE 文件为准）；`FMInference/H2O`、`NVlabs/Atom`、`YaoJiayi/CacheBlend` 的 license **未被自动识别**（应记为"未检出"，而非"无许可"）。

---

## 5. 其他重要框架（次重点）

> 本节细节受篇幅限制，完整笔记见 `kvcache-research/notes_other_oss.md`、`notes_china_vendors.md`、`notes_storage_cloud.md`。

### 5.1 AIBrix（vllm-project/aibrix）

- **5,089★ / 694 forks**，Apache-2.0，2024-06-10 创建，ByteDance 起源，现于 `vllm-project` 组织下开发。最新 **v0.7.0（2026-06-18）**。
- **`KVCache` CRD**：`kvcaches.orchestration.aibrix.ai`，`orchestration.aibrix.ai/v1alpha1`。⚠️ **不存在 `ModelRouter` CRD** —— 路由是 Envoy Gateway ext-proc 网关插件。
- **两层模型，层次独立**：**L1 = 引擎 pod 内 DRAM**（进程内，默认容量 **10 GB**，默认驱逐 **S3FIFO**，也支持 `LRU`/`FIFO`）；**L2 = 引擎 pod 外的分布式 KV 集群**（由 `KVCache` CRD 供给）。可只跑 L1 / 只跑 L2 / 都跑；都跑时 `HOT`（默认）ingestion 策略把 L1 热块写入 L2。
- **L2 后端**：`INFINISTORE`、`HPKV`、`PRISKV`、`ROCKSDB`、`EIC`、`SHFS`、`MOCK`；InfiniStore 支持 RDMA（默认）或 TCP；支持 **GDR（GPU Direct RDMA）**。L2 成员通过 **meta service**（CRD 管理集群用 `redis`）发布，30 s 刷新。
- **策略旋钮**：key builder `RAW`/`ROLLING_HASH`（默认）/`SIMPLE_HASH`；ingestion `ALL`/`HOT`（默认）/`EVICTED`；L2 placement 默认 `SIMPLE`；**double-get 启发式**（缺失 ≥4 块且缺失率 ≥10% 才发第二次 L2 get，是显式的尾延迟保护）；per-token L2 超时 **20 ms**。
- **接入点**：vLLM `AIBrixOffloadingConnectorV1Type3`；**SGLang HiCache 的原生 L3 后端之一**（`--hicache-storage-backend aibrix`）；也可作为**独立组件**使用，无需整套 AIBrix。
- **KV 事件同步**：vLLM 通过 ZMQ 发事件（`--enable-kv-cache-events --kv-events-publisher=zmq ... --kv-events-buffer-steps=10000`），网关维护全局前缀索引按真实缓存状态路由。文档明确划分：**事件同步 = "哪个引擎持有哪些前缀"（路由）；offloading = "搬运缓存内容本身"**。
- **实测数字**：白皮书（arXiv 2504.03648）称分布式 KV cache 带来**吞吐 +50%、推理延迟 −70%**；v0.2.0 博客（Bird Text2SQL）称峰值吞吐 **+~50%**、平均/P99 TTFT **−~60%/−~70%**；单节点 P/D 博客给出命中率–TTFT 曲线：命中率 60% 时 TTFT **805 ms（−48.55%）**，TPOT 保持平稳（"KV 复用不给 decode 阶段引入额外开销"）；AIPerf 多轮测试中最佳配置 **RPS 1.55（3.10× 加速）**，而纯 prefix-cache 基线的 TPOT 因 prefill/decode 争抢**劣化到 168 ms**。⚠️ 生产 GPU 节省数字（峰值省约 1,600 张 L20）为厂商自报，无公开工件可核。⚠️ 仓库内 `benchmarks/scenarios/kvcache/README.md` 仍写"Coming Soon!"。

### 5.2 KServe（kserve/kserve）

- **5,911★ / 1,671 forks**，Apache-2.0，**CNCF Incubating**（TOC 投票公告 2025-11-11，⚠️ 该公告内部自相矛盾地又称 "September 2025"，未能定论）。最新稳定 **v0.20.0（2026-08-06）**；最新 tag **v0.21.0-rc0（2026-09-10）**。
- **`LLMInferenceService` CRD**（v0.16.0 引入 `v1alpha1`，v0.17.0 加 `v1alpha2`）。**最重要的结构事实：`LLMInferenceServiceSpec` 内联了 `WorkloadSpec`**，所以 `replicas` / `template` / `parallelism` / `scaling` / **`kvCacheOffloading`** 都在 `spec.` 直下，而不是 `spec.workload.` 下（⚠️ 官方 docs 页面此处写错）。
- **`spec.kvCacheOffloading`**（v0.20 新增，v1alpha2）—— Go 类型直接映射 vLLM 的 `OffloadingConnector`：`cpu resource.Quantity` → `kv_connector_extra_config.cpu_bytes_to_use`；`evictionPolicy` 默认 `lru`，可选 **`arc`**；`secondary[]` 目前仅支持 fileSystem tier（`emptyDir` | `pvc.spec` | `pvc.ref`，挂载路径 `/mnt/kv-cache-0`、`-1`…）。级联为 **GPU → CPU RAM → disk**，控制器自动渲染 `--kv-transfer-config`。P/D 场景设在 **prefill** spec 上。**RWX PVC（如 CephFS）可让多副本共享缓存。**
- **路由分层**：`spec.router.scheduler` 渲染 GIE 的 `InferencePool` + **EPP**。⚠️ KServe 出厂默认 EPP 配置走的是**近似路径**（`approx-prefix-cache-producer`、`inflight-load-producer`、`prefix-cache-affinity-filter`、`token-load-scorer`）；且**插件词表随版本变动且文档不一致**（出厂配置名与 v0.17 博客、架构文档三者互不匹配）。
- **版本绑定**：KServe 内置 llm-d **v0.6（0.18）→ v0.7（0.19）→ v0.8.0（0.20）**；GIE **v1.3.0（0.17）→ v1.5.0（0.20）**。⚠️ v0.21.0-rc0 未声明 llm-d 版本。
- **实测数字（需严格区分两个来源）**：
  - **Tesla 生产部署（唯一可辩护的生产数据点）**：Tesla 的 Scott Cabrinha / Sai Krishna 与 Red Hat 的 Yuan Tang / Robert Shaw 合著博客（2026-04-21），原文称"在某次部署上观察到 **3× 输出 tokens/s 提升与 2× TTFT 下降**"，配置为 **Llama 3.1 70B、4×AMD MI300X、TP=4、gpu-memory-utilization=0.90、`--max-model-len=65536`**。⚠️ **该博客未发布绝对 tokens/s、TTFT、并发、输入输出长度、数据集或压测工具**。
  - **llm-d 自己的 benchmark（由 Red Hat 复现）**：P90 TTFT "最高约 57× 更快"、token 吞吐 **约 4,400 → 约 8,730 tokens/s（约 2×）**、规模化吞吐 4.5k–11k tok/s、尾延迟约 −50%。⚠️ 该表格被文章自己标注为"基于 llm-d 项目发布的 benchmark"，**不是独立测量，也不属于 Tesla 的 MI300X 部署**。
- LMCache 在 KServe 中是**另一个** InferenceService 侧的分布式 KV 功能，**不要与 `spec.kvCacheOffloading` 混为一谈**。

### 5.3 阿里云 Tair KVCache（alibaba/tair-kvcache）

- **255★ / 58 forks**，Apache-2.0，**2025-12-29 创建**。⚠️ **无正式 release**（仅 `__binary-dependency-0.0.2`，2026-02-12）。商业产品见 <https://www.aliyun.com/product/kvcache>。
- **Tair KVCache Manager（KVCM）是全球 KVCache 元数据服务，不是数据存储**。最重要的架构性质（官方设计文档原话）：**"元数据操作走元数据面到 KVCM，实际 KVCache 数据搬运走数据面直连存储后端，二者不混。KVCM 只管理『数据在哪、能不能读写』，不经手数据本身。"**
- **三个平面**：元数据面（`GetCacheLocation`、`StartWriteCache`、`FinishWriteCache`、`RemoveCache`、`TrimCache`、`RegisterInstance` 等 —— **引擎热路径**）；数据面（`TransferClient` 直连存储后端，绕过 KVCM）；控制面（AdminService：存储增删、Instance Group、账号、配置快照、leader 操作）。
- **数据模型**：Storage（**NFS / 3FS / TairMemPool / Mooncake**）→ **Instance Group（配额单位）** → Instance（**KV 只在单个 Instance 内复用，不跨 Instance**；model 与 KV 配置每 Instance 唯一且不可变）→ Block（有**前缀依赖**）→ CacheLocation（状态机 `writing → serving → deleting`）→ LocationSpec（位置统一为 URI；`spec name` 用户可配以支持不同 TP / PP / **混合注意力**布局）。
- **两阶段写（可靠性）**：`StartWriteCache` 返回 `write_session_id` 与写入 URI（location 转 `writing`，带超时防并发写）→ `SaveKvCaches` 引擎直写后端 → `FinishWriteCache` 带 `success_block_mask` 回报，成功者转 `serving` 进入索引，失败者丢弃 → **"保证只有真正写成功的数据可被后续读取命中"**。
- **驱逐与容量**：Instance Group 维度有 `Quota`（硬上限）与水位（软上限触发驱逐）；驱逐模式含 **TTL / LRU / LFU** 等；跨 Instance 回收预算策略 `GROUP_LRU` / `USAGE_PROPORTIONAL` / `FIXED_PER_INSTANCE`；**删除完全异步**（元数据 CAS + 定时延迟 + 数据删除）；**分层迁移异步且与回收协调**，源 location 在 promotion 前会重新校验仍为 `SERVING`。
- **HA**：`LeaderElector` 基于 `CoordinationBackend`（memory/file/**redis**）的分布式锁；仅 Leader 服务读写；降级时停止新 GC/回收工作、排空 leader-only 请求。
- **元数据后端**：外部 KV 系统 **Valkey / Redis 或 RocksDB**；`MetaIndex` 提供 `Put/Delete/Update/Get` 与一等 **原子 `ReadModifyWrite(keys, ModifierFunc)`**；并发用**分片锁 + 批量对齐**（读不加锁、永不被阻塞；锁按分片升序获取防死锁）；另有 LRU 作为**元数据查询缓存**（写操作提交后失效对应项）。
- **重要：KVCM 不依赖 RDMA** —— "结合 3FS Master 等工作，Tair KVCM 可以仅使用 TCP 和推理引擎及后端存储进行交互，并不强依赖 RDMA 环境"。对只有 GPU 节点有 RDMA 的集群，KVCM 可部署在 RDMA 环境之外。
- **TairMemPool**：与阿里云服务器研发定制计算与芯片系统团队软硬件协同，做多机统一内存寻址与全局访问；给出的唯一具体数字是**多网卡环境下网络带宽利用率 > 90%**。
- **生产采用信号**：支持**阿里集团 RTP-LLM 推理服务加速**，并扩展到 vLLM / SGLang / TRT-LLM；兼容 **Sparse Attention、Sliding Window Attention**。
- **HiSim（推理仿真器）**：CPU-only、通过"动态拦截"劫持推理框架执行流并绕过真实计算，暴露**与 SGLang 兼容的 CLI**、输出**与 `sglang bench_serving` 相同格式的指标**。支持矩阵：**SGLang v0.5.6.post2 + Qwen3-32B-FP8 / Qwen3-8B on H20-96GB**。**"<5%" 的预测精度声明已逐项核实**：按各指标各用例的 MAPE，**Qwen3-8B 最大 4.15%、Qwen3-32B-FP8 最大 3.05%**（三个缓存命中用例）。依赖 NVIDIA 的 `ai-dynamo/aiconfigurator`（441★）作为预测器之一。
- **Optimizer**：回放真实 trace 建模命中率与容量消耗；驱逐策略 `lru` / `random_lru` / `leaf_aware_lru` / `ttl`；trace 类型含 **`publisher_log`** 与 **`qwen_bailian`**（Qwen 百炼 —— 另一个采用信号）。另有 **LiteHit**：一次回放产出与容量无关的事实（`RequestFact` + 命中曲线算术分段 RLE），`HitCurveProjector` 事后推导**任意** LRU 容量下的命中数。文档化局限：仅全注意力、每块计费等额、精确 LRU、请求内逆序提交；**不处理**线性注意力/Mamba、混合块大小、准入、预取、多级策略。
- **带宽论证（阿里云数字）**：跨机 KVCache 传输带宽典型约 **20 GB/s**（EGS 8 卡机 20 GB/s 通用网络；灵骏 8 卡机 25 GB/s 存储带宽 + 200–400 GB/s ScaleOut）；单端口互联从 25 Gbps 升至 200+ Gbps。元数据规模论证：`block_size=64` 时 **64K 上下文需查询 1K 个块的元数据**，单块 KV 为个位数 MB，因此数百 TB 存储意味着**亿级块**；"64K token 对应的 KVCache 传输仅需不到 1 秒"，即**元数据查询延迟成为主导**。
- **相关产品**：
  - **PolarKVCache**（PolarDB for MySQL，商业灰度，2025-11 发布）：**目前中国厂商里数字最好的一组** —— 四层 **VRAM → DRAM → DMP（PB 级）→ disk**，GPUDirect RDMA，逐层 scatter/gather。**TTFT −26.8× 且 TPS +62%**（RTX 4090，DeepSeek-R1-Distill-Qwen-32B-int8 vs vLLM 0.9.2）；**TTFT −8.6×**（8×H20，Qwen3-Coder-480B，200K 上下文）；SGLang 侧 −2.1×；容量 **512 GB → 10 TB**；¥8.0/GB/月。⚠️ 商业产品，无公开可复现协议。
  - **阿里云 Tair KVCache 商业产品**：官方称 **TTFT −90%、吞吐 +30%、成本 −20%、批处理 5–10×、支持百万 token 上下文**。⚠️ **无方法学说明，纯厂商营销。**
  - **阿里云 PAI TokenWorks KV Cache 服务**（`help.aliyun.com/zh/pai/tokenworks-kv-cache`）。

### 5.4 DeepSeek 3FS / Fire-Flyer File System

- `deepseek-ai/3FS`，**10k★**，2025 年 2 月"DeepSeek 开源周"最后一天开源。
- 在 KV Cache 生态中的**实际角色是被当作 L3 存储后端**：SGLang HiCache 的 **`hf3fs` 后端**（`--hicache-storage-backend hf3fs`，需要 operator 部署的 K8s 原生分布式存储）；Tair KVCache Manager 的 **3FS Storage 类型**；NIXL 的 **HF3FS 插件**。
- Mooncake 侧记录：SGLang 于 2025-09-10 同时支持 Mooncake 与 3FS 作为 HiCache 后端；3FS 后端集成由**阿里云 TairKVCache 团队**（Sicheng Pan、Zhangheng Huang 等）完成。
- ⚠️ 关于 3FS 作为 KV store 的**具体性能数字（KV 场景下的读写带宽/TTFT 收益）**，本次调研中未从 3FS 项目自身文档获得可直接引用的 KV 专用 benchmark；请以存储层笔记（`notes_storage_cloud.md`）为准。

### 5.5 腾讯 FlexKV（taco-project/FlexKV）

- **351★ / 73 forks**，Apache-2.0（含第三方组件声明）。README 称由**腾讯云 TACO 团队与社区**开发；Mooncake 的 README 独立描述为"**来自腾讯和 NVIDIA** 与社区合作的分布式 KV 存储与缓存系统"—— 贡献者中确有 NVIDIA 工程师（`linhu-nv` 117 次提交、`wenpengw-nv` 19 次）。⚠️ **无 GitHub Release 对象**（仅 tag：v1.2.1 / v1.2.0 / v1.1.0 / v1.0.0 / v0.1.0）。
- **三个核心模块**：**StorageEngine**（按 block 粒度存 KV，**保持与 GPU 内存相同的 KV 形状**；支持 block-wise 模式把多层多组件 KV 合并成更大块以提升 I/O 大小）、**GlobalCacheEngine**（控制面：**RadixTree** 做前缀匹配 + 内存池跟踪用量并触发驱逐）、**TransferEngine**（数据面：进程内多线程并行传输 + **io_uring**）。
- **三层外部缓存**：**CPU 内存**（L1 external）→ **本地 SSD**（L2 持久）→ **可扩展存储**（L3 分布式跨节点）；腾讯营销文章表述为 **GPU → CPU → SSD → 远端四级**（两处口径不一致，均出自腾讯）。
- **传输**：跨节点用 **Mooncake Transfer Engine**（RDMA）；**GDS**（GPU Direct Storage，2025-12 加入）；io_uring；自适应多路径 GPU↔CPU（2026-07/08）；HugePage 主机缓存（2026-06）。
- **驱逐**：政策含 **`lru`（默认）/ `lfu` / `slru` / `fifo` / `mru` / `filo`**；多级缓存近似 inclusive / write-through（put 先落 CPU，再填充缺失块到 SSD/remote；**某层驱逐不触发向下写回或迁移**，inclusion 是 best-effort）；关键旋钮 `evict_start_threshold`（默认 **0.7** 主动驱逐水位）、`evict_ratio`（默认 **0.05**）、`hit_reward_seconds`（仅 LRU，命中延长有效访问时间）、`slru_protected_threshold`（默认 2）。README 明确宣称 **"逻辑 LRU 驱逐而不触发物理数据移动"**。
- **分布式复用**：**Distributed RadixTree**，每个节点保存全局索引的本地快照（避免中心瓶颈与查询往返）；**lease 机制**保证跨节点传输期间数据有效；**upload & rebuild** —— 本地索引定期上传到 **Global Meta Store（GMS，通常是 Redis）** 并从 peer 拉元数据重建；实际跨节点数据搬运用 **Mooncake TE**。
- **集成面（全部已在主线）**：**vLLM**（PR #34328，`FlexKVConnectorV1` **自 vLLM v0.17.2 起内置**）、**NVIDIA Dynamo**（PR #5858，成为 Dynamo 的**原生 KV Cache Offloading 选项**）、**TensorRT-LLM**（PR #48/#53）、**SGLang**（PR #29701，**`--enable-flexkv`**，v0.5.16+ 可用）、**Mooncake Store 作为远端 tier**（PR #231）。
- **前沿特性**：**DeepSeek-V4 支持**（2026-07-21，PR #225）—— 异构 **C4/C128/indexer KV 组**、**FullKV + SWA 双缓存**、attention/indexer **compress-state sidecar**、**layerwise restore**，即把**异构逐层 KV 布局当作一等对象**；**NVFP4** KV 的字节精确 offload/reload（2026-07-07，PR #204，Blackwell）。
- **实测数字**：⚠️ 仅来自腾讯营销文章/新闻稿，**未给模型、硬件、并发或负载，也没有 benchmark 脚本** —— "可用缓存容量最高可扩展至 GPU 显存的 **100 倍以上**"、"可挂载 **PB 级**远端存储"、**TTFT 降低约 60%**、**TPOT 降低 13%**、**QPM 提升 16%**。**按厂商自报对待。**

### 5.6 字节跳动 / 火山引擎

> 🚨 **重要更正：EIC 不是开源系统。** "ByteDance EIC" = **EIC = Elastic Instant Cache（弹性极速缓存）**，是**火山引擎（字节云）存储团队的商业闭源产品**。SGLang 中的 Apache-2.0 代码（`eic_storage.py`，778 行，PR #10271 于 2025-10-01 合入）与 LMCache 中的 `eic://`（PR #1930，2025-11-21 合入）**只是客户端 shim**；PyPI 的 `eic` / `eic-client` / `volcengine-eic` **全部 404**，也不存在对应开源仓库。**任何把 EIC 称为开源 KV cache 系统的表述都是错的。**

**EIC = Elastic Instant Cache（产品机制已确认）**

- 主源是 **SGLang 内置的后端 README**（`python/sglang/srt/mem_cache/storage/eic/README.md`）："**EIC(Elastic Instant Cache)** is a distributed database designed for LLM KV Cache. It supports **RDMA, GDR** and has the capabilities of **distributed disaster tolerance and expansion**." 后端名 `eic` → 类 `EICStorage`；通过 `--hicache-storage-backend eic` 启用。
- 属**火山引擎存储团队**，基于内部加速需求自研，"历经 **4 年**技术沉淀"，已支撑公司内部**存储、推理、广告推荐**等大规模业务。
- **层次**：内存 + SSD 组成分布式服务，支持 **GPU-本地缓存-分布式缓存(RAM+SSD)** 多级；可**与 GPU 同机部署**，把 **GPU 剩余显存 + 内存 + 磁盘**池化。
- **传输**：**内核态 TCP、用户态 TCP、RDMA、GPUDirect RDMA**；GDR 全链路零拷贝，延迟可达 TCP/RDMA 的**十分之一**。
- **拓扑感知**：感知 GPU↔NIC 拓扑并按亲和选网卡（隐含 NUMA）→ **单机可轻松突破 100 GB/s**。
- **策略/隔离**：TTL 时间策略 + LRU/ARC/FIFO 空间策略；支持进程故障与在线热升级（"写入内存缓存不丢失，支持**毫秒级快速恢复**"）；内存引擎支持 Hugepage、NUMA 感知、全链路零拷贝、JumboFrame；热缓存自动扩副本与生命周期管理；per-Namespace 的介质选择、数据流/驱逐策略、空间配额、**QoS（IOPS 与带宽）**与可观测性。
- **KV 集成设计**：EIC 指出 **SGLang 自身 HiCache 只支持单机 CPU offload**，因此它**扩展了 SGLang 能力、支持外部 KVCache，并通过计算前缀 hash 支持多推理实例间共享**；vLLM 侧走 KV Transfer Connector。不变量：**Swap Out 异步、Swap In 同步且最迟在计算前完成 IO**；EIC Client 自持内存池，先把 GPU KV 拷入 EIC 池再异步发送。已适配 **vLLM、SGLang、Dynamo**。
- **数字（⚠️ 全部为厂商营销文章）**：第 1 轮无复用则持平，**第 2 轮起吞吐从 1.5K 增至 5.5K（3×+）**；"次轮起**时延降至 1 秒，降幅 67%**"；长文本 + PD 分离"吞吐提升 3 倍、TTFT 降低 67%"；模型加载 **DeepSeek-R1 642 GB：546 s（NVMe 基线）→ 13 s（42×）**；**DeepSeek-R1-Distill-Llama-70B 131 GB：84 s → 5 s（16×）**；10 PB 级存储池、命中率提升 >10×；单客户端百 GB 级吞吐与亚毫秒级响应。其中**模型加载与带宽数字较具体且机理可信**，吞吐/TTFT 三元组按厂商自报对待。

**其他字节实体**：**PrisKV**（`aibrix/PrisKV`，**59★ / 8 forks**，Apache-2.0，2025-11-11 创建、**2026-05-20 最后推送**，即约 4 个月无更新）。SGLang 的 AIBrix 后端 README 原话称它由"**ByteDance 的 PrisDB & IAAS & DMI 团队孵化**"，当时"尚未开源"。**PrisKV ≠ EIC**（SGLang 致谢里作为两个不同团队列出）。**PrisKV 的传输已从源码验证**：`rdma.c` / `ucx.c` / `transport.c` 实现 **RDMA、TCP、共享内存、UCX** 四种传输，并支持 **GPUDirect RDMA**（`make PRISKV_USE_CUDA=1`，或 `PRISKV_USE_ACL=1` 走昇腾 NPU）；默认端口 **18512**、最多 16 个绑定地址；**支持分层**（`--backend 'localfs:/data/priskv&size=100GB;s3:bucket1'` 分号分隔多级）；⚠️ **驱逐只有 TTL 扫描**（`--expire-routine-interval` 默认 600 s），**代码里没有任何 LRU/LFU/ARC** —— 不要假设它有淘汰策略；持久化 `--memfile` **仅支持 tmpfs/hugetlbfs**（"ext4, xfs… not supported"）；上限 **16,777,216** 个 key/value block、单块 **≤ 1 MB**；有 C/C++ RDMA 客户端、集群模式（`crc16` + `meta.json`）与 Python 绑定 `pypriskv`。

> ✅ **一个把字节系各个名字串起来的发现：AIBrix 才是那个控制面。** AIBrix 自带 EIC 的 L2 连接器（`l2/connectors/eic/eic.py`，PR **#1718**，2025-11-06）；把 AIBrix 的 EIC README 与 SGLang 的逐字节比对，**正文完全相同**（同一定义、同两个微信链接、同一控制台链接、同一文档 ID `85848/1749188`），只有标题与部署片段不同 —— 即**同一团队、两个框架、相隔六周**（SGLang 2025-10-01，AIBrix 2025-11-06）。而 AIBrix 的 **L2 目录**（原文）为：**`INFINISTORE`、`HPKV`、`PRISKV`、`ROCKSDB`、`EIC`、`SHFS`、`MOCK`**。因此 SGLang HiCache 致谢里那串看起来互不相干的字节系名字实际上是自洽的：**AIBrix 是控制面，PrisKV（PrisDB）与 EIC 是它可插拔的两个 L2 存储**。
> ⚠️ **不要误归因**：**HPKV、RocksDB、SHFS、Vineyard 都不是字节的**；只有 `INFINISTORE` / `PRISKV` / `EIC` 是。

**InfiniStore**（`bytedance/InfiniStore`，**438★**，Apache-2.0，描述即"**KV cache store for distributed LLM inference**"）：**并非无发布物** —— 有 **1 个 GitHub release**（tag `0.2.33`，2025-03-23）、3 个 tag，PyPI 上 `infinistore` **0.2.35、共 25 个版本**（summary 为 "A kvcache memory pool"）；端口 12345/8088；其 PyPI `home_page` 指向 `bd-iaas-us/InfiniStore`。⚠️ **最后推送 2025-11-13，约 10 个月陈旧**。⚠️ **发现一处不一致**：AIBrix 的 `envs.py` 引用 InfiniStore "since **0.2.42**"（RDMA GID pinning），但 **PyPI 最高只有 0.2.35**、GitHub 唯一 release 是 0.2.33（25 个版本全部核对过）—— **无法从公开产物复现**。

**ShadowKV**（`ByteDance-Seed/ShadowKV`，**313★**，ICML'25 Spotlight）—— 把 KV 压到 LongBench 平价下 **6.25%**、50K NIAH 下 **0.26%**。**AIBrix** 起源字节（顶级贡献者 company 字段为 "ByteDance Inc."），现已迁入 `vllm-project`。**veRL 已迁移到 `verl-project/verl`**（23,431★），其 KV 缓存**委托给 Mooncake**（经 vLLM 的 `MooncakeStoreConnector`），字节并无自研开源 KV 引擎。其他相关研究：MegaScale-Infer（SIGCOMM'25）、MixedDimKV、SwiftSpec、FlexPrefill、AHN、Charon。

**Volcengine Ark 的 prompt caching 有完整 API 级文档**：最小块 1024 tokens，TTL 1 小时 – 7 天，按小时计费存储，隐式/显式缓存互斥。

❌ **未发现名为 "ByteDance KVCache" 的开源项目**（在 419 + 208 + 63 个组织仓库中零命中）；❌ "Penguin" 未找到；❌ **`eplb` 属 DeepSeek 而非字节**；❌ **LMDeploy 属上海 AI Lab/InternLM 而非字节**；❌ KVDirect 未验证。

### 5.7 华为 / Ascend

**四层栈（务必区分，不要混为一谈）**：

| 层 | 组件 | 角色 | 传输 |
|---|---|---|---|
| **连接器/策略** | `AscendStoreConnector`、`UCMConnector`、`MooncakeConnectorV1/V2/Hybrid/Layerwise`、`SfaRemoteD2HConnector`、`AscendMultiConnector`（均在 vLLM-Ascend 内） | 实现 `KVConnectorBase_V1`；前缀查找、load/save 编排、PD 交接 | 委托下层 |
| **KV 存储服务** | Mooncake Store（`mooncake_master`）、MemCache（`MetaService`+`LocalService`）、UCM Store、Yuanrong Datasystem | 容量 + 驱逐（水位/LRU/租约）+ 持久化 | MemFabric / Mooncake TE |
| **内存池化** | **MemFabric**、CloudMatrix **EMS**、openEuler **UBS Memory** | GVA 统一寻址、跨节点跨介质零拷贝 | Device UB 1.0(A3) / Device RoCE(A2) / Device URMA·UBOE(A5/950) / Host RoCE·UB |
| **互联** | UB / 灵衢、HCCS、RoCE、UB-Mesh | 物理互联 | — |

**最重要的判断**：Ascend 的 KV cache 故事本质是**内存池化**故事。因为昇腾的高带宽网络在 **NPU 侧而非 Host 侧**（"pooling software built on Host-side networks cannot fully utilise the hardware"），而 UB 提供全局可寻址统一内存 + DMA，华为能把远端 DRAM 当作本地来访问（对全局虚拟地址做 `xcopy`），达到**每 die 约 70–166 GB/s**，约为 CloudMatrix384 论文所述传统集群机间带宽（**约 25 GB/s**）的 **3–7 倍**。这正是 `ASCEND_ENABLE_USE_FABRIC_MEM=1`（"统一内存地址直接传输"）成为 A3 推荐设置的原因。

**vLLM-Ascend KV Cache Pool**：仓库 **2,826★ / 2,257 forks**，Apache-2.0，最新稳定 **v0.23.0（2026-08-16）**、**v0.26.0rc1（2026-09-03）**。`AscendStoreConnector(KVConnectorBase_V1, SupportsHMA)` 把远端 KV 池做成 vLLM 设备内前缀缓存背后的**二级前缀缓存**。官方设计文档的理由："仅使用片上内存时命中率受限，因此提出 KV Cache Pool 利用**片上内存、DRAM、SSD** 等多种存储构成池，并让请求前缀**对所有节点可见**"。
- **KV 位置**：NPU HBM（一级）→ Host DRAM（每节点贡献 pool segment；Mooncake `global_segment_size` 须 **1 GB 对齐**）→ 可选 NVMe/SSD（Mooncake `enable_ssd_offload`；MemCache `memcache_hybrid >= 1.2.0`）→ UCM 额外提供 **NFS / DeepSeek 3FS / Posix** 持久层。⚠️ **未验证**把其他节点的远端 NPU HBM 当作池**容量**使用 —— 池是 CPU-DRAM 中心的；远端 HBM 只作为**传输端点**。
- **传输按硬件分档**：A2 用 `HCCL_INTRA_ROCE_ENABLE=1`；**A3 推荐 `ASCEND_ENABLE_USE_FABRIC_MEM=1`**（需 HDK ≥ 26.0 或 ≥25.5 配 mooncake ≥ v0.3.11、CANN ≥ 9.0.0、灵衢网络 ≥ 1.5）；A5（950PR/950DT）用 UBOE/UB（需 HDK ≥ 25.6、CANN ≥ 9.1.0，容器需挂 `/dev/ummu`、`/dev/uburma` 等）。MemCache 协议 `device_rdma`（A2 推荐）/ `device_sdma`（A3 + HCCS 推荐）/ `device_urma`（950 UB）/ `device_uboe`。
- **驱逐委托给后端**：Mooncake 用 master 侧 `eviction_high_watermark_ratio` / `eviction_ratio` / `default_kv_lease_ttl`；MemCache 用 `ock.mmc.evict_threshold_high=70` / `_low=60` / `rewarm.dram_watermark=95`。
- **逐层与稀疏 offload（不对称设计）**：prefill 阶段传输**完整层**并与计算重叠；decode 阶段把完整 KV 留在 host memory，只加载**被选中的条目**（indexer cache + 每层热 top-k 缓冲）。NPU 主 KV 占用比 ≈ `(I + min(B, R)) / N`。`SfaRemoteD2HConnector` 用 **MemFabric** —— **唯一受支持的 Remote D2H 传输后端**。
- **已知边界**：逐层共享缓冲 offload 需 MemCache 后端**且 eager 模式**；稀疏 decode offload 需 Model Runner V1 + SFA/MLA 稀疏注意力模型且主 KV 为 **BF16**；**不支持混合 KV cache 布局**；稀疏 decode 支持 DP/TP 但**不支持 CP/PP**；联合部署要求 `p_tp_size >= d_tp_size` 且整除；逐层缓冲复用**当前无法与 `MooncakeLayerwiseConnector` 组合**；连接器级读重试**未实现**。

**MindIE（与常见印象相反，是开源的）**：许可为 **Mulan PSL v2**（⚠️ GitHub 界面显示 NOASSERTION，**不要据此判断为专有**）。包含 **KV Cache 池化**（经 **HCCL 单边通信**，**4 MB/link、最多 512 link、容量为 `(卡数−1)×4MB`**，官方示例 508 MB）、**Prefix Cache 与 INT8 KV**、**逐层 KV 传输**（`MooncakeLayerwiseConnector` → `concurrent_engine_sync`，即"引擎按层同步 KV"，⚠️ 但**无协议规范与延迟数字**），以及 **MindIE Motor 的 KV Cache Store / KV Conductor / KV 亲和**。

**MemFabric 才是真正的主角**：基于 **GVA（全局虚拟地址）+ `xcopy`** 的跨节点内存池。**Device UB 1.0 单 die 实测 110.23 / 74.54 / 166.47 / 138.01 GB/s**（四个方向）；**A3 SuperPoD 上可达 128 TB CPU 内存 + 48 TB HBM**。

**CloudMatrix384 与 UB（灵衢/UnifiedBus）**：论文 **arXiv 2506.12708**（已读全文）。384 NPU / 192 CPU、16 机架；**128–512 token 的分页 KV 块**、内容寻址 + 前缀哈希去重、EMS over UB。关键数字：**50% 复用率下 1.42×、90% 复用率下 2.28×**；**UB vs VPC 为 1.52×**；**TTFT 分别降低 861 ms / 1,505 ms**；**节点内约 256 GB/s vs 节点间约 25 GB/s**。
- ⚠️ **"每 NPU 392 GB/s 的 UB 带宽"在论文中并不存在**（全文检索 "392" 零命中）；**"48 TB DRAM" 属于 A3 SuperPoD/MemFabric，不属于该论文**。UB-Mesh 2.0、Atlas 950/960 规格**未能验证**。
- ❌ **`Ascend/TransferQueue` 不是 KV cache 系统**：它是后训练/RL 的样本流式传输库，"KV" 指 sample record（在 verl 中带来 49.1% 收益）。**不要把它列为 KV cache 项目。**

### 5.8 百度

**FastDeploy**（`PaddlePaddle/FastDeploy`，**3,715★ / 756 forks**，Apache-2.0，分支 **`develop`**，最新 **v2.5.0（2026-04-09）**）：

- **原生前缀缓存**：GPU + CPU 两级（CPU 用 `--swap-space` 指定 GB）；⚠️ ERNIE-4.5-VL 不支持。内部实现是真的 `class RadixTree`（`cache_manager/v1/radix_tree.py`，含 `find_prefix` / `insert`），**文档化的驱逐顺序为 `DEVICE → HOST → Storage`**，有显式引用计数契约；`block_size` 默认 **64**、`kv_cache_ratio` 默认 **0.75**。
- **Global Cache Pooling**：**由 Mooncake Store 支撑**的跨实例 KV 池（`--kvcache-storage-backend mooncake`），默认 `global_segment_size`=1 GB、`local_buffer_size`=128 MB、`protocol`=rdma；用 **3 节点 etcd 或单 Redis** 做基于租约的 HA 主选举（有带 fresh-prompt 方法的失效切换测试）。⚠️ **未发布任何性能数字**。
- **PD 分离**：节点内用 `cudaMemcpyPeer`，跨节点用**自研 RDMA 库**。已发现的最有价值的对照数字：**`KVTransferManager` vs Mooncake 头对头**，单张 CX-7 400G 网卡、batch 1538 —— **1K 块时 6.9×，单调衰减到 256K 块时 1.1×**，两者都打满约 50 GB/s（256K 时 45.01 vs 40.71 GB/s）；即优势**只存在于小块场景**。
- **KV 量化（此前判断有误，此处更正）**：`KvCacheQuantzationTypes` 枚举含 `int8`、`float8_e4m3fn`、`float8_e4m3`、**`block_wise_fp8`**、`int8_zp`、`int4_zp`、`float8_e4m3fn_zp`；在线 `block_wise_fp8` KV 需要 **AppendAttn** 后端；**默认不量化 KV**。⚠️ README 与文档在 KV 数据类型上存在不一致（表格只列 BF16）。
- 支持昆仑芯 XPU。

> 🚨 **重大发现：百度自己的生产 KV 缓存系统 AttentionStore 是闭源的 —— 与火山引擎 EIC 结构完全相同。**
>
> - FastDeploy 的 `cache_manager/transfer_factory/mooncake_store/attention_store.py`（295 行，PR **#5823**，2026-01-22 合入）**只是专有 SDK 的客户端包装**，import 的是 `attentionstore_sdk.sdk.AttentionStoreSDK`、`Tokens`、`AttentionType`、`common_pb2`。
> - ❌ **`attentionstore_sdk` 未公开分发**：PyPI 上 `attentionstore-sdk` 与 `attentionstore_sdk` **均为 404**；`requirements.txt` 只列了 `p2pstore`。
> - ⚠️ 另有一个**独立**的 `attnstore` connector（`cache_manager/v1/storage/attnstore/connector.py`，140 行）是**显式 stub** —— 每个方法体都是 `# Placeholder implementation`，返回 `False`/`None`/`[]`/`0`。极易被误认为可用后端。
> - 包装层泄露了内部数据模型：`block_token_size=64`、`shard_id/shard_num`、`bytes_per_shard_layer_per_block=1024`、`layer_num`、`splitwise_role`，以及 `sdk.match(tokens, start_match_block_idx, timeout)` / `read` / `write` / `flush_token_index`。
> - **AttentionStore 产品**（百度百舸，新闻稿 2026-04-02）：每节点一个与引擎解耦的进程，HBM→DRAM→SSD，共享内存 + SSD，大页 + 全生命周期 page-locking，全局 BlockHash→介质索引，缓存感知调度。声称 **命中率 80–90%**、8K+ 时 **TTFT 2–5×**、64K 时 **TTFT 6.2×↓**、多轮**吞吐 5.4×**、DRAM→HBM **4×**；在 **DeepSeek R1 671B / 昆仑芯 P800** 上验证（2 个 prefill 节点 TP4/DP4）。⚠️ **全部来自同一份新闻稿被三家转载 —— 是一个来源，不是三个。**
> - 🚨 **重名警告**：arXiv **2403.19708**（2024，Bin Gao 等）也叫 "AttentionStore" 但数字不同（TTFT −88%、prefill 8.2×）。**是两个不同系统，切勿混淆。**
>
> **由此得到一条跨厂商规律（本报告的重要结论之一）：中国商业厂商的主流模式是"开源客户端 shim + 闭源服务"，且已在两家不同厂商以结构相同的形式出现。** 因此**把"SGLang HiCache 内置后端数"或"FastDeploy 存储后端数"当作开源 KV 缓存系统数量会至少高估两个**。有用的推论是：两种情况下，合入的 shim 都泄露了那个闭源系统最好的设计细节（EIC 硬编码的 H20 GPU↔NIC 亲和表；AttentionStore 的 block/shard/layer 字段）。

**其他百度材料**：
- **LU-KV**（arXiv **2602.08585**，**ICML 2026**，百度百舸 + 复旦，仓库 `baidu-baige/LU-KV`，6★，是 `NVIDIA/kvpress` 的 fork）：80% 压缩下相对损失仅 **0.52%**，RULER@80% 从 **29.53 → 69.98**，multi-key-3 从 **1.00% → 67.40%**。
- **千帆有两个不同的缓存功能**：自动 `prompt cache`（**仅 ERNIE-4.0-Turbo-8K**，命中按 prompt 价格的 **40%** 计）与显式 `前缀缓存`（**邀测**，`POST /v2/caching` 返回 `cache_id`，命中按输入价的 20–25% + 存储 0.000017 元/1K token/小时）。⚠️ **显式前缀缓存支持的模型是 DeepSeek 系列，未列 ERNIE** —— 因此"千帆上 ERNIE 前缀缓存"的说法没有依据。
- **交叉验证**：ERNIE 4.5 技术报告（18K 输出 TPS/H800，**不含** prompt caching）与 FastDeploy 2.0 博客（21K，"+17%"）经算术核对一致（18→21K = +16.7% ≈ 17%），**两份百度文档相互印证**。
- ⚠️ `baidu/vLLM-Kunlun`（466★/102，2026-09-15 有推送）的 **KV Cache Pool 文档是 0 字节的 `.po` 占位文件**，任何分支都没有源 `.md` —— 路径完全照搬 `vllm-ascend`（后者有真实指南）。**不要把昆仑芯列为"有 KV Cache Pool 文档"。**
- ❌ **三个已核实为负的结论**：vLLM 中**不存在**百度/FastDeploy 的 `KVConnector`；**Mooncake README 从未提到百度/FastDeploy/PaddlePaddle/昆仑芯**（关系是单向的）；百度**未参与** SGLang HiCache。
- ❌ **"X-MoE" 确认无法验证**，且已排除两个诱饵：两篇 `developer.baidu.com` 的 "XLarge-MoE"/"MoE-X" 文章从未点名百度（只写"某研究团队"）、数字互相矛盾（2048 vs 3072 卡），其中 "MoE-X" 那篇实际上描述的是**蚂蚁集团/InclusionAI 的 Ling-1T**。唯一真实的 `xMoE` 是微软 2022 年的架构论文。

### 5.9 存储层与云厂商（含三处对常见说法的更正）

**DeepSeek 3FS / Fire-Flyer File System** —— `deepseek-ai/3FS`，**10,200★ / 1,095 forks**，**MIT**，2025-02-27 创建（开源周第 5 天）。3FS 自己的 README **把 "KVCache for Inference" 列为一等负载**，KV-cache 客户端实测**峰值读 40 GiB/s**。
- ⚠️ **成熟度警告**：**`main` 分支最后公开提交是 2026-05-07**（截至 2026-09 已静默 4 个月），且**没有任何 tagged release**。相邻的 DeepSeek 仓库仍活跃（FlashMLA、DeepGEMM 有近期提交），所以这看起来是 3FS 专属现象。是否转私有开发**未能验证**。
- 架构：USRBIO / 零拷贝，HF3FS 后端带 **page-index 分配器**（`reserve_and_allocate_page_indices` / `confirm_write` / `get_page_indices`）。
- ⚠️ **"40 GiB/s" 的口径未定**：3FS README 说"所有客户端"，第三方 open-infra-index 说是"每客户端节点"。

**DeepSeek 模型侧的 KV 压缩比存储层走得更快**（这点对容量规划很关键）：**DeepSeek-V4**（2026-04-26）与 **DeepSeek-V4.1-Flash**（2026-09-10）大幅压缩 KV —— V4-Pro 在 1M 上下文下只需 V3.2 的 **10%** KV；V4.1-Flash 声称全局 KV **890 bytes/token**。V4.1-Flash 的部署说明本身就是一套 KV **分层设计**：SWA KV 不再持久化到 SSD，而是放在**分布式主机 DRAM 池（DRAM 的 10%）并设分钟级 TTL**；全局 KV 有 **72 小时保证生命周期**；另有 **Hierarchical Sparse Indexer**（受限候选池）来约束索引开销。⚠️ 这些数字来自**二手**报道（MarkTechPost, 2026-09-10）+ 一篇佐证博客；**一手技术报告未获取**。

**JuiceFS** —— `juicedata/juicefs`，**14,000★**，Apache-2.0，最新 **v1.4.1**。
- 🚨 **更正：JuiceFS 的 LLM 故事是模型权重与数据集缓存，不是 KV cache。** 官方文档/博客中**找不到任何 JuiceFS KV-cache 后端或 vLLM/SGLang/LMCache 连接器**。
- 🚨 **更正：著名的 "70 GB/s 缓存池" 指的是聚合网卡带宽（600 Gbps ≈ 70 GB/s），不是实测吞吐**；同一篇文章给出的实测瞬时数字是 **10 GB/s**。

**Fluid（CNCF）** —— `fluid-cloudnative/fluid`，**2,000★ / 1,267 forks**，最新 **v1.0.8**。
- **确实有 KV-cache 计划，但仅处于路线图层级，尚无任何发布物**：Fluid ROADMAP 列有 "LLM KV Cache Orchestration"（分离式 vLLM/SGLang KV cache、跨 Pod KV 共享、Mooncake 集成）；issue **#5875** 提议做基于 Mooncake Store 的 `CacheRuntime` PoC。⚠️ **未找到任何 Fluid KV-cache benchmark**；"10x+ 吞吐"是路线图目标而非实测。
- 🚨 **更正：广为人知的网易"42 分钟 → 30 秒"案例是模型权重冷启动，不是 KV cache。**（该案例的实际路径是 42 min → 3 min → <30 s。）

**AWS：Curvine 分层 KV cache（SageMaker HyperPod）** —— **Curvine**（Rust 分布式缓存，**CNCF Sandbox**，约 945★，v0.5.1-alpha）。AWS 官方博客《Tiered KV cache for large LLMs on Amazon SageMaker HyperPod with Curvine》给出：
- 实测**最高 100% 跨 Pod 缓存命中率**、**TTFT 最高 2.7× 改善**、**跨节点 L2 读延迟约 56 ms**（约 1,900-token prompt）；另有 **TTFT 774 → 287 ms** 的一组数字；
- 建议**前缀共享 token 占比 >40%** 的负载才值得做（系统提示、共享 RAG 上下文）；
- **推荐 worker 数据后端用节点本地 NVMe + hostPath**（G6e/P5 约 3 GB/s，远高于 EBS gp3 且无额外成本，对可恢复的缓存可接受丢失）；跨节点 L2 读约 **1.8 GB/s**；
- ⚠️ **AWS 自己的分层建议推荐用 ElastiCache Valkey 而非 S3 作为远端 L2。**

> 🚨 **更正：Curvine 的"KV 故事"是 AWS 的，不是 Curvine 自己的。** Curvine 仓库里那篇"KV blog"是 **AWS 文章的逐字镜像**；Curvine 自有代码中 **`KV` 只有 1 处偶然命中**（就是那条 AWS 链接标题），**`kvcache`/`vLLM`/`LMCache`/`SGLang` 命中数为 0，`3fs` 命中数为 0** —— 因此它**既不兼容 3FS，也不是"类 3FS"**。真正的可复现集成方式是：**用 LMCache 的 `fs://` connector 挂在一个 Curvine 的 `ReadWriteMany` FUSE PVC 上**，即 `LMCACHE_REMOTE_URL=fs://localhost:0/mnt/curvine/l2cache/`、`LMCACHE_REMOTE_SERDE=naive`、`PYTHONHASHSEED=0`。

**Alluxio** —— 🚨 **更正：Alluxio 没有 KV-cache 产品功能。** 对其 AI 3.9 release notes 做 grep 审计，**"kv" 零命中**；Alluxio 自己的文档只列训练数据/checkpoint、**模型分发（权重）**与 feature store。其 KV 相关仅有一次 **2025 年的新闻稿，且不含任何数字**（合作方标为 vLLM Production Stack / LMCache Lab）；**Alluxio ↔ LMCache 的关系未能验证**（LMCache 并未把 Alluxio 列为后端）。
- ⚠️ **两个易踩的陷阱**：（a）Alluxio 的"**sub-millisecond latency**"指的是 **S3 对象上的 TTFB（首字节时间），不是 TTFT**；（b）它全部 15 项量化结果都属于数据/权重/checkpoint 场景（含那个 **7.6 GiB/s**，是**训练 checkpoint 吞吐**）。
- ⚠️ 另外：Alluxio **自 v2.9.6（约 2024 年）起没有新的开源 tag**，AI 3.x 全部为商业版。

**云厂商托管 prompt caching（与自建 KV 池是两条不同赛道）**：
- **Amazon Bedrock**：prompt caching 已 GA，官方称**成本最高降 90%、延迟最高降 85%**。
- **Azure OpenAI / Microsoft Foundry**：prompt caching 文档化，用于长且前缀相同的 prompt，减少重复处理。
- **Google Cloud**：GKE Inference Gateway / llm-d 相关；⚠️ 本次尝试获取 GKE 侧页面时被 Cloudflare 拦截，**未能取得可引用的一手内容**。
- ⚠️ 一个常见混淆需要澄清：**SGLang 的 `object_storage.mdx`（从 `s3://`/`gs://`/`az://` 加载模型权重，`runai_streamer`）是模型权重流式加载，不是 KV cache 存储。** SGLang 真正的 KV L3 后端是 `file`/`mooncake`/`hf3fs`/`nixl`/`aibrix`/`dynamic`；对象存储 KV 层要经 **NIXL 的 `OBJ` 插件**（通常经 LMCache）到达，而不是走模型加载路径。

**NIXL 的存储插件约束（来自 LMCache 的 NIXL 后端文档，实测级）**：

| NIXL 插件 | 目标 | 约束 |
|---|---|---|
| `GDS` / `GDS_MT` | GPUDirect Storage（NVMe，多线程变体） | `nixl_buffer_device` = `cpu` 或 `cuda`；支持 dynamic 模式 |
| `POSIX` | 本地/共享 POSIX 文件 | `nixl_buffer_device` **必须为 `cpu`**；可选 liburing |
| `HF3FS` | DeepSeek 3FS | 必须为 **`cpu`** |
| `OBJ` | S3 兼容对象存储 | `cpu` 或 `cuda`；**唯一**支持 `nixl_endpoint_list` |
| `AZURE_BLOB` | Azure Blob API | 必须为 **`cpu`** |
| `DOCA_MEMOS` | NVIDIA DOCA Memos 内存/对象服务 | 必须为 **`cpu`**；128-bit 小写十六进制对象名 |
| `UCX` / `LIBFABRIC` | P2P / PD 传输（非存储） | vLLM 中经 `kv_connector_extra_config.backends` 选择；UCX 是 NIXL 默认 |

**GDS 的实际地位**：SGLang HiCache 官方博客明确表示"存储延迟通常远高于主机–GPU 传输且更不可预测，我们对 GPU Direct Storage 等**在性能权衡有利时**的技术保持开放" —— 即 **GDS 不是 HiCache 的默认路径**；默认高性能 CPU↔GPU 路径是 SGLang 自己的 **GPU 辅助 I/O kernel（比 `cudaMemcpyAsync` 最高 3×）**。

**三条跨存储层的设计教训**：
1. **元数据放置才是难点，不是数据搬运**。SGLang HiRadixTree **刻意不同步 L3 元数据**、改为访问时实时查询；3FS HF3FS 后端跑 page-index 分配器；Fluid 的 KV PoC 把"Mooncake metadata / master service"当作最需要映射进 `CacheRuntime` 的组件；DeepSeek-V4.1-Flash 专门做了 Hierarchical Sparse Indexer 来约束索引开销。
2. **跨实例/跨 Pod 复用才是价值驱动，也是各厂商真正收敛的地方**：Novita 用 3FS 把命中率从 40% 拉到 80%、vLLM 经 Mooncake Store 做跨实例哈希前缀去重、Fluid 的 "Cross-Pod Cache Sharing"、LMCache 的 shared pool —— 本质都是**给 KV 页建立集群级命名空间**。
3. **模型架构压缩 KV 的速度快于存储层扩容的速度**：V4-Pro 只需 V3.2 的 10% KV、V4.1-Flash 约 V4-Flash 的 1/4（FP4 KV）、第三方 LSA 为全上下文 footprint 的 13.5%。**对 2026 年代的 DeepSeek 模型而言，KV 缓存的关键已不是 NVMe 容量，而是"一个小的、热的、按索引寻址的全局缓存 + 廉价重放 128-token 窗口"。**

### 5.10 其他值得关注的项目

| 项目 | Stars | 机制一句话 |
|---|---|---|
| **kvcached**（`ovg-project`） | **1,386★** | 把 OS 式**虚拟内存抽象**引入 KV：解耦 GPU 虚拟地址与物理分配，实现弹性按需 KV 分配以支持**多模型共享 GPU**；支持 SGLang / vLLM。该工作即 **Prism（OSDI 2026，UC Berkeley Sky Computing Lab）** 的内存 balloon 驱动，声称 **TTFT 降低 2–28×**，已被 Red Hat 的 Sardeenz 采用（arXiv 2508.08448、2505.04021） |
| **KTransformers**（`kvcache-ai/ktransformers`） | **19,518★** | **原任务清单完全遗漏的最大项目**。异构 LLM 推理/微调优化框架（MoE 稀疏专家按需加载、CPU/GPU 异构），与 Mooncake 同属 `kvcache-ai` 组织 |
| **PegaFlow**（`novitalabs`） | **204★**（v0.24.4, 2026-09-09） | Novita 的 **Rust 外部 KV 缓存服务**（GIL-free）：L1 本地 pinned DRAM、L2 跨节点 DRAM（单边 RDMA READ）、L3 本地 SSD（io_uring）；vLLM worker 走 **CUDA IPC（数据面）+ gRPC（控制面）**；经 **vLLM external KV connector** 接入（`kv_connector_module_path`）。**实测**：跨节点 8×400 Gbps **194 GB/s 均值 / 250 GB/s P99 / 261.6 GB/s 峰值**（24 GiB KV 段约 100 ms）；单 SSD 约 **6.9 GB/s** 峰值、稳态 6.5–6.6 GB/s；共享池 vs 进程内隔离池 **+56% 吞吐 / −36% 平均 TTFT / 4.4× 命中率**；MLA 逻辑 KV 去重 **+72% 吞吐 / −41% TTFT**；vLLM 启动 **71.4 s → 33.2 s（2.15×）**；README 微基准暖/冷 TTFT **572.5 ms → 61.5 ms（≈9×）** |
| **KVCache-Factory** | 1,380★ | 统一的 KV 压缩方法库 |
| **R-KV** | 1,212★ | NeurIPS'25，面向**推理模型**的冗余感知 KV 压缩 |
| **uccl**（`uccl-project`，UC Berkeley Sky + UC Davis） | 1,516★ | GPU 通信库（集合通信 + P2P KV 传输），NIXL/Mooncake TE 的竞争者。**在 256 KB–1 MB 区间比 NCCL/RCCL 快 30–50%**；**Mooncake TE 在 100 MB 时无法打满 50 GB/s**（TENT 论文亦以 UCCL-P2P 为基线） |
| **NVIDIA/kvpress** | 1,209★（v0.5.4, 2026-07-02） | KV 压缩工具包 |
| **KVzip**（`snu-mllab`） | 226★ | NeurIPS'25 Oral，查询无关 KV 驱逐 |
| **huawei-csl/KVarN** | 494★ | **原生 vLLM KV 量化后端**，主打 agent 长上下文 |
| **thu-nics/C2C** | 447★ | ICLR'26 "Cache-to-Cache"：在 LLM 之间传**语义缓存**而非原始 KV |
| **ModelEngine-Group/unified-cache-management** | 334★ | 华为 ModelEngine 统一缓存管理（UCM） |
| **AstraNetLab/CacheRoute** | 322★ | 前缀亲和**规划式**路由（arXiv 2608.19677） |
| **RBG**（`sgl-project/rbg`） | 296★（v0.8.0, 2026-08-31） | 角色化云原生部署（KEP-74 把 Mooncake 作为一个 role）；**由 SGLang 社区 + 阿里云 + 小红书共建，不是蚂蚁集团项目**。KEP-74 给出的基准是目前中国生态里**最可复现**的一组 KV offload 数据：Qwen3-32B、SGLang v0.5.3.post1、Mooncake TE v0.3.6.post1、30 GiB L3，多轮 **TTFT 1172.21 → 94.50 ms（−91.94%）**、**吞吐 1384.64 → 1935.69（+39.80%）**、ITL −58.83%、实际 offload 26.96 GiB |
| **checkpoint-engine**（MoonshotAI） | 1,005★（v0.4.2） | Mooncake P2P Store 的开源生产版；**是权重更新中间件，不是 KV cache 系统**。Kimi-K2（1T 参数）数千卡原地更新约 20 s |
| **xLLM** | 1,570★（v0.10.1） | ⚠️ **已从 `jd-opensource/xllm` 迁移到 `xLLM-AI/xllm`，托管于开放原子基金会**；基于 Mooncake 做混合 KV cache 管理（全局管理 + 智能 offload/预取） |
| **vLLM-Ascend** | 2,826★ | 见 §5.7 |
| **InferenceX**（SemiAnalysis） | 1,695★ | 开源持续推理 benchmark 研究平台，是核验 KV/offload 宣称的中立基准源 |

---

## 6. 标准与接口：2026 年有没有收敛？

### 6.1 NIXL（NVIDIA Inference Xfer Library）

- 仓库 `ai-dynamo/nixl`，**1,256★ / 441 forks**，最新 **v1.4.1（2026-09-01）**，2026 年基本保持**每月一个 minor release**（v1.0.1 于 2026-04-14）。许可：源文件 Apache-2.0，**PyPI 元数据标为 `MIT AND Apache-2.0`**，wheel 内捆绑 `LicenseRef-NvidiaProprietary` 的 MLX5 库。
- **定位**：为 Dynamo 等推理框架加速**点对点通信**，同时通过**模块化插件架构**对各类内存（CPU/GPU）与存储（文件、块、对象存储）做抽象。**仅支持 Linux**（Ubuntu 22.04/24.04、Fedora）。
- **插件清单（`meson.build` v1.4.1，共 14 个）**：`UCX`、`LIBFABRIC`、`POSIX`、`OBJ`、`GDS`、`GDS_MT`、`MOONCAKE`、`HF3FS`、`GUSLI`、`GPUNETIO`、`UCCL`、`AZURE_BLOB`、**`INFINIA`**（新）、**`TELEMETRY_DOCA`**（新）。
  - 🚨 **更正：`NVSHMEM` 不是 NIXL 插件**（README 的 ROCm 缺口说明确认其缺失）。
  - ⚠️ **插件在依赖缺失时会静默跳过**，因此**后端可用性取决于构建配置** —— "NIXL 支持 X" **不可移植**。最实用的运行时探测手段是 `get_plugin_params(backend)`。
- **API 模型**：Transfer Agent / Memory Section / Metadata Handler；`create_agent` / `register_memory` / `create_xfer_req` / `post_transfer_request` / `get_xfer_status`；通知（`send_notif` / `get_new_notifs`）走带内。含 Python binding（`pip install nixl` 同时装 CUDA 12/13 后端并按 torch 报告的 CUDA 版本自动选择）、Rust binding（`-Drust=true`）。**支持 ETCD 做跨节点元数据分发**（`NIXL_ETCD_ENDPOINTS`、`NIXL_ETCD_NAMESPACE` 默认 `/nixl/agents`）。
- **跨厂商**：NIXL 本身**厂商中立构建**；CPU 侧通过 PCI vendor `0x1002` 识别 AMD GPU；ROCm wheel 名 `nixl_rocm`；有明确的 ROCm 已知缺口清单。
- 🚨 **治理成熟度接近为零**：**`GOVERNANCE.md` 404、`VERSIONING.md` 404、无基金会归属**。`CONTRIBUTING.md` 只有一句 "We maintain backward compatibility and stable APIs for our users."，**没有 semver 政策** —— 因此下游**精确 pin 版本**（如 `nixl == 1.4.1`）。
- **事实标准证据**：**AWS（2026-03-19）官方称** "NIXL … integrates natively with frameworks including NVIDIA Dynamo, SGLang, and vLLM"（要求 NIXL ≥ 1.0.0、EFA installer ≥ 1.47.0）；NVIDIA 官方博客称 NIXL 已被 **llm-d、TensorRT-LLM、SGLang、vLLM** 广泛采用；**Mooncake TE 亦作为 NIXL 的官方 backend plugin**。vLLM 的 `NixlConnector` 与 `TieringOffloadingSpec` 的 `obj` / `p2p` tier 均构建在 NIXL 之上。
- ❌ **NIXL Connect 的内部实现未能验证**（Dynamo 的 raw 内容在本次调研中不可达）：文件存在与维护它的 commit 已确认，**内容未确认**。
- ⚠️ **NIXL 的存储插件约束（来自 LMCache 的 NIXL 后端文档，实测级）**：`GS`/`GDS_MT` 可用 `cpu` 或 `cuda` buffer；**`POSIX`、`HF3FS`、`AZURE_BLOB`、`DOCA_MEMOS` 的 `nixl_buffer_device` 必须为 `cpu`**；`OBJ` 是**唯一**支持 `nixl_endpoint_list` 的插件；`UCX`/`LIBFABRIC` 是 P2P/PD 传输而非存储。

### 6.2 vLLM KV Connector API

**这是 2026 年最重要的"事实标准"。** 证据（全部源码/文档级已验证）：

- 抽象基类 **`KVConnectorBase_V1`**（`vllm/distributed/kv_transfer/kv_connector/v1/`），按 `kv_role` 区分 scheduler 侧与 worker 侧职责。
- 注册机制 **`KVConnectorFactory.register_connector(...)`** 允许树外实现；配置入口统一为 `--kv-transfer-config` JSON，其中 **`kv_connector_module_path`** 支持从任意 Python 包加载连接器。
- **`MultiConnector`** 让多个连接器串联组合（Mooncake 用它同时做 PD 与分布式池）。
- **v1 Offloading API**（`vllm/v1/kv_offload/`）：`CPUOffloadingSpec` / `TieringOffloadingSpec` / `SecondaryTierManager`（可扩展点）/ `CachePolicy`（`lru` / `arc`）/ chunk 语义 / `self_describing_kv_events`。
- 由于以上机制，**LMCache（`LMCacheConnectorV1`、`LMCacheMPConnector`）、PegaFlow（`PegaKVConnector`）、AIBrix（`AIBrixOffloadingConnectorV1Type3`）、Mooncake（`MooncakeConnector` / `MooncakeStoreConnector`）、KVBM、FlexKV（`FlexKVConnectorV1`，自 vLLM v0.17.2 内置）、vLLM-Ascend（`AscendStoreConnector`）全部无需 fork vLLM**。

> **这是本次调研最强的收敛证据**：一个连接器接口 + 一个事件格式，把原本互相竞争的 KV 系统变成了**可互换的上游**。它们不再争抢同一个 socket，而是在**所有权、传输、准入策略、可观测性**上竞争。

**但"标准"这个词要非常小心 —— 三条硬事实：**

1. 🚨 **不存在 "KV connector API 1.0"。** `KVConnectorBase_V1.__init__` **在每次实例化时都会打日志**：*"This API is experimental and subject to change in the future as we iterate the design."* **没有版本常量、没有 ABI**。唯一被强制的契约是外部连接器的**三参数构造函数**（含 `kv_cache_config`）。
2. 🚨 **vLLM 官方在 2025-07 提出的 RFC #20492《KV-Cache Interoperability API Standardization》已被 "Closed as not planned"**（标签 `RFC` + `stale`，"Over 90 days of inactivity"），**没有替代品**。该 RFC 提出两件事：
   - **技术半部，最终以别的方式落地了**：可复现的块哈希 PR **#20511 已合入**，引入 `PrefixCachingHashAlgo = Literal["sha256", "sha256_cbor", "xxhash", "xxhash_cbor"]`（CBOR 规范序列化 + 跨语言哈希）。⚠️ **但默认值仍是 `"sha256"`**，即**默认并未启用跨语言可复现的那一档**。
   - **契约半部没有落地**：版本化的公开 schema、Go/Python 参考库都不存在。
3. 🚨 **任务描述中提到的 `docs.vllm.ai/en/latest/design/kv_connector.html` 已不存在** —— 该 URL 现在命中文档站的 catch-all 重定向（HTTP 200 但跳到 `/contributing/`）。**KV connector 的"设计文档"现在就是 `base.py` 的 docstring。**

**2026 年 vLLM 连接器层的具体事实**（源码级）：

- 注册的连接器共 **17 个**，含 `NixlConnector` / `NixlPullConnector` / `NixlPushConnector`；**`SharedStorageConnector` 已改名 `ExampleConnector`**（遗留文档问题见 issue #49399）。
- `kv_role` ∈ `kv_producer` / `kv_consumer` / `kv_both`，⚠️ **`NixlConnector` 的 `kv_both` 已废弃**（#33702）。
- `kv_transfer_params` **需要一个有状态代理**；vLLM 另加了**非标准的 `conversation_id`** 字段用于多轮 KV 复用。
- **2026 新增**：NIXL KV-cache **租约续期**（30 s 租约 + 通过 NIXL 的 `"HB:"` 心跳通知，续期间隔 = lease_duration//6，转发循环不单独开线程）；**双向 P↔D 传输**；**push 模式** NixlConnector；**分层 offloading**。
- **`vllm/v1/kv_offload/` 完整结构**：`CPUOffloadingSpec` / `TieringOffloadingSpec`（CPU 是**强制主层**，secondary 只能经它级联/回迁）、`OffloadingManager`、`SecondaryTierManager`、`CachePolicyFactory` 中注册的 **`lru` + `arc`**、**`OffloadKey = block_hash ‖ group_idx(4B 大端)`**、**`Medium{CPU, STORAGE}`** + **`Locality{LOCAL, REMOTE}`**、`OffloadingEvent.ownership`、**`LookupResult{MISS, HIT, HIT_PENDING, RETRY}`**、**`OffloadPolicy{CHUNK_LEVEL, REQUEST_LEVEL}`**、`blocks_per_chunk` 组块、`self_describing_kv_events`。⚠️ 树外连接器有**三个独立的加载器，且每个都会打 "experimental" 日志**。
- **生态中最接近"可移植 KV 块契约"的东西**：**`CanonicalKVCaches` / `CanonicalPageMapping` / `CopyRun` / `parallelism_agnostic`**（RFC #42082）—— 目前**只有 vLLM 在做**。

### 6.3 KV Cache Events

**格式（vLLM 源码为准）**：`KVEventBatch` = `{ts, events[], data_parallel_rank}`；`events[]` ∈ {`BlockStored`, `BlockRemoved`, `AllBlocksCleared`}；`medium` ∈ {`GPU`, `CPU`, `STORAGE`}；并已扩展到 `locality`（LOCAL/REMOTE）、`ownership`（哪个 secondary tier 生成）、`session_id`、`group_idx` / `kv_cache_spec_kind` / `kv_cache_spec_sliding_window`（混合注意力分组）、`extra_keys`（多模态/LoRA/cache_salt/prompt embedding）。

**谁在消费同一套格式**：

| 系统 | 事件来源 | 传输 | 恢复机制 |
|---|---|---|---|
| **vLLM 自身** | `ZmqEventPublisher` | ZMQ PUB（默认 :5557）+ 可选 ROUTER（:5558） | buffer-only replay（`deque`，默认 10,000 步，线性扫描，**无内置初始同步**） |
| **Dynamo KV Router** | worker 本地 RadixTree（`LocalKvIndexer`） | **NATS Core 或 ZMQ**（事件面） | 事件缓冲 + **全量 RadixTree 快照（tree dump）**回退；单调 `event_id` + 逐 DP rank 恢复 |
| **llm-d KV-Cache Indexer（EPP）** | vLLM/SGLang | **ZMQ**（集中式或 Pod 发现式） | 两级 LRU / Ristretto / Redis-Valkey 索引后端 + **speculative indexing（TTL 2s）** |
| **AIBrix** | vLLM `--enable-kv-cache-events --kv-events-publisher=zmq` | ZMQ | 全局前缀索引 |
| **KVBM（Dynamo 1.0）** | KVBM 自身在块跨层移动/驱逐时发事件（覆盖 GPU/CPU/本地 SSD/远端） | Dynamo 事件面 | 由 KV Router indexer 消费 |

**结论**：**同一套语义（三类事件 + medium/locality 分层标注）已在 5 个系统间互通，但它们是"兼容"而不是"同一规范"**。关键证据与缺口：

- ✅ **SGLang 是"刻意"采用 vLLM 的 schema**。其源码 docstring 原话：*"This is the same encoding vLLM uses for its `KVCacheEvent`, so a consumer such as Dynamo decodes both engines with one code path."* 连 **ZMQ topic 也共用**：`kv@<pod-id>@<model-name>`。
- ✅ **llm-d 是"适配器中间人"**：`VLLMAdapter` + `SGLangAdapter` 两个适配器把两家事件归一化。其代码注释还揭示 **vLLM 在 2026 年中改过编码**（PR #42892：**位置数组 → 带 tag 的 map**），llm-d 只能靠**防御性的长度保护解析**来兼容。
- ❌ **Dynamo 是"分歧"的一方**：用自己的 `event_id` / `dp_rank` / `Stored|Removed|Cleared` 信封走 **NATS**，只为 vLLM 保留一个 ZMQ 桥；恢复模型也根本不同（`Events`/`TreeDump`/`TreeDumpFailed`/`TooNew`/`InvalidRange` vs vLLM 的有界缓冲）。
- ❌ **分层词表已经对不上**：**vLLM 用 `CPU`，SGLang 用 `CPU_PINNED`**；SGLang 的 **`DISK`** 与 **`EXTERNAL`** 在 vLLM 侧**没有对应常量**。
- ❌ **不存在 KV-events SIG 或共享规范** —— 针对"KV cache events standard"、"kv_events protocol"、"KVEventBatch spec"、"kv cache events SIG"四个方向的检索**全部为负**。
- **vLLM ZMQ 发布器的线格式**：三帧 `(topic, seq, payload)`，msgpack 序列化，`buffer_steps=10_000`，`hwm=100_000`，`END_SEQ=-1`，daemon 线程，**声称 "at-least-once delivery and monotonic ordering"**，DP 场景按端口偏移，并有 `register_publisher` 扩展点。

⚠️ 已知的跨系统摩擦（Dynamo 官方文档记载）：SGLang 的 `BlockStored` 一度**不支持 bigram tuple 风格的 token ids**（Dynamo issue #5096），需要额外的编码映射。

### 6.4 KV block / offload 抽象的比较

| 系统 | "块"抽象 | offload 抽象 | 分层表达 |
|---|---|---|---|
| **vLLM** | `KVCacheBlock` + block hash（内容寻址，`ExternalBlockHash`） | `OffloadingConnector` + `CPUOffloadingSpec` / `TieringOffloadingSpec` + `SecondaryTierManager` + `CachePolicy` | `medium`（GPU/CPU/STORAGE）+ `locality`（LOCAL/REMOTE） |
| **SGLang HiCache** | **HiRadixTree** 节点（记录"KV 在哪：本地 GPU/CPU/L3，或同时多层"） | `HiCacheStorage(ABC)`：只需 `get`/`exist`/`set` | 层是显式的 L1/L2/L3 参数 |
| **LMCache** | chunk（默认 256 tokens）+ `TokenHasher` | `StorageManager` + `L1Manager` + Store/Prefetch/Eviction Controller + L2 Adapter | L1 / L2 两层 |
| **Dynamo KVBM** | `Block`（`[num_layers][page_size × inner_dim]`）+ `sequence_hash`；**生命周期状态机 Reset→Partial→Complete→Registered→Reset** | `Storage/BlockPool`（Device/Host/Disk/Remote）+ `TransferManager`（per-path 队列） | **G1/G2/G3/G4 四层** + 块级可观测性事件 |
| **AIBrix** | block（I/O 最细粒度）+ chunk（默认 512） | L1（进程内 DRAM）+ L2（`KVCache` CRD 供给的分布式集群，7 种后端） | L1/L2 两层 + ingestion 策略（ALL/HOT/EVICTED） |
| **Tair KVCM** | Block（**带前缀依赖**）+ `CacheLocation`（状态机 writing→serving→deleting）+ `LocationSpec`（URI 统一寻址） | 元数据面 / 数据面分离；`StartWriteCache`→写入→`FinishWriteCache` 两阶段 | Storage 类型（NFS/3FS/TairMemPool/Mooncake）+ Instance Group 配额/水位 |

**没有出现统一的 "KV block" 抽象。** 各家在**块粒度与语义**上分道扬镳：vLLM 是内容寻址哈希块、SGLang 是 radix 树节点、KVBM 是可注册句柄 + 状态机、Tair 是带前缀依赖的元数据对象。真正稳定下来的只有**粒度的方向**（都趋向"page/chunk 级"以便零拷贝 I/O）和**分层命名**（L1/L2/L3 或 G1–G4）。

### 6.5 Gateway API Inference Extension（GIE）

- 仓库 `kubernetes-sigs/gateway-api-inference-extension`，**768★ / 313 forks**，最新 **v1.6.1（2026-09-10 / 09-11）**，另有独立的 `conformance/vX.Y.Z` 发布线与已晋升的 `registry.k8s.io/.../lwepp:v1.6.0` 镜像。
- 🚨 **2026 年 GIE 最重要的变化是 EPP 被"搬了出去"**：**v1.6.0（2026-08）把 `EPP`、`InferenceObjective`、`InferenceModelRewrite`、`BBR` 全部移出到 llm-d 仓库**（`llm-d/llm-d-router`，339★，已到 v0.10.0；BBR 去了 `llm-d-inference-payload-processor`）。**kubernetes-sigs 侧只保留 `InferencePool` + LWEPP + conformance**（外加一份模型服务器协议提案）。同时移除的还有 Alpha API：`InferenceObjective`、`InferenceModelRewrite`、`EndpointPickerConfig`。
- ⚠️ **`InferencePool` 的 GA 状态存在自相矛盾**：README 称已 GA（v1.0.0 起），但其自己的 Roadmap 读起来仍是 **pre-GA**，并把 **prefix-cache-aware LB 列为未来工作**。**本报告如实记录这一矛盾，不给结论。**
- ✅ **前缀缓存感知的"概念"确实是标准的**：GIE 的 Metrics & Capabilities 里有 "Prefix Cache status"，`DataProducer` 是标准插件接口。**但"实现"完全属于 llm-d。**
- ⚠️ `InferenceObjective` 位于 `llm-d-router`（`apix/v1alpha2/`），不在 GIE 里。
- ⚠️ **GIE 的 conformance 套件是整套体系里唯一的合规性测试** —— 而它只覆盖 `InferencePool`，**不覆盖任何 KV 语义**。

### 6.6 2026 年收敛态势判断

**已经收敛的（事实标准）**：

1. **引擎侧接入点** → vLLM `kv_transfer_config` / `KVConnectorBase_V1`（+ `kv_connector_module_path`）。SGLang 侧是高内聚的 `HiCacheStorage(ABC)`（三方法接口）。
2. **KV 状态事件语义** → `BlockStored` / `BlockRemoved` / `AllBlocksCleared` + `medium` + `locality`，由 vLLM 定义并被 SGLang 兼容、Dynamo/llm-d/AIBrix 消费。
3. **传输抽象** → **NIXL**（西方生态 / NVIDIA 体系）与 **Mooncake Transfer Engine**（中国生态 + 跨厂商加速器矩阵）并行。两者**不是竞争而是互相嵌套**：Mooncake TE 是 NIXL 的 plugin。
4. **K8s 编排抽象** → `InferencePool` + EPP（GIE GA）。

**没有收敛的（2026 年仍在分裂）**：

1. **路由决策的所有权**：Dynamo 有自带 KV Router、llm-d 有 EPP、AIBrix 有 Envoy ext-proc 网关、KServe 走 GIE/llm-d、SGLang 无路由。**同一集群里可能有三套索引在各自维护同一份缓存视图。**
2. **块语义与哈希**：内容寻址哈希**不可复现**导致必须全局固定 `PYTHONHASHSEED`；RFC #20492 的 CBOR/SHA256 方案被搁置。
3. **分层命名与语义**：L1/L2/L3（SGLang、AIBrix）vs G1–G4（KVBM）vs L1/L2（LMCache MP）vs Storage/Instance Group（Tair）。**"层"的含义甚至不一致**（SGLang 的 L3 是"可共享"、LMCache 的 L2 才是"持久"）。
4. **元数据/索引后端**：内存 LRU（默认）vs Redis/Valkey vs RadixTree vs 集中式 KVCM。llm-d 明确说 Redis 索引"通常没必要"；Tair 则整个产品建立在集中式元数据服务上。
5. **是否需要中央存储服务**：Mooncake Store / Tair KVCM / PrisKV 要 master/meta 服务；llm-d P2P 与 vLLM P2P tier **明确不要**中心化存储。

**2026 年下半年的两个可能的收敛动作（已公开承诺但未落地）**：

- **llm-d v0.10**：明确把"**A standardized model server interface**"（跨 vLLM/SGLang/TRT-LLM 的统一引擎能力查询/生命周期/运行时配置 API）和"**KV-cache observability and intelligence**"（统一的可观测性框架 + 更智能的缓存管理策略）列为目标。⚠️ v0.10 目标为 2026 年 9 月，**本报告成稿时尚未发布**。
- **KV 感知路由的基准互测**：AIBrix 的 `brixbench` 已内置对 `llmd-routing-*`（含 llm-d v0.8.1）与 `dynamo-routing-*`（含 Dynamo v1.3.1/v1.4.0）的对照场景矩阵 —— 这是少见的、跨项目头的可比评测尝试。

**另一个值得注意的方向转变**：**关键路径正在从"计算"转向"KV 搬运"**。这条线由三个 2026 年论文支撑：
- **TENT**（arXiv 2604.00368，清华 + Moonshot + 阿里云 + 浙大 + 蚂蚁 + Approaching.AI）——把传输意图与执行解耦，路径解析从 init-time 移到 **slice-time 晚绑定**，跨 rail "喷撒"切片；把 **NVLink 提升为一等传输**。在 SGLang HiCache + Qwen3-235B + H800 上（10 轮 agentic，600 GB 相同的 KVCache 预算）：输入吞吐 **20,757 → 78,759 tok/s**（非缓存基线 3.79×），平均 TTFT **2.12s → 0.53s**；相对 **Mooncake TE** 仍有 **1.36× 吞吐 / P90 TTFT 好 26.4%** —— 且归因**完全来自传输层优化**（缓存策略完全相同）。微基准：两节点 8×200 Gbps RoCE，写吞吐 **+33.7%**、P99 延迟 **−27.6%**。NIC 故障注入下抖动 **<50 ms**、重入 **26 ms**、**零应用可见失败**。生产：千卡集群"几乎所有"流量，峰值 **>5000 万 tokens/分钟**，典型 **90% 命中率**，有效计费成本为标准市场价的 **25%**。
- **SAC**（arXiv 2606.19746）——论证 **RDMA 对稀疏注意力是错误的**（会取整个前缀而只有 top-k 条目活跃），主张用 **CXL** 做 cache-line 粒度按需加载：DeepSeek-V3.2 + SGLang，比 RDMA 基线 **吞吐 2.1×、TTFT 9.7×↓、TBT 1.8×↓**。**这暗示"哪种内存织物"本身将成为可调项。**
- **KVServe**（arXiv 2605.13734）——服务感知的**自适应 KV 压缩**（模块化策略空间 + 贝叶斯剖析 + 在线 bandit），并给出**静态压缩设置不安全**的结论；vLLM 内最高 **9.13× JCT 加速 / 32.8× TTFT 下降**。

**另一个值得警惕的 2026 年现象：负面结果开始被发表。** `Metronome`（arXiv 2607.02640）记录了**亚稳、静默的服务悬崖**（崩溃 0/20 vs 14/20）；**llm-d 官方 P2P 博客里"这不是普适加速"的自我纠正**也是同类信号 —— 共同说明 2026 年的 KV 缓存优化已进入需要谨慎标定的阶段。

> ⚠️ **一处来源冲突（不采信任一单方）**：关于 **CacheRoute**，一份并行调研称仓库 `AstraNetLab/CacheRoute`（322★）**没有论文、也没有发布任何数字**（路线图项未勾选），且**同名 arXiv 2608.19677 是另一篇单人作者的工作**；而另一份调研把 arXiv 2608.19677 的 **176 ± 11 QPS @ 3.5s p99（最强基线的 2.3×）、命中率 64.1% → 93.2%** 记作 CacheRoute 的结果。**本报告不对 CacheRoute 的具体数字作断言**，仅记录"前缀亲和存在反例"这一方向性结论（该结论亦被 P2P 博客与 Metronome 独立支持）。

**唯一一份 2026 年写出来的完整 KV cache 规范，以及它为什么可以被忽略**：**`kv-first`**（`openhivesai`）—— 定义了 KV Manifest、KVCC L0/L1/L2 分层、以及一致性测试。**它的 L0 实际上是把 NIXL + vLLM 已经在做的事写成了正式形式，L1 对应 vLLM 的 canonical layout 工作。** 🚨 **但该仓库 0 star、0 fork、无任何实现者**，且**没有证据表明相关项目知道它的存在**。这是"标准缺位"最直观的证据：*不是没人尝试写规范，而是写出来没人用。*

**其他治理层面的负面结论**：
- **PyTorch Foundation 没有 KV 相关工作组**（只有弱信号：llm-d 声明的合作意向，以及一个 PyTorch Conference 的演讲标题）。
- **CNCF 的"分离式服务 AI Conformance profile"仅处于"已宣布计划"阶段，未能验证其存在。**
- 唯一的合规性测试（GIE conformance）**不覆盖任何 KV 语义**。

### 6.7 各存储层的实测数字（本轮新获得，含重要的"收益边界"）

这一组数字的价值在于：**它们都公开了"何时不划算"的边界条件**，这是厂商营销材料里最常被省略的部分。

| 场景 | 数字 | 边界条件 / 诚实度 |
|---|---|---|
| **GPU-direct RDMA 到 S3**（Dell + NVIDIA，NIXL `OBJ` 插件） | 235K token 时 **TTFT 11,223 ms → 837 ms（13.4×）**，CPU 占用 **−约 90%** | ⚠️ **在 4K token 时 offload 是负收益（91 → 113–129 ms）**；**Dell 自己披露了约 8K–16K 的交叉点** —— 这是本轮见到的**披露最规范**的一组数字 |
| **Redis 作为 L2 层** | 平均 TTFT **32.883 s → 21.517 s（−34.6%）**，轮次时间 **−40.3%**；客户端吞吐 **0.278 → 9–10 GB/s（约 30×）** | ⚠️ **任务描述中提到的 Redis 博客本身零 benchmark** —— 这些数字来自**另一篇跟进文章**（redis.io, 2026-03-30）。引用时需注意 |
| **PrisKV（RDMA + GDR，作为 AIBrix L2）** | **TTFT 4,842 → 450 ms（−90.7%）**，吞吐约 **6.35×**（vLLM / H20 / Qwen3-32B / 并发 32） | 有明确配置 |
| **AWS：SageMaker HyperPod → LMCache → Curvine** | **跨 Pod 命中率 100%**，**TTFT 774 → 287 ms（2.7×）**；跨节点 L2 读 **~56 ms**（~1,900 token） | ⚠️ **AWS 自己的分层建议推荐用 ElastiCache Valkey 而非 S3 作为远端 L2** |
| **Tutti**（arXiv 2605.03375） | 相对启用 GDS 的 SSD LMCache：**TTFT −78.3%、请求率 2×、成本 −27%** | 其论点是 **GDS "remains CPU-centric"**，因为 I/O 被切成大量碎片化小随机读 —— 与"GDS 更快"的直觉相反 |
| **py-kvcache**（arXiv 2609.11744, 2026-09-10） | 80K 上下文下比 LMCache **快 2.0×** | 🚨 **但论文自己写道："on an H100 the average request falls below the break-even point"**，结论是 *"external KV caching should be treated as a setup-specific admission decision."* —— **这是本轮最有价值的一句结论**。 |

**一个必须知道的可移植性坑（来自云侧调研）**：**GPU-direct S3 KV 缓存不是厂商中立的。** NIXL 标准 S3 引擎**只支持 `OBJ_SEG` + `DRAM_SEG`（CPU）**，因此**每个厂商都必须重写 `getSupportedMems()` 来加上 `VRAM_SEG`** —— Dell 的贡献正是这个。这意味着"某云支持 S3 KV 直读 GPU"**不能跨云推断**。

**云厂商其实不卖 KV cache，卖的是 prompt caching** —— 这是一个重要的市场事实：**没有任何超大规模云厂商提供 "KV cache as a service"**。各家卖的是**缓存输入 token 的折扣价**：

| 云 | 机制 | 价格/门槛 |
|---|---|---|
| **Amazon Bedrock** | Prompt caching GA（2025-04） | **缓存读 75% 折扣**；最小 512–4,096 tokens |
| **Azure OpenAI / Foundry** | Prompt caching | **Provisioned 部署下最高 100% 折扣**；最小 1,024 tokens；24 小时保留期（经 **GPU 本地 offload**） |
| **Google Vertex** | Context caching | **约 90% 折扣**；最小 2,048 tokens（⚠️ 所有 Google Cloud 侧信息均为二手 —— `*.google.com` 全程 TCP 不可达） |
| **Cloudflare Workers AI** | 前缀缓存 | DeepSeek V4 Flash **$0.440 → $0.014/M** |
| **Fireworks** | 前缀缓存 | **$0.22 → $0.007** |

⚠️ 另外两个概念澄清（**极易混淆，且会影响架构决策**）：
- **llm-d 里的 Valkey 后端存的是 KV *索引*（块→Pod 的路由元数据），不是 KV 块本身**，而且 llm-d 自己都说这个后端**"很少有必要"**（对比内存方案）；**`filesystem` 不是 indexer 后端**。
- **Redis LangCache 是语义化"响应缓存"（整次调用都跳过），不是 KV 复用**。Redis 自己写得很清楚：*"A prefix-cache hit is a cheaper generation call, not an avoided one."*

---

## 7. 对比表

### 7.1 五强对比

| 维度 | **Mooncake** | **LMCache** | **NVIDIA Dynamo（KVBM）** | **llm-d** | **SGLang HiCache** |
|---|---|---|---|---|---|
| Stars（2026-09-15） | 6,575 | **11,812** | 8,083 | 4,542 | 35,982（SGLang 主仓） |
| 最新版本 | v0.3.13（2026-08-26） | v0.5.5（2026-09-12） | v1.4.2（2026-08-29） | v0.9.0（2026-08-17） | v0.5.19（2026-09-05） |
| 维护方 | Moonshot AI + 清华 + 多厂商 | LMCache 社区 / PyTorch Foundation / Tensormesh | NVIDIA | CNCF Sandbox（Red Hat/Google/IBM/CoreWeave/NVIDIA） | SGLang 社区 |
| KV 所在层 | DRAM + SSD/NVMe + VRAM（分布式池） | L1 CPU DRAM / Device-DAX / NVMe(GDS)；L2 持久存储 | **G1 GPU / G2 CPU pinned / G3 本地 SSD / G4 远端对象存储** | 任意（vLLM 原生 CPU/FS，或第三方引擎） | **L1 GPU / L2 host DRAM / L3 存储后端** |
| 传输 | 自有 TE：RDMA / TCP / NVLink / EFA / NVMe-oF / CXL / Ascend 等 | NIXL、CUDA IPC（进程内/MP）、ZMQ（控制）、GDS | **NIXL**（UCX/POSIX/GDS/OBJ/AZURE_BLOB/HF3FS/MOONCAKE…） | NIXL（P2P）、POSIX（FS backend）、ZMQ（事件） | 委托后端（Mooncake TE / 3FS / NIXL / AIBrix / EIC） |
| 驱逐/放置 | per-object 策略：副本数、preferred segment、soft/hard pin；master 水位 | L1 LRU（水位 0.8 / 比例 0.2）；L2 由 adapter 决定 | 块状态机 + OffloadManager；分层权重参与路由（host 0.75 / disk 0.25） | indexer 分层权重（gpu 1.0 / cpu 0.8）；FS backend 不做驱逐（需外部 pvc_evictor） | write_through / write_through_selective / write_back；prefetch best_effort / wait_complete / timeout |
| 集成点 | vLLM（PD + Store）、SGLang HiCache L3、TRT-LLM、LMCache、NIXL plugin、vLLM-Ascend、FlexKV、LMDeploy 等 | `LMCacheConnectorV1` / `LMCacheMPConnector`；LMCache Operator（`LMCacheEngine` CRD） | 自有 connector（vLLM/TRT-LLM）+ NIXL + GAIE 插件 | EPP 插件 + vLLM `OffloadingConnector` / 第三方 connector + KV Events | 引擎内置 + `HiCacheStorage(ABC)` 三方法接口 |
| 强项 | 生产最久、规模最大、跨厂商加速器最广 | 引擎无关、生态最宽、算子化 K8s 部署 | 全栈（KVBM + Router + Planner）、商业支持 | K8s 控制面、路由精度可选、CNCF 中立 | 引擎内零成本集成、L3 后端最开放 |
| 弱项 | 需要 master 服务；生态偏中国 | 需要额外进程/服务；两层而非三层 | 绑定 NVIDIA；SGLang 不在 KVBM 支持矩阵 | 路由与存储分属不同仓库，需自行组装 | 无跨实例 L2；路由能力缺失（靠外部） |

### 7.2 其他框架速览

| 项目 | Stars | 最新版本 | KV 层 | 接入点 | 备注 |
|---|---|---|---|---|---|
| **vLLM 原生** | 91,813 | v0.29.0 | CPU pinned + FS/OBJ/P2P secondary | 自身 | `TieringOffloadingSpec` + 分层 KV events |
| **AIBrix** | 5,089 | v0.7.0 | L1 进程内 DRAM + L2 分布式集群 | `AIBrixOffloadingConnectorV1Type3`；SGLang HiCache L3 后端 | `KVCache` CRD；7 种 L2 后端 |
| **KServe** | 5,911 | v0.20.0 | 同上（走 vLLM） | `spec.kvCacheOffloading` → 自动渲染 `--kv-transfer-config` | CNCF Incubating；Tesla 生产 3×/2× |
| **阿里 Tair KVCache** | 255 | 无正式 release | 元数据服务 + NFS/3FS/TairMemPool/Mooncake | vLLM / SGLang / RTP-LLM / TRT-LLM connector | 元数据面/数据面分离；HiSim 仿真误差 <5% |
| **DeepSeek 3FS** | 10,000 | — | L3 分布式文件系统 | SGLang `hf3fs`、Tair Storage 类型、NIXL 插件 | 本身不是 KV 系统，是 L3 后端 |
| **腾讯 FlexKV** | 351 | tag v1.2.1 | CPU → 本地 SSD → 远端（PB 级） | `FlexKVConnectorV1`（vLLM v0.17.2+ 内置）、`--enable-flexkv`（SGLang v0.5.16+）、Dynamo 原生、TRT-LLM | 支持 DeepSeek-V4 异构逐层 KV |
| **字节 EIC** | 商业产品（SGLang 内置） | — | GPU 余量显存 + 本地 + 分布式 RAM+SSD | SGLang `--hicache-storage-backend eic`；vLLM KV Transfer Connector | GDR 延迟约 TCP/RDMA 的 1/10 |
| **华为 vLLM-Ascend** | 2,826 | v0.23.0 | NPU HBM → Host DRAM → SSD → UCM(NFS/3FS) | `AscendStoreConnector` | 内存池化（MemFabric/UB）是核心 |
| **PegaFlow** | 204 | v0.24.4 | L1 本地 DRAM / L2 跨节点 DRAM / L3 SSD | vLLM external KV connector | 跨节点 194 GB/s；Rust + io_uring |
| **kvcached** | 1,386 | — | GPU 虚拟内存化 | vLLM / SGLang | 目标是**多模型共享 GPU**，不是分布式缓存 |

---

## 8. 给工程选型的实操建议

1. **先问"所有权"而不是"性能"**：KV 池的故障域是否与推理引擎解耦？（LMCache MP / Mooncake Store / PegaFlow 是"是"；进程内 offload 是"否"）
2. **固定 `PYTHONHASHSEED`** 是所有内容寻址共享 KV 存储的**硬前提**（Mooncake Store、vLLM FS/OBJ tier 都需要）。这是当前"缺少哈希标准"的直接代价，最容易被忽略。
3. **事件面是隐藏的运维成本**：Dynamo 与 vLLM 的回放/恢复语义不同，llm-d 的精确索引需要 vLLM render endpoint + ZMQ。上精确路由前先确认网络与 sidecar 预算。
4. **P2P 拉取必须先测交叉点**：llm-d 的公开数据是 2K token 起才有收益、短前缀有 1.2–1.3 s 的 pull 下限。默认值是部署相关的，官方因此默认关闭。
5. **不要把"分层"当成通用语言**：各家 L1/L2/L3 的含义不同（SGLang 的 L3 是"可共享"、LMCache 的 L2 才是"持久"）。对接时以各家的**具体后端名**为准（`hf3fs` / `mooncake` / `eic` / `aibrix` / `resp` …）。
6. **对厂商自报数字保持警惕**：本报告中 FlexKV 的 60%/13%/16%、Tensormesh 的 10×/41×、AIBrix 的 1,600 张 L20、EIC 的 3×/67% 都是**无模型/硬件/脚本细节的营销数字**，与 vLLM×Mooncake（3.8×/46×，有 trace 与配置）、LMCache MP（13×，有完整软硬件与相同内存预算对照）、llm-d P2P（有交叉点表与重复实验）**不在同一个证据级别**。

---

## 9. 明确无法验证 / 存在矛盾的事项

1. **RFC #20492（KV-Cache Interoperability API Standardization）已被 "Closed as not planned"** —— 即 KV cache 接口**没有走 vLLM 正式标准化流程**。是否有其他治理渠道（CNCF / PyTorch Foundation / LF AI）在推进，本次调研**未找到证据**。
2. **NIXL 的正式规范/ABI/版本策略与治理归属未能验证**。目前是 NVIDIA 单一厂商主导。
3. **vLLM `KVConnectorBase_V1` 是否有版本化/稳定 ABI**：未能找到官方承诺；连接器的破坏性变更历史存在（如 `NixlConnector` 在 KServe v0.21.0-rc0 的一个 e2e 样例中被移除）。
4. **llm-d v0.10 尚未发布**（目标 2026 年 9 月），其"标准化模型服务器接口"与"统一 KV 可观测性框架"目前只是路线图承诺。
5. **Tensormesh / Inferact 的可验证 OSS 组件**：Tensormesh 有 2,000 万美元融资（AMD Ventures/CoreWeave/NVentures）与"内存问题"叙事，但**未能从一手来源获得其 KV cache 架构或独立 OSS 组件**；Inferact 是 vLLM 商业化公司（1.5 亿美元种子轮，2026-01-22 宣布），**没有可验证的 KV cache 专属 OSS 组件**，"LMCache 衍生公司"的表述**不成立**。
6. **"PrisDB" 命名**：仅出现在 AIBrix v0.4.0 release note 的文字里（"connector integration for PrisDB and InfiniStore"），**找不到仓库、官网或产品文档**。当前所有 AIBrix 文档与博客都写 **PrisKV**。二者很可能是同一系统改名，**但无法证实**。
7. **AIBrix 的 L2/KVCache 场景 benchmark 尚未发布**（仓库内 README 仍写 "Coming Soon!"），仅有博客/演讲数字。
8. **KServe 的 CNCF 阶段与日期**：TOC 公告 2025-11-11 内部自相矛盾（又称 "September 2025"），未能定论；**未找到毕业证据**。
9. **ByteDance 侧多项未能验证**：不存在名为 "ByteDance KVCache" 的开源项目；`veRL`、`Penguin`、`PrefixCache`、`eplb`（实为 DeepSeek）、`LMDeploy`（实为上海 AI Lab）与字节 KV cache 的关联**均未验证**；Volcengine Ark 的 prompt caching API 文档未获取。**InfiniStore 的 RDMA 传输描述仅为弱验证**（未从源码确认），且其**最后推送为 2025-11-13，约 10 个月陈旧**。
10. **华为/昇腾的若干项未能验证**：`ubsio.wcache.evict_water_level` 的定义在已获取的 openEuler MemStore 文档中找不到；CloudMatrix/UB 的部分指标未验证；把其他节点远端 NPU HBM 当作 KV 池**容量**使用的做法未见文档。
11. **两份昇腾 KV Pool 文档内部矛盾**：设计文档称"目前仅支持 DRAM 作为 KV Cache Pool 存储"，而用户指南已记录 SSD offload 支持。
12. **3FS 作为 KV store 的 KV 专属性能数字**未从 3FS 自身文档获得。
13. **MinIO AIStor "memkv"**：搜索结果中出现了一个 MinIO 的 KV cache 相关产品名，但**未能在本次调研中取得可引用的原始资料**（页面为 JS 渲染）。**不予采信。**
14. **vLLM production-stack 与 llm-d 的关系**：production-stack（2,571★，最新 vllm-stack-0.1.12 / 2026-07-24）README 中 prefix-aware 路由仍标注为 WIP，**未能验证其是否已被 llm-d 取代或二者是并行关系**。
15. **EIC 的容量/延迟/定价/区域**未验证（Volcengine 文档 API 返回"未授权访问"）；承诺的 EIC 开源镜像是否发布过**未能验证**。
16. **百度 AttentionStore**：`attentionstore_sdk` 未公开分发、产品细节仅一份新闻稿；❌ **"X-MoE" 无法验证**（且已排除两篇不点名百度、数字互相矛盾的诱饵文章）；❌ openGauss KV cache、千帆之外的百度侧缓存**未验证**。
17. **华为/昇腾**：MindIE KV 池化的性能数字、MindIE 逐层传输的线协议、MemCache A2/A3 图表数值、MemFabric PrefixCache 的 QPS（只有图表）**均未验证**；`ubsio.wcache.evict_water_level` 的定义在已获取的 openEuler 文档中找不到；CloudMatrix/UB 的部分指标（含网传的"每 NPU 392 GB/s"）**在论文中不存在**。**Gitee 无法抓取**（849 字节 JS 壳），**中国生态的实际代码中心是 GitCode 而非 Gitee**。
18. **3FS**：**"40 GiB/s" 的 per-node vs aggregate 口径未定**；2026-05-07 之后是否继续开发未知；vLLM 3FS connector 的合并日期（PR #37636）未能取得；SGLang PR #9109（3fs zerocopy）与 issue #34969（"HF3FS HiCache 遇 DeepSeek-V4 logical KV anchor 时 ZeroDivisionError"）详情未展开。
19. **DeepSeek-V4 / V4.1-Flash 的一手技术报告未获取** —— 890 bytes/token、FP4 KV、10% DRAM SWA 池、72 小时全局 KV 生命周期等数字来自**二手**报道 + 一篇佐证博客；官方 HuggingFace 权重路径未验证。
20. **云厂商侧**：**Google Cloud 的 GKE / GKE Inference Gateway 页面在本次调研中被 Cloudflare 拦截**，未取得可引用的一手内容；Alluxio、Curvine 自身的 KV-cache 定位、Redis/Valkey 作为 KV cache 后端的官方连接器细节，本轮由并行子任务处理，⚠️ **其汇总文件在本报告成稿时尚未完成合并**（原始产物在 `kvcache-research/raw/distcache/`、`raw/redisgds/`、`raw/cloud/`）。
21. **Mooncake 的贡献者雇主归属无法验证**：所有贡献者的 `company` 字段为空（`alogfans` 自述 "Independent Researcher"；PR #759 作者 `zuocunwei` 列的是美团）。**华为的参与依据是 `MAINTAINERS.md` 与命名，因此本报告表述为"Huawei-affiliated"而非"受雇于华为"。**
22. **Zhipu 声称的 SGLang HiCache 加载时序修复**：GLM-5 "ScalingPain" 报告称系统吞吐 **+132%**，且有一个 HiCache load-timing 修复被 SGLang 接受 —— **但未能定位到具体 PR**。
23. **若干未能识别的项目**：**`moriio`**（vLLM 树内 connector，传输方式与厂商**未能识别**）；**`ai-dynamo/kvcr`**（35★，2026-08-21 新建，机制**仅能推断**，未获一手说明）；**Google "TPU Raiden"** 无官方仓库；**OVMS 的 `--cache_dir` flag 不存在**；TGI 引入 prefix caching 的版本号未能定位；**`ModelEngine-Group/unified-cache-management`**（华为 UCM，334★）声称 **3–10× 延迟改善**，**但为厂商自述且无任何实验设置**。
24. **工具级可靠性警告**：`ungh.cc/releases` **不可靠** —— 它对四个确有 release 的仓库报告"no releases"，应以 `releases.atom` 为仲裁；`api.github.com` 在本轮部分会话中**全程 403**，`raw.githubusercontent.com` 一度**完全不可达**。这些网络约束意味着 **star/版本快照存在时间差**，请按"2026-09-15 当日"理解，不要当作稳定事实。
25. 🚨 **两条反"交叉引用"警告（很容易在二次引用中出错）**：
    - **arXiv 2209.01496《InfiniStore: Elastic Serverless Cloud Storage》是另一个完全不同的系统**（2022 年的 serverless 函数对象存储）。**不要把 GitHub `bytedance/InfiniStore` 的 KV 宣称归到这篇论文上。**
    - **Mooncake 广为流传的 ">90% KV cache hit rate" 仅存在于一篇中文二手转载中，从未出现在一手来源里** —— **不要引用**（一手论文的口径是"全局缓存命中率最高为本地缓存的 2.36×"，见 §3.1）。
26. **InfiniStore 的量化数据极少**：唯一的实测表述是"prefill 期间网络开销 ≤1%"；GitHub 自 v0.2.33（2025-03-23）后无 release，最后提交 **2025-11-13**。
27. **一处时间戳冲突**：PrisKV 的"最后活动时间"在不同来源不一致 —— GitHub API 的 `pushed_at` 为 **2026-05-20**，而逐 commit 核对得到的最后提交是 **2026-01-29**。二者相差约 4 个月，**本报告不裁定**；无论取哪个，结论都是"**停滞且采用度低（59★）**"。
28. **工具瑕疵的连带风险**：本轮并行调研中有一个 GitHub 取文件辅助脚本（`raw/sc/ghfile.py`）存在**失败时静默返回 `/tmp` 下陈旧内容**的 bug，曾被下游子任务误用（短暂读到了另一个仓库的 `pyproject.toml`）。该 bug **已修复**（唯一临时路径 + 显式失败检测与非零退出），且**受影响的载荷性结论已用独立抓取重新核验**（Fluid ROADMAP 的 KV 文本与 issue #5875 一致；SGLang L3 后端清单与 LMsys HiCache 博客一致），**因此没有结论建立在被污染的数据上**。⚠️ 若后续有其他 agent 复用该脚本，请取修复版。

---

## 10. 主要来源 URL

### 10.1 五强

**Mooncake**
- https://github.com/kvcache-ai/Mooncake
- https://www.usenix.org/system/files/fast25-qin.pdf （FAST'25 最佳论文全文）
- https://www.usenix.org/conference/fast25/presentation/qin
- https://dl.acm.org/doi/full/10.1145/3773772 （ACM TOS 期刊版）
- https://arxiv.org/abs/2407.00079
- https://kvcache-ai.github.io/Mooncake/
- https://vllm.ai/blog/2026-05-06-mooncake-store
- https://kvcache-ai.github.io/Mooncake/design/transfer-engine/index.html
- https://arxiv.org/abs/2604.00368 （TENT）
- https://arxiv.org/abs/2605.10670 （EEP）

**LMCache**
- https://github.com/LMCache/LMCache
- https://arxiv.org/abs/2510.09665
- https://blog.lmcache.ai/en/2026/04/03/lmcaches-new-architecture-boosts-moe-inference-performance-by-10x/
- https://blog.lmcache.ai/en/2026/01/21/p2p-1/
- https://blog.lmcache.ai/en/2025/10/31/tensormesh-unveiled-and-lmcache-joins-the-pytorch-foundation/
- https://docs.lmcache.ai/mp/index.html
- https://docs.lmcache.ai/developer_guide/architecture.html
- https://github.com/LMCache/LMCache/blob/dev/operator/DESIGN.md
- https://pytorch.org/blog/lmcache-joins-pytorch-ecosystem/

**NVIDIA Dynamo / NIXL / KVBM**
- https://github.com/ai-dynamo/dynamo
- https://github.com/ai-dynamo/nixl
- https://blog.nvidia.com.br/blog/nvidia-inicia-a-producao-do-dynamo-o-sistema-operacional-de-inferencia-amplamente-adotado-para-fabricas-de-ia/ （Dynamo 1.0，2026-04-09）
- https://docs.dynamo.nvidia.com/dynamo/v1.4.2/llms.txt
- https://docs.dynamo.nvidia.com/dynamo/knowledge-base/modular-components/kvbm/overview.md
- https://docs.dynamo.nvidia.com/dynamo/knowledge-base/modular-components/kvbm/kvbm-design.md
- https://docs.dynamo.nvidia.com/dynamo/knowledge-base/modular-components/router/offloading-support-matrix.md
- https://docs.dynamo.nvidia.com/dynamo/knowledge-base/modular-components/router/kv-event-replay-comparison.md
- https://docs.dynamo.nvidia.com/dynamo/knowledge-base/modular-components/router/router-design.md
- https://docs.dynamo.nvidia.com/dynamo/knowledge-base/modular-components/planner/overview.md
- https://github.com/ai-dynamo/aiconfigurator
- https://github.com/ai-dynamo/nixl/blob/main/docs/nixl.md

**llm-d**
- https://github.com/llm-d/llm-d
- https://github.com/llm-d/llm-d-kv-cache
- https://github.com/llm-d/llm-d-router
- https://llm-d.ai/blog/llm-d-v0.9-hardened-for-scale
- http://llm-d.ai/blog/p2p-kv-cache-sharing-llm-d
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/README.md
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/prefix-cache-aware-routing.md
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/kv-indexer.md
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/kv-offloader.md
- https://github.com/llm-d/llm-d/blob/main/docs/well-lit-paths/foundations/enable-p2p-prefix-cache-sharing.md
- https://www.cncf.io/blog/2026/03/24/welcome-llm-d-to-the-cncf-evolving-kubernetes-into-sota-ai-infrastructure/
- https://llm-d.ai/docs/well-lit-paths/foundations/tiered-prefix-cache

**SGLang HiCache**
- https://github.com/sgl-project/sglang
- https://docs.sglang.io/docs/advanced_features/hicache_design
- https://docs.sglang.io/docs/advanced_features/hicache_best_practices
- https://lmsys.org/blog/2025-09-10-sglang-hicache/
- https://github.com/sgl-project/sglang/pull/10376 （AIBrix KVcache 集成）
- https://github.com/sgl-project/sglang/pull/29701 （FlexKV 集成）
- https://arxiv.org/abs/2312.07104 （RadixAttention）

### 10.2 vLLM

- https://github.com/vllm-project/vllm
- https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/distributed/kv_events.py
- https://docs.vllm.ai/en/latest/features/kv_offloading_usage/
- https://docs.vllm.ai/en/latest/features/disagg_prefill.html
- https://docs.vllm.ai/en/v0.28.0/api/vllm/distributed/kv_transfer/kv_connector/v1/offloading/events/
- https://github.com/vllm-project/vllm/issues/20492 （KV-Cache Interoperability API Standardization RFC，Closed as not planned）
- https://github.com/vllm-project/vllm/pull/20511 （SHA-256 + CBOR 可复现前缀哈希）
- https://github.com/vllm-project/production-stack
- https://github.com/vllm-project/vllm/pull/34328 （FlexKV connector）

### 10.3 其他框架与厂商

- https://github.com/vllm-project/aibrix · https://aibrix.readthedocs.io/latest/features/kvcache-offloading.html · https://aibrix.readthedocs.io/latest/features/kv-event-sync.html · https://aibrix.github.io/posts/2026-06-16-single-node-pd/ · https://aibrix.github.io/posts/2025-11-26-priskv-intro/ · https://arxiv.org/abs/2504.03648
- https://github.com/kserve/kserve · https://kserve.github.io/website/blog/kserve-0.17-release · https://llm-d.ai/blog/production-grade-llm-inference-at-scale-kserve-llm-d-vllm · https://developers.redhat.com/articles/2026/04/21/kserve-llm-d-optimized-gen-ai-inference
- https://github.com/alibaba/tair-kvcache · https://www.aliyun.com/product/kvcache · https://help.aliyun.com/zh/redis/product-overview/tair-kvcache/ · https://help.aliyun.com/zh/pai/tokenworks-kv-cache
- https://github.com/deepseek-ai/3FS
- https://github.com/taco-project/FlexKV · https://cloud.tencent.cn/developer/article/2654280 · https://github.com/Tencent/KsanaLLM
- https://github.com/vllm-project/vllm-ascend · https://docs.vllm.ai/projects/ascend/ · https://github.com/Ascend/TransferQueue
- https://github.com/PaddlePaddle/FastDeploy · https://arxiv.org/abs/2602.08585 （百度 LU-KV, ICML 2026） · https://github.com/baidu-baige/LU-KV · https://github.com/baidu/vLLM-Kunlun
- https://github.com/aibrix/PrisKV · https://github.com/bytedance/InfiniStore · https://github.com/ByteDance-Seed/ShadowKV · https://github.com/verl-project/verl · https://www.volcengine.com/docs/85848/1749188
- https://github.com/curvineio/curvine · AWS《Tiered KV cache for large LLMs on Amazon SageMaker HyperPod with Curvine》 · AWS Bedrock prompt caching GA 公告
- https://arxiv.org/abs/2506.12708 （CloudMatrix384）
- https://github.com/ModelEngine-Group/unified-cache-management
- https://github.com/bytedance/InfiniStore · https://github.com/aibrix/PrisKV · https://www.volcengine.com/docs/85848/1749188
- https://github.com/novitalabs/pegaflow · https://vllm.ai/blog/2026-05-18-pegaflow
- https://github.com/ovg-project/kvcached · https://arxiv.org/abs/2508.08448
- https://github.com/sgl-project/rbg
- https://github.com/MoonshotAI/checkpoint-engine
- https://github.com/xLLM-AI/xllm
- https://github.com/kubernetes-sigs/gateway-api-inference-extension
- https://github.com/ai-dynamo/nixl （v1.4.1, 2026-09-01；`meson.build` 的 14 个插件清单）
- https://github.com/openhivesai/kv-first （2026 年唯一的完整 KV cache 规范草案；0★ 无实现者）
- https://github.com/curvineio/curvine （→ `CurvineIO/curvine`，CNCF Sandbox，945★，v0.5.1-alpha）
- https://redis.io/blog/ （Redis + LMCache 作为 L2 的实测数字在跟进文章中；2026-03-30）
- Dell + NVIDIA GPU-direct RDMA 到 S3（NIXL `OBJ`）的 TTFT 对照与 8K–16K 交叉点披露
- Amazon Bedrock prompt caching GA 公告 · Azure OpenAI / Microsoft Foundry prompt caching 文档 · Google Vertex context caching 文档 · Cloudflare Workers AI 定价 · Fireworks 前缀缓存定价
- https://github.com/fluid-cloudnative/fluid · https://github.com/juicedata/juicefs · https://github.com/valkey-io/valkey · https://github.com/redis/redis
- https://redis.io/blog/get-faster-llm-inference-and-cheaper-responses-with-lmcache-and-redis/
- https://juicefs.com/en/blog/solutions/idle-resources-elastic-high-throughput-storage-cache-pool
- https://github.com/uccl-project/uccl · https://github.com/NVIDIA/kvpress · https://github.com/snu-mllab/KVzip
- https://github.com/SemiAnalysisAI/InferenceX
- https://github.com/jjiantong/Awesome-KV-Cache-Optimization

### 10.4 2025–2026 关键论文

- KV Cache 管理综述：https://arxiv.org/abs/2607.02574 （*From Tensor Buffer to Distributed Memory Hierarchy*）
- 系统感知 KV 优化综述（ACL 2026 Findings, sKis 分类）：https://arxiv.org/abs/2607.08057
- TENT：https://arxiv.org/abs/2604.00368
- EEP：https://arxiv.org/abs/2605.10670
- SAC（CXL 稀疏注意力 KV 分离）：https://arxiv.org/abs/2606.19746
- KVServe：https://arxiv.org/abs/2605.13734
- CacheRoute：https://arxiv.org/abs/2608.19677
- Metronome：https://arxiv.org/abs/2607.02640
- CrossPool：https://arxiv.org/abs/2606.24506
- ScoutAttention：https://arxiv.org/abs/2603.27138
- DistServe：https://arxiv.org/abs/2401.09670 · Splitwise：https://arxiv.org/abs/2311.18677 · MemServe：https://arxiv.org/abs/2406.17565 · TetriInfer：https://arxiv.org/abs/2401.11181 · Preble：https://arxiv.org/abs/2407.00023 · Pensieve：https://arxiv.org/abs/2312.05516 · CacheBlend：https://arxiv.org/abs/2405.16444 · CacheGen：https://arxiv.org/abs/2310.07240 · vAttention：https://arxiv.org/abs/2405.04437
- 压缩/量化里程碑：KIVI https://arxiv.org/abs/2402.02750 · Atom https://arxiv.org/abs/2310.19102 · QServe https://arxiv.org/abs/2405.04532 · SnapKV https://arxiv.org/abs/2404.14469 · H2O https://arxiv.org/abs/2306.14048 · StreamingLLM https://arxiv.org/abs/2309.17453 · KVQuant https://arxiv.org/abs/2401.18079 · GEAR https://arxiv.org/abs/2403.05527 · MiniCache https://arxiv.org/abs/2405.14366 · PyramidKV https://arxiv.org/abs/2406.02069 · InfiniGen https://arxiv.org/abs/2406.19707 · InstInfer https://arxiv.org/abs/2409.04992 · KVzip https://arxiv.org/abs/2505.23416

> ⚠️ **重要更正**：任务中给出的若干 arXiv ID 有误，正确 ID 为：Splitwise = **2311.18677**（非 2401.09686）、MemServe = **2406.17565**（非 2406.16818）、TetriInfer = **2401.11181**（非 2404.01992）、"Infinigen" 实为 **InfiniGen = 2406.19707**（arXiv 2602.18750 是 *HillInfer*，非"重要性持久化"论文）、"InstAttention" 已更名为 **InstInfer = 2409.04992**。✅ 任务中标注为高风险的 2026 年 ID（2604.00368 / 2605.10670）**经核实为真实论文**。
