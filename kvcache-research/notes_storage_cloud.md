# Storage-Layer and Cloud-Vendor KV-Cache Systems

**Research note — compiled 2026-09-15** (all GitHub star/fork counts scraped from GitHub repo HTML on 2026-09-15 unless stated otherwise; release versions from shields.io `github/v/release`).

Scope: open-source LLM KV-cache management and KV-cache-centric inference serving, with emphasis on the **storage layer** (distributed file systems, distributed caches, KV stores) and **cloud-vendor** offerings.

> **Methodology / verification note.** GitHub's unauthenticated REST API was rate-limited (60 req/h) early, so star/fork/release figures below were scraped from the GitHub repo HTML (`id="repo-stars-counter-star"`, `id="repo-network-counter"`) and shields.io JSON endpoints. **Partway through the session both `raw.githubusercontent.com` and then `github.com` itself became unreachable from this sandbox (curl exit 000)**, while `arxiv.org`, `llm-d.ai`, `aibrix.github.io`, `alluxio.io`, `redis.io`, `curvineio.github.io` and `juicefs.com` stayed reachable. Repository files were therefore read by extracting the embedded `"rawLines"` JSON from GitHub blob pages while GitHub was still up (GitHub later recovered, allowing several late re-verifications). Items I could **not** verify are marked **UNVERIFIED** rather than estimated — there are **38** such flags in this note.

---

## Executive summary

1. **DeepSeek's 3FS is the most important "KV cache as a file system" system in the open-source world**, and it is explicitly documented as such: 3FS's own README lists "KVCache for Inference" as a first-class workload, with a measured **40 GiB/s peak read throughput** for KV-cache clients. Development on public `main` appears to have **stalled after 2026-05-07**, and 3FS has **no tagged GitHub releases** — a notable maturity caveat.
2. **DeepSeek's model-side KV-cache compression has moved faster than its storage layer.** DeepSeek-V4 (arXiv, 26 Apr 2026) and DeepSeek-V4.1-Flash (10 Sep 2026) reduce KV footprint dramatically (V4-Pro needs **10% of V3.2's KV cache** at 1M context; V4.1-Flash claims **890 bytes/token** global KV). V4.1-Flash's deployment note — SWA KV no longer persisted to SSD but kept in a **distributed host-DRAM pool (10% of DRAM) with minute-scale TTL**, global KV with a **72-hour guaranteed lifetime** — is itself a KV-cache *tiering* design.
3. **JuiceFS's LLM story is model-weight and dataset caching, not KV cache.** I could not find any official JuiceFS KV-cache backend or vLLM/SGLang/LMCache connector. The famous "70 GB/s cache pool" headline refers to *aggregate NIC bandwidth* (600 Gbps ≈ 70 GB/s), not a measured throughput; the measured instantaneous figure stated in that article is 10 GB/s.
4. **Fluid has a real, roadmap-level KV-cache program**, but nothing shipped in a release yet: the Fluid ROADMAP lists "LLM KV Cache Orchestration" (disaggregated vLLM/SGLang KV cache, cross-Pod KV sharing, Mooncake integration), and issue #5875 proposes a Mooncake-Store-based `CacheRuntime` PoC. The well-known NetEase "42 min → 30 s" case study is about **model-weight cold starts**, not KV cache.
5. **The integration surface has consolidated around a small set of primitives**: SGLang HiCache's `HiCacheStorage` ABC (`get/exist/set`), vLLM's pluggable `KVConnector`s, LMCache, and **NIXL** as the transport/plugin substrate. The storage-facing NIXL plugins documented by LMCache are `GDS`, `GDS_MT`, `POSIX`, `HF3FS`, `OBJ`, `AZURE_BLOB`, `DOCA_MEMOS`; NIXL's own tree additionally carries `ucx`, `ucx_mo`, `libfabric`, `gpunetio`, `mooncake`, `gusli`, `uccl`, `infinia` (§6.6).
6. **The cloud vendors have not built KV-cache storage services — they orchestrate open-source ones, and they mostly sell *prompt caching* instead.** The strongest cloud KV-cache result found is **AWS's own** SageMaker HyperPod blog wiring **vLLM → LMCache → Curvine**, achieving **100% cross-Pod cache hit and TTFT 774 ms → 287 ms (2.7×)**. AWS's *own* tiering guidance recommends **ElastiCache Valkey** — not S3 — as the remote L2. Bedrock/Azure/Vertex/Workers AI/Fireworks all price **cached input tokens** (75–100% discounts), which is prompt caching, not a KV-cache tier. **No hyperscaler sells "KV cache as a service."**
7. **Where the real KV-cache numbers live:** tiered KV stores — **PrisKV** claims **TTFT 4,842 ms → 450 ms (−90.7%) and ~6.35× throughput** on vLLM/H20/Qwen3-32B at 32 concurrency; **AIBrix's v1 connector** adds >20% TPOT/throughput over its legacy connector (Llama 3.1 70B, TP=8); **Ant Group** reports **84% TTFT reduction** with HiCache+Mooncake. **The single most common error in this literature is conflating KV cache with model-weight caching or with semantic/response caching** — see the flagged cases throughout §6.
8. **The benefit of an NVMe/object KV tier is NOT monotonic in bandwidth — it is a break-even decision, and the vendors who publish honestly say so.** **Dell + NVIDIA** contributed a GPU-direct (RDMA, `cuObject`) engine to NIXL's `OBJ` plugin and measured **TTFT 11,223 ms → 837 ms (13.4×) at 235K tokens** on S3-compatible storage — while disclosing that **at 4K tokens offload *loses* (91 ms → 113–129 ms)** and that "below roughly 8K–16K tokens the overhead outweighs the benefit… **This is a long-context capability.**" **Tutti** (arXiv 2605.03375) shows **GDS itself "remains CPU-centric"** because fragmented GPU memory produces "massive numbers of tiny random I/Os", and beats GDS-enabled SSD-backed LMCache with **TTFT −78.3% and 2× request rate**. **py-kvcache** (arXiv 2609.11744) finds at 80k tokens disk loading is **2.0× faster than LMCache**, yet "**on an H100 the average request falls below the break-even point**", concluding that "**external KV caching should therefore be treated as a setup-specific admission decision.**" Any storage-tier ROI claim — ours or a vendor's — must state the GPU, prefix length, and batch regime, or it is not a result.

---

## 1. DeepSeek 3FS / Fire-Flyer File System

### 1.1 What it is, who maintains it, maturity

| Attribute | Value (verified 2026-09-15) |
|---|---|
| Repo | https://github.com/deepseek-ai/3FS |
| Maintainer | DeepSeek (`deepseek-ai` org) |
| Description (from repo) | "A high-performance distributed file system designed to address the challenges of AI training and inference workloads." |
| Stars / forks | **10,200 / 1,095** |
| Created | 2025-02-27 (Open Source Week, Day 5) |
| License | **MIT** |
| Last push to `main` | **2026-05-07** (`pushed_at`), confirmed by the `/commits/main` page: latest commit date 2026-05-07 |
| GitHub releases / tags | **None** — shields reports "no releases or repo not found"; the `/tags` page shows no tags |
| Branches (all) | `3FS`, `ghost`, `KuribohG`, `main`, `SF-Zhou`, `SF-Zhou-patch-1` |
| Open issues | 161 |

**Caveat to flag:** the last public commit is 2026-05-07. As of September 2026 the public 3FS tree has been quiet for four months. Adjacent DeepSeek repos are still active (FlashMLA last commit "today", DeepGEMM "yesterday"), so this looks specific to 3FS rather than to the org. Whether DeepSeek continues 3FS development in public is **UNVERIFIED**.

### 1.2 Architecture

From the 3FS README and `docs/design_notes.md`:

- **Disaggregated architecture**: throughput of thousands of SSDs and network bandwidth of hundreds of storage nodes, accessed locality-obliviously.
- **Strong consistency** via **Chain Replication with Apportioned Queries (CRAQ)**, so application code does not need to reason about stale reads.
- **Stateless metadata services** backed by a **transactional key-value store (e.g. FoundationDB)**. The file interface is POSIX-like, so no new storage API must be learned.
- **Chunk storage system**: on each SSD the chunk engine keeps a fixed number of data files plus a **RocksDB instance** for chunk metadata and system info, with an in-memory chunk-metadata cache; operations are `allocate`, `get` (hashmap cache, O(1) average), `commit` (RocksDB write batches, atomic), and removal. (design_notes.md §"Chunks and the metadata")
- **Client APIs**: FUSE, plus an **asynchronous zero-copy USRBIO API** (`src/lib/api/hf3fs_usrbio.h`, `hf3fs.h`, documented in `src/lib/api/UsrbIo.md`). USRBIO is the path used by SGLang's HF3FS backend.
- **Repository layout relevant to KV cache**: `src/` contains `client`, `core`, `fuse`, `kv`, `lib`, `memory`, `meta`, `mgmtd`, `migration`, `storage`, `tools`; there are also Python packages `hf3fs/`, `hf3fs_fuse/`, `hf3fs_utils/` with `setup.py` / `setup_hf3fs_utils.py` (this is the `hf3fs` pip package that SGLang imports).
- **Important nuance:** `src/kv/{KVStore.cc,KVStore.h,LevelDBStore.*,RocksDBStore.*,MemDBStore.h}` is a **local, embedded key-value store used for 3FS metadata**, *not* a distributed KV-cache API. 3FS does not expose a "KV cache service"; KV caching is done by storing KV blocks as **files/pages on 3FS** and letting an inference framework (SGLang HiCache, LMCache, NIXL) manage keys and placement.

### 1.3 Measured performance (3FS README, "Performance" section)

| Benchmark | Configuration | Result |
|---|---|---|
| Peak read throughput | 180 storage nodes, each 2×200 Gbps InfiniBand NICs + 16×14 TiB NVMe SSD; 500+ client nodes at 1×200 Gbps | **~6.6 TiB/s aggregate read**, *with background traffic from training jobs* |
| GraySort (via smallpond) | 25 storage nodes (2 NUMA/node, 2×400 Gbps NICs/node); 50 compute nodes (192 physical cores, 2.2 TiB RAM, 1×200 Gbps NIC) | **110.5 TiB sorted in 30 min 14 s = 3.66 TiB/min average** across 8,192 partitions |
| **KVCache read** | "all KVCache clients (1×400 Gbps NIC/node)"; peak and average shown | **peak throughput up to 40 GiB/s**; a second figure shows IOPS of GC removal ops during the same period |

**Conflict to flag.** 3FS's README says "the read throughput of *all* KVCache clients … peak throughput reaching up to 40 GiB/s", whereas DeepSeek's `open-infra-index` page says "**40+ GiB/s peak throughput per client node for KVCache lookup**" — i.e. *per node*. These are mutually inconsistent readings of the same figure (a single 400 Gbps NIC is ~50 GB/s line rate, so a per-node figure of 40 GiB/s is physically plausible but near saturation; an aggregate-over-clients figure is equally plausible). **I could not resolve this from the published text; treat "40 GiB/s" as "up to 40 GiB/s peak KVCache read throughput in DeepSeek's benchmark" without asserting per-node vs aggregate.**

Also from `open-infra-index`: 3FS is used for "Training data preprocessing, dataset loading, checkpoint saving/reloading, embedding vector search & **KVCache lookups for inference in V3/R1**" — i.e. 3FS KV caching is in production use inside DeepSeek's own V3/R1 serving stack.

### 1.4 DeepSeek "Open Source Week" (Feb 2025) and later releases

Source: https://github.com/deepseek-ai/open-infra-index (8,065★ / 295 forks; last commit May 2025). The index states the week started **Feb 24, 2025**, "5 repos – one daily drop", and ran to Day 6.

| Day | Release | KV-cache relevance | Headline numbers (from open-infra-index / repo READMEs) |
|---|---|---|---|
| 1 | **FlashMLA** | **High** — MLA decoding kernel with **paged KV cache (block size 64)** | 3000 GB/s memory-bound; BF16 580 TFLOPS compute-bound on H800. Repo now **12,926★ / 1,153 forks**, MIT, last commit *today* — still actively developed |
| 2 | **DeepEP** | Indirect — EP all-to-all for MoE prefill/decode; low-latency decode kernels | First open-source EP communication library; NVLink + RDMA; native FP8 dispatch. Now **10,149★ / 1,439 forks**, **v1.2.1**, MIT, last commit August 2026 |
| 3 | **DeepGEMM** | Indirect — FP8 GEMM powering V3/R1 inference | "Up to 1350+ FP8 TFLOPS on Hopper", fully JIT. Now **7,830★ / 1,261 forks**, **v2.1.1.post3**, MIT, last commit *yesterday* |
| 4 | **DualPipe**, **EPLB**, and a profile-data repo | No | DualPipe = bidirectional pipeline parallelism (training). EPLB = expert-parallel load balancer. Profile-data = "Analyze computation-communication overlap in V3/R1". DualPipe now **3,009★ / 332 forks** (last commit Dec 2025); EPLB **1,430★ / 210** (Mar 2025) |
| 5 | **3FS** + **smallpond** | **High** (3FS) | 6.6 TiB/s read; 3.66 TiB/min GraySort; 40+ GiB/s peak KVCache throughput. smallpond now **5,011★ / 452 forks**, MIT, last commit Mar 2025 |
| 6 | **DeepSeek-V3/R1 Inference System Overview** | Indirect | "**73.7k / 14.8k input/output tokens per second per H800 node**"; "cost profit margin 545%" |

Later items listed in `open-infra-index`: **2025-04 "The Path to Open-Sourcing the DeepSeek Inference Engine"**, **2025-05 ISCA'25 paper** "Insights into DeepSeek-V3: Scaling Challenges and Reflections on Hardware for AI Architectures", and the SC24 paper "Fire-Flyer AI-HPC: A Cost-Effective Software-Hardware Co-Design for Deep Learning".

**Larger DeepSeek open-source footprint (2025–2026).** The `deepseek-ai` GitHub org lists **39 repositories** (2 pages of 30 + 9, sorted by last update). Names observed: `3FS`, `DeepEP`, `DeepGEMM`, `DeepJIT`, `DeepSeek-Coder`, `DeepSeek-Coder-V2`, `DeepSeek-LLM`, `DeepSeek-Math`, `DeepSeek-Math-V2`, `DeepSeek-MoE`, `DeepSeek-OCR`, **`DeepSeek-OCR-2`**, `DeepSeek-Prover-V1.5`, `DeepSeek-Prover-V2`, `DeepSeek-R1`, `DeepSeek-V2`, `DeepSeek-V3`, `DeepSeek-V3.2-Exp`, `DeepSeek-VL`, `DeepSeek-VL2`, `DeepSelect`, `DeepSpec`, `DreamCraft3D`, `DualPipe`, **`Engram`**, `EPLB`, `ESFT`, `FlashMLA`, `Janus`, **`LPLB`**, **`TileKernels`**, `awesome-deepseek-*`, `deepseek-harness`, `deepseek-recipe`, `open-infra-index`, `profile-data`, `smallpond`.
- **KV-cache-relevant among the newer ones:** `TileKernels` and `DeepSeek-V3.2-Exp` (per its README, DSA/CSA indexer kernels land in DeepGEMM PR #200 and sparse-attention kernels in FlashMLA PR #98). `DeepSeek-OCR` (23,889★ / 2,200 forks) and `DeepSeek-OCR-2` are **not** KV-cache systems.
- **There is no `DeepSeek-V4` repository** in the org listing; V4-series weights appear to be distributed via Hugging Face rather than a dedicated GitHub repo (**UNVERIFIED** as to the exact HF org/repo path for the official V4.1-Flash weights — third-party mirrors such as `RedHatAI/DeepSeek-V4-Flash` appeared in search results).

### 1.5 DeepSeek-V4 / V4.1-Flash — the model-side KV-cache story (highly relevant)

**DeepSeek-V4** — arXiv **2606.19348**, "DeepSeek-V4: Towards Highly Efficient Million-Token Context Intelligence", submitted **26 Apr 2026** (DeepSeek-AI et al.):
- Preview of the V4 series: **DeepSeek-V4-Pro** (1.6T params, 49B activated) and **DeepSeek-V4-Flash** (284B params, 13B activated), both **1M-token context**.
- Architectural changes: hybrid attention combining **Compressed Sparse Attention (CSA)** and **Heavily Compressed Attention (HCA)**; **Manifold-Constrained Hyper-Connections (mHC)**; **Muon** optimizer. Pre-trained on >32T tokens.
- **KV-cache headline:** "In the one-million-token context setting, **DeepSeek-V4-Pro requires only 27% of single-token inference FLOPs and 10% of KV cache compared with DeepSeek-V3.2**."

**DeepSeek-V4.1-Flash** — announced **10 Sep 2026**, reported by MarkTechPost (secondary source; the primary technical report link was not fetched — **UNVERIFIED** at the primary-source level):
- 552B backbone params + 196B additional **Engram** params; 1M-token context; **8B activated per token in prefill, 16B in decode**; MIT-licensed open weights with vLLM / SGLang / Transformers paths on Hugging Face.
- **"Global KV cache footprint of 890 bytes per token, about 1/4 of DeepSeek-V4-Flash and roughly 437× smaller than DeepSeek-V1."** (Corroborated independently by a second article titled "DeepSeek V4.1 Flash: 890 Bytes KV Cache per Token".)
- **Causal Encoder–Decoder (CED)**: 40-layer backbone split into 20 causal encoder layers and 20 decoder layers; inspired by YOCO, the decoder computes **no global KV of its own** — per-layer projections derive it from the final encoder hidden state, nearly halving prefill compute. A 128-token sliding-window attention runs in every layer; decoder SWA states are rebuilt by replaying only the last 128 prompt tokens ("Decoder SWA Bounded Replay").
- **Compressed Sparse Attention 2 (CSA2)**, attacking cache size along the *layer* axis. Each CSA2 layer is statically one of three modes — **Full** (computes its own main KV + indexer K, fresh Top-512 indices), **Reindex** (reuses main KV and indexer K, rescores with its own indexer Q), **Reuse** (reuses main KV and latest Top-K indices, skips the indexer). The 18 CSA2 encoder layers use compression ratio 2 in 3 groups of 6 (1 Full, 5 Reuse); the 20 decoder layers use ratio 1 in 5 groups of 4. A **Hierarchical Sparse Indexer** lets the decoder's Full layer build a candidate pool of up to **16,384 positions (2,048 blocks of 8)**, so Reindex layers score a bounded set.
- **FP4 KV cache**: main KV quantized to **E2M1 with one E4M3 scale per 16 channels** (NVFP4-like, without its global scale), introduced via quantization-aware training in post-training, **nearly halving storage vs V4's FP8 cache**.
- **Deployment / KV-cache tiering (directly relevant to this report):** "**SWA KV is no longer persisted to SSD. It lives in a distributed pool carved from 10% of host DRAM with a TTL of minutes, while global KV keeps a guaranteed 72-hour lifetime. On a miss, Encoder SWA Bounded Replay recomputes only 128 tokens** instead of layers × window."
- Efficiency: single-token decode FLOPs rise by only **1/4** when context grows from 4K to 1M.

**Third-party KV-cache research built on DeepSeek-V4** (clearly *not* DeepSeek releases):
- arXiv **2606.09079**, "FlashMemory-DeepSeek-V4: Lightning Index Ultra-Long Context via Lookahead Sparse Attention" (v1 8 Jun 2026, v3 20 Jul 2026): Lookahead Sparse Attention with a Neural Memory Indexer keeps only query-critical KV chunks in GPU memory; backbone-free decoupled training of the indexer as a dual encoder. Reports **average physical KV cache footprint 13.5% of the full-context baseline** with **+0.6% absolute accuracy** on LongBench-v2 / LongMemEval / RULER; at 1M context **per-decode-token compute 0.30×**, **GPU KV cache 3.73 → 0.37 GB (−90%)**, giving **2.8× aggregate throughput and 2.7× concurrency** in PD-disaggregated serving on 8×H20.
- arXiv **2606.01065**, "Leyline: KV Cache Directives for Agentic Inference" (31 May 2026): argues the append-only prefix-cache model breaks under agentic, policy-driven editing of context; introduces a declarative 4-tuple directive with a per-architecture splice kernel using a closed-form RoPE-rotation correction. Reports **+11.2 pp replay cache-hit**, **latency cut of up to 241 ms**, and **+14.3 pp agentic solve rate** on debug-gym. (Note: this paper explicitly says "recent work on position-independent caching for MLA addresses this reuse problem".)

### 1.6 How 3FS is used as a KV-cache store

#### (a) SGLang HiCache — the primary integration

SGLang HiCache organizes memory as **L1 = GPU memory, L2 = host memory, L3 = distributed storage**, and integrates "distributed cache systems such as **Mooncake, 3FS, NIXL, and AIBrix KVCache**" for global KV storage and scheduling (SGLang `docs/docs/advanced_features/hicache_design.mdx`).

- **L3 backends**: `file`, `mooncake`, `hf3fs`, `nixl`, `aibrix`, `dynamic` — selected with `--hicache-storage-backend`. The `file` backend defaults to `/tmp/hicache` (overridable via `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR`) and is node-local unless that path is a shared mount; "distributed backends such as `mooncake`, `hf3fs`, `nixl` and `aibrix` give cluster-wide scope, but only when every instance is pointed at the same namespace and configuration."
- **Backend interface**: `class HiCacheStorage(ABC)`, requiring only **`get(key)`, `exist(key)`, `set(key, value)`**; "everything else, including heavy-lifting tasks such as scheduling and synchronization coordination, is handled by the central cache controller." `dynamic` lets users supply `backend_name`, `module_path`, `class_name` via `--hicache-storage-backend-extra-config` (JSON string, or `@file.toml|json|yaml`).
- **Metadata**: a `HiRadixTree` acts as a page table; each node records where a span's KV lives (GPU, CPU, L3, or several). To avoid overhead, HiRadixTree **does not sync L3 metadata continuously** — L3 access queries the backend in real time for existence and location.
- **Data plane**: GPU-assisted I/O kernels give **up to 3× higher throughput for CPU↔GPU transfers** vs plain `cudaMemcpyAsync`; host pools use a **"page-first" layout** (GPU pools stay "layer-first" for kernel compatibility) enabling larger per-transaction transfers, and with zero-copy this yields **up to 2× higher throughput** in typical deployments. L2→L3 transfers can pass memory addresses/sizes directly (zero-copy).
- **Write policies** for promoting data to slower tiers: **write-through** (strongest caching if bandwidth permits), **write-through-selective** (hit-count tracking, backs up only hot spots), **write-back** (when slower tiers become capacity-constrained). Prefetch from L3 is configurable: best-effort, terminate-in-flight when a request becomes schedulable (minimizes TTFT), or aggressive staging (improves reuse/throughput).
- **HF3FS-specific tuning flags** used in SGLang's own benchmark command: `--page-size 64 --hicache-ratio 2 --hicache-io-backend kernel --hicache-mem-layout page_first --hicache-storage-backend hf3fs --hicache-storage-prefetch-policy wait_complete`.
- **Scope constraint worth flagging** (from `hicache_best_practices.mdx`): "**L1 and L2 are private to a single inference instance; only L3 can be shared. Host memory cannot be pooled across instances or across hosts, not even for two instances on the same node.** Raising `--hicache-ratio` or `--hicache-size` only enlarges the instance's own private L2. Cross-instance reuse is the job of L3." This is the structural reason 3FS/Mooncake/NIXL/AIBrix exist as HiCache backends.
- Other operational knobs verified in `hicache_best_practices.mdx`: **runtime attach/detach of the L3 storage backend via HTTP admin endpoints, no restart required**; `tp_lcm_size` for the TP local cache manager; prefetch policies `best_effort` (terminate prefetch when needed), `wait_complete` (higher cache reuse), `timeout`. The doc contains dedicated **HF3FS and Mooncake deployment** walkthroughs.
- **Implementation** (`python/sglang/srt/mem_cache/storage/hf3fs/`): `storage_hf3fs.py`, `hf3fs_client.py`, `hf3fs_usrbio_client.py`, `hf3fs_utils.cpp` (C++ binding), `mini_3fs_metadata_server.py` (lightweight metadata server for dev/testing), plus a `docs/` folder. Mechanism: a **page-index allocator over namespaces** — `Hf3fsMetadataInterface` exposes `reserve_and_allocate_page_indices`, `confirm_write`, `get_page_indices`, `delete_keys`, `exists`, `clear`, with a `PoolName` namespace selector (`PoolName.KV`, and a v2 **hybrid KV + MAMBA** namespace per SGLang PR #22601). Data movement uses the 3FS **USRBIO** API through `Hf3fsUsrBioClient` (with an `Hf3fsMockClient` for tests).
- **Cross-instance reuse**: SGLang PR #8673 "feature(hicache): Support hf3fs-hicache reusing kvcache across different instances" (author `hzh0425`); SGLang PR #9109 "3fs zerocopy" (title only — **details UNVERIFIED**).

**Measured numbers with 3FS (LMsys blog, 2025-09-10, "SGLang HiCache: Fast Hierarchical KV Caching with Your Favorite Storage Backends"):**

| Source | Setup | Result |
|---|---|---|
| **Novita AI** (community quote in the blog) | Coding-agent scenario, **Qwen3-Coder-480B**, dialogues past 25K tokens over ~8 turns/session; **SGLang HiCache + DeepSeek 3FS KVStore** for large-scale historical KV caching | **average TTFT −56%**, **throughput 2×**, **cache hit rate 40% → 80%** |
| **Ant Group** (community quote) | **DeepSeek-R1-671B**, PD-disaggregated, in-house online general-QA requests; **HiCache + Mooncake** | cache hits gave **84% TTFT reduction** vs full re-computation |
| LMsys authors' own benchmarks | long-context and multi-turn conversation benchmarks | **up to 6× throughput improvement** and **up to 80% TTFT reduction** |

#### (b) vLLM

- vLLM PR **#37636** "[KVConnector] Support 3FS KVConnector" (author `ibifrost`) is **MERGED** — re-verified on the PR page, which carries the "merged commit" marker, "Merged" status text, and the note "merged 6 commits into"; **page dates span 2–9 April 2026**, so the merge landed in **early April 2026**.
- I verified the vLLM `docs/features/` directory listing: `ec_cpu_connector.md`, `index_cache.md`, `kv_offloading_usage.md`, `mooncake_connector_usage.md`, `mooncake_store_connector_usage.md`, `moriio_connector_usage.md`, `nixl_connector_compatibility.md`, `nixl_connector_usage.md`. **There is no 3FS-specific vLLM doc page**, which suggests the 3FS path is reached via the NIXL connector rather than a dedicated connector doc.
- For contrast, vLLM's `MooncakeStoreConnector` (doc verified) uses `MooncakeDistributedStore` as a **shared KV cache pool** for CPU/disk offloading, hash-based prefix dedup across vLLM instances, and single-/multi-node deployment including PD-disaggregated setups, configured via `--kv-transfer-config` plus a JSON config; `mooncake_master --port 50051` manages metadata.

#### (c) LMCache + NIXL

LMCache's NIXL storage backend documents **supported NIXL backends: `["GDS", "GDS_MT", "POSIX", "HF3FS", "OBJ", "AZURE_BLOB", "DOCA_MEMOS"]`** (docs.lmcache.ai, v0.4.7). Constraints verified from that page:
- `nixl_buffer_device` must be **`cpu`** for `POSIX`, `HF3FS`, `AZURE_BLOB`, `DOCA_MEMOS`; **`cpu` or `cuda`** is supported for `GDS`, `GDS_MT`, `OBJ`.
- In CPU mode NIXL shares `LocalCPUBackend`'s pinned buffer.
- **Dynamic mode** is supported for object backends (`OBJ`, `AZURE_BLOB`, `DOCA_MEMOS`) and file backends (`POSIX`, `GDS`, `GDS_MT`, `HF3FS`).
- `nixl_endpoint_list` is honored **only** for the `OBJ` backend.

This is the clearest example of **3FS being reached through a vendor-neutral KV-transfer abstraction**: LMCache/HiCache/Dynamo pick `HF3FS` as a NIXL plugin and the 3FS path is used as a file-backed KV tier.

#### (d) Alibaba Cloud Tair KVCache — **open-sourced, and it treats 3FS/HF3FS as a storage backend**

**Correction to a common assumption: Tair KVCache *is* open source.** Repo: **https://github.com/alibaba/tair-kvcache** — description "Alibaba Cloud's high-performance KVCache system for LLM inference, with components for global cache management, inference simulation (HiSim), and more." Verified signals: **255 stars**, **created 2025-12-29** (recently open-sourced), product page https://www.aliyun.com/product/kvcache. (Forks/license not captured before GitHub became unreachable — **UNVERIFIED**.)

From the README, the open-sourced components are **Tair KVCache Manager** and **Tair KVCache HiSim**:

- **Tair KVCache Manager** — a **centralized global KVCache metadata management service** ("deployed in a centralized mode, responsible for global metadata management of KVCache, providing services such as KVCache queries and storage capacity management"). Its architecture is the most explicit "KV-cache control plane" design found anywhere in this report:
  - **Access Layer (Server)**: HTTP and gRPC.
  - **Cache Logic (CacheManager)**: multiple matching logics — **prefix matching, sliding-window matching, KV matching**; a **two-phase write mechanism (obtain write address → notify after write completion)** "ensures data reliability"; and **dynamic storage-backend selection based on metrics such as storage-backend availability**.
  - **Storage Management (DataStorage)**: "Encapsulates unified interfaces and data location descriptions for heterogeneous storage, supporting systems like **HF3FS, Mooncake, NFS**, etc.", with real-time monitoring of backend availability and **storage water levels**.
  - **Index Management (MetaIndex)**: "metadata persistence based on external KV storage systems, ensuring metadata reliability during KVCM failures"; batch processing for performance; **sharded locks** for update atomicity.
  - **Capacity Management (Reclaimer & Executor)**: multi-dimensional capacity control (e.g. **Instance Group**), backend water-level control, **KVCache eviction based on Quota and water levels**, and a **background thread pool implementing asynchronous deletion** so "deletion does not block foreground requests".
  - **Cache Simulation and Optimization (Optimizer)**: "**Replays KVCache access traces**, efficiently simulates KVCache access behavior, analyzes key metrics such as **KVCache hit rate and capacity consumption**", and "based on simulation results, guides optimization of parameters like capacity to improve overall ROI."
  - **Client/Connector**: "Uses a unified transmission library to support KVCache transmission for multiple inference engines and storage backends. Currently supports engines such as **vLLM, SGLang, RTP-LLM, TRT-LLM**, etc."
- **Tair KVCache HiSim** — "a high-performance **CPU-based simulation system for LLM inference**" that replays real inference workload traces **without requiring GPU resources** to predict **TTFT, TPOT and throughput** across models, hardware, engines and configs. Currently supports **SGLang v0.5.6.post2 with Qwen3 Dense series models on H20 GPUs, achieving prediction errors below 5%.**

**The 3FS engineering story** (Alibaba Cloud developer articles): "阿里云 Tair 联手 SGLang 共建 HiCache，构建面向'智能体式推理'的缓存新范式" (Tair + SGLang co-building HiCache for agentic inference) — https://developer.aliyun.com/article/1693182 — and "阿里云 Tair 基于 3FS 工程化落地 KVCache：企业级部署、高可用运维与性能调优实践" — https://developer.aliyun.com/article/1695651

From the second article's abstract (the page is JS-rendered; only the summary text was retrievable): the Tair KVCache team, together with a hardware team, **deeply optimized 3FS** via RDMA traffic balancing, small-I/O tuning, and a **fully user-space persistence engine**, reporting **+150% 4K random-read IOPS**, and enhanced **GDR zero-copy**, multi-tenant isolation, and cloud-native operations, to build a "high-performance, high-availability, easy-to-manage KVCache storage foundation". This is consistent with the repo's statement that **HF3FS is one of Tair KVCache Manager's supported storage backends** — i.e. **Tair is the clearest example of an enterprise KV-cache control plane running on top of 3FS.**

**Note:** an earlier search surfaced only `li-xiao-qing/tair-kvcache` (**0 stars**, a personal fork) — that is *not* the official repo. The official one is `alibaba/tair-kvcache`.

#### (e) Mooncake's 3FS support

Mooncake PR **#2062** is titled "[Docs] Tag 3fs Feature as Experimental" (title verified; PR body/state **UNVERIFIED**) — i.e. Mooncake carries a 3FS feature marked **experimental**.

### 1.7 3FS maturity & adoption assessment

- **Strong**: production-proven inside DeepSeek's own V3/R1 serving ("KVCache lookups for inference in V3/R1"); multiple independent commercial adopters/derivatives (SGLang `hf3fs` backend, Alibaba Tair, Novita AI quoting 3FS-based HiCache results); a real deployment guide (`deploy/README.md`), Docker build images for TencentOS-4 / OpenCloudOS-9, and packaging for Ubuntu 20.04/22.04, openEuler 2403sp1, OpenCloudOS 9, TencentOS 4.
- **Weak / caveats**: **no tagged releases**; no public commit since **2026-05-07**; requires FoundationDB ≥7.1 and libfuse ≥3.16.1; the build has a `-DSHUFFLE_METHOD` compatibility trap ("binaries compiled with different compiler versions (e.g., g++10 vs g++11+) may be incompatible", issue #368) — a real operational sharp edge; no CNCF/independent governance (single-vendor project, **UNVERIFIED** whether any foundation donation is planned).

---

## 2. JuiceFS

### 2.1 What it is, maintainer, maturity

| Attribute | Value (2026-09-15) |
|---|---|
| Repo | https://github.com/juicedata/juicefs |
| Maintainer | Juicedata, Inc. (open core: Community Edition + Cloud Service + Enterprise Edition) |
| Stars / forks | **14,429 / 1,288** |
| Created | 2021-01-08 |
| License | **Apache-2.0** |
| Latest release | **v1.4.1** (shields.io); the site headline advertises "JuiceFS 1.4" |
| Last commit | *today* (2026-09-15) — actively developed |

### 2.2 Core mechanism

JuiceFS is a **POSIX distributed file system with decoupled data and metadata planes**:
- **Data** lives in **object storage** (S3 and compatible); data is split into **4 MB blocks** (minimum update unit) to reduce write amplification and fix object storage's random-write weakness. JuiceFS "treats object storage as a local disk", and provides an interface to migrate data back to S3, avoiding product lock-in.
- **Metadata** lives in a separate engine: **Community Edition** supports databases such as **Redis and TiKV**; **Enterprise Edition** uses a **Raft-based clustered metadata engine**.
- **Client-side caching** on each application node provides protocol conversion and cache acceleration (via JuiceFS CSI on Kubernetes or directly on the host). Idle local **NVMe and memory** can be pooled into a **distributed cache**; Community Edition users can point the cache directory at a distributed FS such as BeeGFS to build a distributed cache layer.

### 2.3 Measured numbers

**(A) "How JuiceFS Transformed Idle Resources into a 70 GB/s Cache Pool"** — 2025-08-07, Jerry Cai (https://juicefs.com/en/blog/solutions/idle-resources-elastic-high-throughput-storage-cache-pool). Customer: an LLM *training* company, data on AWS S3, previously accessed via **AWS FSx for Lustre**; migrated to JuiceFS.

- Built a **360 TB distributed cache pool**.
- "**With 600 Gbps of aggregate bandwidth provided by six servers, the cache pool achieved an instantaneous throughput of 10 GB/s.**" JuiceFS reports **95% TCP utilization for bandwidths under 100 Gbps**.
- **Headline-vs-body discrepancy (flagged):** the article title's **"70 GB/s"** matches **600 Gbps aggregate NIC bandwidth (≈70 GB/s)** — it is the *network capability* of the pool, **not** a measured 70 GB/s. The measured instantaneous throughput stated in the body is **10 GB/s**. Anyone citing "JuiceFS 70 GB/s" should read the primary text.
- Internal test, **JuiceFS Enterprise Edition 5.2**, large-file sequential read, in a **10 Tbps network aggregated by 100 nodes**: **aggregate throughput reached 1.23 TB/s**; "network utilization can reach over 95%" under 100 Gbps TCP and "approximately 70%" under 200 Gbps. Combining **disk and memory** resources on a 100 Gbps NIC achieved **12.5 GB/s**.
- **CPU overhead**: on a cache service node, reading **11 GB/s** from local disks and transmitting it over the network consumed **less than one CPU core** — "only one core for every 10 GB/s of bandwidth provided". On **client** nodes, each **GB/s read consumed 0.8 CPU cores**; saturating a 100 Gbps NIC with the **FUSE** client needs ~**10 CPU cores**.
- Claimed outcome: "reduces total storage costs to **one-tenth** of original levels while achieving throughput at TB/s scale".

**(B) "How JuiceFS Boosts Foundation Model Inference in Multi-Cloud Architectures"** — 2024-08-29, Changjian Gao (https://juicefs.com/en/blog/solutions/boost-foundation-model-inference-multi-cloud).

- Inference architecture: inference cluster on top, **distributed cache cluster in the middle**, object storage at the bottom, metadata service at top right. Read path: local memory cache → cache cluster → object storage.
- **Concrete number: for a Stable Diffusion Safetensors model on a single GPU, retrieval from the cache cluster showed latency as low as 0.5 ms vs ~20 ms from object storage — "nearly a 40-fold performance improvement."**
- Targets "model files hundreds of gigabytes in size" with "high-concurrency sequential reads", and "thousands of inference instances launched simultaneously".
- Multi-cloud/multi-region: Enterprise Edition **mirror file system** gives one-to-many regional replication; on read, the mirror region pulls from its local object store and falls back to the source region on delay.
- Large existing data: **metadata-only import** (prefix-matched, incremental) so inference can start without copying data; first read falls back to the original bucket and is then cached.
- Heterogeneous hardware: **cache node weights** (example 1:2:3 for servers with 8/16/24 TB SSD) to avoid the smallest node capping the cluster; also used to damp the hit-rate impact of taking cache nodes offline for maintenance.

**(C) "JuiceFS Performance Optimization for AI Scenarios"** (https://juicefs.com/en/blog/engineering/juicefs-ai-workload-performance-optimization): sequential read is bandwidth-bound (cold reads limited by object-storage bandwidth; with distributed cache the network becomes the bottleneck); **single-thread sequential read ≈ 3.5 Gbps**; "a node with a 40 Gbps NIC may achieve less than 5 Gbps usable bandwidth" in some cases; example cold 4 KB random read: **8 IOPS** with **~125 ms** object storage latency → concurrency ≈ 1. It explicitly frames the target workload as **model loading** (PyTorch `.pt` pickle files) and dataset random access (TFRecord/HDF5/LMDB).

### 2.4 Is JuiceFS a KV-cache layer? — **No (as far as I could verify)**

This is an important correction to a common framing. JuiceFS's documented LLM-inference role is **model-weight and dataset caching, plus multi-region distribution** — i.e. the *cold-start / model-loading* problem, not KV-block reuse.

Evidence:
- Both cited blogs discuss model files, image-generation model loading, training data, and checkpoints; **neither mentions KV cache, prefix caching, vLLM, SGLang, or LMCache.**
- The AI performance-optimization blog's workload list is bulk/big-file sequential read, dataset random access, and metadata — no KV-cache workload.
- I found **no official JuiceFS KV-cache storage backend or connector** for vLLM / SGLang / LMCache in JuiceFS docs or blogs (**UNVERIFIED whether one exists informally**; absence of evidence from the official docs is what I can assert).
- The only KV-cache-adjacent mention found is *architectural*: Fluid's NetEase case study lists **JuiceFS as one of the swappable Fluid cache runtimes** (alongside Alluxio and JindoCache) for **model loading** — https://www.cncf.io/blog/2026/05/21/how-netease-games-achieved-30-second-llm-cold-starts-on-kubernetes/

**Implication for a KV-cache report:** JuiceFS is best characterized as the **model-weight / dataset tier** that shortens inference cold starts and feeds weights to GPU nodes, and as a *substrate* on which a KV-cache directory could be mounted (e.g. as SGLang's `file` HiCache backend pointed at a shared JuiceFS mount) — but that is my inference, **not a documented JuiceFS KV-cache feature**.

### 2.5 Other JuiceFS signals (2026)

From the blog index: "Everything Is a File for Agents: Hello Uses JuiceFS to Build Stateful AI Workspaces" (2026-09-10); "How Tencent Cloud Built a Unified Storage Platform with JuiceFS and FoundationDB" (2026-08-27); "AI Data Storage: Challenges, Capabilities, and Comparative Analysis" (2026-08-03, compares S3, EFS, FSx for Lustre, Azure, GPFS, BeeGFS, JuiceFS); "5.5× Faster Small-File Writes: Tuhu Built a Unified AI Storage Platform with JuiceFS + Ceph RADOS" (2026-07-30).

---

## 3. Fluid (CNCF)

### 3.1 What it is, maintainer, maturity

| Attribute | Value (2026-09-15) |
|---|---|
| Repo | https://github.com/fluid-cloudnative/fluid |
| Maintainer | Fluid community; **CNCF project** — accepted to **Sandbox 2021-04-27**, **promoted to CNCF Incubating on 2026-01-08** (per README "What is NEW!") |
| Stars / forks | **1,979 / 1,267** |
| License | **Apache-2.0**, vendor-neutral |
| Releases | **v1.0.8** (2025-10-31), v1.0.7 (2025-09-21), v1.0.6 (2025-07-12) — shields reports **v1.0.8 as latest**; the `/releases` page showed only v1.0.0–v1.0.8 |
| Last commit | September 2026 (shields `last-commit`) |

**Caveat:** the newest release I could verify is **v1.0.8 (2025-10-31)**, i.e. ~10 months before this note, despite recent commits and CNCF Incubating status. **UNVERIFIED** whether a v1.1 existed but was untagged/missed by shields.

**Papers** (from README): Rong Gu, Kai Zhang, Zhihao Xu, et al., *"Fluid: Dataset Abstraction and Elastic Acceleration for Cloud-native Deep Learning Training Jobs"*, IEEE **ICDE 2022**, pp. 2183–2196 (conference version); Rong Gu, Zhihao Xu, Yang Che, et al., *"High-level Data Abstraction and Elastic Data Caching for Data-intensive AI Applications on Cloud-native Platforms"*, IEEE **TPDS** vol. 34(11), pp. 2946–2964, 2023 (journal version).

### 3.2 Core mechanism / abstractions

- **Dataset** — a unified, Kubernetes-native abstraction over datasets from multiple storage sources, with **observability** to help decide when to scale the cache. ("A Dataset is a set of data logically related that can be used by computing engines, such as Spark … and TensorFlow … we hope to start with data acceleration to support the management of datasets.")
- **Runtime** — enforces dataset isolation/sharing, provides version management, and enables data acceleration through a fixed interface set over the Dataset lifecycle. `pkg/ddc/` contains the runtime engines: **`alluxio`, `jindocache`, `jindofsx`, `juicefs`, `efc`, `thin`, `vineyard`** (+ `base`, `cache`, `factory.go`, `types`) — this is the "runtime platform agnostic" portability story.
- **CacheRuntime / CacheRuntimeClass** — the newer Kubernetes-native orchestration model for distributed cache runtimes, which the KV-cache PoC reuses (see 3.4).
- Features per README: Dataset Abstraction; **Scalable Cache Runtime** (unified access interface for third-party storage systems); **Automated Data Operations**; **Elasticity and Scheduling** (caching + elastic scaling, portability, observability, data-affinity scheduling); **Runtime Platform Agnostic** (native, edge, serverless Kubernetes, multi-cluster).

### 3.3 Fluid's LLM/inference work: model loading and cold starts

**NetEase Games end-user post — "How NetEase Games achieved 30-second LLM cold starts on Kubernetes"**, CNCF blog, **2026-05-21**, by Haifeng Liao (Senior Infrastructure Engineer) and Xiang Zhang (Head of AI Infrastructure), NetEase Games — https://www.cncf.io/blog/2026/05/21/how-netease-games-achieved-30-second-llm-cold-starts-on-kubernetes/ (also CNCF news item 2026-05-08 referencing The New Stack).

**What the numbers actually measure — flagged:** this case study is about **MODEL WEIGHT loading during cold start, not KV-cache caching.** There is no KV-cache measurement in it. The task brief's framing of "42 min → 30 s cold starts" as KV-cache acceleration is a category error; the correct reading is model-data-path acceleration.

Verified numbers and claims:
- NetEase's AI platform **Tmax** runs on Kubernetes. For **70B-class models**, pulling "hundreds of gigabytes of weights" from remote storage into inference nodes "could take **tens of minutes**", which "erased the value of autoscaling."
- "In one representative workload, model load time was reduced from **42 minutes** with cross-region direct storage access to **14 minutes** with a **traditional Alluxio-based cache** and then to **3 minutes** after we enabled **Fluid's prefetching workflow**."
- "After further tuning in production, the startup time for **two model inference services** was reduced to **about one minute** and, in some cases, even **under 30 seconds**."
- Why not run Alluxio directly (their comparison table): Fluid added (i) automated runtime deployment/lifecycle, cache elasticity via **HPA/KEDA**, data-aware scheduling; (ii) **prefetch workflows** — scheduled, event-driven, proactive warm-up — optimized for "**framework-specific access behavior, including vLLM and SGLang-style model-loading patterns**", plus scaling the cache back down after deployment; (iii) dataset abstraction separated from the runtime layer, keeping "the option to switch runtimes over time, such as **Alluxio, JindoCache, or JuiceFS**"; (iv) dataset-level logical isolation and **cross-namespace sharing** with access control aligned to native Kubernetes; (v) both **CSI- and Sidecar-based access patterns**, with webhook-based Sidecar injection minimizing application changes.
- Operational benefits: prefetch **before** startup so inference Pods do not pay the full cold-start penalty; schedule scale-up and warm-up for predictable traffic windows; **share a common base model across namespaces** instead of re-caching per team (lower cache memory overhead, less version-management overhead); the distributed cache absorbs startup bursts instead of pushing them onto backend storage.

### 3.4 Fluid's KV-cache program (roadmap + PoC) — the genuinely KV-cache-relevant part

**Fluid ROADMAP.md** (https://github.com/fluid-cloudnative/fluid/blob/master/ROADMAP.md), under the objective *"Achieve cross-region, cross-cluster, and cross-platform data mobility and accessibility"*, contains a section titled **"LLM KV Cache Orchestration"** with three verified bullets:

- **Disaggregated KV Cache:** "Externalize vLLM/SGLang KV Cache to Fluid-managed distributed storage, enabling **10x+ throughput improvement for long-context inference**." (This is a **roadmap target**, not a measured result — flag.)
- **Cross-Pod Cache Sharing:** "Live migration of KV Cache between inference instances for preemptive scheduling and spot instance tolerance."
- **Mooncake Integration:** "Official partnership for high-performance KV Cache backend with RDMA acceleration."

The same roadmap section also lists **"Efficient Data Prewarming & Migration"** (distributed prewarming to maximize bandwidth utilization; **throttling control** to avoid saturating the network; rsync optimization for cross-region sync) and **"JindoRuntime High Availability"** (master Pod crash recovery; WAL-based metadata persistence).

**Fluid issue #5875** — "[FEATURES] Add Mooncake Store based LLM KV cache orchestration PoC for CacheRuntime", authored by **CAICAIIs**, opened **2026-05-14**, still **open**, label `features` — https://github.com/fluid-cloudnative/fluid/issues/5875. Verified content:
- Proposes adding a **Mooncake Store**-based LLM KV cache orchestration PoC for Fluid's **`CacheRuntime`**. States plainly: "**Fluid's 2026 roadmap includes LLM KV Cache Orchestration**", specifically *Disaggregated KV cache for vLLM / SGLang*, *Cross-Pod KV cache sharing between inference instances*, and *Mooncake integration for a high-performance KV cache backend with **RDMA** acceleration*.
- **Background it cites:** vLLM provides **`MooncakeStoreConnector`**, which uses **`MooncakeDistributedStore`** as a shared KV cache pool for KV offloading and cross-instance prefix-cache reuse; **SGLang HiCache** organizes KV across GPU memory, host memory, and external **L3** backends such as Mooncake; **Mooncake Store** is a distributed KVCache storage engine specialized for LLM inference supporting **TCP/RDMA** transfer. It notes Fluid already orchestrates distributed cache runtimes via `CacheRuntime`/`CacheRuntimeClass`, and asks whether that abstraction "can cover LLM KV cache infrastructure, not only file / dataset cache systems."
- **Proposed scope:** map Mooncake metadata/master service to a Fluid-managed runtime component; decide whether Mooncake participants are modeled as **worker, client, or inference-side participants**; define the PoC boundary using existing `CacheRuntimeClass`/`CacheRuntime` fields where possible; ship a sample `CacheRuntimeClass` for Mooncake Store, a sample `CacheRuntime` deploying the Mooncake control plane, and **a sample vLLM workload using `MooncakeStoreConnector`** (SGLang HiCache example only after the vLLM path is accepted); and validate cross-instance reuse by starting ≥2 vLLM instances against the same Mooncake Store, sending repeated long-prefix requests, and verifying later requests reuse KV from the shared store — recording **TTFT reduction, connector logs, cache-hit logs, or other metrics**.
- **Non-goals for the first PoC:** no production-grade Mooncake operator; **RDMA hardware not required** for initial validation (TCP acceptable, RDMA documented); no changes to vLLM/SGLang/Mooncake internals; no requirement for Dataset-mounted POSIX semantics.
- **Follow-ups listed:** RDMA-aware scheduling/node selection; observability for **KV cache capacity, hit ratio, and transfer throughput**; integration with runtime dynamic configuration for online tuning of **Mooncake memory pool size, protocol, and transfer settings**; **Dataset-less runtime creation** (managing Mooncake Store as infrastructure without a bound Dataset); KServe/Knative examples.
- **References it links:** Fluid ROADMAP; vLLM MooncakeStoreConnector usage guide (`https://docs.vllm.ai/en/latest/features/mooncake_store_connector_usage/`); SGLang HiCache design (`https://docs.sglang.io/docs/advanced_features/hicache_design`); Mooncake (`https://github.com/kvcache-ai/Mooncake`); LMCache Mooncake backend docs (`https://docs.lmcache.ai/kv_cache/storage_backends/mooncake.html`).

**Fluid PR #6163** — "docs: add a Mooncake CacheRuntime sample for client-less cache systems", author **btxu-db**, createdAt **2026-08-16**, **MERGED 2026-08-29** (observed `"pullRequestState":"MERGED"`, `closedAt` 2026-08-29T10:37:50Z) — https://github.com/fluid-cloudnative/fluid/pull/6163. This is the concrete follow-through on #5875 as documentation/sample for **"client-less"** cache systems (i.e. caches without a per-node FUSE client, which is exactly how a KV store like Mooncake Store behaves).

**Bottom line on Fluid:** Fluid's *shipped* LLM value today is **data/model caching, prefetch and cold-start reduction** across heterogeneous, multi-tenant Kubernetes clusters; its *KV-cache* value is **roadmap + a merged PoC/sample**, with the intended mechanism being **Fluid orchestrating an external KV store (Mooncake Store) as a `CacheRuntime`** rather than Fluid itself storing KV blocks. I found **no Fluid release notes or measured benchmark for KV-cache orchestration** — any "10x+ throughput" figure is a roadmap aspiration (**flagged**).

---

## 4. Alluxio, Curvine, InfiniStore and other distributed caches

**Everything below was verified directly in this session** (GitHub HTML scrapes on 2026-09-15, vendor docs, design posts, and READMEs extracted from GitHub blob pages). A parallel sub-agent completed a deeper pass on this section; its full write-up is at **`raw/distcache/notes_distcache.md`** (587 lines) and it materially **corrected** two items below (Alluxio, Curvine) via grep-based audits. Its findings are credited inline where they changed a conclusion.

### 4.1 Alluxio

| Attribute | Value |
|---|---|
| Repo | https://github.com/alluxio/alluxio |
| Maintainer | Alluxio, Inc. (open core: OSS `alluxio/alluxio` + commercial **Alluxio Enterprise AI**) |
| Stars / forks | **7,242 / 2,933** |
| Latest OSS release | tags go up to **v2.9.6** (the `/tags` page lists v2.9.4 / v2.9.5 / v2.9.6, while shields reports v2.9.4 — **unresolved discrepancy**); **no new OSS tag since ~2024** |
| Commercial line | **Alluxio AI 3.9** (2026-05-19); **all AI 3.x features are commercial-only** |
| License | **Apache-2.0** |
| Last commit | September 2026 (shields); the OSS commits feed shows activity as recent as **2026-09-01** |

**⚠️ Correction to the common framing: Alluxio has no KV-cache *product* feature.** A dedicated grep-based audit (delegated pass, `raw/distcache/notes_distcache.md` §1) found **zero occurrences of "kv" (case-insensitive) in the Alluxio AI 3.9 release notes** (https://documentation.alluxio.io/ee-ai-en/release-notes/ai-3-9-16-0-0.md), and Alluxio's own "what is Alluxio" page lists only three scenarios — **training data reads/checkpoints, model distribution (weights), and feature store** (https://documentation.alluxio.io/ee-ai-en/what-is-alluxio.md). **Alluxio is overwhelmingly a data and model-weight cache.** Its KV-cache involvement is a **co-marketing relationship**, not a shipped feature.

**What the KV-cache material actually says (and why it is weak evidence).** The only Alluxio KV-cache-specific item is a **press release**, "Alluxio Partners with vLLM Production Stack to Accelerate LLM Inference" (2025-03-19; sub-headline "Faster Time-to-First-Token through Advanced KV Cache Management") — https://www.alluxio.io/news-press/alluxio-partners-with-vllm-production-stack-to-accelerate-llm-inference. Its partner is **vLLM Production Stack, built by the LMCache Lab at the University of Chicago**. The claims are **entirely qualitative**:
- **Expanded KV cache capacity**: KV cache stored "across GPU/CPU memory and a distributed caching layer (**NVMe-backed Alluxio**)", for long-context/agentic workloads.
- **Distributed KV cache sharing**: "Storing KV Cache in an additional Alluxio service layer instead of locally on the GPU machines allows **prefiller and decoder machines to share the same KV Cache** more efficiently"; it "leverages **mmap or zero-copy** technology … minimizing memory copies".
- **Cost**: NVMe's "lower unit cost per byte" vs a DRAM-only solution; commodity hardware claimed to match "other parallel file systems".

**There is no measured KV-cache number anywhere in Alluxio's material** — no TTFT delta, no prefix-cache hit rate, no KV GB/s. Furthermore, **LMCache does not list Alluxio as a storage backend** (its documented set is CPU RAM, local disk, Redis/Valkey, Mooncake, InfiniStore, S3, NIXL, GDS), so **the Alluxio↔LMCache/vLLM connector is UNVERIFIED** despite the press release. Treat the partnership as intent, and require a benchmark before citing Alluxio as a KV tier.

**Two conflations to avoid, both from Alluxio's own marketing:**
1. **"Sub-millisecond latency" in Alluxio AI 3.7 is TTFB — time to first *byte* on S3 objects — NOT TTFT (time to first *token*).** (https://www.alluxio.io/blog/alluxio-ai-3-7-now-with-sub-millisecond-latency, 2025-08-06). This is the single most likely number to be mis-cited as a KV-cache result.
2. The widely-repeated Alluxio **"10×"** KV-cache claim is a **recorded meetup talk by Junchen Jiang (Assistant Professor, University of Chicago / LMCache Lab)** hosted on Alluxio's site — "a **10x solution for long contexts inference** … over multiple **vLLM** engines with tailored **KV-cache backend**" (https://www.alluxio.io/videos/ai-ml-infra-meetup-a-faster-and-more-cost-efficient-llm-inference-stack). It is **the speaker's claim about the LMCache/vLLM-Production-Stack stack, not an Alluxio measurement**.

**Alluxio's actual quantitative results are data/weights/checkpoints — label them accordingly:**
- AI 3.7 (2025-08-06): sub-millisecond TTFB; **45× lower latency than S3 Standard** and **5× lower than S3 Express One Zone**; **11.5 GiB/s per worker** on a 100 G NIC. The low-latency caching technology was **co-developed with Salesforce engineering** and is presented in a white paper on **1,000× acceleration of Parquet queries on PB-scale data lakes** (target: "PB-scale **agentic memory**") — **data caching, not KV**.
- AI 3.8 (2026-02-12): S3 write cache **5–8× PUT latency**, **6+ GB/s per worker**, safetensors weight loading — **model weights**.
- AI 3.9 (2026-05-19): **7.6 GiB/s single-node checkpoint write**, near-linear to **~20 GiB/s across 3 workers, sub-2 ms P99**; RDMA **23.2 GB/s @200G IB, 49.5 GB/s @400G, 62.5 GB/s @3×3** — **training checkpoints, not inference**.
- **Fireworks AI**: model load **20+ min → 2–3 min per replica**, **50% egress cost reduction**, ~**2 PB served daily** — **model weights** (see §6.5). (This supersedes the earlier "1TB/s+" phrasing on Alluxio's site; both describe weight distribution.)
- **Blackout Power Trading**: inference query latency **37–83× faster (3,727 ms → 45 ms)** — this is a **feature store** (Parquet feature retrieval), **not KV cache**, despite the word "inference".

**OCI**: a joint Oracle + Alluxio tech talk promises "**sub-millisecond latency and up to 5× faster data access on OCI**", citing **MLPerf Storage 2.0 and Warp** benchmarks (Oracle Master Principal Cloud Architect Xinghong He and Alluxio VP of Technology Bin Fan). This is the closest thing found to the brief's "llm-d on OCI blog" — it is a **tiered-caching/data-access result, not a KV-cache result** (**flagged**).

**Version divergence to note:** the **newest OSS release tag is v2.9.6** (the `/tags` page lists v2.9.4, v2.9.5, v2.9.6; shields reports v2.9.4 — a **discrepancy I could not resolve**), while the **commercial line is at Alluxio AI 3.9** (2026-05-19). All AI 3.x features above are **commercial-Edition-only**, so an OSS user cannot obtain them. The OSS repository shows commits as recent as **2026-09-01** per its commits feed, but **no new OSS release tag since v2.9.6 (~2024)** — an important caveat for anyone evaluating "open-source Alluxio" for KV caching.

### 4.2 Curvine — the most interesting new entrant, and it is already in an AWS KV-cache design

| Attribute | Value |
|---|---|
| Repo | https://github.com/CurvineIO/curvine |
| Self-description | "AI-Native & Cloud-Native FS: A high-performance **file semantic layer for cloud object storage**, integrated with high-speed cache. **CNCF Sandbox Project**." |
| Stars / forks | **945 / 113** |
| Latest release | **v0.5.1-alpha** |
| License | **Apache-2.0** |
| Last commit | **today** (2026-09-15) — very active |

**Architecture** (https://curvineio.github.io/docs/Overview/instroduction/): written in **Rust**; classic **Master/Worker** architecture with **Raft** for metadata consistency and HA; **multi-tier cache (memory, SSD, HDD)**; unified cached filesystem view over S3-compatible systems, HDFS, OSS, MinIO; access via **Rust CLI, FUSE, Java/Python SDK, S3-compatible gateway, and a Kubernetes CSI driver**; asynchronous I/O and "zero-copy-oriented data paths". Modules: `orpc`, `curvine-common`, `curvine-server`, `curvine-client`, `curvine-fuse`, `curvine-libsdk`, `curvine-ufs`, `curvine-cli`, `curvine-s3-gateway`, `curvine-web`, `curvine-csi`, `curvine-tests`.

**⚠️ Note the gap — Curvine itself has no KV-cache feature (grep-verified).** Curvine's own docs claim LLM-inference value only generically, and a delegated audit found: **`README.md` has exactly 1 incidental `KV` match** — the title of the externally-authored AWS blog link — with **0 matches for `kvcache`, `vLLM`, `LMCache` or `SGLang`**; its best-practices page has **0** matches for any of those; and its six listed use cases are agent-platform storage, LLM *training* acceleration (datasets/checkpoints), LLM *model distribution*, multimodal data lake, OLAP, and multi-cloud caching — i.e. **data and weights, not KV cache**. **3FS compatibility: NOT FOUND** (`grep -ci 3fs` = 0 across README, architecture, metadata, roadmap, best-practices and Transfer Service docs) — so Curvine should **not** be described as "3FS-like" or 3FS-compatible.

**What the KV story actually is:** a **Curvine-hosted page is a verbatim mirror of an AWS-authored post** — AWS original: *"Tiered KV cache for large LLMs on Amazon SageMaker HyperPod with Curvine"*; Curvine mirror (2026-08-13): https://curvineio.github.io/blog/2026/08/13/tiered-kv-cache-sagemaker-hyperpod-curvine — content verified near-identical. So **the KV-cache design is AWS's, not Curvine's.**

**The integration point is worth recording precisely**, because it is the most reproducible "NVMe as a KV tier" recipe in this report: **L0 GPU HBM** (vLLM paged-attention prefix cache) → **L1 local CPU DRAM** (LMCache inside the pod, managed by the HyperPod Inference Operator via `enableL1Cache: true`) → **L2 shared cross-node NVMe**, where **Curvine pools node-local NVMe into one namespace and exposes it as a `ReadWriteMany` PVC over FUSE**; LMCache reaches it through its **`fs://` connector**, so the distributed pool simply looks like a local directory. Environment: **`LMCACHE_REMOTE_URL=fs://localhost:0/mnt/curvine/l2cache/`**, **`LMCACHE_REMOTE_SERDE=naive`**, **`PYTHONHASHSEED=0`**. Cache-aware routing (`prefixaware` / `kv-aware`) sits in front. Numbers (single deployment, serial requests, Qwen2-7B): **100% cross-Pod hit rate (1,925/1,925 tokens)**; **cold 774 ms → 287 ms (2.7×)** at 2,500 tokens, **1.7× @1,000**, **0.99× @500 (no benefit)**, **2.2× @3,000** (490 ms saved, largest absolute); **cross-node L2 read ≈56 ms**; N2N write ~9.6 GB/s / read ~1.8 GB/s; 4-turn conversation 4.21 s → 3.25 s (1.30×); 109 MB at 7.8 GB/s aggregate.

**Caveat on Curvine's MLPerf claim:** Curvine's comparison against Alluxio is a **vendor-authored internal comparison, not an MLPerf Closed submission**, and in that run Curvine was **slightly slower** (23.83 vs 24.14 GiB/s at 128 accumulators, −1.3%) — which sits oddly beside the vendor table below.

**Curvine's own published benchmarks** (vendor-self-reported, "Open Source Edition"):
- **Metadata QPS at concurrency 40**: `create` **19,985** (JuiceFS 16,000; OSS 2,000); `open` **60,376** (JuiceFS 50,000; OSS 3,900); `rename` **43,009** (JuiceFS 21,000; OSS 200); `delete` **39,013** (JuiceFS 41,000; OSS 1,900). Curvine cites JuiceFS's own published benchmark data for the comparison.
- **256 KiB sequential read vs open-source Alluxio, same hardware** (GiB/s, by thread count): 1 thread **2.2 vs 0.6**; 4 threads **6.8 vs 2.3**; 8 threads **8.9 vs 4.5**; 32 threads **9.5 vs 8.8**; 64 threads **9.2 vs N/A**.
- **256 KiB random read vs open-source Alluxio** (GiB/s): 1 thread **0.3 vs 0.0**; 8 threads **2.8 vs 0.2**; 16 threads **5.2 vs 0.4**; 32 threads **7.8 vs 0.3**; 128 threads **9.0 vs N/A**.
- **Resource consumption**: in big-data shuffle acceleration in production, "memory usage is reduced by **over 90%**, and CPU usage by **over 50%**" vs Alluxio — attributed to Rust.
- Curvine discloses that the Alluxio baseline numbers come from Alluxio's own website, which is fair but means the comparison is AS-published.

### 4.3 ByteDance InfiniStore — RDMA KV store, but development looks stalled

| Attribute | Value |
|---|---|
| Repo | https://github.com/bytedance/InfiniStore |
| Maintainer | ByteDance |
| Stars / forks | **438 / 44** |
| Latest release | **v0.2.33** |
| License | **Apache-2.0** |
| Last commit | **November 2025** — i.e. **~10 months stale** as of this note |

**What it is** (README, verified): "an open-source high-performance **KV store** … designed to support **LLM Inference clusters**, whether the cluster is in **prefill-decoding disaggregation** mode or not. InfiniStore provides high-performance and low-latency **KV cache transfer and KV cache reuse among inference nodes** in the cluster." Also usable standalone as a KV store for other training/inference services.

**Two supported modes:**
- **PD-disaggregated**: enables **KV cache transfer between prefill and decoding node pools**, plus KV cache reuse.
- **Non-disaggregated**: serves as "an **extra large KV cache pool** in addition to GPU cache and local CPU cache", plus **cross-node KV cache reuse**.

**Mechanism / integration point:** network is **TCP/IP or RDMA** — start with `--service-port 12345` (TCP), `--dev-name mlx5_0 --link-type Ethernet` (RoCE), or `--dev-name mlx5_0 --link-type IB` (InfiniBand). "Currently InfiniStore has been **integrated with vLLM. The integration is done via LMCache** for the flexibility purpose. Integration with SGLang and other inference engines are in progress." Installable via `pip install infinistore`; server + client model with async client examples; `/selftest` management endpoint on `--manage-port 8088`.

**Maturity verdict (dates now pinned):** the integration story is clean (LMCache → vLLM) and RDMA-native, but this is a **dormant, low-adoption** project: **438★ / 44 forks**, **last commit to `main` = 2025-11-13** (~10 months stale), **no GitHub release since v0.2.33 (2025-03-23)** and **no PyPI release since 0.2.35 (2025-04-04)**. SGLang integration is still "in progress" (i.e. stalled). The CI badge points at **`bd-iaas-us/InfiniStore`** rather than `bytedance/`, suggesting an internal-org mirror rather than the maintained upstream.

**Mechanism detail:** a DRAM pool with **variable-length keys** (model id / token hash), a **pre-registered RDMA memory pool**, bitmap + jemalloc allocation, **layer-by-layer prefill writes**, and a **separate decode download thread**. **The only measured number in the repo/docs is "network overhead increases by no more than 1%" during prefill** (https://bytedance.github.io/InfiniStore/design.html) — **no GB/s or latency benchmarks exist in the repository**.

**⚠️ Critical cross-citation warning.** The paper **"InfiniStore: Elastic Serverless Cloud Storage" (arXiv 2209.01496, Sep 2022, rev Mar 2023) is a DIFFERENT SYSTEM** — a serverless-function-memory object store ("ServerlessMemory"). **Do not attribute this repo's KV-cache claims to that paper, and do not use that paper's numbers for this project.** (Flagged by the delegated audit.)

**⚠️ Also unverified:** AIBrix's docs reference **InfiniStore 0.2.42**, a version that exists on **neither GitHub nor PyPI** — flagged rather than reconciled. And InfiniStore's **GPUDirect RDMA support and its "master/member" naming could not be verified** from the README/docs (GDR appears only in PrisKV's README).

### 4.4 PrisKV — "colocated tiered KVCache store", with the strongest published KV-cache numbers in this section

Source: AIBrix blog **"PrisKV: A Colocated Tiered KVCache Store for LLM Serving"**, 2025-11-26 — https://aibrix.github.io/posts/2025-11-26-priskv-intro/. Repo: https://github.com/aibrix/PrisKV ("High Performance KV Cache Store for LLM") — **59★ / 8 forks**, **Apache-2.0**, **no releases**, last commit **2026-01-29** (verified 2026-09-15). **Low adoption by star count**, and note the AIBrix integration PR **#1303 ("KVCache: add Pris connector") merged 2025-07-21**, i.e. the connector is older than the last PrisKV commit. **PrisKV publishes no independent benchmark methodology** — the numbers below are the project's own blog claims (see §9).

**Core mechanism (verified from the design post):**
- **Client–server, RDMA-first**: "The entire data path—from client request to server response—is designed around **RDMA primitives**", with dedicated RDMA connection management, completion-queue processing, and scatter-gather list handling for multi-buffer transfers.
- **GPU Direct RDMA (GDR)**: "KV cache data [flows] directly between **GPU memory and the network fabric without staging through CPU memory**. This zero-copy path is what makes **sub-millisecond offload/reload operations** possible."
- **Tiering**: an in-memory KV engine "built on **hash tables with slab and buddy allocators**" serves hot data; under memory pressure **LRU eviction moves cold entries to lower-cost backends**. Currently supports **local filesystem storage and Redis-compatible services** — explicitly so teams can point the cold tier at **AWS ElastiCache or GCP Memorystore**.
- **Cluster**: **consistent hashing** for automatic key distribution across nodes; AIBrix orchestration turns multiple PrisKV servers into "a coherent cluster"; **cluster specs (capacity, nodes, tiers) are described declaratively via CRDs**. HTTP interface for runtime management/monitoring (memory stats, connection counts, KV engine metrics), **ACLs for basic multi-tenancy**, liveness endpoints.
- **Integration point (3 layers, verbatim structure):** engine-side KV cache manager (**SGLang HiCache**, vLLM's KV management) → **AIBrix KVCache Offloading Framework** (bridges engines and external **L2** KV stores such as PrisKV) → **PrisKV + AIBrix orchestration** (cluster-wide shared in-memory pool). Deployed via Docker Compose; published images include `aibrix/priskv:v0.0.2` and vLLM/SGLang images bundling `aibrix_kvcache + nixl + PrisKV`.
- **Architectural framing worth quoting:** "A **KVCache-centric** prefill/decode architecture treats KVCache as a **first-class schedulable resource** rather than a by-product of a fixed prefill–decode pair. Instead of directly wiring each prefill worker to a dedicated decode worker (as in **Nixl-style P↔D designs**), this approach introduces a **logically shared KV layer** and lets a **global scheduler** independently choose prefill and decode instances while routing KV blocks through the KV pool. Although this adds one extra hop on the critical path, it enables **cluster-wide reuse of KVCache** across requests, sessions, and even different applications." It notes this "has already been adopted in large-scale MaaS systems such as **Kimi's Mooncake** architecture."

**Measured numbers (vLLM end-to-end, NVIDIA H20, Qwen3-32B, TP=4, 8K-token prompts, 200-token outputs):**

| Concurrency | Throughput | Mean TTFT | TPOT |
|---|---|---|---|
| 16 | request & token throughput **~4.8×** | **~−90%** | **~−75%** |
| 32 | **~6.35×** | **−90.7% (4,842 ms → 450 ms)** | **−83…84%** |

These are **vendor-published** and compare PrisKV-powered KV offloading against an unspecified baseline; the baseline is presumably no offloading. Still, they are among the largest KV-cache-offload deltas in this report.

### 4.5 AIBrix (the orchestration/connector layer around these stores)

| Attribute | Value |
|---|---|
| Repo | https://github.com/vllm-project/aibrix |
| Stars / forks | **5,089 / 694** |
| Latest release | **v0.7.0** |
| License | Apache-2.0 |

AIBrix matters here because it supplies the **connector/offloading framework** that both HiCache and external stores plug into:
- **v0.5.0** (2025-11-10, https://aibrix.github.io/posts/2025-11-10-v0.5.0-release/) introduced the connector **`AIBrixOffloadingConnectorV1Type3`** with two verified mechanisms: **pipelined KV cache prefetching and loading** (overlapping prefetch / load / compute "to eliminate latency penalties on TPOT") and **layer-wise KV cache offloading** ("hiding the latency of KV cache transfer by performing offloading concurrently with each layer's forward pass, enabling efficient inference **even with a low cache hit ratio**"). Reported result: vs the legacy `AIBrixOffloadingConnectorV1Type1`, for **Llama 3.1 70B with TP=8**, "**over a 20% improvement in both TPOT and overall throughput**, while still maintaining efficient TTFT."
- AIBrix is also a **HiCache L3 backend name** (`--hicache-storage-backend aibrix`).
- Follow-on work: PR **#2056** "AIBrix L2 KVCache Zero-Copy APIs and vLLM v0.14.0 integration"; PR **#1303** "KVCache: add Pris connector" (both titles verified; bodies **UNVERIFIED**).

### 4.6 FlexKV and the full SGLang L3 backend roster

Beyond the named systems above, SGLang's `python/sglang/srt/mem_cache/storage/` directory (verified listing) contains the following pluggable KV-storage backends: **`aibrix_kvcache`, `eic`, `file`, `flexkv`, `hf3fs`, `lmcache`, `mmap`, `mooncake_store`, `nixl`, `npu_memcache`, `shm`, `simm`, `umbp`** — a useful map of who is building KV-cache storage in the SGLang ecosystem, including Ascend/NPU-oriented (`npu_memcache`), shared-memory (`shm`), and simulation (`simm`) targets.

**FlexKV** (`taco-project/FlexKV`, https://github.com/taco-project/FlexKV) — **351★ / 73 forks**, created **2025-07-02**, **no GitHub releases** (a v1.0.0 API version is referenced in its README), license shown as **Apache-2.0 in the README** but **not identifiable by GitHub** at the repo level (**flagged**). It is more significant than its star count suggests: the delegated audit found FlexKV is **built into vLLM v0.17.2+**, exposed in SGLang via **`--enable-flexkv`**, and integrated with **NVIDIA Dynamo, TensorRT-LLM, and Mooncake Store as a remote tier** — making it a **first-class vLLM/SGLang KV-cache backend**, not a peripheral project. **No performance benchmarks were found** for it (**do not attribute numbers**). Its last-commit date could not be retrieved (the atom feed returned empty repeatedly) — **UNVERIFIED**.

### 4.7 Mooncake (brief — covered more deeply elsewhere in this project)

Mooncake (https://github.com/kvcache-ai/Mooncake) — **6,577★ / 1,221 forks**, **Apache-2.0**, latest release **v0.3.13.post1 (2026-09-01)** — is the reference "KVCache-centric disaggregated" store that keeps recurring in this report: it is **SGLang HiCache's most-cited L3 backend**, the store behind **vLLM's `MooncakeStoreConnector`**, one of **Fluid's three roadmap KV-cache bullets** ("official partnership … with RDMA acceleration"), the backend behind **Ant Group's 84% TTFT-reduction quote**, and it carries a **3FS feature marked experimental** (PR #2062). **Verified Mooncake numbers:** its Transfer Engine reached **87 GB/s at 4×200G RoCE and 190 GB/s at 8×400G** for a 40 GB transfer (**2.4× / 4.6× vs TCP**), and it reports **Kimi K2 at 224k tok/s prefill and 288k tok/s decode**. It is commercially backed by **KVCache.AI** (the company behind Mooncake; blog at https://kvcache.ai/blog/), with named production users **Moonshot Kimi** and **Approaching.AI** (claimed **>1 trillion tokens/day** as of 2026-09-15). **⚠️ Mooncake's widely-quoted ">90% KV cache hit rate" was found only in a secondary Chinese re-post and never in a primary Mooncake/Moonshot/AWS source — treat as UNVERIFIED.**

---

## 5. Redis / Valkey as a KV-cache backend

A parallel sub-agent ran a deeper pass; its full write-up is at `raw/redisgds/notes_redis_gds.md`. Findings below were verified directly in this session.

### 5.1 Redis and Valkey: project signals

| Project | Repo | Stars / forks (2026-09-15) | Latest release | License | Last commit |
|---|---|---|---|---|---|
| **Valkey** | https://github.com/valkey-io/valkey | **27,204 / 1,311** | **v9.1.2** | **BSD-3-Clause** | today |
| **Redis** | https://github.com/redis/redis | **76,370 / 24,808** | **v8.10.1** | shields: **"not identifiable by github"** (**UNVERIFIED** at SPDX level) | today |

Valkey is the Linux Foundation fork created after Redis's 2024 license change, hence the BSD-3-Clause license — relevant because it is the license-clean option for embedding in a serving stack. **Valkey 9.1 GA'd on 2026-05-19** (Linux Foundation press release) with a claimed **up to −10% per-key memory** improvement; **Valkey Search 1.2** is marketed with "microsecond latency" and "millions of requests per second" — **vendor claims with no methodology (flagged)**. LMCache ships a **real Valkey connector via `valkey-glide ≥ 2.0`**, though LMCache v0.3.7's doc page for it still said "coming soon", so the exact shipping version is **UNVERIFIED**. Minor discrepancy to flag: redis.io's own navigation lists "Redis open source framework **Redis 8.8**" while shields reports the latest release as **v8.10.1**; I could not reconcile which is current (**UNVERIFIED**).

### 5.2 Redis + LMCache — the flagship KV-cache integration (and its missing numbers)

Source: **"Get faster LLM inference and cheaper responses with LMCache and Redis"**, Redis blog, **2025-07-28**, by Rini Vasan and Yihua Cheng — https://redis.io/blog/get-faster-llm-inference-and-cheaper-responses-with-lmcache-and-redis/

**⚠️ Headline finding: this flagship Redis KV-cache post publishes NO measured benchmark numbers.** It explains architecture and configuration but contains **no TTFT, throughput, latency, hit-rate, or cost measurement** from Redis or LMCache. The only quantitative claim on the page is a marketing call-to-action — "**Cut costs by up to 90% and lower latency with semantic caching powered by Redis**" — and that is about **Redis LangCache / semantic caching (response caching), not KV cache**. Anyone citing "Redis + LMCache is X% faster" is not citing this post.

**Verified mechanism (Redis is LMCache's default remote store):**
1. LMCache receives a chunk of input tokens, computes a **SHA-256 hash** of the chunk, and constructs a Redis key in the format **`format@model_name@world_size@worker_id@chunk_hash`**.
2. It writes **two entries** per chunk: a **`@metadata`** entry stored as a **Redis hash** with key-value fields (model name, format, temperature, …), and a **`@kv_bytes`** entry stored as a **binary blob serialized with pickle by default**.
3. On later requests it rehashes the chunk and queries Redis for both entries; on a match it "**injects the cached KV values directly into the model**", skipping "the LLM's forward pass over that chunk, including token embedding and attention computation."
4. **Granularity:** chunk-level, not prefix-only — "It caches token-level KV pairs for **all previously seen content—not just prefixes**—and reuses them even if the same text appears later in the prompt or **in a different order**." The cache "works **across any serving engine instance**, making reuse possible at scale."
5. **Defaults it documents:** **128-token chunks with optional overlap**; backend priority "**in-memory first, then Redis**"; storage "**Pickle format, no Redis TTL**". Configurable: chunk size/overlap, cache priority, serialization format, expiration, eviction policy.
6. **Scope limit it states explicitly:** LMCache "**does not support KV reuse or token caching for hosted APIs like OpenAI or Anthropic**" — it targets open-weight self-hosted models (Mistral, Qwen, Llama) via **vLLM**.
7. Redis arguments for being the backend: low-latency retrieval at scale, **hybrid filtering on metadata** (e.g. temperature or model), **TTL management** for cache freshness, and production scalability "across thousands of requests or replicas"; works with open-source Redis or Redis Cloud via a connection string.

**Redis's own tiering guidance elsewhere:** AWS's KV-cache-tiering guidance (see §6.2) recommends **Amazon ElastiCache Serverless (Valkey)** as the remote **L2** (~5–15 ms same-AZ), which is the clearest "Redis-family-as-KV-cache-tier" production recommendation found.

### 5.2b ⭐ The Redis blog that *does* have numbers — "Throughput-optimizing Redis for L2 KV Cache Reuse"

***This is the most useful Redis KV-cache source, and it is *not* the blog most briefs name (which has none — see §5.2).*** Source: **"Throughput-optimizing Redis for L2 KV Cache Reuse"**, published **2026-03-30** (updated 2026-04-02), by **Samuel Shen, Paulo Sousa, Srijith Rajamohan** — a **Redis + Tensormesh** co-development — https://redis.io/blog/throughput-optimizing-redis-for-l2-kv-cache-reuse/

**Tiering model and the SLO it defines:**
- LMCache hierarchy: **L0 = VRAM, L1 = host RAM, L2 = external storage** (disk, RDMA, databases, object stores).
- Production KV chunk sizes: **500 KB to 40 MB**. For **Llama 3.1 8B**, a single **10,000-token request produces 1.2 GB** of KV cache — "even a **256-token chunk is 31 MB**."
- **Stated SLO: 2 GB/s** — the throughput an LMCache L2 backend needs to "outrun" prefill on modern datacenter GPUs.
- Priority order for KV operations is **Lookup > Retrieve > Store** (Store is asynchronous); the real targets are **tail latency** (every chunk must arrive before inference can continue) and **GB/s**, not ops/s.

**Verified throughput ladder (client/transport optimization):**

| Stage | Change | Measured throughput |
|---|---|---|
| Baseline `redis-py` async SDK | — | **0.278 GB/s** |
| `memtier_benchmark` (C), local **Redis 8.2**, 4 MB payloads | reference ceiling | **SET 372.97 ops/s = 1.53 GB/s**; **GET 1,427.53 ops/s = 5.85 GB/s** |
| Custom RESP parser, zero-copy receive + scatter/gather send | removes user-space copies | **2 GB/s** retrieve (**7×**) |
| Fixed-size chunks (drop per-chunk metadata; read exactly `chunk_size` bytes) | halves Redis op count, removes delimiter scanning | **4–5 GB/s** |
| C++ client core + GIL release + batched tiling + `eventfd` completions | true multi-core concurrency | **9–10 GB/s standalone** on a **128-vCPU bare-metal node with ConnectX-7 NICs** — **30× over the original `redis-py` client** |
| Full LMCache integration, end-to-end local | GPU↔DRAM transfer costs ~2–3 GB/s | **7 GB/s** |
| Self-hosted Redis on a GCP VM, same AZ + VPC, tuned | — | **6 GB/s** standalone |
| **Redis Cloud** | still tuning | **~2.6 GB/s** |

**Operational findings worth quoting:** "**Cross-AZ drops bandwidth 5–10×**" — "**Same AZ + VPC is non-negotiable**"; on GCP VMs bandwidth converges around **64 parallel streams at ~40 Gbps**, and matching client worker count to that achieves >90% of raw `iperf3` throughput; default GCP TCP buffer sizes (**~212 KB**) are too small for multi-MB transfers; throughput vs chunk size is **non-monotonic and machine-specific**.

**⭐ End-to-end inference result.** Workload: long-document QA, **40 documents × 40,000 input tokens, 100 output tokens, 66.7% cache hit rate** (every third request has no KV reuse). Two GCP VMs in the same VPC: an **8× A100 GPU node** and a **c2d-standard-112 Redis node**.

| Configuration | Mean TTFT | Total round time |
|---|---|---|
| vLLM baseline (**no prefix caching**) | **32.883 s** | **393.485 s** |
| **LMCache + Redis** | **21.517 s** | **235.072 s** |
| **Improvement** | **34.6%** | **40.3%** |

Implementation references given: LMCache PR **#2541** (client optimizations) and PR **#2642** (new native southbound protocol); benchmarking playground **https://github.com/LMCache/lmcache_redis**. This is the highest-quality *end-to-end, non-marketing* KV-cache-over-Redis measurement in this report, because it states hardware, workload, hit rate, and baseline together.

### 5.2c LMCache's native RESP (Redis/Valkey) backend

Source: LMCache docs `kv_cache/storage_backends/resp.html`. LMCache now ships a **native C++ RESP connector** for Redis/Valkey rather than only an in-process Python path. Verified server-side figures: **GET ~5.9 GB/s at 4 MB chunks** (but **5.2 GB/s at 1 MB** and only **1.4 GB/s at 8 MB** — chunk size dominates), **SET 4.36 GB/s**, **EXISTS 143,528 ops/s**; and **Redis 8.2 with `--io-threads 4` reaches ≈6 GB/s versus ~1.5 GB/s on Redis 6.0 defaults**. This is the mechanism behind the C++ client results in §5.2b, and it shows the Redis *server* configuration matters as much as the client. (Throughput is non-monotonic in chunk size — see the caveat above.) These are the numbers that make Redis a *credible* L2 tier rather than merely a convenient one.

### 5.3 Valkey/Redis in llm-d — **an index backend, not a KV-block store** (important correction)

The brief's premise that Valkey serves as an "llm-d KV indexer backend" is **confirmed but often misunderstood**. The authoritative doc is llm-d's **KV-Cache Indexer** page (https://llm-d.ai/docs/dev/architecture/advanced/kv-management/kv-indexer). Verified facts:
- The **KV-Cache Indexer lives inside the llm-d Router/EPP** and "enables precise prefix-cache-aware routing". It "**subscribes to KVEvents emitted from model servers** to maintain a near-realtime view of the KV cache state"; the `precise-prefix-cache-producer` feeds the `prefix-cache-scorer` in the EPP **filter → score → pick** flow. Model servers (**vLLM and SGLang today**) publish events "over **ZMQ**".
- **The Index is a `block key → pods` mapping** — i.e. it records *which pod holds which KV block*, so the router can send a request where its prefix is already cached. **It does not store KV tensors.** The Redis/Valkey row is therefore about **metadata**, not KV bytes.
- **Backends (verbatim options):**

| Backend | Storage | When to use | Tradeoff |
|---|---|---|---|
| **In-Memory (default)** | Two-level LRU: outer cache keyed by block hash, inner cache of pods per block | "Default choice for most deployments" | Lowest latency; fixed entry count (default **100M keys × 10 pod entries**) makes sizing predictable |
| **Cost-Aware Memory** | **Ristretto** cache with admission control and cost-based eviction | Workloads where per-entry size varies a lot (multimodal, variable-length LoRA metadata) | Budget specified in **bytes** (e.g. 2 GiB) rather than entry count; probabilistic admission can reject entries under pressure |
| **Redis / Valkey** | **External server (TCP; Valkey is Redis-wire-compatible, BSD-licensed)** | "Need for persistent or very-long lived index (**uncommon**)" | "Adds a **network hop per lookup** and ties EPP availability to the external store; shared state gives strong consistency across replicas but is **rarely necessary**" |

- llm-d's own recommendation: "**In-memory is typically the best option**, offering low-latency, simple operations, and high availability via multi-replica deployment." For Redis/Valkey, "the key space is proportional to **unique blocks across the fleet, not to request volume**."
- **Sizing guidance**: "plan for roughly keys × pod_entries with overhead for the two-level LRU."
- Related work: llm-d-kv-cache PR **#139** "feat: Add **Valkey and RDMA support for KV-cache indexing**" (author `rishi-jat`) — **merged 2025-10-19**; example configs at `examples/valkey_configuration.md`; implementation files `pkg/kvcache/kvblock/index.go` and `pkg/kvcache/kvblock/redis.go`. `redis.go` supports **both Redis and Valkey** (treated as API-compatible) with a `BackendType` selector plus an **experimental `EnableRDMA`** option; the index is stored as **Redis HASHes for the `requestKey → pods` mapping** and **`engine:`-prefixed sorted sets for `engineKey → requestKey`**, pruned by **two Lua scripts**. Repo signals: **llm-d-kv-cache 177★ / 156 forks, v0.9.0**, Apache-2.0; **llm-d 4,542★ / 768 forks, v0.9.0**, Apache-2.0 (**CNCF Sandbox**).
- **⚠️ Two corrections to the usual framing of this component:**
  1. **The indexer's only storage backends are in-memory (default), cost-aware in-memory, and Redis/Valkey.** A "filesystem indexer backend" does **not** exist. The FS/object-store choice belongs to a *separate* path — the vLLM `TieringOffloadingSpec` / `llmd-fs-connector` (final release `llmd-fs-connector==0.23`, since upstreamed) — which moves KV *blocks*, not the *index*.
  2. **The indexer has moved** out of `llm-d-kv-cache` into **llm-d-router** (PR #1886), so `llm-d-kv-cache` is now primarily the library rather than the home of the router-side indexer.
- Other indexer details verified: two event-distribution shapes (**centralized** — all model-server pods `zmq.PUB` to one EPP-bound endpoint on `tcp://*:5557`; **pod discovery** for active-active multi-EPP); three event types including `BlockStored` (with an `extra_keys` field for multimodal hashes) and `AllBlocksCleared` (**"can occur in RL weights rollouts"**); the **Scorer** finds the longest *unbroken* cached prefix per candidate pod (causal attention means a cached block is only reusable if the whole prefix chain is present); the older gRPC-over-UDS tokenizer sidecar is **deprecated** in favour of calling vLLM's `/v1/completions/render` and `/v1/chat/completions/render` endpoints.

**Takeaway:** Redis/Valkey is a legitimate KV-cache component in two distinct roles — **KV-block storage tier** (LMCache's default remote store; AWS's recommended ElastiCache L2; PrisKV's cold tier) and **KV-block *location index*** (llm-d routing). The literature often blurs these, and llm-d itself rates the index role "rarely necessary" versus in-memory.

### 5.4 Redis LangCache — a *different* product (semantic response caching)

Redis's product navigation currently lists **Redis LangCache** ("Save on tokens for common questions"), **Redis Iris** ("Real-time context for agents"), **Redis Context Retriever**, and **Redis Agent Memory**. LangCache is **semantic/response caching for LLM answers**, not KV-block reuse: it embeds the incoming prompt, runs a **vector search** over stored prompt/response entries, and **returns the previously generated response** if a similarity threshold is cleared; on a miss the app calls the LLM and stores the result. It is built on the Redis vector database, with documented embedding options including OpenAI models and Redis's own `redis/langcache-embed-v1` (research paper: https://huggingface.co/papers/2504.02268). API: `POST /v1/caches/{cacheId}/entries/search` and `POST /v1/caches/{cacheId}/entries`, via REST + Python/JavaScript SDKs.

**Verified LangCache signals and numbers:**
- Launch announcement "LangCache public preview": https://redis.io/blog/langcache-public-preview.md — **published 2025-09-04, updated 2026-08-13**; available to **all Redis Cloud users**, part of "September's Fall Release."
- **"Cache-hit response speedup up to 15× faster than re-querying large models"** (launch blog) — **vendor claim, no methodology**.
- Product page now claims **up to 90% savings**; the launch material said **70%**, and the 70%→90% shift is **not explained** (**flagged**).
- The only concrete measurement found: a controlled demo on a **paraphrased question** — direct inference **2.232 s with 514 input + 250 output tokens**, versus LangCache **0.37 s with zero LLM input/output tokens** (~6× faster in that single run). Source: a 2026-09-10 third-party write-up.
- **Pricing is UNVERIFIED**: the launch blog says only "consumption-based pricing", and https://redis.io/calculator/langcache/ is JS-rendered with no extractable numbers.
- **Status: still "public preview"** as of 2026-09-10.
- **Redis itself states the distinction cleanly** and it is worth quoting in any report that mixes these up: *"A prefix-cache hit is a cheaper generation call, not an avoided one."* — i.e. KV reuse still pays for output tokens, whereas semantic response caching avoids the call entirely.

**Treat LangCache and KV cache as separate features.** Almost all "Redis makes LLM inference 90% cheaper" headlines are LangCache (response caching) claims, not KV-cache-reuse claims.

---

## 6. Cloud vendors

Full detail (with ~54 explicit `UNVERIFIED` flags) is in `raw/cloud/notes_cloud_vendors.md`. **Access caveats that bound these findings:** every `*.google.com` host was **TCP-unreachable** from the research sandbox, so **all Google Cloud claims below are second-hand or mirror-sourced**; `blogs.oracle.com` returned 403 and `infoq.com` 405. Numbers below are **vendor-published benchmarks** unless stated otherwise.

### 6.1 The headline: AWS published a tiered KV-cache design using an open-source cache (Curvine)

**"Tiered KV cache for large LLMs on Amazon SageMaker HyperPod with Curvine"** (AWS ML Blog) — https://aws.amazon.com/blogs/machine-learning/tiered-kv-cache-for-large-llms-on-amazon-sagemaker-hyperpod-with-curvine/

Three-tier design: **vLLM GPU (L0) → LMCache CPU (L1) → Curvine shared NVMe (L2)**.

| Claim | Value (AWS-published) |
|---|---|
| Cross-Pod cache hit rate | **100% (1,925 / 1,925 tokens)** |
| TTFT at 2,500-token prompts | **774 ms → 287 ms (2.7×)**; 1.7× at 1k, ~0.99× at 500, 2.2× at 3k |
| Same-node L2 write bandwidth | **9.6 GB/s** |
| Cross-node L2 read bandwidth | **1.8 GB/s** |
| Cross-node load time | **~56 ms** for 1,925 tokens |
| Multi-turn conversation | **4.21 s → 3.25 s (1.30×)** |
| Hardware | 2× `ml.g5.4xlarge` (A10G), Qwen2-7B fp16, TP1, 2 vLLM replicas, 256-token chunks |

**This is the single most concrete storage-layer KV-cache measurement in the cloud-vendor set**, and it makes **Curvine** (see §4) a production-grade AWS-blessed L2 for KV blocks — a notable finding given how new Curvine is (`v0.5.1-alpha`).

### 6.2 AWS

- **`aws-samples/sample-eks-cache-aware-llm-routing`** — repo signals: **1 star, 0 forks, no releases, MIT-0**. Despite that, the README contains a concrete benchmark: **150 concurrent users / 25 QPS Poisson / 8× vLLM Mistral-7B on EC2 G5 / 3-minute multi-turn**; **p90 TTFT 4,443 ms (round-robin) → 1,370 ms (cache-aware), i.e. +69%**, measured in the 150–180 s bucket. Mechanism: vLLM **KVEvents over ZeroMQ** feeding the **llm-d EPP** global prefix-block index, with scorers `prefix-cache(3) + queue(2) + kv-utilization(2) + LRU(2)`; EKS v1.31, vLLM v0.22+, Envoy Gateway v1.2.0, GAIE InferencePool v1.5.0. **Flag: a 1-star sample repo is not adoption evidence, and the benchmark is self-reported.**
- **AWS-authored KV-cache tiering guidance (APEX Skills)** — https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-genai/references/kv-cache-and-cost/ — documents L0 GPU VRAM (~0), **L1 CPU RAM ~1–5 ms**, **L2 = Amazon ElastiCache Serverless (Valkey) ~5–15 ms same-AZ**, and a workshop-validated result on `g6e.2xlarge` (L40S) with Ministral-3-8B at 90% overlap: **TTFT 0.43 s → 0.12 s (~3.6×)**. Decision rule given: enable caching when **≥50% of request tokens are shared prefixes**. **Key nuance: AWS's own recommended remote L2 is Valkey/ElastiCache, not S3.**
- **S3 as a KV-cache store — mostly unverified.** The LMCache S3 example README **explicitly recommends S3 Express One Zone** with same-AZ colocation ("Normal S3 bucket is functional but gives worse performance"), but gives **no numbers**, and this is LMCache's advice rather than AWS's. The only AWS-published S3 Express One Zone figures found (95% caching cost cut, single-digit-ms in-AZ, 100k+ req/s per bucket) are about **AI search result caching — not KV cache**. **No AWS-authored, measured KV-cache-on-S3-Express-One-Zone result exists → UNVERIFIED.**
- **SageMaker HyperPod DPD** (July 2026): prefill/decode split with **KV cache transferred between pools over EFA**, EKS orchestrator + EFA instances — **no published numbers → UNVERIFIED**.
- **Amazon Bedrock prompt caching**: GA **April 2025**. AWS's own GA wording: **"up to 90% cost reduction and up to 85% latency reduction."** Pricing footnote: **"Cache read input tokens will be 75% less than on-demand input token price."** Minimum tokens per checkpoint: **512** (Claude Opus 5 / Fable 5), **1,024** (Sonnet 5, GPT-5.6), **4,096** (Haiku 4.5); **max 4 checkpoints**; TTL **5 min default, 1 h opt-in** (`"ttl":"1h"`; 30 min for GPT-5.6). Anthropic cache-write multipliers are client-side rendered → **UNVERIFIED**.
- **Bedrock intelligent prompt routing** routes between models *within one family* by predicted quality vs a fallback — **model routing, NOT KV-cache routing** (no headline % in the docs → UNVERIFIED).

### 6.3 Microsoft Azure

- **NIXL `AZURE_BLOB` plugin is real and co-owned by Microsoft**: `src/plugins/azure_blob/README.md` carries **both** `Copyright (c) 2026 NVIDIA` and `Copyright (c) 2026 Microsoft`, Apache-2.0; uses the Azure SDK for C++ (`azure-storage-blobs 12.15.0`, `azure-identity`); required params `account_url` + `container_name` (plus optional `connection_string`). This is the mechanism by which Azure Blob becomes a KV tier in Dynamo/LMCache.
- **LMCache now ships a native Azure Blob backend** (docs.lmcache.ai → `kv_cache/storage_backends/azure.html`): "offload KV cache to Azure Blob Storage via an **async-native connector (parity with the S3 backend, no NIXL dependency)**", URI `azure://<container>`, four auth paths ending in **DefaultAzureCredential**, one flat blob per chunk, full chunks only. Implements LMCache issue **#3575**.
- **NVIDIA Dynamo KVBM tiers**: **G1 GPU → G2 CPU → G3 disk → G4 object storage**, configured by `DYN_KVBM_CPU_CACHE_GB`, `DYN_KVBM_DISK_CACHE_GB` (+`O_DIRECT`), and `DYN_KVBM_OBJECT_ENABLED/BUCKET/ENDPOINT/REGION` (S3-compatible, `{worker_id}` bucket templating). Sizing rule of thumb given: `CPU_CACHE_GB >= 100` and `DISK_CACHE_GB >= CPU_CACHE_GB`. **No G4 performance numbers → UNVERIFIED.**
- **⚠️ Major conflation to avoid:** Dynamo's "Storage for Model Caching on AKS" page recommends **Azure Managed Lustre** / Local CSI / Azure Disk / **Azure Blob** — but by its own framing it is about **MODEL WEIGHTS and compilation caches, not KV cache.**
- **Azure OpenAI prompt caching**: cache reads discounted on Standard and **up to 100% discount on Provisioned**; **minimum 1,024 tokens, and the first 1,024 tokens must be identical**; GPT-5.6+ uses explicit breakpoints only; `prompt_cache_options.ttl` accepts **only `30m`**; **~15 requests/min per prefix+key** before misses; **max 4 cache writes per request**; reads consider the latest **50 breakpoints**; in-memory retention clears after **5–10 min idle / 1 h max** and is **never shared across subscriptions**; **extended retention up to 24 h** via — verbatim — "**offloading the key/value tensors to GPU-local storage when memory is full**". So Azure's long-TTL KV cache is **local offload, not object storage**.
- **Microsoft three-layer routing on AKS** (RouteLLM + Agentgateway + GAIE EPP + KAITO vLLM): **~95% of GPT-4 MT-Bench quality while sending only ~26% of calls to GPT-4 → up to 85% cost savings** — **this is semantic *model* routing, not KV cache**; the article itself warns that switching models "cools both caches."
- **Not found / unverified**: no Microsoft blog measuring **AMLFS or Blob as a KV-cache tier**; no Azure "KV cache as a service"; Azure Container Storage v2 GA relevance to KV cache (**UNVERIFIED**, InfoQ 405). **KAITO**: 1,012★ / 184 forks, **v0.12.0** — no KV-cache feature verified.

### 6.4 Google Cloud (⚠️ second-hand — google.com unreachable from the sandbox)

- **GKE Inference Gateway prefix-cache-aware routing vs round-robin**, Llama 3.1 8B on A100: **92.8% shorter TTFT, 62.6% lower inter-token latency, +15.7% throughput** — quoted by a third-party article (https://dev.to/pvgomes/your-ai-gateway-is-a-cache-scheduler-now-cl) from the Google Cloud blog, which was **unreachable**. Echoed elsewhere as "up to 92% faster TTFT". **Treat as second-hand.**
- **Vertex AI context caching** (via a mirror of Google's own generative-ai samples): **cached tokens cost ~90% less**; **minimum 2,048 tokens** (Gemini 2.5); **TTL default 60 min, max 1 h**; explicit `client.caches.create(...)` API with `cached_content` reuse. Exact per-token and cache-storage prices **UNVERIFIED**.
- **llm-d tiered prefix cache → shared storage** (verified first-hand from the llm-d repo): the llm-d **FS connector** plugs into **vLLM's native `OffloadingConnector`** over any POSIX FS (naming **GCP Lustre**, IBM Storage Scale, CephFS, AWS Lustre), uses GPU DMA, and has **no built-in eviction** (a PVC Evictor reference implementation lives in `llm-d/llm-d-kv-cache`); default config Qwen3-32B, TP4, H100, 100 GB CPU offload. Lustre-via-LMCache `inference-perf` deltas: **mean TTFT −38.4%, P90 TTFT −45.1%, +47.8% throughput** (best config) and **mean TTFT −21%, +23% throughput** (another) — **the guide itself warns these come from a previous release** (llm-d/llm-d#680). llm-d's **precise** routing is driven by **vLLM KVEvents** (vLLM issue #16669).
- **GCS as a KV-cache store: UNVERIFIED** — no Google doc, guide, or number found. "Predicted latency scheduling" as a named Google product feature: **UNVERIFIED**.

### 6.5 Other vendors

- **Baseten + NVIDIA Dynamo KV-aware routing** — best-available numbers: **TTFT −50%, TPOT −34% at an 89% cache hit rate across 4 replicas** (~50k-token inputs); **P95 −48%, P99 −49%** on shadowed production OpenRouter traffic; **+61% RPS, +62% output TPS**; "often see **2× faster TTFT** in production." Mechanism: Dynamo LLM-Aware Router, radix-tree request hashing + overlap scoring, over vLLM/SGLang/TensorRT-LLM.
- **LMCache + CoreWeave AI Object Storage** (Cohere North): **TTFT −22…−32%**, **decoding throughput +41%** vs full prefill, **1.2× vs S3 Express cold**, **3× vs S3 Express hot**. ⚠️ CoreWeave's **Tensorizer** (5× faster model loading) is **MODEL WEIGHTS, not KV cache.**
- **Red Hat / llm-d**: **3× output throughput, 2× TTFT reduction** vs round-robin (vendor-reported). Red Hat AI Inference is now on **CoreWeave CKS and Azure AKS**; **llm-d is a CNCF Sandbox project**. Repo signals: llm-d **4,542★ / 768 forks, v0.9.0**, Apache-2.0; `llm-d-kv-cache` **177★ / 156 forks, v0.9.0**, Apache-2.0.
- **Cloudflare Workers AI**: genuine **prefix caching**, on by default for select models, requires the **`x-session-affinity`** header. Verified cached-input prices: DeepSeek V4 Flash **$0.440 → $0.014 /M (~96.8% off)**, GLM 5.2/5.3 **$1.40 → $0.260 (~81%)**, Kimi K2.5 **$0.600 → $0.100**. **No Cloudflare KV or R2 use as an LLM KV-cache store was found** (the brief's "Cloudflare R2 as KV store" is **UNVERIFIED**).
- **Fireworks AI** serverless cached input (input / cached / output per 1M tokens): Kimi K3 **$3.00 / $0.30**, DeepSeek V4.1 Flash **$0.22 / $0.007 (~96.8% off)**, GLM 5.2 **$1.40 / $0.14 (90%)**, GLM 5.3 **$1.40 / $0.26**, Qwen 3.8 Max **$2.00 / $0.25**. ⚠️ Fireworks' **training** catalog also has a "Cached Prefill" column — that is a **fine-tuning** cost, not inference KV cache.
- **Together AI**: cached-input discounts exist but are **automatic, prefix-based, fleet-shared, best-effort, with no configurable retention**; dedicated endpoints get caching by default. Exact percentages **UNVERIFIED**.
- **Oracle OCI, Modal, RunPod**: **no verified KV-cache product or number → UNVERIFIED.** (Oracle's blogs returned 403; the brief's "llm-d on OCI blog" could not be read.) Modal's GPU memory snapshots are cold-start state, **not** KV cache.
- **"KV cache as a service"**: **no hyperscaler SKU exists.** What hyperscalers sell is **cached-input-token prompt caching** (Bedrock, Azure OpenAI, Vertex AI, Workers AI, Fireworks). Adjacent vendor marketing (Cloudian; Alluxio "10×") is **unverified**.

### 6.6 NIXL plugins as of September 2026 (authoritative list)

Repo: `ai-dynamo/nixl` — **1,256★ / 441 forks**, latest release **v1.4.1 published 2026-09-01**, Apache-2.0 per file headers (shields cannot classify a top-level license).

**Plugin inventory (from `src/plugins/` and `src/plugins/meson.build`):** `ucx`, `ucx_mo`, `posix`, **`obj`** (S3), **`azure_blob`**, `libfabric`, **`cuda_gds`** (GPUDirect Storage / cuFile), `gds_mt`, `gpunetio`, **`hf3fs`** (DeepSeek 3FS via `hf3fs_usrbio.so`), `mooncake`, `gusli`, `uccl`, `infinia`, plus telemetry/tracing.

**The `obj` plugin's GPU-direct story (the key mechanism):** standard object-store engines (standard AWS SDK S3 client, S3 CRT client, and the *base* `S3AccelObjEngineImpl`) support **only `OBJ_SEG` and `DRAM_SEG` — i.e. CPU memory**. GPU-direct object I/O requires a **vendor engine to override `getSupportedMems()` to add `VRAM_SEG`** — which is exactly what Dell's accelerated engine does (§7.3b). **This is why GPU-direct S3 KV caching is not vendor-neutral today**: the capability exists in the plugin API but must be explicitly exposed per vendor. `cuobjclient-13.1` (in CUDA Toolkit 13.1+) provides the client libraries, and the `accelerated` flag plus `type` selector choose the engine, auto-disabling when the library is absent.

**Caveat carried forward:** the AWS and GKE headline TTFT numbers are **vendor-published benchmarks** (the AWS EKS one from a **1-star** sample repo; the GKE one **second-hand** because google.com was blocked). Only the Curvine AWS blog and the Baseten post publish enough methodology to sanity-check. The **single most common vendor error is conflating KV cache with (a) model-weight caching and (b) response/semantic caching** — flagged cases: Dynamo AKS "model caching" (weights), CoreWeave Tensorizer (weights), Tavily/S3 Express One Zone (search results), Microsoft RouteLLM (model routing), Fireworks "Cached Prefill" (fine-tuning), Cloudflare AI Gateway caching (responses).

---

## 7. GPU Direct Storage / NVMe / S3 KV-cache tiering

> Researched by a delegated sub-agent in parallel; see `raw/redisgds/notes_redis_gds.md` §(2) for the full detail.

### 7.1 Verified findings from this session

**NIXL is the de-facto plugin substrate for KV-cache storage.** LMCache's NIXL backend doc (docs.lmcache.ai) enumerates the storage-capable NIXL plugins and their constraints:

| NIXL plugin | What it targets | Verified constraint (LMCache config) |
|---|---|---|
| `GDS`, `GDS_MT` | **GPUDirect Storage** (NVMe, multi-threaded variant) | `nixl_buffer_device` = `cpu` **or** `cuda`; dynamic mode supported |
| `POSIX` | local/shared POSIX files | `nixl_buffer_device` must be **`cpu`**; dynamic mode supported; optional liburing build |
| `HF3FS` | **DeepSeek 3FS** | `nixl_buffer_device` must be **`cpu`**; dynamic mode supported |
| `OBJ` | **S3-compatible object storage** (S3 API) | `cpu` or `cuda`; supports `nixl_endpoint_list` (**only** this backend) and dynamic mode; multi-TP-worker example documented |
| `AZURE_BLOB` | **Azure Blob Storage** API | must be **`cpu`**; dynamic mode supported |
| `DOCA_MEMOS` | NVIDIA DOCA Memos memory/object service | must be **`cpu`**; dynamic mode supported; 128-bit lowercase-hex object names |
| `UCX`, `LIBFABRIC` | transport backends for P2P/PD transfer (not storage) | selected in vLLM via `kv_connector_extra_config.backends`; UCX is the NIXL default |

Sources: LMCache NIXL backend docs; vLLM `docs/features/nixl_connector_usage.md` and `nixl_connector_compatibility.md` ("Multiple NIXL backends (UCX, GDS, LIBFABRIC, etc.)").

**Where GDS stands in the serving frameworks (as of the sources I verified):**
- SGLang HiCache (Sept 2025 blog) explicitly says: "the often significantly higher and less predictable latency of storage compared to host–GPU transfers, and we remain open to techniques such as **GPU Direct Storage when the performance tradeoffs are favorable**" — i.e. **GDS is not the default HiCache path**; the default high-performance CPU↔GPU path is SGLang's own **GPU-assisted I/O kernels (up to 3× vs `cudaMemcpyAsync`)**.
- SGLang exposes `--hicache-io-backend {direct,kernel}` to choose the CPU↔GPU I/O backend, and `--hicache-mem-layout page_first` for IO-optimal host layout (with zero-copy, up to 2× throughput in typical deployments).
- vLLM's `NixlConnector` is centered on **P2P / PD-disaggregated transfer** and lists `UCX` (default) plus e.g. `LIBFABRIC` and `GDS` as selectable transport backends; storage-tier offloading in vLLM is done by the Mooncake/`KVConnector` family instead.

**S3 as a KV-cache store — important distinction.** Verified in SGLang's own docs: `docs/docs/advanced_features/object_storage.mdx` ("Loading Models from Object Storage") covers **model weights**, streaming them from `s3://`, `gs://`, `az://` or S3-compatible URIs via the **`runai_streamer`** load format, with a two-phase approach (metadata download once, then lazy weight streaming), `distributed` / `concurrency` (default 4) / `memory_limit` options, `.safetensors`-only support. **This is model-weight streaming, not KV-cache storage.** SGLang's *KV-cache* L3 backends are `file`, `mooncake`, `hf3fs`, `nixl`, `aibrix`, `dynamic` — an object-store KV tier is reached through **NIXL's `OBJ` plugin** (via LMCache), not via the model-loading path. Conflating these two is a common error in vendor material.

### 7.2 LMCache's GDS backend — the concrete GDS-based KV-cache loader

Source: LMCache docs, `kv_cache/storage_backends/gds.html` (verified). The GDS backend uses "**GPU-Direct Storage optimizations … for zero-copy I/O from GPU memory to storage systems**" and **supports both NVIDIA `cuFile` and AMD `hipFile`**. Remote file systems let multiple LMCache instances share data. Configuration:
- `LMCACHE_GDS_PATH` — "Path to file system, local, remote or GDS-enabled mount"; `LMCACHE_GDS_BUFFER_SIZE` — GDS buffer size in MiB (example: 8192).
- **Multi-NVMe sharding**: `LMCACHE_GDS_PATH_SHARDING` with `by_gpu` (the only supported, and default) mode. Docs give the bandwidth rationale verbatim: "**a single PCIe Gen 4 x4 NVMe tops out at ~7 GB/s. With four drives the aggregate bandwidth can reach ~28 GB/s**, matching what multi-GPU [nodes need]." On a 4-GPU node each `cuda:N` writes to `/mnt/nvmeN/cache`, wrapping around if there are more GPUs than paths.
- The docs also warn in an example comment that "**CPU can get in the way of GPUDirect operations**" — foreshadowing the Tutti critique below.

The equivalent NIXL-level plugins are **`GDS`** and **`GDS_MT`** (§7.1), with `nixl_buffer_device` allowed to be `cpu` **or** `cuda` — the only storage plugins in LMCache's list with a `cuda` option besides `OBJ`.

### 7.3 NVMe/SSD KV-cache benchmarks — where the real numbers are (two Sept/May 2026 papers)

**⚠️ These two papers are the strongest evidence in this report about how KV cache behaves on NVMe, and they partially contradict the optimistic GDS framing.**

**(a) arXiv 2605.03375 — "Tutti: Making SSD-Backed KV Cache Practical for Long-Context LLM Serving"** (submitted **5 May 2026**; Shi Qiu, Yifan Hu, Xintao Wang, Wenhao Zhu, Jianqin Yan, Hao Chen, Kaiqiang Xu, Kai Chen, Yiming Zhang):

- **Direct critique of GDS for KV cache:** "restoring KV cache from SSDs suffers from poor I/O performance and incurs significant GPU stalls. This is primarily because the **fragmented GPU memory layout results in a massive number of tiny random I/Os**, rendering the low-parallelism CPU a severe bottleneck **even with GPU Direct Storage (GDS), which still relies on CPU intervention to initiate each I/O and thus remains CPU-centric.**"
- **Design:** a **GPU-centric KV cache object store** where the CPU only asynchronously loads I/O kernels once per layer — a GPU-native object abstraction for bulk KV transfers, a re-architected GPU storage stack introducing **GPU `io_uring`** for asynchronous GPU direct object I/O, and **slack-aware I/O scheduling** to avoid GPU resource contention. Integrated into **vLLM**.
- **Results vs "the state-of-the-art GDS-enabled, SSD-backed LMCache":** **TTFT reduced by 78.3% under strict SLO constraints**, **2× achievable request rate**, **serving cost reduced by 27%** — while achieving "nearly the same inference performance as **DRAM-backed** LMCache, while providing almost infinite capacity."

**(b) arXiv 2609.11744 — "Building py-kvcache: A Performance Characterization of External KV Caching for vLLM with NVMe SSDs"** (submitted **10 Sep 2026** — five days before this note; Joseph Kanichai, Tiziano De Matteis, Animesh Trivedi):

- **The central caution, stated plainly:** "Prefix caching can reduce TTFT of long-context LLM requests by reusing previously computed KV states, **but for short prefixes or fast GPUs, recomputation can be faster than loading from an external cache.**" Characterization across GPU, CPU and NVMe tiers with synthetic workloads, long-context benchmarks and production traces found that "cache performance depends on **transfer granularity, intermediate memory use, and *when transfers enter the request schedule*, not only on device bandwidth**."
- **Design:** `py-kvcache`, "a vLLM **KV Offload connector** with **asynchronous direct I/O, bounded shared staging, and scheduler-aware preloading**, which starts disk reads while requests are still waiting, overlapping with compute."
- **Results:** at **80k tokens, py-kvcache loading from disk is 2.0× faster than LMCache**, with **preloading contributing 1.34×**. With GPU + CPU + disk caching enabled it is **1.23× faster than LMCache** and **within ~4% of the native vLLM KV Offload implementation**. LongBench and SCBench show benefits extend to irregular prefix chains and multi-turn workloads.
- **The negative result that matters most:** on **Bailian trace replays**, external caching improves TTFT **on a weaker GPU**, but "**on an H100 the average request falls below the break-even point and GPU memory alone retains enough prefixes.**" The authors' conclusion: "**External KV caching should therefore be treated as a setup-specific admission decision.**"

**Implication for anyone designing a KV-cache storage tier:** the benefit of an NVMe/remote KV tier is **not monotonic in device bandwidth**. It depends on prefix length, GPU speed, transfer granularity, staging-buffer design, and crucially *whether the load is initiated early enough to overlap compute* (scheduler-aware preloading). On fast GPUs with short prefixes, HBM alone may suffice and the external tier can be a net loss. This directly qualifies the aggressively-positive vendor claims in §§4 and 6.

### 7.3b ⭐ Object-store (S3) KV cache with measured numbers — the strongest numbers in this report

**(a) Dell ObjectScale + NVIDIA NIXL `OBJ` plugin — GPU-direct KV offload to S3.**
Source: Dell Technologies blog, **published 2026-08-19**, author Jason Goldschmidt, media "Dell + NVIDIA" — https://www.dell.com/en-us/blog/kv-cache-offload-to-object-storage-gpu-direct-and-upstream/

- **What was contributed:** an **accelerated engine for the NIXL `OBJ` plugin** — RDMA-based asynchronous PUT/GET, **VRAM segment support**, and runtime engine selection — with **every enhancement merged upstream** (no private fork). Dell's framing of the prior state: LMCache's route to object storage ran over **S3-HTTP with the CPU and a host memory copy in the data path**, so "the fast lane belonged to file"; the new path lands data **directly in GPU memory over RDMA with no host bounce buffer**, using **`cuObject`**. Stated upstream placement: **LMCache v0.4.5** and **NVIDIA NIXL v1.1.0**; `cuObject` client libraries already ship in **CUDA Toolkit v13.1+**.
- **Benchmark setup (quoted):** "PowerEdge XE9680 server with NVIDIA H100 GPUs and ConnectX-7 NICs, serving **Qwen3-Coder-30B-A3B-Instruct at tensor parallelism 4**. TTFT was measured as the **median of five hot passes on a single request**, across context sizes from **4K to 235K tokens**."

| Metric | Value |
|---|---|
| **TTFT at 235K-token context, S3 endpoint** | **837 ms** |
| Baseline: recompute prefill at 235K tokens | **11,223 ms** |
| **TTFT speedup vs recompute** | **13.4×** |
| Speedup vs the same offload over **S3-HTTP** | **1.3–1.5×** (margin widens with scale) |
| CPU utilization vs the HTTP path | **−~90%** |
| KV cache size for one **235K-token** request | **43 GB** |
| **4K context: baseline vs offloaded** | **91 ms** vs **113–129 ms** — **offload LOSES** |
| **Crossover** | "**below roughly 8K–16K tokens the overhead outweighs the benefit**" |

- **Dell's own explicit caveat (quoted):** "Below roughly 8K–16K tokens, offload overhead outweighs the benefit and the baseline wins … **This is a long-context capability.**" This is an unusually honest vendor disclosure and should accompany any use of the 13.4× figure. It independently **corroborates the py-kvcache break-even finding in §7.3**.
- **NIXL `OBJ` plugin internals verified from source:** dual-client architecture (standard AWS SDK S3 client for small objects, **S3 CRT client** for large ones) selected by a **`crtMinLimit`** threshold (recommended ≥ 10 MB); `throughput_target_gbps` (default 10, integer Gbps) sizes the CRT scheduler's parallel connections; AWS enforces a **5 MiB minimum part size** (lower values silently clamped with a warning); `accelerated` (`true`/`false`, default false) plus `type` (e.g. `dell`) select the accelerated engine, which **requires `cuobjclient-13.1`** or auto-disables back to standard S3/CRT. Crucially, the **memory-type table** shows `DefaultObjEngineImpl`, `S3CrtObjEngineImpl` and the base `S3AccelObjEngineImpl` support only **`OBJ_SEG` and `DRAM_SEG` (CPU memory)**; **vendor engines must explicitly override `getSupportedMems()` to add `VRAM_SEG`** — that override is the exact mechanism by which Dell's engine achieves GPU-direct object I/O. Reads support offsets; **writes do not** (whole object at once).

**(b) ObjectCache — the cleanest academic answer to "how much does S3 cost you in TTFT".**
**arXiv 2605.22850**, "ObjectCache: Layerwise Object-Storage Retrieval for KV Cache Reuse", **submitted 16 May 2026** (Yu Zhu, Aditya Dhakal, Yunming Xiao, Dejan Milojicic, Gustavo Alonso) — https://arxiv.org/abs/2605.22850

- **Problem framing (verbatim):** "the accumulated KV cache is often larger than what GPU memory and local DRAM can hold. To preserve latency, current systems keep the KV cache in **remote DRAM pools, increasing serving-cluster size and cost**. In this paper, we explore a different approach: storing the KV cache in **S3-compatible object storage** so that capacity is no longer the constraint."
- **Mechanism:** co-designs the **storage protocol and transfer schedule** so the storage server delivers KV data **in the order the GPU consumes it**, overlapping transfer with compute across concurrent requests ("layerwise"). Prototype: a **100 Gbps RoCE cluster** using **NIXL**, **Ceph RGW** and **DAOS**.
- **Measured results:** at **64K contexts** only **5.6% added latency over local DRAM**; at **4K contexts** (less compute to mask transfer) **56–75 ms added** over the optimal local layerwise baseline; under shared bandwidth caps the scheduler **reduces added TTFT by 1.2–1.8×** versus equal bandwidth sharing.

**(c) WEKA Augmented Memory Grid + TensorRT-LLM over GDS** — headline prefill latency at **128K tokens: 22,998.583 ms → 301.481 ms** (marketed as "**75× faster TTFT**", 2025-06-20). **Flag:** the 75× figure states **no repetition count, concurrency, batch size or harness**; treat as a vendor claim (https://www.weka.io/article/weka-sets-a-new-bar-with-75x-faster-time-to-first-token-ttft).

**(d) Mooncake + SGLang HiCache SSD offload** — the clearest *hit-rate-cliff* demonstration in this report. Setup: **8×A100 + 5× Samsung NVMe in RAID0 (≈27 GB/s), Qwen3-8B**. Results: **TTFT −57% vs GPU-only** and **−34% vs Mooncake without SSD**; input-token throughput **2.4×**. Without SSD the hit rate collapses **83% → 36%** by round 7 with TTFT rising **6 s → 16 s**, whereas with SSD the hit rate stays **>84%** and TTFT lands at **9.4 s**. Source: Mooncake benchmark doc at commit `c251eefa` plus PR #1835 (**undated doc — date UNVERIFIED**).

Source: LMCache docs `kv_cache/storage_backends/s3.html` documents three verified S3 configurations — basic S3, **S3 Express One Zone** (`s3_enable_s3express: True`, URL form `s3://{BUCKET}.s3express-{AZ_ID}.{REGION}.amazonaws.com`), and **CoreWeave S3-compatible** (`remote_url: "s3://test-127.cwlota.com"`, `s3_region: "US-WEST-04A"`, `s3_max_io_concurrency: 320`). Notable parameters: `save_unfull_chunk` **must be False for S3**; `s3_max_inflight_reqs` creates that many **`/dev/shm`** buffers (tmpfs, so transfers land in RAM rather than a block device); `save_chunk_meta` should be **False** for performance. LMCache publishes **no throughput** for the S3 path.

### 7.3c Consolidated cross-system tiering comparison (the numbers I would cite first)

Every row below states its tier boundary, metric, date and source. Vendor claims with no methodology are flagged as such in §§7.3–7.3b.

| System | Tier boundary crossed | Metric | Value | Date |
|---|---|---|---|---|
| LMCache + Redis (vLLM) | GPU → remote Redis (network) | Mean TTFT / round time | **32.883 s → 21.517 s (−34.6%)** / **393.485 s → 235.072 s (−40.3%)** | 2026-03-30 |
| LMCache RESP native client | client → Redis/Valkey server | GET / SET / EXISTS | **~5.9 GB/s @4 MB** / **4.36 GB/s** / **143,528 ops/s** | 2026 (undated page) |
| **Tutti** (vLLM) | GPU → **NVMe via GPU `io_uring`** | TTFT / req rate / cost | **−78.3% / 2× / −27%** vs GDS-enabled SSD-backed LMCache | **2026-05-05** |
| py-kvcache (vLLM) | GPU → **NVMe** | disk-load speed | **2.0× faster than LMCache @80K** (1.34× from preloading); 1.23× with GPU+CPU+disk | **2026-09-10** |
| **Dell ObjectScale + NIXL OBJ (RDMA)** | GPU → **S3-compatible object store, GPU-direct** | TTFT @235K | **11,223 ms → 837 ms (13.4×)**; −~90% CPU; **loses at 4K** | **2026-08-19** |
| **ObjectCache** | GPU → **S3-compatible object store** | Added latency vs local DRAM | **+5.6% @64K**; **+56–75 ms @4K**; 1.2–1.8× better than equal sharing | **2026-05-16** |
| Mooncake + SGLang HiCache | DRAM pool → **local NVMe** | TTFT / token throughput | **−57% vs GPU-only**, −34% vs no-SSD; **2.4×** | undated |
| WEKA AMG + TRT-LLM (GDS) | GPU → NVMe-backed distributed store | Prefill @128K | **22,998.583 ms → 301.481 ms** ("75×", no methodology) | 2025-06-20 |
| SGLang HiCache (own) | GPU → DRAM → L3 | Throughput / TTFT | **up to 6×** / **up to 80% reduction** | 2025-09-10 |
| SGLang HiCache + **3FS** (Novita AI) | GPU → DRAM → 3FS | TTFT / throughput / hit rate | **−56%** / **2×** / **40%→80%** | 2025-09-10 |
| SGLang HiCache + Mooncake (Ant Group) | GPU → DRAM → Mooncake | TTFT on hit | **−84%** vs full recompute (R1-671B, PD-disagg) | 2025-09-10 |
| AWS SageMaker HyperPod + Curvine + LMCache | GPU → CPU → **shared NVMe** | TTFT / hit rate | **774 ms → 287 ms (2.7×)** / **100% cross-Pod** | 2026 (AWS blog) |
| Mooncake (Kimi production) | GPU → cluster CPU/DRAM/SSD | Requests handled | **+75%** in production; up to **525%** in simulation | 2024-06-24 (rev 2025-09-03) |
| Redis Cloud (L2 tier) | client → managed Redis | Retrieval throughput | **~2.6 GB/s** (vs 6 GB/s self-hosted same-AZ GCP) | 2026-03-30 |

**Three patterns visible in this table:**
1. **Every credible measurement has a stated crossover or regression point.** Dell loses at 4K tokens; py-kvcache loses on an H100 with short prefixes; Tutti exists because GDS stalls GPUs. A KV-cache tier claim without a break-even statement is not credible.
2. **The tier boundary matters more than the device.** Crossing to remote DRAM/Redis costs ~35% TTFT at 40K tokens; crossing to NVMe with good scheduling costs ~5.6% more than *local DRAM* at 64K; crossing to S3 with a GPU-direct RDMA engine costs 837 ms absolute at 235K. The protocol and scheduling dominate raw bandwidth.
3. **Locality is non-negotiable.** Redis measured a **5–10× bandwidth collapse crossing AZs**; Dell reports **−90% CPU** purely from removing the host bounce buffer. Placement decisions beat tuning.

### 7.4 Related GDS/KV work located but not fully verified here

- **WEKA "Open Sourcing GDS Integration"** (Augmented Memory Grid) — a vendor GDS contribution whose *article* is JS-rendered and yielded no details; the 75× TTFT figure I do cite comes from a **different** WEKA post (§7.3b(c)) and lacks methodology. WEKA's GDS-contribution specifics remain **UNVERIFIED** (https://www.weka.io/article/open-sourcing-gds-integration-from-augmented-memory-grid-see-results-for-yourself).
- **Nutanix + LMCache, "Context Overload, of the GPU Kind" (Part 3)** — a storage-vendor KV-cache case study; **not verified**.
- **"Prompt Caching on Flash: Achieving Memory-Class Latency for LLM Inference"** — IEEE/CSDL 2026 (https://www.computer.org/csdl/journal/ca/2026/02/11601066/2hZ80Kwgbxm) — located, **not fetched/verified**. The title alone suggests it is directly relevant (flash/SSD prompt caching), so this is a **priority follow-up**.
- **Dell follow-on post "Accelerating AI Inference with Open Source and Dell ObjectScale"** — referenced by the Dell blog for implementation detail (LMCache/cuFile configuration, NIXL buffer sizing, full methodology) but the URL **could not be located**; contents **UNVERIFIED**. This is also a **priority follow-up**, since it would document the methodology behind the 13.4× figure.
- **NVIDIA Dynamo KVBM** exposes disk/object tiers with `O_DIRECT` (§6.3); its G4 object tier has **no published performance numbers → UNVERIFIED**. It does have one distinctive **non-performance** mechanism worth noting: an **SSD-lifespan filtering policy that offloads CPU→disk only when a block's access frequency ≥ 2**, i.e. it protects flash endurance by refusing to write cold-once blocks.
- **KVBench / NIXLBench** publish **metric definitions but no result tables**; the harness (which includes a dedicated GDS profiling tutorial) is the best route to **first-party GDS-vs-POSIX numbers**, which nobody has published yet. This is a notable **gap in the public evidence base for GDS KV caching**.
- **No Redis Enterprise KV-cache-tier productisation, SKU or benchmark was found**, and **no SGLang↔Redis/Valkey or TensorRT-LLM↔Redis KV integration exists** — SGLang's L3 backends remain `file`, `mooncake`, `hf3fs`, `nixl`, `aibrix`. So the "Redis as a universal KV-cache backend for all engines" framing is not supported: the shipping integrations are **vLLM (via LMCache)** and **llm-d (as an index)**.
- Working doc paths useful for follow-up: vLLM's KV-offloading page is at `/en/v0.25.0/features/kv_offloading_usage/` (the `/latest/` path **404s**); LMCache docs live under `/kv_cache/storage_backends/`.
- **Valkey 9.1** claims **up to −10% per-key memory** (Linux Foundation press release, 2026-05-19); **Valkey Search 1.2** claims "microsecond latency" and "millions of requests per second" with **no methodology** → vendor claims.

---

## 8. Synthesis: how KV blocks move through the storage stack

| Tier | Mechanism | Representative systems (verified in this note) |
|---|---|---|
| L1 — HBM | paged KV, radix/prefix cache, block size 64 in DeepSeek's MLA kernel | FlashMLA paged KV cache (block size 64); vLLM PagedAttention; SGLang RadixAttention |
| L2 — host DRAM | pinned host pools, page-first layout, GPU-assisted I/O kernels | SGLang HiCache L2 (`--hicache-ratio`, `--hicache-size`); **DeepSeek-V4.1-Flash SWA KV pool = 10% of host DRAM, TTL minutes** |
| L3 — local NVMe | file/page stores, GDS or POSIX I/O | SGLang HiCache `file` backend (`/tmp/hicache`); NIXL `GDS`/`GDS_MT`/`POSIX`; JuiceFS client-side NVMe cache |
| L3 — distributed FS / cache | RDMA fabrics + SSD clusters; page-index metadata services | **3FS** (`hf3fs` HiCache backend, USRBIO zero-copy); JuiceFS (model/data tier); Fluid `CacheRuntime` (orchestration) |
| L3 — distributed KV store | RDMA one-sided / object-store semantics | Mooncake Store (`MooncakeStoreConnector`, HiCache L3); InfiniStore (see §4); NIXL `OBJ`, `AZURE_BLOB` |
| Model weights (distinct!) | bulk sequential read at cold start | JuiceFS (0.5 ms vs 20 ms), Fluid + NetEase (42 min → 3 min → <30 s), SGLang `runai_streamer` from S3/GCS/Azure Blob |

**Three recurring design lessons visible across the sources:**

1. **Metadata placement is the hard part, not data movement.** SGLang HiRadixTree deliberately **does not synchronize L3 metadata**, querying the backend at access time; 3FS's HF3FS backend runs a **page-index allocator with `reserve_and_allocate_page_indices`/`confirm_write`/`get_page_indices`**; Fluid's KV PoC treats "Mooncake metadata / master service" as *the* component to map into `CacheRuntime`; and DeepSeek-V4.1-Flash ships a **Hierarchical Sparse Indexer** (bounded candidate pools) precisely to bound index work.
2. **Cross-instance / cross-Pod reuse is the value driver, and it is where the vendors converge.** Novita's 40%→80% hit-rate jump with 3FS, vLLM's hash-based prefix dedup across instances via Mooncake Store, Fluid's "Cross-Pod Cache Sharing", and LMCache's shared-pool model are all the same idea: a **cluster-wide namespace** for KV pages.
3. **The model architectures are attacking the cache faster than the storage layer can.** V4-Pro at 10% of V3.2's KV, V4.1-Flash at ~1/4 of V4-Flash with FP4 KV, and third-party LSA at 13.5% of full-context footprint all shrink the bytes that need tiering — while V4.1-Flash simultaneously *simplifies* the storage problem by moving SWA KV out of SSD into a host-DRAM pool and giving global KV a 72-hour lifetime. **KV caching for 2026-era DeepSeek models is less about NVMe capacity than about a small, hot, index-addressed global cache plus cheap replay of a 128-token window.**

---

## 9. Explicitly NOT verified / open gaps

1. **3FS per-node vs aggregate "40 GiB/s" KVCache throughput** — README says all clients; `open-infra-index` says per client node. Unresolved.
2. **3FS merge/commit activity after 2026-05-07** — last public commit observed 2026-05-07. Whether development continues privately is unknown.
3. ~~vLLM 3FS KVConnector merge date~~ — **RESOLVED**: PR #37636 is merged; page dates span 2–9 April 2026, so **early April 2026**.
4. **Details of SGLang PR #9109 ("3fs zerocopy") and PR #8673** beyond their titles, and of SGLang issue #34969 ("[Bug] HF3FS HiCache hits ZeroDivisionError with **DeepSeek-V4 logical KV anchor**", which surfaced in search but was not opened).
5. **DeepSeek-V4.1-Flash primary technical report** — figures (890 bytes/token, FP4 KV, 10% DRAM SWA pool, 72-hour global KV lifetime, CSA2 modes) come from a **secondary** article (MarkTechPost, 2026-09-10) plus a corroborating blog. The linked primary "Technical Report" was not fetched.
6. **Official Hugging Face paths for the V4/V4.1-Flash weights** — not verified.
7. **Tair KVCache repo signals** — now fully verified: **255★ / 58 forks**, **Apache-2.0**, **no GitHub releases** (only `__binary-dependency-*` tags), created **2025-12-29**, active as of 2026-09-15. The "+150% 4K random-read IOPS" figure still comes only from an Alibaba Cloud blog abstract that is JS-rendered and readable in summary form. A confusingly-named personal fork (`li-xiao-qing/tair-kvcache`, 0 stars) exists and is *not* the official repo. **Tair's "HF3FS" storage backend is almost certainly DeepSeek 3FS, but Alibaba never expands the abbreviation — UNVERIFIED.**
8. **Fluid v1.1 / any release after v1.0.8** — not found.
9. **Any JuiceFS KV-cache backend/connector** — not found in official docs/blogs.
10. **A Fluid KV-cache benchmark** — none found; the "10x+ throughput" figure is a roadmap target.
11. **Exact star/fork snapshots** are point-in-time scrapes of GitHub's HTML counter on 2026-09-15 and may lag/round relative to the API.
12. **Alluxio KV-cache measurements** — none found. Alluxio's KV-cache pages describe mechanism (GPU/CPU/NVMe tiers, mmap/zero-copy, prefiller↔decoder sharing) but publish no benchmark. The "**10×**" KV-cache figure is a **University of Chicago presenter's claim about a multi-vLLM stack**, not an Alluxio measurement. Alluxio AI 3.7's 98%/80% latency reductions are about **data-lake/Parquet/agentic-memory caching, not KV cache**.
13. **Alluxio version mapping** — OSS `alluxio/alluxio` latest is **v2.9.4**, while the commercial line is "Alluxio AI 3.7"; the relationship between the two version schemes is **UNVERIFIED**. Alluxio AI 3.7's sub-millisecond claim is stated in a Chinese-language announcement I read only in summary form.
14. **PrisKV repo signals** — now verified: **59★ / 8 forks**, Apache-2.0, **no releases**, last commit **2026-01-29**. PrisKV's benchmark tables compare against an **unspecified baseline** (likely "no offloading") — **not confirmed**, so treat the −90.7% TTFT / 6.35× figures as **project claims without published methodology**.
15. **InfiniStore performance numbers** — **none exist in the repo or docs**; the only measured figure is "network overhead increases by no more than 1%" during prefill. **⚠️ The paper "InfiniStore: Elastic Serverless Cloud Storage" (arXiv 2209.01496) is a DIFFERENT SYSTEM** (a 2022 serverless-function-memory object store) — do **not** cross-cite it for this project.
16. **Weka "Augmented Memory Grid" GDS integration numbers**, the **Nutanix + LMCache** case study, and the paper **"Prompt Caching on Flash"** (IEEE/CSDL 2026) were located but **not fetched/verified**.
17. **Redis LangCache specifics** — GA date, pricing, and benchmark claims **not verified** here.
18. **Redis license** — shields reports "not identifiable by github"; the SPDX license of `redis/redis` and the current version (redis.io nav says **8.8**, shields says **v8.10.1**) are **UNVERIFIED**.
19. **llm-d "Cost-Aware Memory" (Ristretto) indexer backend** — the row exists in the backends table; I did not verify its configuration surface or any benchmark.
20. **Projects that publish NO performance benchmarks at all** — verified absence, so **do not attribute numbers to them**: **AIBrix KVCache**, **PrisKV**, **Tair KVCache**, and **FlexKV**. For AIBrix specifically, v0.5.0 claims ">20% improvement in TPOT and throughput" for its v1 connector versus its own legacy connector, but no harness/table is published. **Mooncake's ">90% KV cache hit rate"** appears only in a secondary Chinese re-post, never in a primary source. **NIXL's license is not identifiable by GitHub** (composite/custom licensing likely) — my "Apache-2.0 per file headers" (§6.6) and this must both be treated as provisional pending legal review.
21. **Alluxio**: the **newest OSS release tag (v2.9.6) vs shields' v2.9.4** discrepancy is unresolved, and **no OSS release tag has appeared since v2.9.6 (~2024)** even though the OSS repo has recent commits. **Alluxio↔LMCache/SGLang/TensorRT-LLM connectors are UNVERIFIED** — the press release exists but no connector appears in LMCache's backend list. All Alluxio AI 3.x features are **commercial-only**.
22. **No DeepSeek 3FS forks or "3FS-like" clones were verified**, and **Curvine is not 3FS-compatible** (grep-verified: 0 matches for `3fs` in its docs).
23. **Tooling caveat.** The helper `raw/sc/ghfile.py` used in this session **initially had a bug**: on a failed fetch it could silently return stale content from a fixed `/tmp` path (the delegated audit hit this and read a NIXL README that was actually a different repo's `pyproject.toml`). **I have since fixed it** (unique temp path per invocation + explicit failure detection returning a non-zero exit). I re-verified the load-bearing extractions it produced against independently-fetched sources — the Fluid ROADMAP KV text matches issue #5875's own description of the roadmap, and the SGLang L3 backend list matches the LMsys HiCache blog — **so no conclusion in this note rests on a corrupted read**, but anyone reusing that script should use the fixed version.
24. **GitHub reachability** — `github.com` and `raw.githubusercontent.com` both became unreachable partway through this session (curl exit 000), while `arxiv.org`, `llm-d.ai`, `aibrix.github.io`, `alluxio.io`, `redis.io`, `curvineio.github.io` and `juicefs.com` stayed reachable. A few late verifications (noted inline) were therefore impossible; the delegated sub-agent reports in `raw/cloud/`, `raw/distcache/` and `raw/redisgds/` may cover some of them in more depth.

---

## Sources

### DeepSeek 3FS and DeepSeek Open Source Week
- https://github.com/deepseek-ai/3FS
- https://github.com/deepseek-ai/3FS/blob/main/README.md
- https://github.com/deepseek-ai/3FS/blob/main/docs/design_notes.md
- https://github.com/deepseek-ai/3FS/commits/main
- https://github.com/deepseek-ai/3FS/tree/main/src
- https://github.com/deepseek-ai/3FS/tree/main/src/kv
- https://github.com/deepseek-ai/3FS/tree/main/src/lib/api
- https://github.com/deepseek-ai/3FS/tree/main/docs
- https://github.com/deepseek-ai/3FS/tags
- https://github.com/deepseek-ai/3FS/branches/all
- https://github.com/deepseek-ai/open-infra-index
- https://github.com/orgs/deepseek-ai/repositories?type=all&sort=updated
- https://github.com/deepseek-ai/FlashMLA
- https://github.com/deepseek-ai/DeepEP
- https://github.com/deepseek-ai/DeepGEMM
- https://github.com/deepseek-ai/DualPipe
- https://github.com/deepseek-ai/EPLB
- https://github.com/deepseek-ai/smallpond
- https://github.com/deepseek-ai/DeepSeek-V3.2-Exp
- https://huggingface.co/deepseek-ai/DeepSeek-V3.2-Exp/tree/main/inference
- https://docs.vllm.ai/projects/recipes/en/latest/DeepSeek/DeepSeek-V3_2-Exp.html

### DeepSeek-V4 / V4.1-Flash and KV-cache research
- https://arxiv.org/abs/2606.19348 — DeepSeek-V4: Towards Highly Efficient Million-Token Context Intelligence
- https://arxiv.org/abs/2606.09079 — FlashMemory-DeepSeek-V4 (Lookahead Sparse Attention)
- https://arxiv.org/abs/2606.01065 — Leyline: KV Cache Directives for Agentic Inference
- https://www.marktechpost.com/2026/09/10/deepseek-ai-released-deepseek-v4-1-flash-with-1m-context-fp4-kv-cache-and-cross-layer-attention-reuse/
- https://www.contextstudios.ai/blog/deepseek-v4-1-flash-890-bytes-kv-cache-per-token
- https://huggingface.co/RedHatAI/DeepSeek-V4-Flash

### SGLang HiCache / 3FS integration
- https://lmsys.org/blog/2025-09-10-sglang-hicache/
- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hicache_design.mdx
- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hicache.mdx
- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hicache_best_practices.mdx
- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hicache_storage_runtime_attach_detach.mdx
- https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/object_storage.mdx
- https://github.com/sgl-project/sglang/tree/main/python/sglang/srt/mem_cache/storage
- https://github.com/sgl-project/sglang/tree/main/python/sglang/srt/mem_cache/storage/hf3fs
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/hf3fs/storage_hf3fs.py
- https://github.com/sgl-project/sglang/pull/8673
- https://github.com/sgl-project/sglang/pull/9109
- https://github.com/sgl-project/sglang/pull/22601
- https://github.com/sgl-project/sglang/issues/34969
- https://docs.sglang.io/docs/advanced_features/hicache_design

### vLLM, LMCache, NIXL
- https://github.com/vllm-project/vllm
- https://github.com/vllm-project/vllm/pull/37636
- https://github.com/vllm-project/vllm/blob/main/docs/features/mooncake_store_connector_usage.md
- https://github.com/vllm-project/vllm/blob/main/docs/features/nixl_connector_usage.md
- https://github.com/vllm-project/vllm/blob/main/docs/features/nixl_connector_compatibility.md
- https://github.com/vllm-project/vllm/tree/main/docs/features
- https://docs.vllm.ai/en/latest/features/mooncake_store_connector_usage/
- https://github.com/LMCache/LMCache
- https://docs.lmcache.ai/kv_cache/storage_backends/nixl.html
- https://docs.lmcache.ai/v0.3.7/kv_cache/storage_backends/nixl.html
- https://docs.lmcache.ai/v0.4.7/mp/l2_storage.html
- https://docs.lmcache.ai/kv_cache/storage_backends/mooncake.html
- https://github.com/ai-dynamo/nixl
- https://github.com/kvcache-ai/Mooncake
- https://github.com/kvcache-ai/Mooncake/pull/2062

### Alibaba / Tair on 3FS
- https://github.com/alibaba/tair-kvcache — Tair KVCache (255★, created 2025-12-29)
- https://www.aliyun.com/product/kvcache
- https://help.aliyun.com/zh/redis/product-overview/tair-kvcache/
- https://developer.aliyun.com/article/1695651
- https://developer.aliyun.com/article/1693182
- https://github.com/li-xiao-qing/tair-kvcache (personal fork — NOT the official repo)

### JuiceFS
- https://github.com/juicedata/juicefs
- https://juicefs.com/en/blog/solutions/idle-resources-elastic-high-throughput-storage-cache-pool
- https://www.juicefs.io/zh-cn/blog/solutions/building-high-throughput-cache-pool-resilience-with-juicefs
- https://juicefs.com/en/blog/solutions/boost-foundation-model-inference-multi-cloud
- https://www.juicefs.io/zh-cn/blog/solutions/data-storage-multi-cloud-model-training-juicefs
- https://juicefs.com/en/blog/engineering/juicefs-ai-workload-performance-optimization
- https://juicefs.com/docs/community/ai_ml/
- https://www.juicefs.io/docs/zh/community/articles/

### Fluid (CNCF)
- https://github.com/fluid-cloudnative/fluid
- https://github.com/fluid-cloudnative/fluid/blob/master/ROADMAP.md
- https://github.com/fluid-cloudnative/fluid/issues/5875
- https://github.com/fluid-cloudnative/fluid/pull/6163
- https://github.com/fluid-cloudnative/fluid/releases
- https://github.com/fluid-cloudnative/fluid/tree/master/pkg/ddc
- https://github.com/fluid-cloudnative/fluid/tree/master/docs
- https://github.com/fluid-cloudnative/fluid/issues?q=kvcache
- https://www.cncf.io/blog/2026/05/21/how-netease-games-achieved-30-second-llm-cold-starts-on-kubernetes/
- https://www.cncf.io/news/2026/05/08/the-new-stack-how-netease-games-cut-llm-cold-starts-from-42-minutes-to-30-seconds/
- https://devops-daily.com/posts/netease-fluid-30-second-llm-cold-starts-kubernetes
- https://www.alibabacloud.com/help/en/ack/cloud-native-ai-suite/user-guide/model-acceleration-using-fluid-in-kserve

### Cloud vendors
- https://aws.amazon.com/blogs/machine-learning/tiered-kv-cache-for-large-llms-on-amazon-sagemaker-hyperpod-with-curvine/ (SageMaker HyperPod + Curvine + LMCache, 2.7× TTFT)
- https://github.com/aws-samples/sample-eks-cache-aware-llm-routing
- https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-genai/references/kv-cache-and-cost/
- https://docs.aws.amazon.com/bedrock/
- https://docs.lmcache.ai/kv_cache/storage_backends/azure.html
- https://github.com/ai-dynamo/nixl/blob/main/src/plugins/azure_blob/README.md
- https://github.com/ai-dynamo/nixl/blob/main/src/plugins/meson.build
- https://dev.to/pvgomes/your-ai-gateway-is-a-cache-scheduler-now-cl (second-hand quote of the GKE Inference Gateway blog)
- https://github.com/llm-d/llm-d
- https://github.com/llm-d/llm-d-kv-cache
- https://aibrix.github.io/posts/2025-11-10-v0.5.0-release/
- https://developers.cloudflare.com/workers-ai/
- https://fireworks.ai/pricing
- https://www.together.ai/pricing

### PrisKV — Colocated Tiered KVCache Store
- https://aibrix.github.io/posts/2025-11-26-priskv-intro/ — "PrisKV: A Colocated Tiered KVCache Store for LLM Serving"
- https://github.com/aibrix/PrisKV — "High Performance KV Cache Store for LLM"
- https://github.com/vllm-project/aibrix/pull/1303 — "[Feature] KVCache: add Pris connector"
- https://github.com/vllm-project/aibrix/pull/2056 — "[Feature] AIBrix L2 KVCache Zero-Copy APIs and vLLM v0.14.0 integration"
- https://github.com/vllm-project/aibrix/releases/tag/v0.4.0

### Curvine
- https://github.com/CurvineIO/curvine — "AI-Native & Cloud-Native FS … CNCF Sandbox Project"
- https://curvineio.github.io/docs/Overview/instroduction/
- https://curvineio.github.io/docs/Benchmark/meta/
- https://curvineio.github.io/docs/User-Manuals/best-practices
- https://curvineio.github.io/blog/2026/08/13/tiered-kv-cache-sagemaker-hyperpod-curvine (verbatim mirror of the AWS post)
- https://aws.amazon.com/cn/blogs/machine-learning/tiered-kv-cache-for-large-llms-on-amazon-sagemaker-hyperpod-with-curvine/
- https://www.alluxio.com.cn/alluxio-enterprise-vs-open-source/
- https://juicefs.com/zh-cn/blog/engineering/meta-perf-hdfs-oss-jfs
- https://deepwiki.com/CurvineIO/curvine

### Alluxio (docs, release notes, customer stories)
- https://github.com/alluxio/alluxio
- https://documentation.alluxio.io/ee-ai-en/what-is-alluxio.md
- https://documentation.alluxio.io/ee-ai-en/release-notes/ai-3-9-16-0-0.md
- https://www.alluxio.io/blog/alluxio-ai-3-7-now-with-sub-millisecond-latency (2025-08-06 — **TTFB, not TTFT**)
- https://www.alluxio.com.cn/alluxio-ai-3-7-now-with-sub-millisecond-latency/
- https://www.alluxio.io/blog/alluxio-ai-3-9-brings-checkpoint-acceleration-to-any-ai-training-framework
- https://www.alluxio.io/customer-stories/fireworks-ai-accelerates-inference-cold-starts-across-multiple-gpu-clouds-with-alluxio
- https://www.alluxio.io/customer-stories/blackout-power-trading
- https://www.alluxio.io/news-press/alluxio-partners-with-vllm-production-stack-to-accelerate-llm-inference (2025-03-19 — **no numbers**)
- https://www.alluxio.io/videos/ai-ml-infra-meetup-a-faster-and-more-cost-efficient-llm-inference-stack (UChicago talk — the "10×")

### Other §4 projects
- https://github.com/bytedance/InfiniStore
- https://bytedance.github.io/InfiniStore/design.html
- https://github.com/bytedance/InfiniStore/commits/main.atom
- https://github.com/kvcache-ai/Mooncake
- https://kvcache.ai/blog/
- https://arxiv.org/abs/2209.01496 — **WARNING: a DIFFERENT "InfiniStore" system; do not cross-cite**
- https://github.com/aibrix/PrisKV
- https://github.com/vllm-project/aibrix
- https://github.com/taco-project/FlexKV


### GPU Direct Storage / NVMe KV cache
- https://arxiv.org/abs/2605.03375 — Tutti: Making SSD-Backed KV Cache Practical for Long-Context LLM Serving
- https://arxiv.org/abs/2609.11744 — Building py-kvcache: A Performance Characterization of External KV Caching for vLLM with NVMe SSDs
- https://docs.lmcache.ai/v0.4.7/kv_cache/storage_backends/gds.html
- https://www.weka.io/article/open-sourcing-gds-integration-from-augmented-memory-grid-see-results-for-yourself
- https://next.nutanix.com/community-blog-154/context-overload-of-the-gpu-kind-how-lmcache-and-nutanix-files-storage-tame-llm-inference-costs-at-scale-part-3-45413
- https://www.computer.org/csdl/journal/ca/2026/02/11601066/2hZ80Kwgbxm — Prompt Caching on Flash

### Redis / Valkey / llm-d KV indexer
- https://redis.io/blog/get-faster-llm-inference-and-cheaper-responses-with-lmcache-and-redis/ (2025-07-28 — **no benchmarks**)
- **https://redis.io/blog/throughput-optimizing-redis-for-l2-kv-cache-reuse/** (2026-03-30 — **the Redis KV-cache source with real numbers**)
- https://redis.io/blog/langcache-public-preview.md (2025-09-04, updated 2026-08-13)
- https://redis.io/langcache/
- https://redis.io/calculator/langcache/ (JS-rendered; no extractable pricing)
- https://huggingface.co/papers/2504.02268 (redis/langcache-embed-v1)
- https://docs.lmcache.ai/kv_cache/storage_backends/resp.html (LMCache native Redis/Valkey RESP connector)
- https://github.com/LMCache/lmcache_redis (benchmarking playground)
- https://github.com/LMCache/LMCache/pull/2541
- https://github.com/LMCache/LMCache/pull/2642
- https://www.linuxfoundation.org/press/valkey-enhances-efficiency-security-and-modular-performance-with-9.1-release-and-new-ecosystem-integrations
- https://github.com/valkey-io/valkey
- https://github.com/redis/redis
- https://llm-d.ai/docs/dev/architecture/advanced/kv-management/kv-indexer
- https://github.com/llm-d/llm-d-kv-cache/pull/139 — "feat: Add Valkey and RDMA support for KV-cache indexing"
- https://github.com/llm-d/llm-d-kv-cache/blob/v0.5.1-rc1/examples/valkey_configuration.md
- https://github.com/llm-d/llm-d-kv-cache/blob/v0.8.1/pkg/kvcache/kvblock/redis.go
- https://github.com/llm-d/llm-d-kv-cache/blob/v0.6.1/pkg/kvcache/kvblock/index.go
- https://github.com/redis/redis/releases

### Object-store (S3) KV cache
- https://www.dell.com/en-us/blog/kv-cache-offload-to-object-storage-gpu-direct-and-upstream/ (2026-08-19 — Dell ObjectScale + NIXL OBJ, 13.4× @235K)
- https://arxiv.org/abs/2605.22850 — ObjectCache: Layerwise Object-Storage Retrieval for KV Cache Reuse (2026-05-16)
- https://docs.lmcache.ai/kv_cache/storage_backends/s3.html
- https://www.weka.io/article/weka-sets-a-new-bar-with-75x-faster-time-to-first-token-ttft
- https://github.com/kvcache-ai/Mooncake/blob/c251eefa/docs/source/performance/ssd-offload-benchmark-results.md
- https://github.com/kvcache-ai/Mooncake/pull/1835

### Adjacent projects referenced
- https://github.com/valkey-io/valkey
- https://github.com/redis/redis
- https://github.com/alluxio/alluxio
- https://github.com/curvineio/curvine
- https://github.com/bytedance/InfiniStore
- https://github.com/ai-dynamo/dynamo
- https://github.com/run-ai/runai-model-streamer

---

*End of note. Compiled 2026-09-15. Companion raw material: `raw/sc/` (this session's fetches plus the extraction tooling `ghfile.py` — **bug-fixed**, see §9 item 23 — `ghraw.py`, `html2txt.py`, `extract_readme.py`, `ghmeta2.sh`), **`raw/cloud/notes_cloud_vendors.md`** (cloud-vendor deep dive, 54 UNVERIFIED flags), **`raw/redisgds/notes_redis_gds.md`** (Redis/Valkey + GDS/NVMe/S3 deep dive, 91 source URLs, 42 UNVERIFIED flags), and **`raw/distcache/notes_distcache.md`** (Alluxio/Curvine/InfiniStore/others deep dive, 587 lines — source of the Alluxio and Curvine corrections in §4).*

**Revision history:** v1 written from direct verification; then revised after two parallel deep-dive passes landed, which (a) **corrected §4.1 Alluxio** (no KV-cache product feature; TTFB≠TTFT) and (b) **corrected §4.2 Curvine** (no KV feature of its own; KV design is AWS-authored; not 3FS-compatible), and (c) **resolved** the vLLM PR merge date, and the PrisKV/Tair/Mooncake/FlexKV metadata that a mid-session GitHub outage had left UNVERIFIED.
