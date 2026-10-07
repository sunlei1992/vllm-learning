# Chinese-Vendor / China-Ecosystem KV-Cache Systems

**Technical research notes — state as of 2026-09-15 (report target: September 2026)**

Scope: open-source KV-cache management and KV-cache-centric LLM inference serving systems from Chinese vendors and the China-centered open-source ecosystem. Covers Alibaba/Tair, Ant Group + Approaching.AI, Tencent, ByteDance, Huawei/Ascend, Baidu, Moonshot AI, JD/xLLM, Zhipu, and the accelerator-vendor transport backends.

## Verification conventions used in this document

- All GitHub metrics (stars, forks, releases) were read from the **GitHub REST API via an authenticated `gh` client on 2026-09-15** and are reproduced verbatim. Where a repo has no GitHub "Release" object, that is stated explicitly rather than guessed.
- Performance numbers are quoted with the **exact figure and the exact source URL**. Where a vendor page gives a number without a reproducible benchmark protocol, that is noted.
- **Everything I could not verify is flagged inline with `⚠️ UNVERIFIED` or `❌ COULD NOT VERIFY`.** I did not invent stars, versions, or benchmark numbers.
- Raw fetched artifacts (READMEs, docs, HTML→text extractions) are stored under `kvcache-research/raw/cnv/` and `kvcache-research/raw/`.

### Corrections to the research brief's premises (important)

**Five** premises in the task brief turned out to be wrong or imprecise, and are corrected in the relevant sections:

1. **RBG (`sgl-project/rbg`) is *not* an Ant Group project.** It was built by the SGLang community jointly with developers from **Alibaba Cloud and Xiaohongshu (小红书)**, with Alibaba Cloud and Xiaohongshu contributors explicitly named in the project's own acknowledgement list (`cheyang` = Yang Che, Alibaba Cloud). **Ant Group's actual contribution is elsewhere**: named Ant Group engineers (Tingwei Huang, Yongke Zhao) built the **Mooncake** integration for **SGLang HiCache**, and Ant Group reports an **−84% TTFT** cache-hit result on DeepSeek-R1-671B. Ant Group is also a **Mooncake co-builder**. See §2.1–§2.2.
2. **`xLLM` is no longer at `jd-opensource/xllm`.** `https://github.com/jd-opensource/xllm` now **301-redirects to `https://github.com/xLLM-AI/xllm`**, and the project is described as "hosted in **OpenAtom Foundation**". See §7.2.
3. **EIC is not an open-source KV-cache system.** "ByteDance EIC" resolves to **EIC = Elastic Instant Cache (弹性极速缓存)**, a **commercial, closed-source** Volcengine product. The Apache-2.0 code in SGLang/LMCache is only a **client shim**; `eic` / `eic-client` / `volcengine-eic` on PyPI all return 404 and no repo exists. See §4.1 — this is the single most important correction in the report.
4. **`Tencent/AngelPTM` does not exist** (GitHub API HTTP 404). Tencent's `TurboTransformers` exists but is a **2020-era transformer runtime with no KV-cache management** — it is not relevant to this topic. See §3.3.
5. **"PrisDB" is a ByteDance team, not an Alibaba product.** The brief grouped "Tair KVCache / PrisDB / Tair KVCache for Qwen"; PrisKV is "incubated by **ByteDance's PrisDB & IAAS & DMI team**" per SGLang's own AIBrix README. See §4.4.

Also note: the brief's "Tencent FlexKV … from Tencent + NVIDIA" is **confirmed** — NVIDIA engineers are among the top contributors (`linhu-nv`, `wenpengw-nv`), and Mooncake's README describes FlexKV as "a distributed KV store and cache system from Tencent and NVIDIA in collaboration with the community".

And two premises that were **understated** rather than wrong: Alibaba's KV-cache footprint includes a second, undocumented-in-the-brief commercial system (**PolarKVCache**, §1.4) which publishes the most concrete numbers of any Alibaba offering; and Baidu's FastDeploy turns out to ship a full **Mooncake-backed Global Cache Pooling** feature plus its own RDMA KV-transfer library (§6.3–§6.4).

---

## Summary table

| # | System | Owner / maintainer | License | ★ / forks (2026-09-15) | Latest release | Primary KV tiers | Transport |
|---|--------|--------------------|---------|------------------------|----------------|------------------|-----------|
| 1 | **Tair KVCache Manager (KVCM)** | Alibaba Cloud Tair + Alibaba Intelligent Engine + Infra/Stability Eng. | Apache-2.0 | **255 / 58** | no official release (only `__binary-dependency-0.0.2`, 2026-02-12, prerelease) | metadata-only; backs NFS / 3FS / TairMemPool / Mooncake | TCP or RDMA; data plane bypasses KVCM |
| 1b | **Tair KVCache HiSim** | same repo | Apache-2.0 | (same repo) | — | simulator (CPU-only) | n/a |
| 1c | **PolarKVCache** (PolarDB for MySQL) | Alibaba Cloud PolarDB | commercial, gray-release | n/a (closed) | GA not verified | L1 VRAM → L2 DRAM → L3 DMP → L4 disk | GPUDirect RDMA, layer-wise scatter/gather |
| 1d | **Tair KVCache (commercial)** | Alibaba Cloud Tair | commercial | n/a | paid product | HBM/DRAM pooling + SSD + remote | Redis-semantic + memory-semantic API |
| 2 | **Mooncake** | kvcache-ai (Moonshot AI + Tsinghua + Approaching.AI + Alibaba Cloud + Ant Group + 9#AISoft + …) | Apache-2.0 | **6575 / 1221** | v0.3.13 (2026-08-26); v0.3.14-rc1 (2026-09-07) | DRAM / VRAM / NVMe SSD pool | GPUDirect RDMA (zero-copy), multi-NIC; also ROCm/MUSA/EFA/NPU backends |
| 2b | **SGLang HiCache** | sgl-project/sglang | Apache-2.0 | **35 982 / 8871** | — | GPU HBM → host DRAM → remote | pluggable backends (11 registered) |
| 2c | **RBG** | SGLang community + **Alibaba Cloud + Xiaohongshu** | Apache-2.0 | **296 / 80** | v0.8.0 (2026-08-31) | orchestrates external KV store as a "role" | K8s-level; RDMA/NVLink/PCIe affinity |
| 3 | **FlexKV** | Tencent Cloud TACO team + **NVIDIA** + community | Apache-2.0 (third-party notices) | **351 / 73** | tag v1.2.1 (no Release object) | GPU → CPU → local SSD → remote/PB-scale | Mooncake TE (RDMA), GDS, io_uring, multi-path PCIe |
| 3b | **KsanaLLM** | Tencent | Tencent license (NOASSERTION) | **550 / 46** | no tags/releases | GPU HBM page-based; Global Cache Connector → Mooncake | RDMA (Mooncake Store) |
| 3c | **TurboTransformers** | Tencent | NOASSERTION | **1551 / 208** | — | no KV-cache management (2020-era) | n/a |
| 4 | **EIC = Elastic Instant Cache (弹性极速缓存)** | **Volcengine (ByteDance) Storage team** | ⚠️ **NOT open source** — commercial; only the *client shim* is Apache-2.0 (in SGLang via PR #10271 and LMCache via PR #1930). PyPI `eic`/`eic-client`/`volcengine-eic` = 404 | n/a (paid product) | Volcengine console only | GPU VRAM → local cache → distributed DRAM + SSD; co-located with GPUs | kernel TCP / user-space TCP / RDMA / **GPUDirect RDMA**; namespace + TTL/LRU/ARC/FIFO eviction |
| 4b | **InfiniStore** | `bytedance` (origin: `bd-iaas-us`, now 404) | Apache-2.0 | **438 / 44** | **no releases**; created 2024-09-06, last push **2025-11-13** (⚠️ ~10 mo stale) | distributed KV cache store for LLM inference (PD-disagg or not) | RDMA; vLLM integration **via LMCache**; SGLang "in progress" |
| 4c | **PrisKV** (from ByteDance's **PrisDB / IAAS / DMI** team) | `aibrix` org, branch `dev` | Apache-2.0 | **59 / 8** | 0 releases/0 tags; created 2025-11-11, pushed **2026-05-20** (⚠️ stale) | distributed KV cache store, port 18512; **tiered** `localfs` quota + `s3`; memfile on tmpfs/hugetlbfs; ≤16.7M keys, block ≤1 MB | **RDMA / TCP / shmem / UCX + GPUDirect RDMA**; CUDA and Ascend NPU (`PRISKV_USE_ACL`) builds; ⚠️ **eviction = TTL scan only (600 s), no LRU** |
| 4d | **AIBrix** (KVCache Offloading Framework) — **the control plane tying the ByteDance names together** | **`vllm-project/aibrix`** — ByteDance-originated, now community-governed | Apache-2.0 | **5089 / 694** | v0.7.0 (2026-06-18) | L1 DRAM + L2 distributed | **L2 catalogue: `INFINISTORE`, `HPKV`, `PRISKV`, `ROCKSDB`, `EIC`, `SHFS`, `MOCK`**; RDMA/GDR; L1 LRU/**S3FIFO** eviction |
| 4e | **ShadowKV** | ByteDance-Seed (+ CMU) | Apache-2.0 | **313 / 26** | no releases; pushed 2025-05-01 | **KV-cache compression + value-cache offload** (research) | n/a (algorithm) |
| 5 | **vLLM-Ascend KV Cache Pool / `AscendStoreConnector`** | vllm-project (Huawei-affiliated maintainers) | Apache-2.0 | **2826 / 2257** | v0.23.0 (2026-08-16, stable); v0.26.0rc1 (2026-09-03) | NPU HBM → host DRAM → NVMe SSD; backends `mooncake` (default) / `memcache` / `yuanrong` | **HCCL** (A2 RoCE, A3 fabric-mem/UB, 950 URMA/UBOE); MemFabric; Mooncake TE |
| 5b | **MindIE-LLM / MindIE-Motor** | Ascend org (Huawei) | **Mulan PSL v2** (GitHub reports NOASSERTION — not proprietary) | **27 / 7** and **2 / 4** | no releases (pushed 2026-09-07 / 2026-09-15) | KV Cache Pooling via **HCCL one-sided comm**; KV Conductor (Rust) indexes HBM/CPU/Disk | HCCL; Mooncake / MemCache / Yuanrong / UCM backends |
| 5c | **MemFabric / MemCache** | Ascend org (Huawei) | **Mulan PSL v2** | **7 / 4** and **11 / 4** | PyPI `memfabric-hybrid`, `memcache-hybrid` | GVA-pooled cross-node DRAM + HBM (up to **128 TB CPU + 48 TB HBM** on A3 SuperPoD) | Device UB 1.0 (A3), Device/Host RoCE (A2), URMA (Kunpeng K5) |
| 6 | **FastDeploy** | Baidu / PaddlePaddle | Apache-2.0 | **3715 / 756** | v2.5.0 (2026-04-09) | 3-tier block cache `DEVICE → HOST → Storage` on a **RadixTree**; `block_size`=64, `kv_cache_ratio`=0.75; KV quant `int8`/`fp8`/**`block_wise_fp8`**/`int4_zp`…; **Global Cache Pooling** → Mooncake Store | self-developed `KVTransferManager` (RDMA/IPC) **and** Mooncake (rdma/tcp); etcd/Redis HA leader election |
| 6b | **AttentionStore** (百度百舸 Baige) | Baidu Intelligent Cloud — ⚠️ **NOT open source** (FastDeploy ships only a client wrapper; `attentionstore_sdk` = **404 on PyPI**) | proprietary | n/a | press release 2026-04-02 | HBM → DRAM → SSD, engine-decoupled, survives engine restart | C++ SDK async P↔D; claimed **80–90% hit rate**, **6.2× TTFT @64K** ⚠️ single press release |
| 6c | **LU-KV** | Baidu Baige + Fudan | Apache-2.0 (fork of NVIDIA/kvpress) | **6 / —** | — | **KV-cache eviction research**, ICML 2026, arXiv 2602.08585 | n/a (algorithm) |
| 7 | **checkpoint-engine** | Moonshot AI | MIT | **1005 / 108** | v0.4.2 (2026-07-04) | weight update middleware (not KV) | Mooncake TE (P2P), CUDA IPC |
| 7b | **xLLM** | xLLM-AI (was jd-opensource), OpenAtom Foundation | Apache-2.0 | **1570 / 298** | v0.10.1 (2026-07-14) | hybrid KV cache mgmt built on Mooncake | Mooncake |
| 7c | **dInfer** | Ant Group / InclusionAI | Apache-2.0 | **480 / 49** | no releases (pushed 2026-02-11) | diffusion-LM KV-cache manager, prefix caching (`--cache prefix`/`dual`) | in-process |
| 8 | **UCM (Unified Cache Manager)** | third-party, integrated on Ascend | third-party | n/a | — | HBM → DRAM → SSD/NFS/**3FS** (persistent) | vendor-neutral; Mooncake for distributed PD |

---

# 1. Alibaba — Tair KVCache, Tair KVCache Manager, HiSim

## 1.1 Canonical repo

**`https://github.com/alibaba/tair-kvcache` is canonical.** Verified via the GitHub API on 2026-09-15:

- `alibaba/tair-kvcache` — `"fork": false`, owner type `Organization`, id `1124513859`, description "Alibaba Cloud's high-performance KVCache system for LLM inference, with components for global cache management, inference simulation(HiSim), and more."
- `ZhihanYan/tair-kvcache` — `"fork": true`
- `li-xiao-qing/tair-kvcache` — `"fork": true` (`description: null`)

So the two mirrors named in the brief are **forks**, not mirrors maintained by Alibaba. Registry: `https://github.com/alibaba/tair-kvcache`.

### Maturity signals (2026-09-15)

| Metric | Value |
|---|---|
| Stars | **255** |
| Forks | **58** |
| Open issues | 32 |
| Created | **2025-12-29T06:34:44Z** ("Initial commit") |
| Last push | **2026-09-15T10:58:02Z** |
| License | **Apache-2.0** |
| Primary language | C++ |
| Commits | ~268 (GitHub `Link: … page=268` on a `per_page=1` query) |
| Contributors | **21** (non-anonymous) |
| Top contributors | `wangxiyu191` (88), `lucky-zzz` (26), `oldsharp` (25), `MMeecatfish` (23), `charpty` (19), `YoungRX` (18), `Tyndalllll` (17), `shaohuaxi` (12), `lpdiink`/`lpdink` (12), `DWAE86` (10) |
| Releases | **No official release.** The only "releases" are `__binary-dependency-0.0.2` (2026-02-12, `prerelease: true`) and `__binary-dependency-0.0.1` (2026-01-29, prerelease) — these are binary-dependency build artifacts, not product versions. The only tags are those two. |

> ⚠️ The repo was only open-sourced at the **end of December 2025**, so its star count (255) is not comparable to multi-year projects. This is a **9-month-old** repository as of September 2026.

### Maintainership

The open-sourcing announcement states the project was built jointly by **阿里云 Tair KVCache 团队 + 阿里巴巴智能引擎 + 基础设施与稳定性工程团队** ("Alibaba Cloud Tair KVCache team, jointly with Alibaba Intelligent Engine and the Infrastructure & Stability Engineering teams"). Source: <https://developer.aliyun.com/article/1704765> (dated 2026-01-08) and the WeChat long-form version <https://mp.weixin.qq.com/s/apZIaiI5zazumEYNQHTdHg>.

## 1.2 Tair KVCache Manager (KVCM) — what it is and how it works

Tair KVCache Manager is a **centralized global metadata service for KVCache**, not a data store. The single most important architectural property: **KVCM only records where KV data lives and whether it may be read/written; KV data itself never flows through KVCM.**

From `docs/design/module_architecture.md` (fetched from the `main` branch):

> "**元数据操作走元数据面到 KVCM，实际 KVCache 数据搬运走数据面直连存储后端，二者不混**。KVCM 只管理"数据在哪、能不能读写"，不经手数据本身。"

### Module decomposition (from `docs/design/module_architecture.md`)

Server core, a strictly one-directional dependency chain:

```
service → manager → meta → config → data_storage → common
```

| Module | Directory | Responsibility |
|---|---|---|
| Entry | `main.cpp` | constructs CLI, runs it |
| **service** | `service/` | access layer. `Server` wires almost every component at startup; `*ServiceImpl` (meta/admin/debug) are transport-agnostic business entrypoints; `grpc_service/` + `http_service/` are transport adapters |
| **manager** | `manager/` | orchestration + business core. `CacheManager` is the central facade; coordinates `MetaSearcher`, `WriteLocationManager`, `DataStorageSelector`, `CacheReclaimer`, `CacheGarbageCollector`, `MigrationManager`, `SchedulePlanExecutor` |
| **meta** | `meta/` | metadata plane. `MetaIndexerManager` owns one `MetaIndexer` per `instance_id`; maps cache key → `CacheLocation`. `meta_search_cache` is a query cache. Backends pluggable |
| **config** | `config/` | config models + `RegistryManager` (persists instance registration) + `CoordinationBackend`/`LeaderElector` (active-standby leader election) |
| **data_storage** | `data_storage/` | pluggable KV data storage backends. `DataStorageManager`, `DataStorageBackend`, `DataStorageUri` |
| **client** | `client/` | C++/Python client SDK: **metadata plane** `MetaClient` (gRPC) and **data plane** `TransferClient` |
| **py_connector** | `py_connector/` | Python integration into **vLLM / SGLang / TRT-LLM**; also ships a pure-Python HTTP metadata-plane client `KvCacheManagerClient` (`common/manager_client.py`) |
| **protocol** | `protocol/protobuf/` | gRPC/proto contracts for meta/admin/debug/kv_meta services |
| **metrics** | `metrics/` | `MetricsRegistry`/`MetricsCollector`, reporters (kmonitor/local/logging/dummy), `PrometheusExporter` |
| **event** | `event/` | lightweight event bus (`EventManager`, `EventPublisher`) |
| **optimizer** | `kv_cache_manager/optimizer/` | trace replay + capacity/policy analysis; also an online `TraceQuery` service |

### Three planes (explicitly distinguished by the docs)

1. **Metadata plane** — MetaService RPCs: `GetCacheLocation`, `GetCacheLocationLen`, `GetCacheLocationsByBackend`, `StartWriteCache`, `FinishWriteCache`, `GetCacheMeta`, `RemoveCache`, `TrimCache`, `RegisterInstance`, `GetClusterInfo`, `ReportEvent`. This is the **hot path** for the engine.
2. **Data plane** — `TransferClient` moves KV bytes between engine HBM/host memory and the storage backend, **directly, bypassing KVCM**.
3. **Control plane** — AdminService only: storage create/delete, Instance Group management, accounts, config snapshots, ops monitoring, leader ops. Not on the inference hot path.

Two equivalent metadata paths exist: C++ `MetaClient` over gRPC, or Python `KvCacheManagerClient` over HTTP `/api/*`. The Python client uses a default `request_timeout_seconds` of **1 second**, with a separate **5-second** timeout for leader discovery.

### Client roles

`InitParams.role_type`:
- `SCHEDULER` — creates only `MetaClient` (metadata match + write-address acquisition)
- `WORKER` — creates only `TransferClient` (data movement); its storage config is pushed down from KVCM via `MetaClient::GetStorageConfig()` so it always matches the server
- `HYBRID` — both

### Core data model (from `docs/design/basic_concepts.md`)

- **Storage** — one storage system with its own connection config. Supported types: **NFS, 3FS, TairMemPool, Mooncake**. A Storage may be shared across Instance Groups/Instances.
- **Instance Group** — the quota unit. "同 Group 内所有 Instance 共享一套配额"; each group can have its own available Storage list. Total quota plus per-storage-type quota (documented example: `总Quota = 100T, TairMemPool Quota = 1T, 3FS Quota = 99T`).
- **Instance** — a KVCache instance. **KV is reused only within a single Instance; cross-Instance reuse does not happen.** The model and KV config (fp8/bf16, block_size) are unique and immutable per Instance.
- **Block** — a fixed-length run of consecutive tokens; has **prefix dependency** ("自身 Token 序列相同但前缀不一致的两个 Block 是不同的"). Each Block can have multiple `CacheLocation`s (multiple tiers).
- **CacheLocation** — one storage location of one Block. State machine: **`writing → serving → deleting`**. All data within one CacheLocation must be the same storage type.
- **LocationSpec** — a sub-part of a CacheLocation. Positions are unified as **URIs** (address for a memory pool, path for a filesystem, key for a KV store), with `size` recorded in the URI for capacity accounting; `blkid + size` supports sub-block storage inside one large file (e.g. one 3FS file). `spec name` is user-configurable to support different TP, PP and **hybrid attention** layouts — and a Location may hold only *some* Specs, because "混合注意力场景下很多 Block 不需要存储线性注意力" (in hybrid-attention models many blocks don't need linear-attention state stored).

### Two-phase write (reliability mechanism)

1. `StartWriteCache` — returns `write_session_id` + write-location URIs; the `CacheLocation` transitions to **`writing`**. A key in `writing` cannot be written concurrently (guarded by a timeout).
2. `SaveKvCaches` — the engine writes KV bytes **directly to the backend** via `TransferClient`.
3. `FinishWriteCache` — the engine reports back with a `success_block_mask`; successful `CacheLocation`s become **`serving`** and enter the metadata index; failed blocks are dropped. "保证只有真正写成功的数据可被后续读取命中."

### Eviction, capacity management, HA, migration

- Capacity control has **two dimensions**: Instance Group (`Quota` = hard cap; `水位`/watermark = soft cap triggering eviction) and storage-backend-level (planned).
- Eviction modes: **TTL, LRU, LFU** and more; watermark and Quota are **updatable at runtime**.
- `instance_reclaim_budget_policy` selects cross-Instance eviction policy among **`GROUP_LRU`**, **`USAGE_PROPORTIONAL`** (usage-proportional budget with cross-round rotation), and **`FIXED_PER_INSTANCE`**. All three sample candidates without side effects through `meta`'s `SampleReclaimCandidates`.
- Deletion is **asynchronous**: `CacheReclaimer` picks keys, submits an end-to-end async task to `SchedulePlanExecutor`; workers do metadata Get/CAS/Sync, then wait a delete delay in a timer queue (waiting does not hold a worker), then delete data + CAS the metadata index. Reclaimer maintains pending locations and delete-byte credit per Instance Group + BaseStorageType for de-duplication, over-eviction avoidance, and bounded back-pressure.
- **Tiered-storage migration** is asynchronous and coordinated with reclaim: migration is triggered by the source storage type's watermark; `MigrationManager` re-reads current Instance/config/strategy/Location, excludes pending-delete Locations from the snapshot, then does Backend Create and a unified Copy/Mark admission. Copy completion re-verifies the source Location is still `SERVING` with unchanged create-time before promoting the target. Ready tasks are chosen in the order **`Reclaim → System → Migration Continuation → Migration Prepare`**.
- **HA**: `LeaderElector` uses a distributed lock over `CoordinationBackend` (`memory` / `file` / `redis`). Only the Leader serves read/write. Failover: `DoRecover` → start GC → resume Reclaimer → start MigrationManager → open leader-only requests; on demotion, stop new GC/Reclaimer work, drain leader-only requests, join GC, stop MigrationManager, then `DoCleanup` (in-flight writes are treated as failures).
- **Background metadata GC** (`CacheGarbageCollector`) runs only on the Leader; identifies `CLS_WRITING` Locations past grace that are not active migration targets, and for normal `CLS_SERVING` Locations calls low-cost `MightExist()` per storage in batches.

### Metadata backend and concurrency design (from the WeChat article)

- Metadata is stored in an **external KV system**: Valkey / Redis (in-memory-first, persistent) or RocksDB (LSM-tree, write-heavy). Choice justified by ecosystem maturity and by "元数据同样适用 KV 存储，与上层 Cache 的 KV 语义统一".
- `MetaIndex` exposes `Put/Delete/Update/Get`, plus a first-class **atomic `ReadModifyWrite(keys, ModifierFunc)`** with user-supplied modifier functions.
- Concurrency: **sharded locking + batch alignment**. Key space is hash-partitioned into N shards (N must be a multiple of a power of two); each shard has an independent lock. **Reads take no lock and are never blocked by locks.** Locks are acquired in ascending shard order to avoid deadlock; large batches are split so that consecutive small batches touch disjoint shard sets, with the batch size jointly bounded by `batch_size` and shard count.
- An **LRU Cache acts as a metadata search cache**: every value lookup tries the local LRU first; new KV query results are inserted; all writes (`Put/Delete/Update`) invalidate the corresponding entry after committing to the underlying store.

### Deployment shape and network assumptions

KVCM is deployed **centrally**. Because it only handles metadata and is written in C++, "依靠 scale up 就可以满足单一推理集群的需求"; the Instance Group abstraction allows horizontal scale-out across clusters. Centralization also avoids injecting KVCM logic into inference containers and "规避了可能导致的元数据存储后端（如 Valkey）连接数爆炸等问题".

Crucially: **KVCM does not require RDMA.** "结合 3FS Master 等工作，Tair KVCM 可以仅使用 TCP 和推理引擎及后端存储进行交互，并不强依赖 RDMA 环境." For clusters where only GPU nodes have RDMA, KVCM can be deployed outside the RDMA environment, avoiding GPU-node failure rates.

### Storage backends and TairMemPool

Supported backends: **3FS, TairMemPool, Mooncake, NFS** (same Storage shareable across Instance Groups/Instances). Dynamic switching between backends is supported for availability — "将热数据存储到 TairMemPool，将冷数据存储到 3FS"; if one backend dies, cache service stays available. For storage systems lacking metadata capability or with limited metadata performance (NFS, 3FS), KVCM provides **block allocation** (allocate a few large files, carve them into small pieces).

**TairMemPool** is described as co-developed by the Alibaba Cloud Tair team and the "服务器研发定制计算与芯片系统团队" (server R&D custom-compute & chip systems team): hardware/software co-optimization for multi-node **unified memory addressing and global access**, multi-medium/multi-protocol access, KVCache-specific transfer optimization, and — the one concrete number given — **"在多网卡环境下网络带宽利用率超 90%"** (multi-NIC network bandwidth utilization above 90%), with enterprise HA.

### Engines and attention mechanisms supported

The open-sourcing article states KVCM **"支持了阿里巴巴集团 RTP-LLM 推理服务加速，并且扩展支持到 vLLM、SGLang 等众多开源引擎，兼容 Sparse Attention、Sliding Window Attention 等在内的多种注意力机制"**.

- **RTP-LLM is Alibaba's internal/Group inference engine — this is a real production-adoption signal.**
- The README additionally lists **vLLM, SGLang, RTP-LLM, TRT-LLM** as engines supported by the client/connector.
- The Optimizer supports a **`qwen_bailian` trace type** — i.e. traces from **Qwen on Bailian** (Alibaba's model service), which is another adoption signal. See `docs/optimizer.md`.

### Documented scale/bandwidth reasoning (Alibaba Cloud numbers)

From the WeChat article:
- Alibaba Cloud intelligent-computing cross-machine KVCache transfer bandwidth is **~20 GB/s** typically: **EGS 8-card machines → 20 GB/s general network**; **Lingjun (灵骏) 8-card machines → 25 GB/s storage bandwidth**, plus **200–400 GB/s ScaleOut network bandwidth**.
- Single-port interconnect rose from **25 Gbps to 200+ Gbps**; interconnect scale spans 千卡/万卡 (thousand- to ten-thousand-card) and even cross-AZ; eRDMA now covers mainstream storage machines.
- Metadata scale argument: with `block_size=64`, a **64K context requires querying 1K blocks' metadata**; a single block's KV is **single-digit MB**, so **hundreds of TB of storage implies 亿级 (hundreds of millions) of blocks**. "64K token 对应的 KVCache 传输仅需要不到 1 秒" — i.e. metadata query latency dominates.
- Prefill-throughput cross-check: DeepSeek prefill throughput taken from an RTP-LLM reproduction report, with "DeepSeek 官方披露中为 32.2K"; **Qwen3-Coder prefill throughput measured at ~10 000 token/s in single-machine deployment**.

### Optimizer module

`kv_cache_manager/optimizer/` replays real traces to model hit rate and capacity consumption. From `docs/optimizer.md` and `kv_cache_manager/optimizer/README.md`:

- Eviction policies: **`lru`, `random_lru`, `leaf_aware_lru`, `ttl`** (`ttl_refresh_on_read` toggles sliding vs fixed TTL window; `fallback_on_pressure` toggles TTL-only vs TTL-then-LRU).
- Eviction modes: `1=GROUP_ROUGH`, `2=INSTANCE_ROUGH`, `3=INSTANCE_PRECISE`.
- Trace types: **`publisher_log`** and **`qwen_bailian`**.
- Build: `bazel build //kv_cache_manager/optimizer:optimizer_main`; run via `bazel run`.
- Analysis tooling: hit-rate-over-time chart (`--draw-chart`), Radix Tree visualization (`visualize_tree`), Pareto capacity-vs-hit-rate curve (`tradeoff -c config.json --num-points 30`, using infinite-capacity warmup to get the theoretical hit rate and max cache size, then replaying per capacity point — **non-tiered mode only**; in tiered mode the scan only modifies `quota_capacity`, not per-tier capacities).
- **LiteHit**: a lightweight *exact* LRU hit-rate analyzer for full-attention KV blocks. A single replay produces capacity-independent facts (`RequestFact`, hit curve as arithmetic-segment RLE); `HitCurveProjector` derives the hit count for **any** LRU capacity after the fact, so "capacity no longer needs to be given before the analysis starts". Documented limits: full attention only, equal per-block charge, exact LRU with in-request reverse-order submission; **does not** handle linear attention / Mamba, mixed block sizes, admission, prefetch, or multi-level policies.
- Future direction stated in the article: prefix-aware eviction (suffix blocks evicted before parent blocks; Linear/Full prefix-suffix correlation under hybrid attention).

## 1.3 Tair KVCache HiSim — inference simulator (the "<5% prediction error" claim)

`hisim/README.md` (main branch). HiSim is a **CPU-based LLM inference simulation system** that replays real workload traces to predict TTFT/TPOT/throughput without GPU resources.

- **Mechanism**: "dynamic interception" — it hijacks the execution flow of the inference framework and bypasses actual LLM computation. It exposes an **SGLang-compatible CLI** and outputs **metrics identical to `sglang bench_serving`**, so standard benchmarking scripts work.
- **Support matrix (as documented)**: inference engine **SGLang v0.5.6.post2**; models **Qwen3-32B-FP8, Qwen3-8B**; GPU **H20-96GB**.
- **Config sections**: `platform` (accelerator name, `disk_read/write_bandwidth_gb` for L3, `memory_read/write_bandwidth_gb` for L2), `predictor` (`aiconfigurator` or `schedule_replay`; `device_name`, optional `prefill_scale_factor`/`decode_scale_factor` calibration), `scheduler` (`tp_size`, `ep_size`, `data_type`, `kv_cache_data_type`, `backend_name`, `backend_version`).
- Example config in the README: H20, `disk_*_bandwidth_gb: 4`, `memory_*_bandwidth_gb: 64`, `tp_size: 1`, `ep_size: 1`, `kv_cache_data_type: FP16`.
- **TimePredictor dependency**: HiSim uses **`ai-dynamo/aiconfigurator`** (<https://github.com/ai-dynamo/aiconfigurator>, 441★, Apache-2.0, pushed 2026-09-09) as one predictor. `hisim/pyproject.toml` pins it as a git dependency: `aiconfigurator @ git+https://github.com/ai-dynamo/aiconfigurator.git@h20e-higher-acc`. The H20 hardware specs + operator interpolation data package are obtained from the **`hisim` branch of `kunluninsight/LatencyPrism`** (<https://github.com/kunluninsight/LatencyPrism>, 12★, created 2025-12-11).

### Accuracy numbers (exact, from `hisim/README.md`)

"We evaluated both models under three KV cache hit scenarios across varying request rates. **All prediction errors are below 5%**." Errors are **MAPE**.

**Qwen3-8B on H20** (`aiconfigurator` predictor):

| Case | Mean TTFT | Mean TPOT | Mean ITL | Input Throughput | Duration | Prefix Hit Ratio |
|---|---|---|---|---|---|---|
| `no_cache` | 3.42% | 1.64% | 1.78% | 1.41% | 1.39% | 0.0% |
| `L1` | 4.15% | 3.47% | 3.54% | 2.4% | 2.33% | 0.04% |
| `L2` | 2.38% | 4.05% | 4.07% | 2.35% | 2.29% | 0.0% |

**Qwen3-32B-FP8 on H20**:

| Case | Mean TTFT | Mean TPOT | Mean ITL | Input Throughput | Duration | Prefix Hit Ratio |
|---|---|---|---|---|---|---|
| `no_cache` | 2.77% | 0.58% | 0.52% | 0.52% | 0.51% | 0.00% |
| `L1` | 2.40% | 1.03% | 1.02% | 1.04% | 1.03% | 0.04% |
| `L2` | 3.05% | 1.11% | 1.02% | 1.13% | 1.12% | 0.00% |

Case definitions per the README: `no_cache` = no KV cache hits; `L1` = hits only in **GPU HBM** (Level-1); `L2` = two-level hits — **both HBM and host DRAM** (Level-2).

The Chinese README summarises the same claim: "当前支持 SGLang v0.5.6.post2，在 H20 GPU 上运行 Qwen3 Dense 系列模型，预测误差低于 5%".

Sample HiSim output block (synthetic random workload, 50 prompts, `--request-rate 4`, input/output len 1024): request throughput 2.46 req/s, input token throughput 2530.02 tok/s, output token throughput 2514.64 tok/s, total 5044.66 tok/s, Mean TTFT 10.97 ms, Mean TPOT 9.29 ms, Mean E2E latency 9509.61 ms. (Note the README itself marks several fields `-1` as "unsupported metrics in simulation mode".)

> ⚠️ The `<5%` figure is a **self-reported vendor benchmark** on a 2-model × 3-case matrix on a single accelerator (H20). It is not an independent third-party measurement. Treat as a vendor claim with a documented protocol, not an audited result.

## 1.4 Tair KVCache — the Alibaba Cloud commercial product

### Product page: <https://www.aliyun.com/product/kvcache> (CN: <https://cn.aliyun.com/product/kvcache>) and <https://help.aliyun.com/zh/redis/product-overview/tair-kvcache/>

Positioning (translated): "Tair KVCache is a caching service for LLM inference that pools and manages GPU server HBM and DRAM, upgrading KVCache from **purely VRAM-resident** to a **tiered cache architecture**. Replace compute with storage (以存代算), raising compute efficiency and throughput of LLM inference services and improving GPU server utilization."

Architecture: **three layers** — 智能调度层 (**Gateway**), 模型服务层 (**Model Serving**), and 存储管理层组 (**KVCache Pool**).

Concrete product claims (all from the Alibaba Cloud product/help pages):

| Claim | Exact wording / number | Source |
|---|---|---|
| TTFT reduction | **"首Token时间（TTFT）缩短90%"** — by pooling idle GPU-cluster memory into a distributed memory pool and reusing historical KV cache (e.g. dialogue cache) combined with PD disaggregation | <https://cn.aliyun.com/product/kvcache>, <https://help.aliyun.com/zh/redis/product-overview/tair-kvcache/> |
| Throughput / cost | **"吞吐提升30%、成本降低20%"** | <https://cn.aliyun.com/product/kvcache> |
| Batch size | **"批处理规模提升5~10倍"** (5–10× larger batch size) by keeping only hot data in HBM and offloading the rest | both product pages |
| Context length | supports **百万 token 级输入** (million-token-level input) | both |
| Tiering | 三级缓存体系: **显存 (HBM) – 内存 (DRAM) – 存储 (SSD/remote)** | help page |
| APIs | a **memory-semantic interface** manageable "like a Jemalloc allocator", plus a **Redis-semantic interface** supporting dynamic rate limiting, queue-based load balancing, and multi-turn dialogue caching | help page |
| Engine compatibility | TensorRT-LLM, vLLM, SGLang | help page |
| Routing | KVCache-affinity routing that optimizes cross-node paths, compresses redundant transfers and reduces network bandwidth contention | both |

> ⚠️ These 90%/30%/20%/5–10× numbers come from **vendor marketing pages with no published benchmark protocol, hardware, model, or baseline**. They are directionally consistent with the more detailed PolarKVCache numbers below, but they are not independently reproducible. Flagging explicitly.

### Related Alibaba products found

**PolarKVCache** (PolarDB for MySQL) — a second, largely independent Alibaba KV-cache product that the brief did not mention but which has the most concrete published numbers of any Alibaba KV offering. Source: <https://help.aliyun.com/zh/polardb/polardb-for-mysql/user-guide/polarkvcache-inference-acceleration> (status: **灰度阶段 / gray release**, ticket required).

- **Four-tier hierarchy**: **L1** local GPU VRAM (highest perf, smallest) → **L2** local host DRAM → **L3** distributed memory pool (**PolarDB DMP**, "PB级" scale, the "core storage layer" for cross-node / cross-session sharing) → **L4** distributed disk pool (cold persistent archive, lowest cost).
- **Control plane**: a **PolarKVCache Meta Server** that stores no KV data itself, only per-block placement (which GPU node's VRAM, or the DMP) and session ownership. DB nodes act as **affinity schedulers**, dispatching Prefill vs Decode tasks to the appropriate GPU compute nodes.
- **Transport**: **GPUDirect RDMA** — GPU bypasses CPU and reads/writes remote memory directly through the RDMA NIC, "将数据传输延迟降至微秒级，性能接近访问本地内存" (microsecond-scale, approaching local-memory performance).
- **Layer-wise pipelined transfer**: KV is not transferred as a whole; it moves **per Transformer layer** with **Scatter/Gather pipelining**, so while layer N's KV is in flight over RDMA the compute unit can begin layer N+1, hiding network latency.
- **CacheBlend**: the stated core innovation — a **selective recomputation** policy that decides per page whether to keep it cached or evict to the next tier (retrievable from DMP later, or simply recomputed), balancing generation quality against efficiency.
- **Capacity claim**: "容量可扩展至 10 TB 级别"; comparison table says native vLLM is "几十到上百 GB" while PolarKVCache extends **single-node memory from 512 GB to 10 TB**.
- **Integration**: vLLM and SGLang, "无需修改模型代码".

**Measured performance numbers (exact, with test environments) from the same Alibaba help page:**

| Scenario | Hardware | Model | Baseline | Context | Result |
|---|---|---|---|---|---|
| Chatbot (multi-turn) | NVIDIA **4090 48 GB** | DeepSeek-R1-Distill-Qwen-32B-int8 | **vLLM 0.9.2**, VRAM-only KVCache | 3000 tokens history × 10 turns | **TTFT −26.8×**, **TPS +62%** |
| Coder (very long context) | **8 × NVIDIA H20 96 GB** | Qwen3-Coder-480B-A35B-Instruct-FP8 | **vLLM 0.10.0**, VRAM-only KVCache | **200K tokens** history × 10 turns | **TTFT −8.6×** |
| SGLang integration | 8 × H20 96 GB (**44 GB HBM**, **256 GB host DRAM**, **450 GB DMP**) | GLM-4.5 | **SGLang 0.5.0rc2**, default caching | 10K tokens history, 10 turns, QPS=4 | **TTFT −2.1×** |

Billing: **CNY 8.0 per GB per month** in mainland China (13.2 Hong Kong, 12.8 Tokyo/Seoul, 15.2 Singapore/KL/Jakarta-adjacent, 12.4 US Silicon Valley, 10.4 US Virginia, 16.0 North China 2 gov-cloud). Subscription (包年包月/prepaid) only. Requires PolarDB MySQL **8.0.2** with kernel minor version **8.0.2.2.31+**.

> Note the SGLang-integration result (−2.1×) is much smaller than the vLLM results (−26.8×, −8.6×). The baseline difference (SGLang's native caching vs vLLM VRAM-only) is the likely cause; this is a fair reading of the published table, not a vendor claim.

### Alibaba article series (context the brief asked about)

The WeChat long-form (2026-01-08/09) is article #4 in a 7-part series. The series list, quoted from the article, is:
1. 智能体式推理对 KVCache 的挑战与 SGLang HiCache 技术深度剖析
2. **3FS-KVCache 工程化落地：企业级部署、高可用运维与性能调优实践**
3. Hybrid Model Support：SGLang 对 Mamba-Transformer 等混合架构模型的支持方案
4. **本文 | Tair KVCache Manager：企业级全局 KVCache 管理服务的架构设计与实现**
5. KVCache 仿真分析：高精度的计算和缓存模拟设计与实现
6. **Hierarchical Sparse Attention：分层稀疏注意力框架下的 KV 分层管理与按需加载**
7. 展望：KVCache 驱动的软硬结合演进

The framing: "Tair KVCache 作为阿里云数据库 Tair 产品能力的延伸，本质是缓存范式的三次跃迁" — (i) Redis: cache data → reduce I/O; (ii) GPU KVCache: cache compute intermediates → reduce recomputation; (iii) Tair KVCache: **scale-out, intelligent attention-state management → restructure the LLM inference cost model**.

Also relevant: <https://developer.aliyun.com/article/1717041> — "拆墙现场：阿里云 Tair KVCache 携手 SGLang、千问与 NVIDIA 共话大模型推理优化" (Tair KVCache together with SGLang, Qwen and NVIDIA). ⚠️ The article body is JS-rendered and I could only retrieve the title/summary — I could **not** verify its technical content.

### "PrisDB" — resolved (it is NOT Alibaba)

The brief asked about Alibaba's "Tair KVCache / PrisDB / Tair KVCache for Qwen". **PrisDB is a ByteDance entity, not Alibaba.** SGLang's HiCache blog acknowledgement thanks "the LMCache, AIBrix, **PrisDB**, and **ByteDance EIC** teams", and SGLang's AIBrix backend README states PrisKV is "incubated by **ByteDance's PrisDB & IAAS & DMI team**". See §4.

❌ **COULD NOT VERIFY**: a product specifically named "Tair KVCache for Qwen". What *is* verifiable is (a) the Alibaba Cloud product's general compatibility with Qwen-family models, and (b) that the Tair Optimizer ships a **`qwen_bailian`** trace converter, i.e. it consumes Qwen-on-Bailian production traces.

---

# 2. Ant Group and Approaching.AI — Mooncake, SGLang HiCache, and RBG

This section contains the two premise corrections.

## 2.1 RBG (`sgl-project/rbg`) is Alibaba Cloud + Xiaohongshu + SGLang, **not Ant Group**

`https://github.com/sgl-project/rbg` — 296★, 80 forks, 68 open issues, **Apache-2.0**, language **Go**, created 2025-08-28, last push 2026-09-13, homepage <https://rolebasedgroup.github.io/>, topics `k8s llm pd-disagg sglang`. Latest release **v0.8.0 (2026-08-31)**.

Release highlights from the README news table: v0.7.0 (2026-06-11) "`v1alpha2` API stable release, conversion webhooks, CLI multi-node LLM serving, pod port allocator, coordinated policies, gang scheduling"; v0.6.0 (2026-02-18) "Coordinated scaling, stateful InstanceSet"; **v0.5.0 (2025-12-03) "Native InstanceSet, in-place updates, Mooncake integration"**; v0.4.0 (2025-09-23) "RBGS scaling, Volcano podgroup support".

**Who built it** — the project's own Chinese article ("SGLang × RoleBasedGroup（RBG）", bylined "作者 | RBG 项目维护者", fetched from <https://m.sohu.com/a/936180014_355140/>) says verbatim:

> "RBG 由 SGLang 社区联合来自**阿里云和小红书**的开发者共同开发"

("RBG was developed by the SGLang community together with developers from **Alibaba Cloud and Xiaohongshu**.")

And the acknowledgement list at the end names:
- **SGLang community** — Yineng Zhang, Ying Sheng, Lianmin Zheng, Simo Lin, Yanbo Yang
- **Alibaba Cloud team** — Jing Gu, Tongyu Guo, Xiongfeng Guo, Zhihao Xu, Teng Ma, Yang Lu, Shangming Cai, **Yang Che**, Kai Zhang
- **Xiaohongshu team** — Weixiang Sun, Yang Song, Yue Zhang, Xiying Ding, Feng Xiong, Yuqi Huang

This is corroborated by GitHub data: the top contributor `cheyang` (135 contributions) is **Yang Che**. `gujingit` (84) self-describes on GitHub as "2016-2019 Peking University Master / **2019-2024 Alibaba Cloud**". **Ant Group is not named anywhere in RBG's attribution.** Other top RBG contributors: `Syspretor` (114), `diw-zw` (53), `bcfre` (17), `NoobDream2568` (17), `JasonHe-WQ` (10), `sebest` (9), `TrafalgarZZZ` (6).

Other verifiable RBG facts relevant to KV caching:
- RBG's stated "Performance" capability: "Hardware affinity scheduling: **GPU-NVLink → PCIe → RDMA → VPC**".
- The article positions RBG as the **workload-orchestration layer**, and OME (SGLang's operator) as the **service layer**; "RBG 作为 OME 的 Workload 实现".
- The article cites "在特定场景下，尤其在 Decode 阶段实现了高达 **5 倍**的吞吐提升" for SGLang PD-disaggregation combined with DeepEP/EPLB/FlashInfer/DeepGEMM — this is a **citation of the SGLang PD-disaggregation result, not an RBG result**, and it is about PD disaggregation generally, not about KV caching.

### RBG's KV-cache integration: KEP-74 (Mooncake as a role)

`keps/74-mooncake-integration/README.md` in the RBG repo. Motivation: "Mooncake Store is a distributed KVCache storage engine specifically designed for inference with LLMs based on Transfer Engine… The goal of Mooncake Store is to store reusable KV caches at various locations within the inference cluster. Mooncake Store is already supported by SGLang's Hierarchical KV Caching and vLLM's prefill serving. It is now integrated with LMCache…" The KEP makes Mooncake a **first-class role** in an RBG-deployed SGLang service, so the workload handles service discovery, startup ordering and lossless updates between the inference service and the external KV store.

**Measured benchmark from KEP-74** (two SGLang services, identical engine config and GPUs, one with Mooncake one without):

- Config: model **Qwen3-32B**, Mooncake TransferEngine **v0.3.6.post1**, SGLang **v0.5.3.post1**, **L3 cache = CPU RAM 30 GiB (3 × 10 GiB)**, tool `sglang.bench_serving`, 300 prompts, `--random-input 2048 --random-output 512 --random-range-ratio 0.5`, `--request-rate 10`, ShareGPT V3 dataset.

| Turn | Metric | Without Mooncake | With Mooncake | Delta |
|---|---|---|---|---|
| First turn | Total token throughput | 1300.41 | 1352.45 | ~flat |
| First turn | Mean TTFT (ms) | 4808.37 | 5016.66 | ~flat (slightly worse) |
| First turn | Mean ITL | 162.69 | 157.70 | ~flat |
| **Multi-turn** | **Total token throughput** | 1384.64 | **1935.69** | **+39.80%** |
| **Multi-turn** | **Mean TTFT (ms)** | 1172.21 | **94.50** | **−91.94%** |
| **Multi-turn** | **Mean ITL** | 139.95 | **57.62** | **−58.83%** |

The KEP also logs that **26.96 GiB of KVCache was offloaded to the Mooncake store** at measurement time (`Master Metrics: Storage:26.96 / 30.00 GB … | Keys: 219474`).

RBG otherwise has KEPs for warmup, EPD (encode-prefill-decode) disaggregation, pod port allocation, gang scheduling, in-place scheduling, network enhancement, and leader-only service — i.e. it is an **orchestration** project, not a KV-cache data-plane project. `keps/74-mooncake-integration` is its KV-cache contribution.

## 2.2 Ant Group's actual role: Mooncake + SGLang HiCache (verified with named engineers)

**Ant Group IS a verified contributor to the SGLang HiCache ↔ Mooncake integration.** The SGLang HiCache blog's acknowledgement section (<https://www.lmsys.org/blog/2025-09-10-sglang-hicache/>) states:

> "We are grateful to **Sicheng Pan, Zhangheng Huang, Yi Zhang, Jianxing Zhu, and Yifei Kang from the Alibaba Cloud TairKVCache team** for the 3FS backend integration; **Tingwei Huang and Yongke Zhao from Ant Group**; Teng Ma, Shangming Cai, and Xingyu Liu from Alibaba Cloud; Jinyang Su and Ke Yang from Approaching.AI; and Zuoyuan Zhang and Mingxing Zhang from the Mooncake community for their efforts on **Mooncake integration**; Moein Khazraee, Vishwanath Venkatesan, and the Dynamo team from NVIDIA for enabling the NIXL integration. … Finally, we appreciate the ongoing contributions from the LMCache, AIBrix, **PrisDB**, and **ByteDance EIC** teams in bringing their products into the ecosystem."

**Ant Group also contributed a production benchmark quote to the same blog** — this is the single most concrete Ant Group KV-cache number I found:

> "Effective KV caching significantly reduces TTFT by eliminating redundant and costly re-computation. Integrating SGLang HiCache with the Mooncake service enables scalable KV cache retention and high-performance access. In our evaluation, we tested the **DeepSeek-R1-671B** model under **PD-disaggregated deployment** using **in-house online requests sampled from a general QA scenario**. On average, **cache hits achieved an 84% reduction in TTFT** compared to full re-computation."
> — **Ant Group**

So: Ant Group's verifiable KV-cache contribution = (a) named engineers on the SGLang HiCache Mooncake backend, and (b) a production-shaped DeepSeek-R1-671B PD-disaggregated evaluation showing **−84% TTFT on cache hits**. That is a strong, citable result.

**Mooncake's `MAINTAINERS.md`** additionally lists **`ant_group_logo.png`** as a project contributor/partner, alongside Approaching AI, Huawei, NVIDIA, Moore Threads, Tencent, Volcengine, AMD, IEIT Systems, Sunrise, Hygon, Alibaba Cloud, MadSys, Moonshot and AWS.

### Mooncake codeownership (concrete, from `.github/CODEOWNERS`)

| Scope | Owners |
|---|---|
| LLM eco-system cooperation | @stmatengss (Teng Ma, **Alibaba Cloud**) |
| SGLang integration | @ShangmingCai (Shangming Cai, **Alibaba Cloud**) |
| Transfer Engine | @alogfans (Feng Ren, **9#AISoft**) |
| **Store** | **@ykwd (Ke Yang, yangke@approaching.ai, Approaching AI)** |
| EP / PG | @UNIDY2002 |
| `ascend_transport` | @alogfans, **@ascend-direct-dev** |
| `hip_transport` | @alogfans, @amd-arozanov (**AMD**) |
| `efa_transport` | @alogfans, @whn09 |
| `scripts/ascend/` | **@ascend-direct-dev**, @VNightMare, @MingYang119 |

`MAINTAINERS.md` "Primary Codeowner Contact" list: **Teng Ma (Alibaba Cloud, LLM Eco-System Cooperation)**, **Shangming Cai (Alibaba Cloud, SGLang Integration)**, **Feng Ren (9#AISoft, Mooncake Transfer Engine)**, **Ke Yang (Approaching AI, Mooncake Store)**.

## 2.3 Approaching.AI (趋境科技) — identity resolved

The brief listed "Ant Group / Approaching.AI" together. They are **separate organizations**.

**Approaching.AI = 趋境科技**, a Beijing startup founded **2024**, spun out of **Tsinghua University's Department of Computer Science and Technology, High-Performance Computing Institute**. Per the funding report (<https://zhidx.com/p/575150.html>, 2026-07-13):

- Chief scientific advisor: **郑纬民 (Zheng Weimin)**, academician of the Chinese Academy of Engineering; Chief scientist: **武永卫 (Wu Yongwei)**, Tsinghua professor; co-founder: **章明星 (Zhang Mingxing)**, Tsinghua CS associate professor; CEO 艾智远.
- Raised **>CNY 1 billion in half a year**; Series A announced 2026-07-13 led by 河南投资集团汇融基金. Self-reported: average per-machine AI-token production efficiency **up >3×** since Spring Festival 2026, total high-quality token capacity **up >30×**, and **daily trillion-token-scale** capacity projects in production; some business units already profitable.
- Technical offerings include **国产 Prefill-Decode 异构协同**, **高性能异构 KVCache 转换** (high-performance heterogeneous KVCache conversion), and **异构算力计算池化**.
- **Co-builds Mooncake** — verbatim: "与清华大学、月之暗面Kimi、9#AISoft、阿里云、**蚂蚁集团**等机构共建开源项目 Mooncake" (co-builds the Mooncake open-source project with Tsinghua, Moonshot Kimi, 9#AISoft, Alibaba Cloud, **Ant Group**, and others). **This is the direct textual evidence that Ant Group co-builds Mooncake.**
- Approaching.AI also leads **KTransformers** (see §2.4).

The `Approaching-AI` GitHub org itself is small and mostly edge/consumer inference: `AIMA` (★16, AI-Inference-Managed-by-AI edge manager), `AIMA-AMD395-Qwen36-35B-*` engines, `mate` ("MUSA AI Tensor Engine", ★0). ❌ **COULD NOT VERIFY** any large KV-cache repository under the `Approaching-AI` org. Their KV-cache footprint is expressed through **`kvcache-ai`** (Mooncake Store, KTransformers) rather than through their own org.

## 2.4 `kvcache-ai` org — the actual Mooncake/KTransformers home

| Repo | ★ | Last push | Note |
|---|---|---|---|
| `kvcache-ai/ktransformers` | **19 518** | 2026-09-15 | Apache-2.0, 1572 forks; "A Flexible Framework for Experiencing Heterogeneous LLM Inference/Fine-tune Optimizations". Releases: **v0.7.1 (2026-09-15)**, v0.7.0.post4 (2026-09-13), v0.7.0 (2026-08-17), v0.6.4 (2026-07-23) |
| `kvcache-ai/Mooncake` | **6576** | 2026-09-15 | see above |
| `kvcache-ai/AgentENV` | 3469 | 2026-09-15 | |
| `kvcache-ai/kvcache-blog` | 27 | 2026-09-15 | |
| `kvcache-ai/sglang-npu` | 0 | 2025-08-12 | stale |
| `kvcache-ai/vllm` | 19 | 2026-09-07 | fork |

## 2.5 Mooncake — mechanism, and its integration surface

`kvcache-ai/Mooncake`: 6575★/1221 forks, **Apache-2.0**, C++, created 2024-06-25, last push 2026-09-15, homepage <https://kvcache-ai.github.io/Mooncake/>. Latest releases: **v0.3.13 (2026-08-26)**, v0.3.13.post1 (2026-08-31), **v0.3.14-rc1 (2026-09-07, prerelease)**, v0.3.12.post1 (2026-07-25).

- **Paper**: FAST'25, <https://www.usenix.org/system/files/fast25-qin.pdf> — "Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving" (Qin et al.). Traces released under `FAST25-release/traces`.
- **Headline production claim (README)**: "Under real workloads, Mooncake's innovative architecture enables **Kimi to handle 75% more requests** while adhering to SLOs."
- **Architecture** (docs/source/design/architecture.md): builds a multi-level cache pool over high-speed interconnected DRAM/SSD; uses **(GPUDirect) RDMA zero-copy** transfer from initiator DRAM/VRAM to target DRAM/VRAM, maximizing multi-NIC use. Provides object-level `Get/Put/List/Del` + dynamic `Replicate`; supports **replication with slice-level placement guarantees**, **striping and parallel I/O** for large objects to use aggregated multi-NIC bandwidth, atomic single-version `Get` semantics, dynamic add/remove of cache resources. A **master node** centrally manages object→VRAM/DRAM/NVM mappings and drives managed pool buffer nodes through Transfer Engine APIs.
- **Transport backends shipped** (PyPI wheel matrix in README): CUDA ≤12.9, CUDA 13.0/13.1, **non-CUDA**, **NPU**, **MUSA** (Moore Threads), **EFA** (AWS), **ROCm** (AMD). Plus `ascend_transport`, `hip_transport`, `efa_transport` in-tree.
- **Integrations (from README updates)**: SGLang HiCache (2025-09-10), vLLM v1 KV Connector (2025-12-19), TensorRT-LLM `mooncake_utils` for PD-disaggregated KV transfer (2025-12-19), **vLLM Ascend as distributed KV cache pool backend (2025-09-18)**, RBG (2025-11-07), checkpoints-engine (2025-09-10), xLLM (2025-08-23), FlexKV distributed reuse (2026-01-28), LMCache, lmdeploy, vLLM-Omni, SGLang EPD.
- **Non-KV but notable**: vLLM official blog on Mooncake Store (2026-05-07, <https://vllm.ai/blog/mooncake-store>); **SGLang RDMA P2P weight transfer achieving 7× faster weight updates for 1T-param Kimi-K2 (53s → 7.2s)** across thousands of GPUs (2026-04-29); Mooncake joined the **PyTorch Ecosystem** (2026-02-12).

## 2.6 SGLang HiCache — the plug-in surface that all these vendors target

`python/sglang/srt/mem_cache/storage/backend_factory.py` registers exactly these built-in backends:

| Backend name | Module | Class |
|---|---|---|
| `file` | `hicache_storage` | `HiCacheFile` |
| `sim` | `storage.sim_storage` | `SimHiCacheStorage` |
| `nixl` | `storage.nixl.hicache_nixl` | `HiCacheNixl` |
| `mooncake` | `storage.mooncake_store.mooncake_store` | `MooncakeStore` |
| `npu_memcache` | `storage.npu_memcache.npu_memcache_store` | `NpuMemcacheStore` |
| `hf3fs` | `storage.hf3fs.storage_hf3fs` | `HiCacheHF3FS` |
| `aibrix` | `storage.aibrix_kvcache.aibrix_kvcache_storage` | `AibrixKVCacheStorage` |
| **`eic`** | `storage.eic.eic_storage` | **`EICStorage`** |
| `simm` | `storage.simm.hicache_simm` | `HiCacheSiMM` |
| `mori` | `storage.umbp.umbp_store` | `UMBPStore` |
| `shm` | `storage.shm` | `HiCacheShm` |

The authoritative list is the **`choices` array in `python/sglang/srt/arg_groups/fields/memory.py`**: **`file, sim, mooncake, npu_memcache, hf3fs, nixl, aibrix, dynamic, eic, simm, mori, shm`** — i.e. **12 values = 11 concrete built-in backends + `dynamic`**. `backend_factory.py` contains **12** `register_backend(` occurrences, **one of which is the method definition**, giving **11 registrations** — consistent.

> ⚠️ **Correction to an earlier draft of this document**, which said "13 directories / 11 registered". The `storage/` directory does contain **14** sub-directories (`aibrix_kvcache, eic, file, flexkv, hf3fs, lmcache, mmap, mooncake_store, nixl, npu_memcache, shm, sim_storage, simm, umbp`) — but **directory count ≠ registered-backend count**. `flexkv`, `lmcache` and `mmap` are **not** in the `choices` array. The safe statement is **11 concrete built-ins + `dynamic`**.

- **ByteDance-related backends: exactly two** — **`eic`** (direct, Volcengine) and **`aibrix`** (indirect: it fronts InfiniStore / PrisKV / EIC). Everything else is generic or third-party: `mooncake` = Moonshot, `nixl` = NVIDIA, `hf3fs` = DeepSeek, `simm` = external contributor.
- ⚠️ **Documentation defect worth knowing**: the `help=` string on that CLI arg still reads only *"Built-in backends: file, mooncake, npu_memcache, hf3fs, nixl, aibrix"* — it was **never updated** for `eic`, `simm`, `mori`, `shm` or `sim`. So **`--help` hides the ByteDance backend**, a practical reason a reader might miss it.

**HiCache mechanism and numbers** (from the blog):
- Extends RadixAttention with a **HiRadixTree** acting as a page table referencing KV caches in GPU and CPU memory, plus a cache controller managing load/backup across GPU, CPU, disks and remote memory.
- **Data-plane optimization**: the host memory pool's layout is **decoupled** from the GPU layout. GPU stays "layer-first" for kernel compatibility; other layers use **"page-first"** to prioritize I/O efficiency. This enables larger transfer sizes per transaction and, combined with zero-copy, "**achieves up to 2× higher throughput** in typical deployments".
- **Write policies**: `write_through`, `write_through_selective` (uses hit-count tracking to back up only hot spots), `write_back`.
- **Backend contract**: implement only `get(key)`, `exist(key)`, `set(key, value)`.
- **SGLang's own measured results**: "**up to 6× throughput improvement and up to 80% reduction in TTFT**".
- **Third-party quote in the blog — Novita AI**: "In a coding agent scenario using **Qwen3-Coder-480B**, the observed dialogues often stretched past **25K tokens around 8 turns per session**… By integrating SGLang HiCache with **DeepSeek 3FS KVStore**… the session's **average TTFT dropped by 56%**, **inference throughput doubled**, and the **cache hit rate jumped from 40% to 80%**."

## 2.7 Alibaba Cloud's contribution to HiCache (the 3FS backend)

Directly attributable from the blog acknowledgement: **Sicheng Pan, Zhangheng Huang, Yi Zhang, Jianxing Zhu, Yifei Kang from the Alibaba Cloud TairKVCache team** did the **3FS backend integration**. This is the concrete Alibaba↔SGLang HiCache link, complementing the Tair KVCM work in §1.

---

# 3. Tencent — FlexKV, KsanaLLM, TurboTransformers

## 3.1 FlexKV — the deepest Tencent KV-cache system

`https://github.com/taco-project/FlexKV` — **351★ / 73 forks**, 32 open issues, 7 watchers, language **Python** (with a C++ core), created **2025-07-02**, last push **2026-09-15T11:52:38Z**. License: the API reports `NOASSERTION`, but the repo's `LICENSE` file reads: **"flexKV is licensed under the Apache-2.0 license except for the third-party components listed below."** So: **Apache-2.0 with third-party notices**.

Commits: **~636** (GitHub `Link: … page=636` on `per_page=1`). Tags: **v1.2.1, v1.2.0, v1.1.0, v1.0.0, v0.1.0** — but ❌ **there are no GitHub Release objects** (`/releases` returns an empty array), so there is no published release date for v1.2.1. `v1.2.0` tag → commit date **2025-11-28T06:54:53Z**. (Tag→commit resolution for v1.2.1/v1.1.0/v1.0.0/v0.1.0 returned HTTP 422 "No commit found" — annotated-tag objects would need a second dereference; treating those dates as unverified.)

**Maintainership**: "developed by **Tencent Cloud's TACO team** in collaboration with the community" (README). Mooncake's README independently describes it as "a distributed KV store and cache system from **Tencent and NVIDIA** in collaboration with the community". Contributor evidence supports the NVIDIA part directly:

| Contributor | Contributions | Note |
|---|---|---|
| `zhuofan1123` | 193 | Tencent (presumed lead) |
| **`linhu-nv`** | 117 | **NVIDIA** (`-nv` suffix) |
| `peaceforeverCN` | 62 | |
| `charliecgxu` | 31 | |
| **`wenpengw-nv`** | 19 | **NVIDIA** |
| `Luis-xu` 16, `axxx03` 13, `XingLiu1` 11, `zhjc1124` 11, `gz944367214` 10, `xianweihuihuan` 9, `staryxchen` 6, `Claisenn` 5, `feiqiangs` 5, `jianyingzhu` 4 | | |

### Architecture (from README)

Three core modules:

1. **StorageEngine** — initializes the multi-level cache. Groups multiple tokens per request into a **block**, stores KV at block granularity, **maintaining the same KV shape as GPU memory**; the actual storage offset is computed from block ID. Supports **block-wise mode**, merging caches across multiple layers and KV components into larger blocks to increase I/O size and speed up transfer.
2. **GlobalCacheEngine** — the **control plane**. Contains a **RadixTree** for prefix matching (`match`/`insert`) and a **memory pool** tracking space usage and triggering eviction. On a new request it compares matched-token counts across the three storage levels and decides which blocks to fetch and from where, then moves them through CPU memory to GPU.
3. **TransferEngine** — the **data plane**. Multi-threaded per-process parallel transfers; uses **io_uring** for high-performance I/O.

### Cache tiers, transport, eviction

- **Three-tier external cache below the GPU** (per the README "Three-Tiered Caching"): **CPU memory** (L1 external), **local SSD** (L2 persistent), **scalable storage** such as cloud storage (L3 distributed, cross-node sharing). The Tencent marketing article describes this as a **four-level GPU → CPU → SSD → remote** hierarchy. Note the internal inconsistency: "three-tier" counts only the *external* tiers below GPU, while "four-level" includes GPU HBM. Both descriptions are from Tencent sources.
- **Transport**: **Mooncake Transfer Engine** (RDMA-based) for cross-node; **GPU Direct Storage (GDS)** for direct SSD↔GPU without CPU involvement (added Dec 2025, PR #25); **io_uring** for host/SSD I/O; adaptive multi-path GPU↔CPU transfers (PR #203, Jul–Aug 2026); **HugePage-backed host cache** (Jun 2026).
- **Eviction** (from `docs/eviction_policy/README_en.md`): FlexKV evicts from **that tier's Radix Tree** when a tier runs low on space or crosses a utilization threshold. Policies: **`lru` (default), `lfu`, `slru`, `fifo`, `mru`, `filo`**. Multi-level cache is **approximately inclusive / write-through**: on `put`, data goes to CPU first, then missing blocks are also filled into SSD/remote when enabled and available; **eviction in one tier does not trigger write-back or migration** to a lower tier. Note the inclusion property is explicitly **best-effort**. Relevant tuning knobs (env var / config): `evict_start_threshold` (default **0.7** — proactive eviction starts at 70% full), `evict_ratio` (default **0.05** — at least 5% of blocks evicted per round), `hit_reward_seconds` (**LRU only** — each hit adds N seconds to a node's effective access time, a frequency-aware grace mechanism), `slru_protected_threshold` (default **2** — hit count promoting a node to the protected segment).
- **"logical LRU eviction without triggering physical data movement"** is an explicit design claim in the README.
- **Asynchronous API**: `get` can be asynchronous so match + transfer overlap with prior computation via prefetching; `put` can be asynchronous so GPU→CPU copy overlaps with subsequent computation. CPU↔SSD↔remote transfers are fully async and transparent to the main process.
- **Distributed KVCache reuse** (`docs/dist_reuse/README_en.md`): a **Distributed RadixTree** where **each node keeps a local snapshot of the global index**, avoiding a centralized bottleneck and network round-trips on query; a **lease mechanism** guarantees data validity during cross-node transfer; **upload & rebuild** — local indexes are periodically uploaded to a **Global Meta Store (GMS, typically a Redis service)** and distributed indexes rebuilt by pulling metadata from peers. Uses **Mooncake Transfer Engine** for the actual cross-node data movement. The Tencent article claims this "规避了单点性能瓶颈、网络延迟瓶颈和单点故障问题" versus centralized indexing, and that the design is peer-to-peer ("无需中心化组件即可完成高效访问与同步") — note this sits alongside the Redis GMS, so "no centralized component" refers to the *data path*, not metadata.
- **Monitoring**: Prometheus integration across Python and C++ layers, zero-intrusion via `FLEXKV_ENABLE_METRICS=1`, exposing cache hit/miss, memory-pool status and transfer stats over HTTP; `docs/monitoring/README_en.md` covers the Prometheus + Grafana stack.
- **DeepSeek-V4 support** (Jul 21 2026, PR #225): "heterogeneous **C4/C128/indexer KV groups**, **FullKV + SWA dual caches**, attention/indexer **compress-state sidecars**, and **layerwise restore**". This is notable because it means FlexKV models *heterogeneous per-layer KV layouts* (sliding-window attention + full attention + indexer state) as first-class objects.
- **NVFP4**: byte-exact NVFP4 KV-cache offload and reload for vLLM on Blackwell GPUs (Jul 7 2026, PR #204).
- **API history**: Nov 2025 FlexKV moved from a client-server model to a **directly-callable library** (commit `0290841`), "eliminating inter-process communication overhead. This is the v1.0.0 API."

### Integration points and adoption (all verified from README + PR links)

| Target | How | Date / reference |
|---|---|---|
| **vLLM** | Merged to mainline, PR **[vllm#34328](https://github.com/vllm-project/vllm/pull/34328)**; **`FlexKVConnectorV1` built in from vLLM v0.17.2**, no patch required | README states Mar 17 2026; the Tencent press release says the vLLM merge was **2026-03-12** (minor conflict, both cited). Cross-check: v0.17.2 is a plausible historical version — vLLM is at **v0.29.0 (2026-09-09)** with **91 816★ / 22 221 forks**, so a v0.17.x baseline ~6 months earlier is consistent |
| **NVIDIA Dynamo** | Merged PR **[ai-dynamo/dynamo#5858](https://github.com/ai-dynamo/dynamo/pull/5858)** — FlexKV is a **native KV Cache Offloading option in Dynamo**, enabling "KV-aware routing + multi-level cache offloading in a unified pipeline" | README: Mar 3 2026; press release: **2026-03-03** |
| **TensorRT-LLM** | PR #48; TP16 support PR #53 | Jan 2026; press release says the TRT-LLM merge was **2026-03-28** |
| **SGLang** | Connector merged to SGLang mainline, PR **[sglang#29701](https://github.com/sgl-project/sglang/pull/29701)** — "native CPU/SSD KV-cache offloading through **`--enable-flexkv`**"; available in upstream SGLang **v0.5.16+**, no patch required. DeepSeek-V4 adaptation needs PR [sglang#31781](https://github.com/sgl-project/sglang/pull/31781) pinned to commit `ee0465a` | README: Jul 7 2026 |
| **Mooncake Store as remote tier** | PR #231 — Mooncake Store serves as FlexKV's **key-addressed remote cache tier**, "enabling cluster-wide KV reuse with **zero-copy RDMA** and support for DeepSeek-V4 SWA/state sidecars" | README: Jul 24 2026 |
| TP16 on vLLM and TRT-LLM | PRs #53, #59 | Jan 2026 |
| Pipeline Parallel support | commit `1a91e7f` | Jun 24 2026 |

The press release claims this is "行业内首个实现请求路由 - 缓存管理全链路协同的生产级优化方案" (the industry's first production-grade solution achieving full-chain request-routing + cache-management coordination).

### FlexKV measured numbers

**From the Tencent Cloud developer article** (<https://cloud.tencent.cn/developer/article/2654280>) and the matching press release (<https://www.donews.com/news/detail/4/6512672.html>):

| Claim | Exact figure |
|---|---|
| Cache capacity extension | **">100×"** the GPU VRAM ("可用缓存容量最高可扩展至 GPU 显存的 100 倍以上"; "扩展至 GPU 显存的100倍以上"); "可挂载**PB级别**的远端存储" |
| TTFT | **"首Token延迟 (TTFT) 降低约60%"** |
| TPOT | **"单Token延迟 (TPOT) 降低13%"** |
| QPM | **"单集群每分钟请求处理量 (QPM) 提升16%"** |
| Industry context cited | In high-concurrency scenarios **">70% of GPU VRAM"** is occupied by KV Cache; per NVIDIA's estimate, clusters without KV-cache offload see per-token cost rise **2–3×** from recomputation, peaking at **3.5×** |
| Anecdotal customer economics | For a mid-size enterprise AI customer-service cluster, KV-cache VRAM pressure + eviction-driven extra cost = **78% of monthly total operating cost**; for a typical large internet company, recomputation compute cost from cache eviction **>5% of hardware procurement cost** |

> ⚠️ The 60%/13%/16% FlexKV figures are from a **vendor press release / marketing article**; no model, hardware, concurrency, or workload is specified, and no benchmark script is published for them. By contrast, the **RBG KEP-74 numbers are reproducible** (exact configs and script given) but they benchmark *Mooncake*, not FlexKV. Treat FlexKV's headline trio as a vendor claim.
>
> Separately, the press release contains a factual inconsistency: it says vLLM code was merged "2026年3月12日" while the FlexKV README says Mar 17 2026. Both are cited rather than reconciled.

### FlexKV roadmap (README)

In-process cache engine integration (dev branch); deepen native vLLM/SGLang/TRT-LLM integrations; **distributed query support** for scalable distributed KVCache lookup; latency optimization via smarter prefetching and compression.

## 3.2 Tencent KsanaLLM

`https://github.com/Tencent/KsanaLLM` — **550★ / 46 forks**, 14 open issues, 16 watchers, language **C++**, created **2024-05-22**, last push **2026-08-27T08:11:19Z**. License: `NOASSERTION` (Tencent's own license). ❌ **No tags and no releases at all.**

Contributors: `ksanallm` (1189 — an org/bot account), then `pcg-mlp` (8), `whitelok` (4), and single-digit contributors. **Note: the commit history is dominated by one account**, which suggests a periodic bulk-export/sync workflow rather than normal open development.

KV-cache-relevant features (from README):

- **PagedAttention** for KV memory management (citing the vLLM paper, arXiv 2309.06180).
- **Prefix caching support** (listed as a headline feature).
- **PD disaggregation** with `backend: "v2"` (explicitly "the v2 version of PD disaggregation") in the runtime config.
- **FP8 E4M3 KV Cache quantization** with mandatory scaling factors ("When enabling FP8 E4M3 KV Cache quantization, it is necessary to provide scaling factors to ensure inference accuracy") — config section "6.3 KV Cache Scaling Factors".
- `MASTER_OFFLOAD_LAYER_NUM` environment variable in the deployment config (layer-wise offload control).
- **Global Cache Connector (Mooncake Store backend)** — the most significant KV-cache feature. README §3.5: "Global Cache Connector enables **RDMA-based global KV cache access using Mooncake Store as the storage backend**."
  - Requires building **Mooncake v0.3.9** — and CMake **verifies the git tag and errors on mismatch** (`MOONCAKE_SOURCE_ROOT` "Must be checked out at tag `v0.3.9`").
  - Build flags: `-DUSE_MOONCAKE_REAL_STORE=ON`, `-DMOONCAKE_SOURCE_ROOT=…`, optional `-DMOONCAKE_BUILD_ROOT=…`. Default `OFF` uses a **mock backend**. Produces `libglobal_cache_connector.so`, which can also be built standalone from `csrc/global_cache_connector/`.
  - Runtime: `export ENABLE_GLOBAL_CACHE_HOOK=1`; with the hook on, serving **auto-starts a local `mooncake_master`** if the RPC port is free. Configure `setting.global_cache_connector.service_endpoint` (empty → connector disabled); require event-driven scheduler `setting.batch_scheduler.scheduler_type: 1`; keep `service_endpoint`/`master_server_addr` ports consistent (defaults **8080** / **50051**).
- **Hardware support**: NVIDIA (A10, A100, L40, L20, H20), **Huawei Ascend NPU 910B2C**, **Kunlunxin XPU P800** (Baidu's chip). The README also mentions testing on "A10, A100, L20, L40, H20, 910B2C".
- **Models verified**: LLaMA 7B/13B, LLaMA-2 7B/13B, LLaMA3 8B/70B, Baichuan1/2 7B/13B, Qwen 7B/14B, Qwen1.5 7B/14B/72B/110B, Qwen-VL, Yi1.5-34B, **DeepSeek V3/R1**.
- Tencent-internal integration: `-DWITH_INTERNAL_LIBRARIES=ON` to use **Tencent's internal nameserver Polaris** — i.e. this engine is wired into Tencent's internal service discovery, a production-deployment signal (the build flag is `WITH_INTERNAL_LIBRARIES`; the internal libs themselves are not public).

> ⚠️ KsanaLLM publishes **no benchmark numbers** for its prefix cache or Global Cache Connector that I could find. ❌ Nothing quantitative verified.

## 3.3 Tencent TurboTransformers and AngelPTM

`Tencent/TurboTransformers` — 1551★ / 208 forks, created **2020-04-20**, last push **2025-07-18** (effectively unmaintained), license `NOASSERTION`, description "a fast and user-friendly runtime for transformer inference (Bert, Albert, GPT2, Decoders, etc) on CPU and GPU". ❌ **Grep of its README finds no KV-cache, prefix-cache or paged-KV content** — it is a 2020-era transformer runtime. **Not relevant to KV-cache management.** Treat any suggestion otherwise as unverified.

`Tencent/AngelPTM` — ❌ **does not exist.** The GitHub API returns HTTP 404 for `repos/Tencent/AngelPTM`. (There is a Tencent `Angel` project, but I could not verify an `AngelPTM` repository.) Flagging as an invalid premise in the brief.

---

# 4. ByteDance

> **Provenance.** This section merges my own primary-source research with a dedicated deep-dive pass whose full notes are at **`kvcache-research/raw/bytedance.md`** (714 lines, 75-entry source list). The deep-dive pass contributed the decisive negative results (especially: **EIC is not open source**) and the ByteDance-Seed KV-cache research inventory.

**Two premises in the brief resolve as follows:**
1. **"ByteDance EIC" is real and fully identified** — **EIC = Elastic Instant Cache (弹性极速缓存)**, a **commercial, closed-source** distributed KV-cache product of **Volcengine (火山引擎)**, ByteDance's cloud, built by the **Volcengine Storage Team**. It reached SGLang as an in-tree HiCache backend.
2. **"ByteDance KVCache" as a project name does not exist.** A GitHub repo search for `kvcache` across **419 `bytedance` repos, 208 `volcengine` repos and 63 `ByteDance-Seed` repos returned zero results.** Do not cite a "ByteDance KVCache" project.

## 4.1 EIC = Elastic Instant Cache (Volcengine / ByteDance) — identified, and **NOT open source**

**Primary source — the SGLang HiCache storage backend README** (`python/sglang/srt/mem_cache/storage/eic/README.md`), quoted verbatim:

> "**EIC(Elastic Instant Cache)** is a distributed database designed for LLM KV Cache. It supports **RDMA, GDR** and has the capabilities of **distributed disaster tolerance and expansion**."

Deployment is via the **Volcengine console at `https://console.volcengine.com/eic`**, with official docs at **`https://www.volcengine.com/docs/85848/1749188`** (Volcengine doc library **85848** is titled 弹性极速缓存 — the confirming match). Enabling it in SGLang:

```bash
python -m sglang.launch_server \
    --model-path [model_path] \
    --enable-hierarchical-cache --hicache-storage-backend eic \
    --hicache-write-policy 'write_through' --hicache-mem-layout 'page_first'
```

### ⚠️ CRITICAL FLAG: EIC is a paid closed-source service, not an open-source system

- **PyPI packages `eic`, `eic-client` and `volcengine-eic` all return HTTP 404.** No repository named `eic` or `kvcache` exists in any ByteDance or Volcengine GitHub org.
- Deployment **requires the Volcengine console**. The SGLang and LMCache backends are **client shims for a commercial service**, not an open-source store.
- **Any report describing EIC as an open-source KV-cache system is wrong.** The *integration code* is Apache-2.0 (in SGLang and LMCache); the *system* is proprietary.
- Its own articles state EIC was developed **"基于自身业务内部加速需求自主研发…历经 4 年技术沉淀"** and already serves ByteDance-internal **storage, inference and ad-recommendation** workloads at scale.
- The Volcengine product doc body is **unextractable**: all `volcengine.com/docs/85848/*` pages return an ~11 KB JS shell, and the docs content API returns `未授权访问` (UnauthorizedAccess). So **EIC's capacity, latency, pricing and regional availability remain unverified** from vendor docs.

### Contribution and integration evidence (verified from PRs)

| Evidence | Detail |
|---|---|
| **SGLang PR [#10271](https://github.com/sgl-project/sglang/pull/10271)** | "[Feature] Add EIC as sglang HiCache Storage backend" — opened **2025-09-10** by user **`mss1213`**, **merged 2025-10-01T13:43:34Z**, **+927 / −2 across 6 files** |
| Reviewer comment on that PR | titled **"Introduction to Volcano Engine EIC KVCache"** (user `rzwei`) — the explicit **ByteDance → Volcengine** bridge |
| **LMCache `eic://` connector** | PR **#1930** by `Leafykn`, opened 2025-10-31, **merged 2025-11-21**; files `lmcache/v1/storage_backend/connector/eic_connector.py`, `eic_adapter.py` (registers the `eic://` scheme), `tests/v1/storage_backend/test_eic.py`; configured as `remote_url: "eic://your-eic-endpoint"` |
| Merged SGLang code | `eic_storage.py` (**778 lines**), registered as a **built-in** backend in `backend_factory.py` alongside `file/nixl/mooncake/aibrix/hf3fs/simm/mori` |

**What the merged backend reveals about EIC's design** (from `eic_storage.py`):
- Supports both **`page_first`** (zero-copy) and **`layer_first`** memory layouts.
- **MLA load-balanced transfer**.
- **Multi-NIC / RDMA** support.
- **Namespace + TTL eviction**.
- Contains a **hard-coded H20 GPU↔NIC affinity table** for 8 GPUs (`cuda:0/1 → eth1`, `cuda:2/3 → eth2`, `cuda:4/5 → eth3`, `cuda:6/7 → eth4`) plus a CPU-affinity map — strong evidence the integration was written against **one specific production cluster topology**.

### EIC design (from the two Volcengine Storage-team WeChat articles)

A: "推理加速新范式：火山引擎高性能分布式 KVCache （EIC）核心技术解读" — <https://mp.weixin.qq.com/s/tasDqXf0Gxr3o_WCJ2IJUQ>
B: "火山引擎 EIC 解析：构建以 KVCache 为中心的推理新基建" — <https://mp.weixin.qq.com/s/b_4YhTa96Zeklh23lv8qBw>

- **Tiers**: "支持将**内存和 SSD** 组成一个分布式服务"; "支持 **GPU-本地缓存-分布式缓存(RAM+SSD)** 等多层级缓存". Can run **co-located with GPUs**, pooling "GPU 剩余显存、内存和磁盘".
- **Transports**: "支持**内核态TCP、用户态TCP、RDMA 及 GPU Direct RDMA** 访问". **GDR achieves full-chain zero-copy**; per the article's figure 7, latency "可以达到 TCP 或 RDMA 的**十分之一**".
- **Topology awareness**: GPU↔NIC topology affinity mapped to NUMA ("Mem0 利用 R0 网卡和 R1 网卡发送延迟更低，GPU0 利用 R0 网卡发送延迟更低"); result **single machine easily exceeds 100 GB/s**.
- **Eviction / data flow**: TTL, **LRU/ARC/FIFO**.
- **Persistence**: survives process failure and online hot upgrade — "写入内存缓存不丢失，支持**毫秒级快速恢复**"; supports **Hugepage, NUMA-aware, full-chain zero-copy, JumboFrame**.
- **Hot-spot management**: hot-cache identification plus **automatic replica scaling and lifecycle management**, with multi-replica load balancing.
- **Namespace isolation**: per-Namespace medium selection (memory / SSD / mixed), data-flow & eviction policy, **space quota**, **QoS (IOPS + bandwidth)**, and observability (throughput / latency / **hit rate** / cache count / capacity). Uses: model isolation, model-version switching (old-version KV auto-invalidated), and isolating **model-load bandwidth from KVCache bandwidth** via weighted fair queuing.
- **KV Cache integration design**: EIC notes **SGLang's own HiCache only supports single-machine CPU offload**, so "EIC 扩展了 SGLang 能力，支持了外部 KVCache，并通过**计算前缀 hash** 的方法来支持多推理实例间共享". For vLLM it uses the **KV Transfer Connector** path. Stated invariant across engines: "**Swap Out**（从 GPU KVCache 到 remote KVCache）需以**异步**方式执行…**Swap In**（从 remote KVCache 到 GPU KVCache）则为**同步**操作，且最迟需在计算前完成 IO."
- **Frameworks adapted**: **vLLM, SGLang, and NVIDIA Dynamo** — "已完成对 vLLM、SGLang 以及 Dynamo 等推理框架的适配，并将其集成至火山引擎 AI 相关重要业务中".

### EIC numbers (exact; ALL self-reported by the vendor — no independent verification)

| Claim | Exact figure |
|---|---|
| Multi-turn recomputation pressure | 8K tokens/round, after **6 rounds**, historical-token recomputation exceeds **80%** of input |
| KV memory pressure | LLaMA-70B on **H20**: **1.6 GB of KV per 1K tokens**; prefill exceeds the memory threshold within **20 minutes** |
| Memory-wall effect | LLaMA-70B long-context: token throughput **drops 70%** past single-machine memory |
| Storage pool scale | **10 PB-scale** pool; **cache hit rate up >10×** |
| Per-client throughput | **100 GB-class** KV throughput per client with **sub-millisecond** response |
| Inference throughput | Round 1 (no reuse) parity; **from round 2: 1.5K → 5.5K, a 3×+ gain** |
| TTFT | Round 2 onward **latency → 1 s, −67%** |
| Long-text + PD sharing | throughput **3×**, **TTFT −67%** |
| Multi-turn serving test (**2 × H20-96G, SGLang + DeepSeek-R1**, TTFT SLO 5 s, 8K in / 200 out) | throughput **3×+** from round 2; latency reduced **to 67%** (−33%) |
| Model load, DeepSeek-R1 (**642 GB**) on H20 | **546 s (NVMe SSD baseline) → 13 s** = **42× faster** |
| Model load, DeepSeek-R1-Distill-Llama-70B (**131 GB**) | **84 s → 5 s** = **16× faster** |
| Single-machine read bandwidth | **>100 GB/s** with multi-NIC + topology affinity |
| Write overhead inside SGLang | "写开销始终控制在 **5% 以内**" |
| AI-coding-agent case (SGLang + DeepSeek-V3, avg input 30k, output 1k–2k, 2× H20 96G) | peak read throughput **50 GB/s**; at 1088 KB per KVCache entry = **48,188.23 tokens/s** of reuse |
| 2000-request A/B (pure GPU vs EIC+GPU) | total runtime **4232 s → 2065 s** (−51%); per-metric gains **30%–70%** |
| 100-node rolling restart | **200/400/800 GB/s** vs **≥10 min/restart on NVMe** |
| QPS economics (DeepSeek-R1, TP=16, 8000/200 tokens, TTFT ≤2 s) | **2× H20 ≈ 3K QPS**; 30K QPS would need **20× H20**; with 3× KV-reuse uplift, 30K QPS needs only **10** machines |
| Cold-start cost of the status quo | DeepSeek R1 FP8 = **700 GB**; at 400 MBps/TiB density, cold pull ≈ **30 minutes** |

⚠️ Articles A and B are **vendor marketing articles with image-only charts** (图1–图12) that I could not read; baseline models/harnesses are not fully specified beyond "同算力条件下". **Treat all throughput/TTFT triples as vendor claims.** The model-load numbers (642 GB: 546 s → 13 s) and the bandwidth figures are concrete and mechanically plausible, but still single-source.
⚠️ **ByteDance/Volcengine employment of `mss1213` and `rzwei` is INFERRED, not confirmed** — neither GitHub profile lists a company. The ByteDance→Volcengine attribution rests on the reviewer comment title, the Volcengine console/docs links in the merged README, and the 4-year internal-development statement.

## 4.2 ByteDance-Seed KV-cache research (peer-reviewed, a separate track from serving infra)

ByteDance's **research** arm publishes genuine KV-cache work — distinct from EIC/InfiniStore on the serving side. All repo metrics read 2026-09-15.

| Repo | ★ / forks | License | Last push | Note |
|---|---|---|---|---|
| [`ByteDance-Seed/ShadowKV`](https://github.com/ByteDance-Seed/ShadowKV) | **313 / 26** | **Apache-2.0** | 2025-05-01 | **[ICML 2025 Spotlight]**. Created 2024-10-22. No releases. Homepage <https://ByteDance-Seed.github.io/ShadowKV/> |

⚠️ Provenance detail: the ShadowKV README's "code available at" line links to `github.com/bytedance/ShadowKV`, which **redirects** to `ByteDance-Seed/ShadowKV` — the project appears under both orgs.

**Verified papers** (arXiv abstract pages read; numbers quoted verbatim from the sources):

| Paper | Venue / arXiv | KV-cache-relevant result |
|---|---|---|
| **ShadowKV** | **ICML 2025 Spotlight**; arXiv **2410.21465** (v1 2024-10-28) | CMU + ByteDance Seed. Low-rank **key** cache + **value-cache offload**. "comparable performance to full attention on LongBench with only **6.25%** of the KV cache"; "maintains **100% accuracy** at a **50K** context length while using as little as **0.26%** of the cache" in Needle-in-a-Haystack. Earlier version reported **up to 6× larger batch** and **3.04× throughput on A100** |
| **MegaScale-Infer** | **ACM SIGCOMM 2025**; arXiv **2504.02263** (v4 2025-07-26); DOI 10.1145/3718958.3750506 | attention/FFN **disaggregation** for MoE, ping-pong pipeline parallelism, M2N comm library; **up to 1.90× per-GPU throughput**. KV-relevant as a *disaggregated serving* architecture |
| **MixedDimKV** | arXiv **2603.20616** (Seed portal date 2026-03-21) | "Beyond Token Eviction…" — LongBench parity with **6.25%** of the KV cache; NIAH **100% at 50K** with **0.26%** |
| **SwiftSpec** | **ASPLOS'26**; arXiv **2506.11309** | **1.75×** vs SOTA speculative decoding; **Llama3-70B at 348 tok/s on 8 Hopper**; proposes **tree-aware KV cache management** |
| **FlexPrefill** | **ICLR 2025 Oral (1.77%)**; arXiv **2502.20766** | context-aware **sparse prefill attention** |
| **AHN** | arXiv **2510.07318** (v1 2025-10-08) | 32k sliding-window KV cache + fixed-size compressed long-term memory (Mamba2 / DeltaNet / GatedDeltaNet). No public repo found |
| **Charon** | Seed, 2026-05-16 | Simulator; prediction error **<5.35%** (training **<3.74%**) — directly comparable to Tair HiSim's <5% claim. ⚠️ **arXiv ID not captured** |

⚠️ **KVDirect (arXiv 2501.14743)** — ByteDance affiliation could **NOT** be verified. **Do not attribute it.**
⚠️ A useful technique if anyone reproduces this: `seed.bytedance.com/api/get_article_list_v2?...&work_team_id=261` and `seed.bytedance.com/en/public_papers?...&research_area_id=91` return **server-rendered** listings that the SPA otherwise hides — but the API **paginates incorrectly from outside** (reports total 24, returns 2).
⚠️ `bytedance/ByteMLPerf` was **renamed to `bytedance/xpu-perf`** (383★, HPCA 2026 accelerator benchmark) — it is a **hardware benchmark, not a KV-cache system**.

## 4.3 `bytedance/InfiniStore` — the verified open-source ByteDance KV store

| Field | Value |
|---|---|
| Repo | <https://github.com/bytedance/InfiniStore> |
| Description | **"KV cache store for distributed LLM inference"** |
| Stars / forks | **438 / 44** |
| License | **Apache-2.0** |
| Created | **2024-09-06** |
| Last push | **2025-11-13** (⚠️ **~10 months stale** as of 2026-09-15) |
| Releases | **1 GitHub release**: tag **`0.2.33` (2025-03-23)**; 3 tags total |
| PyPI | **`infinistore`, latest `0.2.35` (2025-04-04), 25 releases**, summary "**A kvcache memory pool**" |
| Homepage | <https://bytedance.github.io/InfiniStore/> |
| Ports | server `--service-port 12345`, management `--manage-port 8088`; TCP or RDMA (`--dev-name mlx5_0 --link-type Ethernet` or `IB`) |
| AIBrix client defaults | `CONNECTION_TYPE=RDMA`, `USE_GDR=True`, `IB_PORT=1` |

README (verbatim): *"InfiniStore is an open-source high-performance KV store. It's designed to support LLM Inference clusters, whether the cluster is in **prefill-decoding disaggregation** mode or not. InfiniStore provides high-performance and low-latency **KV cache transfer and KV cache reuse** among inference nodes in the cluster."* And: *"Currently InfiniStore has been integrated with **vLLM**. The integration is done via **LMCache**… Integration with **SGLang** and other inference engines are **in progress**."*

- ⚠️ **Provenance note (now doubly confirmed)**: the README's CI badge points at **`github.com/bd-iaas-us/InfiniStore`** (ByteDance IAAS-US), and the **PyPI `home_page` field points at the same `bd-iaas-us/InfiniStore`**. `gh api orgs/bd-iaas-us/repos` returns **404** (private/removed), so the origin org is not publicly enumerable. The repo is hosted under the public `bytedance` org. Earliest visible commits date to 2024-09/2024-12.
- ⚠️ **NEW discrepancy flagged**: AIBrix's `envs.py` cites *"Since **0.2.42**"* for RDMA GID pinning, but **PyPI's maximum is 0.2.35** and the only GitHub release is **0.2.33** (the full 25-version PyPI list was checked). **That feature is not reproducible from any public artifact** — either it is unreleased or the citation is wrong.
- The **"IAAS"** in that org name is suggestive but **not proof** that this is the same "IAAS" as in "ByteDance's PrisDB & IAAS & DMI team" (§4.4).
- Note the maintenance signal: **10 months without a push and no releases**, even though AIBrix's own docs name it as an L2 backend. Flag this if recommending it.

## 4.4 PrisDB / PrisKV — a second, distinct ByteDance KV-cache entity

Primary source, quoted verbatim from SGLang's AIBrix backend README (`python/sglang/srt/mem_cache/storage/aibrix_kvcache/README.md`):

> "AIBrix KVCache currently supports multiple distributed KVCache backends, including **ByteDance's open-source Infinistore** and the **not-yet-open source PrisKV incubated by ByteDance's PrisDB & IAAS & DMI team**."

- Repository: **`https://github.com/aibrix/PrisKV`** — "High Performance KV Cache Store for LLM". API metrics 2026-09-15: **59★ / 8 forks**, **Apache-2.0**, created **2025-11-11**, last push **2026-05-20** (⚠️ **~4 months stale**), default branch **`dev`**, **0 releases / 0 tags**.
- Rename confirmed: AIBrix PR **#1807** "[Feat] KVCache: change Pris to PrisKV" by **`DwyaneShi`** (= Haiyang Shi, whose GitHub company field reads "ByteDance Inc."), merged **2025-11-27**, +87/−56 across 6 files.

**PrisKV architecture (VERIFIED — this corrects my earlier "transport not verified" caveat):**

| Aspect | Detail |
|---|---|
| **Transports** | **RDMA, TCP, shared-memory and UCX** (`rdma.c` / `ucx.c` / `transport.c`), plus **GPUDirect RDMA**. Optional GPU builds: `make PRISKV_USE_CUDA=1`, or **`PRISKV_USE_ACL=1` for Ascend NPU** (`include/priskv-cuda.h`) |
| Default port | **18512**; up to **16 bind addresses** |
| **Tiering** | **Yes** — `--backend` is documented as *"Tiered/backing storage address. Supports multiple backends separated by `;`"*, e.g. `'localfs:/data/priskv&size=100GB;s3:bucket1'` (local-fs quota + S3 tier) |
| **Eviction** | ⚠️ **TTL scanning only** — `--expire-routine-interval` default **600 s**. **No LRU/LFU/ARC is documented** (contrast AIBrix's L1, which offers **S3FIFO**). Flagged so nobody assumes a policy that isn't there |
| Persistence | `--memfile` on **tmpfs / hugetlbfs only** — "ext4, xfs… not supported" |
| Limits | max **16,777,216 keys** and 16,777,216 value blocks; block size **≤ 1 MB** |
| Ops | HTTP/HTTPS management endpoint **off by default**; ACLs; slow-query logging at 1000 µs |
| Clients | C/C++ RDMA client; cluster client (`crc16` sharding + `meta.json`); Python **`pypriskv`** |

- **The Redis question, resolved but with a caveat.** PrisKV's cluster example is `priskvClusterConnect("127.0.0.1", 6379, "kvcache-redis")` — the port **6379** and password **`kvcache-redis`** appear **byte-identically in SGLang's AIBrix startup env vars**, and the tree contains `valkey_bench.c` plus `hiredis` deps. That is strong circumstantial evidence of a **Redis/Valkey-compatible front end**, but **the README never states it**, and AIBrix attributes its Redis meta service to *InfiniStore and HPKV* — so this remains an **inference, not a documented fact**.
- ⚠️ The README's "not-yet-open source" wording was written when the note was added; a public repo now exists. Whether its contents are the **full production store or a partial/stub release** is **not verified**. Its **transport details are NOT verified.**
- ⚠️ What "PrisDB", "IAAS" and "DMI" expand to as ByteDance org units is **not verified**, and **no PrisDB performance number** was found.

## 4.5 AIBrix — the actual distribution channel for ByteDance's KV-cache stores

| Field | Value |
|---|---|
| Repo | **`vllm-project/aibrix`** (moved from ByteDance) |
| Stars / forks | **5089 / 694** |
| License | Apache-2.0 |
| Latest release | **v0.7.0 (2026-06-18)**; v0.6.0 (2026-03-03), v0.5.0 (2025-11-09) |

- **ByteDance-originated**: KubeCon speakers **Jiaxin Shan / Liguang Xie**; the **top contributor `DwyaneShi` = Haiyang Shi, whose GitHub company field reads "ByteDance Inc."**; InfoQ CN describes it as 字节跳动开源 AIBrix (ByteDance open-sourced AIBrix). It is **now governed under `vllm-project`**.
- **KVCache Offloading Framework** (added v0.3.0): **L1 DRAM + L2 distributed**, pluggable eviction (**LRU, S3FIFO**), pluggable L2 backends — the design doc **explicitly names `bytedance/InfiniStore`** as a backend, alongside comparisons to **Dynamo, LMCache and Mooncake**. RDMA/GDR flags.
- Also registered as an SGLang HiCache backend under the name **`aibrix`**.
- The `aibrix` GitHub org (which hosts `PrisKV`) is separate from `vllm-project/aibrix` — it hosts the project site, forks of vLLM/v6d, and PrisKV (6 public repos total).
- AIBrix KVCache offloading design doc: <https://aibrix.readthedocs.io/latest/_sources/designs/aibrix-kvcache-offloading-framework.rst>

### The single most useful new finding: **AIBrix is the control plane that wires the ByteDance names together**

**AIBrix ships its own EIC L2 connector** — `l2/connectors/eic/eic.py` (12,926 B), added by `kenan.666` in PR **#1718 on 2025-11-06**. Diffing AIBrix's EIC README against SGLang's shows the **prose is byte-identical** (same definition, same two WeChat URLs, same console link, same doc ID `85848/1749188`) — only the title and deploy snippet differ. So **the same team onboarded EIC to two frameworks in parallel**, SGLang on 2025-10-01 and AIBrix on 2025-11-06.

**AIBrix's L2 backend catalogue** (verbatim from `kvcache-offloading.rst`): **`INFINISTORE`, `HPKV`, `PRISKV`, `ROCKSDB`, `EIC`, `SHFS`, `MOCK`** — empty disables L2 entirely.

**This makes the SGLang HiCache blog's acknowledgement list internally coherent.** The blog thanks "the LMCache, AIBrix, **PrisDB**, and **ByteDance EIC** teams" — which reads like three unrelated ByteDance entities. It is actually: **AIBrix is the control plane, and PrisKV (PrisDB) and EIC are two of its pluggable L2 stores.** That is the cleanest available resolution of the "ByteDance EIC / PrisDB" question.

⚠️ **Do not misattribute non-ByteDance L2 backends**: **HPKV, RocksDB, SHFS and Vineyard are NOT ByteDance projects.** Only `INFINISTORE`, `PRISKV` and `EIC` are ByteDance/Volcengine-related. AIBrix's connector git history is mostly Haiyang Shi / ByteDance (InfiniStore memory layout, RDMA auto-detect, TCP fix, GDR; PrisKV rename + zero-copy).

### ⚠️ Methodology trap worth recording

**Two of the three most important ByteDance KV-cache artifacts live OUTSIDE ByteDance-named orgs**: **PrisKV** in the standalone **`aibrix`** org (6 repos), **AIBrix** in **`vllm-project`**, and **InfiniStore** dual-homed at the **404-ing `bd-iaas-us`**. A repo enumeration of the `bytedance` / `volcengine` / `ByteDance-Seed` orgs therefore **legitimately returns "no KV-cache repo"** while still being **misleading as a conclusion**. Anyone repeating that org-enumeration negative result must add this caveat. (Mirror-image note: the *name*-level negative result — that no project called "ByteDance KVCache" exists — **does** still hold.)
- So **ByteDance's KV-cache stores reach users through a vLLM-governed, CNCF-adjacent ecosystem project**, not a ByteDance-branded distribution. Mooncake's README independently lists **AIBrix** among HiCache's contributing projects.

## 4.6 veRL — moved to `verl-project`, and its KV caching is *delegated to Mooncake*

- **`volcengine/verl` has MOVED to `verl-project/verl`**: **23 431★ / 4543 forks**, latest **v0.9.0 (2026-08-14)** (v0.8.0 2026-06-01, v0.7.1 2026-03-16, v0.7.0 2026-01-05, v0.6.1 2025-11-14, v0.6.0 2025-10-15, v0.5.0 2025-07-23). Same pattern as xLLM — **a ByteDance project donated to community governance**.
- **KV-cache relevance: yes, but entirely delegated.** `docs/perf/rollout_kv_offload.md` (updated 2026-05-27) offloads **rollout prefix KV to a Mooncake store** via **vLLM's `MooncakeStoreConnector`** (`kv_role: kv_both`, requires **vLLM ≥ 0.22**), deduplicating prefixes across requests and replicas and easing long-tail balance. Critically, it **clears both local and Mooncake KV at every weight update** for RL correctness.
- **GitHub code search: `hicache` in verl = 0 hits.** No hybrid-engine cross-phase KV reuse exists.
- `verl/checkpoint_engine/` (mooncake / nixl / nccl / hccl / kimi / delta) moves **weights, not KV**.
- **The irony worth reporting**: veRL — ByteDance-originated — uses **Mooncake** (a Moonshot AI / `kvcache-ai` project) for rollout KV caching rather than EIC or InfiniStore.

## 4.7 Volcengine Ark / BytePlus ModelArk prompt caching (API-level, fully verified)

BytePlus docs embed content as Quill-delta JSON and are extractable (the `docs.volcengine.com` CN equivalents are not). From `docs.byteplus.com/en/docs/ModelArk/1398933` and `/1396491`:

**Implicit cache** — auto-enabled, **cannot be disabled** (Dola Seed 2.0+); **cache storage is FREE**; hit price varies by input band (`[0,32k]` / `[32k,128k]` / `[128k,256k]` for Seed 2.0); **minimum cache block = 1024 tokens** (2048 for several `deepseek-v4`/`glm-5-2` models; **8960** for `glm-5-3-flash-260828`); detected via `usage.prompt_tokens_details.cached_tokens > 0`; hits are **not guaranteed** — "distributed routing also affects the hit probability".

**Explicit cache** — two modes:
- **prefix cache**: minimum **256 tokens**; `stream` cannot be `true`; **TTL 1 h–7 d** (`[3600, 604800]` s); supports concurrency.
- **session cache**: stateful; **no concurrent calls per `context_id`**.
- Both require `"store": true` + `"caching":{"type":"enabled"}` on **every** prior turn; `json_schema` unsupported.
- **Overflow modes**: `last_history_tokens` (FIFO, free) vs `rolling_tokens` (delete length B **and recompute**). Example: `seed-2-0-lite-260228` at 256k−128k drops and recomputes 128k of history.

**Billing**: input, cached input, **storage (USD per 1k tokens per HOUR; <1 h counts as 1 h)**, output. Responses API `expire_at` max **7 days**. **Implicit and explicit cache are mutually exclusive.**

**Status**: the older **Context API is archived / titled "(Sunsetting)"** (last updated 2026-09-01), superseded by the **Responses API**. Public Go SDK confirmed: `github.com/volcengine/ark-runtime-go`, base `https://ark.ap-southeast.bytepluses.com/api/v3`.

⚠️ A `docs.byteplus.com` Responses-API page (`/1602228`) returned HTML but yielded **0 extractable characters**, so some Responses-API-specific parameter detail is **unverified**.

## 4.8 ByteDance — consolidated negative results (do NOT cite these)

- ❌ **"ByteDance KVCache"** — **no such project.** Repo search for `kvcache` across 419 `bytedance`, 208 `volcengine`, 63 `ByteDance-Seed` repos: **0 results**. (`kv cache` returns exactly 2: `bytedance/InfiniStore` and `ByteDance-Seed/ShadowKV`.)
- ❌ **"Penguin" as a ByteDance KV-cache paper** — **not found. No evidence at all.**
- ❌ **"ByteDance eplb"** — **EPLB is DeepSeek's** project (`github.com/deepseek-ai/EPLB`). No ByteDance EPLB exists. **Do not misattribute.**
- ❌ **LMDeploy** is **Shanghai AI Lab / InternLM**, not ByteDance. (Brief's caution is correct.)
- ❌ **ByteDance internal inference framework name** — none findable publicly.
- ❌ **KVDirect (arXiv 2501.14743)** — ByteDance affiliation **not verified**.
- ❌ **Whether Volcengine ever contributed the EIC prebuilt images it promised to open source** — no artifact found. Unverified.
- ❌ **EIC capacity / latency / pricing / regions** — the vendor docs API returns `未授权访问`.
- ⚠️ `bytedance/ERTACache` (26★) and `volcengine/LoRA_Serving_Trace` (3★) have **no descriptions**; contents **unverified**.
- ℹ️ `bytedance/flux` (1360★) is comm-overlap for TP/EP with **no KV-cache code**.
- ⚠️ **PrisKV's eviction policy is undocumented beyond TTL** — no LRU/LFU/ARC appears in its docs or source config. **Do not assume one.**
- ⚠️ **PrisKV's Redis/Valkey compatibility is an inference, not a documented fact** (§4.4) — the port/password match is strong circumstantial evidence but the README never states it.
- ⚠️ **AIBrix cites InfiniStore "since 0.2.42" for RDMA GID pinning, but PyPI's maximum is 0.2.35 and the only GitHub release is 0.2.33** (§4.3) — that feature is **not reproducible from public artifacts**.
- ⚠️ **HPKV, RocksDB, SHFS and Vineyard are NOT ByteDance** — they appear in AIBrix's L2 backend list but must not be attributed to ByteDance.

# 5. Huawei / Ascend

> **Provenance note.** This section is based on a deep-dive research pass whose full raw notes (704 lines, 15-item "could not verify" list, complete source list, ~45 saved artifacts) are at **`kvcache-research/raw/huawei_ascend.md`**. Findings below are labelled `[V-CODE]` (verified from source code), `[V-DOC]` (official documentation), or `[V-PAPER]` (verified from paper full text) as in the source file.

## 5.1 The four-layer stack (do not conflate these)

| Layer | Component | Role | Transport |
|---|---|---|---|
| **Connector / policy** | `AscendStoreConnector`, `UCMConnector`, `MooncakeConnectorV1/V2/Hybrid/Layerwise`, `SfaRemoteD2HConnector`, `AscendMultiConnector` (all in vLLM-Ascend) | implements `KVConnectorBase_V1`; prefix lookup, load/save orchestration, PD handoff | delegates |
| **KV store service** | Mooncake Store (`mooncake_master`), MemCache (`MetaService`+`LocalService`), UCM Store, Yuanrong Datasystem | capacity + eviction (watermarks/LRU/leases) + persistence | MemFabric / Mooncake TE |
| **Memory pooling** | **MemFabric**, CloudMatrix **EMS** (MP SDK/Controller/Server), openEuler **UBS Memory** | GVA unified addressing, cross-node cross-medium zero-copy | **Device UB 1.0 (A3)**, Device RoCE (A2), Device URMA/UBOE (A5/950), Host RoCE/UB |
| **Fabric** | UB / 灵衢 (LingQu), HCCS, RoCE, UB-Mesh | physical interconnect | — |

**The single most important takeaway:** the Ascend KV-cache story is fundamentally a **memory-pooling** story. Because Ascend puts its high-bandwidth network on the **NPU side, not the host side** ("Ascend's high-bandwidth network is on the NPU side, not the Host side, so pooling software built on Host-side networks cannot fully utilise the hardware"), and because UB provides globally addressable unified memory with DMA, Huawei can expose remote DRAM as if local (`xcopy` on a global virtual address) at **~70–166 GB/s per die** — roughly **3–7× the ~25 GB/s inter-node bandwidth** that the CloudMatrix384 paper cites for conventional clusters. This is why `ASCEND_ENABLE_USE_FABRIC_MEM=1` ("unified memory address direct transmission") is the recommended A3 setting.

## 5.2 vLLM-Ascend KV Cache Pool / `AscendStoreConnector`

**Repo** `vllm-project/vllm-ascend`: **2826★ / 2257 forks**, **Apache-2.0**, C++, created 2025-01-29, last push 2026-09-15, 3270 open issues, homepage <https://docs.vllm.ai/projects/ascend>.

**Releases** (from API, `prerelease` flagged): **`v0.26.0rc1` 2026-09-03 (prerelease)**; **`v0.23.0` 2026-08-16 — latest *stable***; `v0.23.0rc1` 2026-07-19; `v0.22.1rc1` 2026-06-30; `v0.21.0rc1` 2026-06-16; `v0.20.2rc1` 2026-06-03; `v0.19.1rc1` 2026-04-30; `v0.18.0` 2026-04-30 (stable); `v0.13.0` 2026-02-05 (stable); `v0.11.0` 2025-12-16 (stable).

### What it is

`AscendStoreConnector` is a **vLLM KV Connector V1** implementation — class `AscendStoreConnector(KVConnectorBase_V1, SupportsHMA)` — that turns a *remote KV pool* into a **second-level prefix cache** behind vLLM's on-device prefix cache. Path: `vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py`. `[V-CODE]`

Documented rationale, from `docs/source/developer_guide/Design_Documents/KV_Cache_Pool_Guide.md`:

> "Prefix caching … performance gain … highly dependent on the cache hit rate, while the cache hit rate can be limited if one only uses on-chip memory … Hence, KV Cache Pool is proposed to utilize various types of storage including **on-chip memory, DRAM, and SSD**, making a pool for KV Cache storage while making the **prefix of requests visible across all nodes**."

⚠️ **Naming inconsistency in the docs**: the design document still calls the connector `MooncakeStoreConnectorV1`; the shipped class and registered name are `AscendStoreConnector`. Treat `MooncakeStoreConnectorV1` as an alias (§ below).

### Registration and API surface

Registered in `vllm_ascend/distributed/kv_transfer/__init__.py` via vLLM's `KVConnectorFactory.register_connector(...)` `[V-CODE]`:

| Registered name | Class |
|---|---|
| **`AscendStoreConnector`** | `AscendStoreConnector` (kv_pool/ascend_store) |
| `MooncakeConnectorStoreV1` | **alias** → same `AscendStoreConnector` |
| `MooncakeConnectorV1` / `V2` / `MooncakePullConnector` / `MooncakeHybridConnector` / `MooncakeLayerwiseConnector` | live PD-transfer connectors (kv_p2p), a **different layer** |
| `UCMConnector` | `UCMConnectorV1` |
| `SfaRemoteD2HConnector` | prefill→decode remote D2H KV pull |
| `AscendMultiConnector` | overrides vLLM's `MultiConnector` |
| `AscendOffloadingConnector`, `AscendSimpleCPUOffloadConnector`, `RecomputeCPUOffloadConnectorV1` | offload overrides |

Ascend also **replaces vLLM's native offloading specs** (`CPUOffloadingSpec` → `NPUOffloadingSpec`, `TieringOffloadingSpec` → `NPUTieringOffloadingSpec`), keeping the scheduler-side managers upstream and swapping only the worker-side transfers to `torch.npu` streams and the Ascend batched-memcpy op. `[V-CODE]` — a clean layering choice.

**Configuration** via `--kv-transfer-config` / `kv_transfer_config`:

```json
{
  "kv_connector": "AscendStoreConnector",
  "kv_role": "kv_both",
  "kv_load_failure_policy": "recompute",
  "kv_connector_extra_config": {
    "lookup_rpc_port": "1",
    "backend": "yuanrong",
    "use_layerwise": false
  }
}
```

| Key | Meaning |
|---|---|
| `kv_role` | `kv_producer` (prefill writes) / `kv_consumer` (decode reads) / `kv_both` |
| `kv_load_failure_policy` | `recompute` (roll back to last valid prefix and recompute) or `fail` (terminate). vLLM's default is `fail` |
| **`backend`** | **`mooncake` (default), `memcache`, `yuanrong`** |
| `lookup_rpc_port` | RPC port between the pooling **scheduler process** and **worker process**; unique per instance |
| `load_async` | async loading, default `false` |
| `consumer_is_to_put` / `consumer_is_to_load` | whether Decode also puts / loads (default `false`); used with MLA models |
| `use_layerwise` | layer-by-layer KV save/load; **prefill node only, `memcache` backend only** |
| `prefill_pp_size` / `prefill_pp_layer_partition` | required when Prefill uses PP |
| `qos_priority` | transfer QoS priority, int in `[0, 4]` |

**Operational gotcha**: `export PYTHONHASHSEED=0` on **all** nodes, otherwise token hashing diverges and cache keys do not match. `[V-CODE]`

`KVConnectorBase_V1` methods implemented include the scheduler-side `get_num_new_matched_tokens`, `update_states_after_alloc`, `build_connector_meta`, `request_finished`; worker-side `register_kv_caches`, `start_load_kv`, `wait_for_layer_load`, `save_kv_layer`, `wait_for_save`, `get_finished`; plus `request_finished_all_groups`, `prepare_mamba_state_copy`/`finish_mamba_state_copy` (Mamba/hybrid support), `get_block_ids_with_load_errors`, `bind_gpu_block_pool`, `build_prom_metrics`. `[V-CODE]`

### Where KV blocks live

- **HBM (NPU)** — level-1 prefix cache, managed by vLLM's own block pool.
- **Host DRAM** — each node contributes a *pool segment*. Mooncake: `global_segment_size` (must be **1 GB-aligned**) registered per card. MemCache: `ock.mmc.local_service.dram.size` per die (on A3, a 640 GB pool ⇒ `640/16 = 40 GB`).
- **NVMe/SSD** — optional L3. Mooncake: `enable_ssd_offload: true` + `ssd_offload_path` + `mooncake_master --enable_offload=true`. MemCache: `ock.mmc.local_service.storage.enabled = true` + `ubsio.disk.path` (requires `memcache_hybrid >= 1.2.0`).
- **Remote/shared storage** — UCM adds **NFS / DeepSeek 3FS / Posix** as a persistent tier.
- ⚠️ `[UNVERIFIED]` No documented use of **another node's remote NPU HBM** as pool *capacity* for `AscendStoreConnector`; the pool is CPU-DRAM-centric. Remote HBM appears as a **transport endpoint** (MemFabric D2RH/RH2D/RD2D) rather than as pool capacity.

### Transport — hardware-specific, not one thing

| Hardware | Mechanism / env var | Notes |
|---|---|---|
| Atlas 800I/T **A2** | `HCCL_INTRA_ROCE_ENABLE=1` | required by the direct-transmission scheme on A2 |
| Atlas 800I/T **A3** | **`ASCEND_ENABLE_USE_FABRIC_MEM=1`** | **recommended.** "Enables unified memory address direct transmission scheme." Requires **HDK ≥ 26.0** (or ≥ 25.5 with mooncake ≥ v0.3.11), **CANN ≥ 9.0.0**, **LingQu (灵衢) Computing Network ≥ 1.5**. With SSD offload, sizes must be 1 GB-aligned |
| Ascend **950PR/950DT (A5)** | UBOE: `ASCEND_GLOBAL_RESOURCE_CONFIG='{"comm_resource_config.protocol_desc":["uboe:device"]}'`; UB: `ASCEND_LOCAL_COMM_RES='{"version":"1.3"}'` | Requires **HDK ≥ 25.6** (mooncake ≥ v0.3.11), **CANN ≥ 9.1.0**. Container must mount `/dev/ummu`, `/dev/uburma`, `/usr/bin/urma_admin`, `/lib/route.conf`, `/etc/hccl_rootinfo.json` |
| Link type (A3) | `LINK_TYPE=ROCE` or `HCCS` | both supported |

MemCache protocol values `[V-CODE]`: `device_rdma` (A2/A3 with device RoCE; **recommended for A2**), `device_sdma` (**A3 with HCCS; recommended for A3**), `device_urma` (Ascend 950 UB), `device_uboe` (Ascend 950 UBOE). MemFabric also supports `host_rdma`, `host_urma` (Kunpeng K5), `host_shm`.

For **layerwise Remote D2H**, the protocol is chosen at launch via `kv_connector_extra_config["memfabric_transfer_protocol"]`: `sdma` (default) or `device_rdma` for A3; `device_urma` for A5. **Prefill and Decode must use the same protocol.**

Additional required setup: `/etc/hccn.conf` must exist (mount into containers); hugepages (`echo 200000 > /proc/sys/vm/nr_hugepages`); various `*_SOCKET_IFNAME`/`HCCL_IF_IP` env vars.

### External store service: **required**

- **Mooncake backend**: a `mooncake_master` process (one node suffices): `mooncake_master --port 50088 --eviction_high_watermark_ratio 0.9 --eviction_ratio 0.1 --default_kv_lease_ttl 11000 --enable_offload=false --client_ttl=120`. Client config via `MOONCAKE_CONFIG_PATH` → `mooncake.json` with `"metadata_server": "P2PHANDSHAKE"`, `"protocol": "ascend"`, `"device_name": ""`.
- **MemCache backend**: `MetaService` + ≥1 `LocalService`.
- **Yuanrong backend**: `openyuanrong-datasystem` importable (`yr.datasystem`) on all nodes + a Coordinator or etcd.
- **UCM**: an external UCM Store configured by a `store_pipeline`.

### Eviction

Eviction is **delegated to the backend**, not implemented in the connector `[V-CODE]`:

- **Mooncake**: master-side watermarks `eviction_high_watermark_ratio` (where eviction starts) and `eviction_ratio` (fraction evicted per pass). `default_kv_lease_ttl` (ms) controls the KV object lease and must exceed `ASCEND_CONNECT_TIMEOUT` and `ASCEND_TRANSFER_TIMEOUT`.
- **MemCache**: `ock.mmc.evict_threshold_high = 70`, `ock.mmc.evict_threshold_low = 60`, `ock.mmc.rewarm.dram_watermark = 95`, plus `ubsio.wcache.evict_water_level` for the UBS IO write-cache tier. ⚠️ The definition of `ubsio.wcache.evict_water_level` could **not** be located in the openEuler MemStore docs fetched — `[UNVERIFIED]`.
- **Layerwise**: Decode uses a **per-layer LRU residency table** for hot top-k buffers.
- **CloudMatrix EMS**: MP Server uses its own LRU + capacity thresholds for the DRAM tier; DRAM → EVS SSD under pressure, then LRU removal. `[V-PAPER]`

Documented DFX caveats: on a lookup miss, **no further blocks are looked up** for that request; on a failed *put*, **no further blocks are put**.

### Layerwise and sparse KV offload

`docs/source/developer_guide/Design_Documents/layerwise_and_sparse_kv_cache_offloading.md` (based on vLLM RFC [#48203](https://github.com/vllm-project/vllm/issues/48203)) describes an **asymmetric** design `[V-CODE]`:

| Stage | Compute pattern | Offload strategy | NPU-resident data |
|---|---|---|---|
| Prefill | high compute/layer | transfer **complete layers**, overlap with compute | a few reusable layer buffers |
| Decode | low compute/token | keep full KV in host memory, load only **selected entries** | indexer cache + per-layer hot top-k buffers |

Buffer-footprint formula: with `N` cache-bearing layers, `I` independent layers, `R = N − I`, and `B` configured shared buffers → `physical buffers = I + min(B, R)` and `main-KV NPU footprint ratio ≈ physical buffers / N`.

`AscendStoreConnector` manages Layerwise Prefill Offload via **Memcache**; `SfaRemoteD2HConnector` exposes Prefill NPU buffers so Decode can pull main KV into Decode-owned host memory and indexer data into rank-local NPU memory via **MemFabric** — **the only supported Remote D2H transfer backend**.

**Known boundaries**: layerwise shared-buffer offload requires the Memcache backend **and eager mode**; Sparse Decode Offload requires Model Runner V1 and an SFA/MLA sparse-attention model with **BF16** main KV (LIC8 quantization only for the device-resident indexer cache); **hybrid KV cache layouts are not supported**; Sparse Decode Offload supports DP and TP but **not CP or PP**; joint deployment requires `p_tp_size >= d_tp_size` and `p_tp_size % d_tp_size == 0`; layerwise buffer reuse **cannot currently be combined with `MooncakeLayerwiseConnector`** (no per-buffer completion gate); connector-level data-read retry is **not implemented**.

### KV Pool limitations (from the KV Cache Pool Guide)

1. "Currently, MooncakeStore for vLLM Ascend only supports **DRAM** as the storage for KV Cache Pool." ⚠️ This line **predates** the later SSD-offload support documented in the user guide — **the two docs are internally inconsistent**.
2. If a key is found but the `get` fails, the code only logs and continues, so "the accuracy of that specific request may be affected." Planned fix: recompute fallback.

In PD disaggregation the pool by default stores only KV generated by the **Prefill** node; with `MultiConnector`, `connectors[0]` does live P/D transfer while `connectors[1]` (`AscendStoreConnector`) acts as the prefix-cache node.

## 5.3 Mooncake Transfer Engine on Ascend — five transports, not one

Mooncake's Ascend support is far more extensive than a single backend. `[V-CODE]`

| Transport | Directory | Protocol / mechanism |
|---|---|---|
| **Ascend Transport (HCCL)** | `ascend_transport/hccl_transport` | one-sided semantics over **HCCL**; auto-selects HCCS or ROCE per transfer |
| **Ascend Direct Transport** | `ascend_transport/ascend_direct_transport` | built on **CANN ADXL**; H2D / D2H / **D2D** over **HCCS** and **RDMA** |
| **UB shared memory** | `ascend_transport/ubshmem_transport` | UB shmem transport |
| **Heterogeneous RDMA** | `ascend_transport/heterogeneous_rdma_transport` | cross **Ascend ↔ GPU** |
| **Kunpeng UB** | `kunpeng_transport/ub_transport`, `ub_allocator`, `ub_context`, `ub_endpoint` | **URMA** over UB; doc `docs/source/design/transfer-engine/kunpeng_ub_transport.md` |
| tent/UB | `tent/src/transport/ub/ub_transport.cpp` | newer "tent" stack has a first-class UB transport |

**Ownership** (verified): Mooncake `.github/CODEOWNERS` assigns `/mooncake-transfer-engine/*/transport/ascend_transport/` to `@alogfans @ascend-direct-dev` and `/scripts/ascend/` to `@ascend-direct-dev @VNightMare @MingYang119`; `MAINTAINERS.md` includes `image/partners/huawei_logo.png` in its Contributors partner wall; `scripts/ascend/` contains `dependencies_ascend.sh`, `dependencies_ascend_installation.sh`, **`dependencies_openeuler.sh`** and `perf/`.

> ⚠️ **Correction to a natural assumption — do not over-attribute.** Querying the GitHub user API for **every** account involved returns an **empty `company` field** for all of them. Specifically: **`alogfans` = Feng Ren, bio "Independent Researcher"** — not Huawei; and **PR #759's author `zuochunwei` lists `meituan`** (Meituan — confirmed independently in my own API query, see §2's Mooncake ownership notes). Huawei's involvement is therefore **corroborated by `MAINTAINERS.md`, by account naming (`ascend-direct-dev`) and by the `ascend_transport@yeah.net` co-author address, but it is NOT attributable per-account from GitHub data.** There is no `GOVERNANCE.md` (HTTP 404). State this as "**Huawei-affiliated contributors / partner listing**", not as "Huawei employees own these files".

**Published protocol registry** (<https://kvcache-ai.github.io/Mooncake/getting_started/supported-protocols.html>) `[V-DOC]`: protocol name **`ascend`** — "Huawei Ascend NPU communication using **HCCL (Huawei Collective Communication Library)** or direct transport", maturity **⚠️ Advanced** (not Experimental, not Stable). For an "Ascend NPU Cluster" the registry recommends **`rdma + ascend`** — i.e. plain RDMA *plus* the Ascend transport, not Ascend-only.

**PyPI wheel**: **`mooncake-transfer-engine-npu`** — "A KVCache-centric Disaggregated Architecture for large-scale LLM inference and training. (**Ascend NPU version**)". Latest **`0.3.13.post1`, uploaded 2026-08-31**. Only **5 releases** exist (`0.3.11.post1`, `0.3.12`, `0.3.12.post1`, `0.3.13`, `0.3.13.post1`) — a **much newer, thinner release line** than the main Mooncake line. Wheels are **`manylinux_2_35_<arch>`** for cp310/cp311 on **aarch64 and x86_64** — which is exactly why vLLM-Ascend docs require **glibc ≥ 2.35**. PyPI's `license` field is `None` (the repo is Apache-2.0). The vLLM-Ascend docs pin **`0.3.11.post1`**, with the policy that `0.3.11.post1` remains supported when `tenant_id` is `default`/omitted; **non-default tenants require ≥ `0.3.12`**.

**Heterogeneous Ascend Transport (NPU↔GPU KV transfer)** — a genuinely distinct cross-vendor capability. PR [#759](https://github.com/kvcache-ai/Mooncake/pull/759) (19 files, +1036/−303, merged 2025-09-03); doc `docs/source/design/transfer-engine/heterogeneous_ascend.md`. `[V-CODE]`

- **910B executes PREFILL, H20 handles DECODE**; the transport "manages cross-device KVCACHE transmission, enabling efficient data exchange between **910B NPU memory and H20 GPU memory**."
- **Current version supports WRITE semantics only**; READ is future work.
- Mechanism: RDMA-based heterogeneous memory transfer with **GPU Direct** on the H20 (decode) side. Build flag `USE_ASCEND_HETEROGENEOUS` in `mooncake-common/common.cmake`. Parameters: `source` (910B NPU address), `target_offset` (H20 GPU address), `opcode` (WRITE only).
- **Optimization rationale**: "The copy bandwidth from HBM to DRAM is constrained by the size of data blocks. **Small data blocks smaller than 2 MB result in underutilized bandwidth.**" Fix: **data aggregation + pipeline parallelism** — small blocks are aggregated into **8 MB** blocks in HBM before transfer to DRAM, while the copy and the RDMA transmission run in parallel, to "hide the HBM-DRAM copy latency and significantly reduce the overall transmission time."
- ⚠️ `[UNVERIFIED]` **No measured GB/s figures are published** for this path — it is a design/mechanism statement.
- Tests: initiator `transfer_engine_heterogeneous_ascend_perf_initiator.cpp` (910B, `--npu_id=1 --block_size=65536 --batch_size=128`); target reuses `rdma_transport_test.cpp` (H20).

**vLLM-Ascend ↔ Mooncake is bidirectional and two-layered** `[V-CODE]`:
1. **Mooncake Transfer Engine** = the *transport* for live P/D KV disaggregation (`MooncakeConnectorV1` etc.), integrated **Aug 18 2025** ("vLLM-Ascend integrates Mooncake Transfer Engine for KV cache register and disaggregate prefill").
2. **Mooncake Store** = the *distributed KV cache pool backend* behind `AscendStoreConnector`, integrated **Sept 18 2025** ("Mooncake Store empowers vLLM Ascend by serving as the distributed KV cache pool backend").

Connector choice depends on attention architecture `[V-CODE]`: standard attention (Qwen3, GLM-5, DeepSeek V3.1) → `MooncakeConnectorV1`; **hybrid attention** (DeepSeek V4 / V4 Flash / V4 Pro) → **`MooncakeHybridConnector`**. Misconfiguring a hybrid-attention model with V1 can make the Decode node "crash and restart during inference."

## 5.4 UCM (Unified Cache Manager) — a third, external pooling path

An external (non-Huawei-branded) project at <https://ucm.readthedocs.io/>, registered on Ascend as `UCMConnector` / `UCMConnectorV1`. Doc: `docs/source/user_guide/feature_guide/ucm_deployment.md`. `[V-CODE]`

- **Three tiers**: `HBM (GPU memory) → DRAM (local cache) → Storage Backend (SSD/NFS/3FS)`. It explicitly contrasts itself with KV Pooling: "Unlike KV Pooling, which expands prefix-cache capacity only by aggregating device memory and therefore remains limited by HBM/DRAM size and **lacks persistence**, UCM **decouples compute from storage**."
- **Claimed**: "**3–10× reduction** in inference latency across various scenarios … up to **8× improvement in TTFT** for prefix caching scenarios." ⚠️ vendor claim, no baseline stated.
- **Published benchmark** — GLM-5.1-w4a8, 128 requests at concurrency 128, prefix ratio 0.8 pre-seeded, output 1000 tokens; **TTFT in ms**:

| Input len | Recalculation | HBM PC | UCM PC |
|---|---|---|---|
| 32k | 140,730 | 108,879 | **51,861** |
| 64k | 181,864 | 144,444 | **69,718** |
| 128k | 268,016 | 267,680 | **105,083** |

The doc's own honest caveat: with data parallelism, HBM prefix cache achieves a **lower** hit rate than the intended 0.8 because requests may not route to the DP process that pre-seeded the cache, whereas UCM stores everything in shared external storage and thus gets a true 0.8 hit rate. This is a good example of a well-documented benchmark.

- Also lists **GSA** (Graph-based Sparse Attention) and **CacheBlend** sparse-attention methods; supports CUDA (H100/H20/L40/L20), **CANN (Atlas A2/A3)**, **MUSA (Mthreads S5000)**, **MACA (MetaX C500)**.
- MindIE Motor integration: UCM is `UCMConnector` with `kv_role: "kv_both"` on the **Prefill** side only; MindIE docs explicitly warn you must **not** set `"backend": "ucm"`.

## 5.5 MindIE — open source, contrary to common assumption

**MindIE-LLM and MindIE-Motor ARE open source on GitHub under the `Ascend` org, licensed Mulan PSL v2.** `[V-CODE]`

| Repo | ★ | Forks | Language | License | Created | Last push |
|---|---:|---:|---|---|---|---|
| [Ascend/MindIE-LLM](https://github.com/Ascend/MindIE-LLM) | **27** | 7 | C++ | **Mulan PSL v2** | 2026-03-30 | 2026-09-07 |
| [Ascend/MindIE-Motor](https://github.com/Ascend/MindIE-Motor) | **2** | 4 | Python | **Mulan PSL v2** | 2026-03-30 | 2026-09-15 |

⚠️ **Licensing trap:** the license files begin `# 木兰宽松许可证，第2版` with the canonical link `http://license.coscl.org.cn/MulanPSL2`, but **GitHub's API reports `spdx_id: NOASSERTION`** because GitHub does not auto-detect Mulan PSL v2. **`NOASSERTION` here must NOT be read as "proprietary".** The same applies to `Ascend/memfabric_hybrid` and `Ascend/memcache`.

- ❌ **`Ascend/MindIE-Service` → HTTP 404 on GitHub.** MindIE-Service appears to be distributed via Ascend run/whl packages (`mindieservice_daemon`, `mindie_llm_server`) rather than as a GitHub repo.
- ⚠️ `[UNVERIFIED]` The GitHub repos were created **2026-03-30**, *later* than the content they contain (memcache's README describes a Nov-2025 open-sourcing). Canonical homes appear to be **GitCode** (`gitcode.com/Ascend/memcache`, `gitcode.com/Ascend/memfabric_hybrid`). Whether the GitHub repos are mirrors, imports, or transfers is undetermined.
- **Star counts are very low (27 and 2)** because the project is mirrored/young on GitHub — **do not read low stars as low maturity**. The *product* is still primarily delivered via Ascend Hub / image downloads.

### MindIE-LLM: KV Cache Pooling (KV Cache 池化)

Docs: `docs/zh/user_guide/feature/kv_cache_pool.md` + `mempool.md`. `[V-CODE]`

> ⚠️ **Source warning — the two HiAscend URLs are NOT equivalent.**
> - ✅ **Use the Chinese MindIE 2.3.0 page**: <https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0538.html> — this is the genuine *"KV Cache 池化"* page and matches the GitHub `MindIE-LLM` doc in substance (`kvPoolConfig` table, the 4 MB/HCCL-link + 512-link cap + `(cards/dies−1)×4MB` formula, and the "4机+4机 = 508 MB" worked example all agree).
> - ❌ **Do NOT cite the English URL** <https://www.hiascend.com/document/detail/en/mindie/300/LLMframe/llmdev/user_guide/feature/kv_cache_pool.md> for pooling content. It returns HTTP 200 and its `<title>` genuinely reads "KV Cache Pooling-…", **but the rendered body is the MindIE LLM architecture overview** — zero occurrences of `kvPoolConfig`, `DRAM`, or `HCCL`.
>
> **Fetching trap for anyone reproducing this**: both HiAscend pages are SPAs with the document HTML embedded inside a `<script>` as a JSON-escaped JS string (`\u003C` etc.). A naive "strip `<script>` blocks, then strip tags" pipeline **silently deletes the entire payload** and returns only ~1–5 KB of navigation chrome. You must unescape `\uXXXX` first and **not** strip scripts. (This is why my own first fetch of `help.aliyun.com` product pages returned so little text — same class of problem.)

**Purpose**: Prefix Cache normally uses only on-chip memory, which is capacity-limited. KV Cache Pooling extends the hierarchy to include **DRAM and even SSD**, "breaking through the on-chip memory capacity limit."

**Constraints and cost model (exact, translated)** — this is the most useful hardware-level detail in the Huawei stack:
- Supported on **Atlas 800I A2** inference servers and **Atlas 300I Duo** inference cards.
- Currently **only DRAM pooling is supported** — a 2-level cache when stacked with Prefix Cache.
- **Prefix Cache must be enabled** to use KV Cache Pooling.
- The backend uses **HCCL one-sided communication (HCCL 单边通信)**. Each HCCL link occupies **4 MB** of device memory; due to HCCL limits the **maximum number of links is 512**.
- Extra device-memory cost: **`(total cards/dies in the pool − 1) × 4 MB`**.
- Lowering the memory factor by **0.01 frees ~600 MB**; the **maximum** permissible reduction is **0.04**. ⚠️ **Version discrepancy** — the `MindIE-LLM` GitHub `master` doc says "at most **0.01**"; the official HiAscend **2.3.0** page says **0.04**. **Prefer the official 2.3.0 value (0.04).**
- **Worked example**: Atlas 800I A3, 4 machines + 4 machines (8 × 16 = 128 dies) ⇒ `(8*16 − 1) × 4 MB = **508 MB**`. Default memory factor 0.92; lowering by 0.01 (≈600 MB freed) suffices, at the cost of reduced context length.
- For scale-out, reserve the max reduction of **0.04** (0.92 → **0.88**). ⚠️ The GitHub `master` text reads "0.92 → 0.08", an evident typo contradicted by its own "reserve 0.04" instruction. The **official page's 0.92 → 0.88 is arithmetically correct**; use it.
- **The official docs contradict themselves on tiers**: the feature introduction advertises *"DRAM **甚至 SSD**"* (DRAM and even SSD) while the constraints section states flatly *"当前仅支持 DRAM 池化"* (currently only DRAM pooling is supported). This confirms the SSD-vs-DRAM tension flagged in §5.2 is a **documentation defect that appears in both the GitHub doc and the official page** — not a fork artifact.
- Recommendation: for a unified logical pool, keep **total cards/dies ≤ 512**.

**Configuration** (`BackendConfig` in server `config.json`):
```json
"kvPoolConfig": {"backend": "kv_pool_backend_name", "configPath": "/path/to/config", "asyncWrite": false}
```
`backend: ""` disables pooling. Documented backend: **Mooncake**, built with `cmake -DUSE_ASCEND_DIRECT=ON -DBUILD_SHARED_LIBS=ON -DBUILD_UNIT_TESTS=OFF ..`; requires `"protocol": "ascend"`, `"use_ascend_direct": true`, `mooncake_master --port 12345 --eviction_high_watermark_ratio 0.8 --eviction_ratio 0.05 --rpc_thread_num 128`, `ASCEND_BUFFER_POOL=4:8`, jemalloc recommended.

**Async-write support matrix (explicit)**: Qwen dense (non-MoE) and DeepSeek V3/V3.1/R1 only. Compatible: Qwen dense — async scheduling, Prefix Cache, Function Call, thinking parse, Yarn; DeepSeek — async inference, Prefix Cache, Context Parallel, Sequence Parallel. **Not supported with SplitFuse, Micro Batch, Multi-Lora.**

**Unusually candid security note from Huawei**: *"Mooncake currently only supports plaintext transmission between Mooncake Master Server and Client"* — production deployments must keep those IPs/ports off the public internet.

### MindIE Prefix Cache and INT8 KV

Enabled via `"plugin_params": "{\"plugin_type\":\"prefix_cache\"}"`. Also documents an **NZ-format KV cache** (`kv_cache_options.enable_nz`) that is **mandatory for DeepSeek-R1 / V3 / V3.1** and must be off for other models. There is a separate `kv_cache_int8.md` (INT8 KV cache) feature.

### MindIE layer-wise KV transfer (逐层/分层 KV 传输)

Verified in source **and** docs — the brief specifically asked about this:

- **MindIE-LLM code**: `mindie_llm/connector/request_router/layerwise/` contains `request_router_lwd.py` (layerwise disaggregation), `request_router_cloud.py`, `request_router_edge.py`. `examples/atb_models/atb_llm/utils/layerwise_disaggregated/` contains `chunk_prefill_policy.py`, `cloud_cut_policy.py`, `edge_cloud_ctrl_comm.py`, **`edge_cloud_data_comm.py`**. Graph wrappers: `layerwise_prefill_graph_wrapper.py`, `layerwise_decode_graph_wrapper.py`, `layerwise_combined_graph_wrapper.py`.
  - **Interpretation**: this is a **layer-wise, edge–cloud disaggregated** architecture where a cloud node and an edge node split a model's layers and exchange activations/KV mid-stack, with a "cloud cut policy" deciding the split point.
- **MindIE Motor docs** (`docs/zh/design/pd_disaggregation.md`): **`MooncakeLayerwiseConnector` ⇒ `concurrent_engine_sync`** (a.k.a. `trigger`), described as **"引擎按层同步 KV"** — the engine synchronises KV **layer by layer**. By contrast `MooncakeConnectorV1` / `MooncakeHybridConnector` / `NixlConnector` ⇒ `prefill_handoff_decode` (handoff). In `trigger` mode, Decode starts first and triggers Prefill via a Worker metaserver (`POST /v1/metaserver`, default base port **12000**).
- ⚠️ `[UNVERIFIED]` **No wire-protocol spec and no measured per-layer transfer latency** were found. The *files, structure and routing semantics* are verified; the protocol and numbers are not.

### MindIE Motor: KV Cache Store, KV Conductor, KV affinity

**MindIE Motor** is the cloud-native orchestration/serving layer — "一键式 PD 分离与 PD 混部部署" (one-click PD-disaggregated and PD-colocated deployment) adapting to **vLLM / vLLM-Ascend** and **SGLang**. Docs: <https://mindie-motor.readthedocs.io/>.

**KV Cache Store** — two mechanisms:

| Pooling feature | Store Connector | Storage impl | Usage |
|---|---|---|---|
| Shared KV Pool | `AscendStoreConnector` | `backend` selects **MemCache** or **Mooncake Store** | both P and D load the Store Connector; write and read a shared KV cache |
| UCM | `UCMConnector` | `store_pipeline` composes Cache, Posix etc. | Prefill saves/loads cross-request prefixes; **Decode does not load UCM** |

Backends: Mooncake, **MemCache (default backend)**, Yuanrong (TODO). Global config `kv_cache_store_config: {"backend": "memcache", "local_service_mode": "standalone"}`. Notable: `store_mode: embedded | standalone` (Mooncake), `local_service_mode: inprocess | standalone` (MemCache), and **`target_job_id`** letting a second K8s inference service reuse another service's KV store (`mindie-motor-kvs-master.service-a.svc.cluster.local`) instead of deploying a duplicate MetaService/`mooncake_master` pod.

**KV Conductor** (`docs/zh/design/kv_conductor.md`, ~34 KB) — a **Rust** external KV-metadata/index service for tiered KV cache (HBM / CPU / Disk). This is the most architecturally detailed KV-index design in the Huawei stack:
- Three-tier model: **HBM (NPU)** indexed by a **concurrent Radix Tree**; **CPU (Host DDR)** and **DISK (SSD/NVMe)** indexed by a *continuation-edge graph* with "breakpoint-continuation lookup" plus unconditional root walk.
- Identity: `WorkerKey = (instance_id, backend_id, dp_rank, medium)`; cross-medium hits aggregated per `(instance_id, dp_rank)`, mutually exclusive with priority **NPU > CPU > Disk**.
- `matched_tokens = (npu + cpu + disk) × block_size`; affinity scoring by the Coordinator scheduler with weights `scheduler_config.kv_affinity.w_npu/w_cpu/w_disk` (**defaults `1.0/1.0/0.0`**).
- Hashing: **XXH3** token → `LocalBlockHash`.
- Event ingress: **ZMQ** (`PUB`, 3-frame `[topic][seq: u64 BE][msgpack payload]`, e.g. `tcp://master:5557`) and HTTP `/events`.
- Backend adapters: **Mooncake / Memcache / YuanRong**.
- Modules: `server.rs` (Axum), `registry.rs`, `indexer/mod.rs`, `concurrent_tree.rs`, `lower_tier.rs`, `hashing.rs`, `backend.rs`, `zmq_subscriber.rs`, `events/`, `protocols.rs`, `error.rs`.

**KV Cache affinity scheduling** (`kvcache_affinity.md`): routes requests to the Worker already caching the longest token prefix, "reducing cross-instance KV cache transfer overhead and improving inference throughput." A documented failure mode: if a hybrid-attention model's block size is misconfigured to the engine page size, main-group events are dropped with `block_size_mismatch` and the **hit rate is 0**. ⚠️ `[UNVERIFIED: numbers]` — no numeric hit-rate/throughput-improvement figures in the docs.

**PD disaggregation design**: the Coordinator auto-detects topology; `dispatch_capabilities` are derived from the engine connector with a **fail-closed** policy (unknown/incompatible connectors fail at NodeManager command construction rather than mid-transfer). KV-pool/store connectors (`AscendStoreConnector`, `MooncakeConnectorStoreV1`, `UCMConnector`, `LMCacheAscendConnector`) are expected as `connectors[1]` and are **not** in the capability whitelist. **Handoff and trigger instances cannot be mixed** in one cluster (HTTP 503).

## 5.6 MemFabric and MemCache — the memory-pooling foundation

Arguably the most important KV-cache-enabling subsystem in the ecosystem, and easy to miss because it is not branded "KV cache".

| Repo | ★ | Forks | Language | License |
|---|---:|---:|---|---|
| [Ascend/memfabric_hybrid](https://github.com/Ascend/memfabric_hybrid) | **7** | 4 | C++ | **Mulan PSL v2** |
| [Ascend/memcache](https://github.com/Ascend/memcache) | **11** | 4 | C++ | **Mulan PSL v2** |

PyPI: `memfabric-hybrid`, `memcache-hybrid`. Canonical homes: `gitcode.com/Ascend/memfabric_hybrid`, `gitcode.com/Ascend/memcache`.

### MemFabric — GVA-based cross-node memory pooling

"A memory-pooling software for Ascend supernodes and servers." Core idea: pool heterogeneous device memory (**DRAM | HBM**) across nodes and expose a **memory-semantic interface — `xcopy` with a global virtual address** — close to classic `memcpy`, supporting **D2RH, RH2D, RH2H, D2D**. `[V-CODE]`

**GVA (Global Virtual Address)** properties (verbatim): it is a simple `uint64`; **all processes have the same GVA start address**; **all processes' GVAs are linearly arranged and identical**. Four modules: Global Memory Management (GVA orchestration, page-table mapping strategy injected via driver); Data Operation (`xcopy` driving xDMA / LD/ST); Transport Management (QP/Jetty links for Host RDMA, Device RDMA, UDMA — **not needed** for SDMA/MTE/LD-ST); and API (BM API, SHM API, Trans API).

**Southbound hardware matrix (verbatim)** `[V-CODE]`:
- Ascend **A3 supernode**: DRAM+HBM pooling over **Device UB 1.0**; DRAM pooling over **Host RoCE**
- Ascend **A2 server**: DRAM+HBM pooling over **Device RoCE**; DRAM pooling over Host RoCE
- **Kunpeng server**: DRAM pooling over Host RoCE
- **Kunpeng supernode**: DRAM pooling over **Host UB**

Host RDMA **cannot** serve HBM pool directions; **device RDMA and Device UB 1.0 serve all of DRAM / HBM / HBM+DRAM** pool directions.

**Measured bandwidth — A3 supernode, single DIE + single CPU, DRAM and HBM pooling over UB 1.0** (MemFabric README) `[V-CODE]`:

| Direction | 1 GB | 2 GB |
|---|---|---|
| RH2D | **110.23 GB/s** | 110.19 GB/s |
| D2RH | **74.54 GB/s** | 74.54 GB/s |
| RD2D | **166.47 GB/s** | 166.47 GB/s |
| D2RD | **138.01 GB/s** | 138.01 GB/s |

**Measured bandwidth — A3 supernode, single-die cross-node** (official HiAscend article, Dec 2025; different direction naming) `[V-DOC]`:

| Direction | Size | Time (ms) | Bandwidth |
|---|---|---|---|
| RH2LD | 1 / 2 GB | 9.741 / 19.49 | **102.66 / 102.62 GB/s** |
| LD2RH | 1 / 2 GB | 14.405 / 28.81 | **69.42 / 69.42 GB/s** |
| LD2RD | 1 / 2 GB | 7.78 / 15.56 | **128.53 / 128.53 GB/s** |
| RD2LD | 1 / 2 GB | 6.45 / 12.9 | **155.04 / 155.00 GB/s** |

⚠️ The two tables differ by ~7% — likely different runs/naming conventions. **Both are reported rather than reconciled.**

**Scale**: MemFabric on the **Atlas 900 A3 SuperPoD** reaches **up to 128 TB CPU memory + 48 TB NPU HBM** mixed memory pool. Ascend hardware supports **zero-copy** RH2D/D2RH/RH2H via NPU-side networking (no staging, no control-plane messages, one shot). MemFabric maps NPU HBM and CPU memory onto the **UB 1.0 灵衢 interconnect**, completing global physical-address addressing.

**PrefixCache QPS experiment** (official article) `[V-DOC]`: Atlas A3 supernode, **4 nodes in 2P1D (D = 2 machines)**, model **DeepSeek-R1**. KVPool: each machine contributes **40 GB × 16 die = 640 GB** of CPU memory ⇒ **4 machines = 2.5 TB KVPool**, high watermark **85%**, evict **5%** above watermark. Benchmark: input 4K tokens, output 1 token, **400 distinct prefixes × 25 requests ≈ 10k requests**; hit rate constructed by ordering. Compared Baseline / memory-semantic KVPool / non-memory-semantic ("Message") KVPool. ⚠️ `[UNVERIFIED]` **The article reports the improvement only as a figure — no numeric QPS values were stated in the text.**

### MemCache — distributed KV-cache storage engine

"A high-performance distributed KVCache storage engine designed for LLM inference **and GR (generative recommendation) inference**." `[V-CODE]`

- **Object API**: batch and non-batch `put`/`get`/`exist`/`remove`; multi-level KV Block read/write interface.
- **Replicas**: an object can be placed as multiple replicas on different LocalServices (default single replica; `put` can specify replica count).
- **Transport (built on MemFabric)**: `device_rdma` (A2), `device_sdma` (A3), `host_rdma` (A2/A3) give **OneCopy cross-machine cross-medium direct access**; on Kunpeng, `host_urma` (K5); `host_shm` same-node.
- **Two components**: **MetaService** (cluster-wide pool space allocation, LocalService join/leave; single-point or **HA mode** via K8s ClusterIP Service + Lease) and **LocalService** (client library loaded into the app process *and* memory provider). Supports dynamic scale-in/out and best-effort HA with metadata recovery.
- A3 guidance: `ock.mmc.local_service.dram.size = 0GB` when HCCS is available on A3.
- **Test block size used by Huawei**: simulating DeepSeek-R1 KV, a single block is `61×128K + 61×16K = 8784 KB ≈ 8.57 MB`, spanning **122 discrete addresses**. Tests on 2× A2 nodes (8 cards each) and 2× A3 nodes (8 cards/16 dies each).
- Timeline: MemCache/MemFabric open-sourced **2025/11**; `[2025/12]` MemCache enabled as a **vllm-ascend backend**; `[2026/01]` DRAM-pooling companion released. MemCache is described as a **MindCluster** component.

## 5.7 CloudMatrix384 and UB (UnifiedBus / 灵衢)

### Primary paper

**"Serving Large Language Models on Huawei CloudMatrix384"**, arXiv **2506.12708**, published **2025-06-15**, **46 authors** (first author Pengfei Zuo). Verified from full text (`https://arxiv.org/html/2506.12708v3`). `[V-PAPER]`

**Scale and topology:**
- **384 Ascend 910 NPUs** + **192 Kunpeng CPUs** in one supernode over the UB network; "direct all-to-all communication … allowing compute, memory, and network resources to be dynamically pooled, uniformly accessed, and independently scaled."
- **16 racks: 12 compute racks** (48 Ascend 910 nodes) + **4 communication racks** housing second-tier (L2) UB switches.
- Each Ascend 910 is a **dual-die package**: two identical compute dies sharing **8 on-package memory stacks**, connected by a high-bandwidth cross-die fabric; **24 AI cube (AIC) cores per die**.
- Each node has **16 links** (one to every L2 switch chip in its sub-plane), so "a node's aggregate uplink bandwidth to the L2 fabric precisely matches its internal UB capacity, maintaining the **non-blocking** characteristic across the supernode."
- **All reported network bandwidth values in the paper are unidirectional.**

**Three network planes:**
1. **UB Plane** — primary scale-up fabric; non-blocking all-to-all over all 384 NPUs + 192 CPUs. Enables TP/EP beyond node boundaries and **"fast peer-to-peer access to pooled memory (spanning both CPU and NPU memory), which is crucial for efficiently caching model weights and KV caches."**
2. **RDMA Plane** — scale-out between supernodes; currently **RoCE**. Functions include **"(1) high-speed transfer of active KV cache data between prefill and decode NPUs during inference."** NPUs are the sole participants.
3. **VPC Plane** — Huawei **Qingtian** NICs over standard Ethernet/IP, optionally **UB-over-Ethernet (UBoE)**; control plane + access to **OBS / EVS / SFS**.

**KV-cache-specific findings:**
- **Memory tiering via EMS**: Context Caching and Model Caching are delivered via Huawei Cloud's **Elastic Memory Service (EMS)**, built on a **UB-driven disaggregated memory pool** of **CPU-attached DRAM aggregated across nodes**. Three components: **MP SDK** (KV-store-style `Put`/`Get` API), **MP Controller** (centralized control plane, DHT view, namespaces), **MP Server** (DRAM-contributing nodes; tiering + recovery). Mechanisms: **global consistent hashing** for placement, **DMA over UB** (zero-copy, bypassing CPU mediation), low-level memory primitives for remote memory registration, and **global unified memory addressing and routing — UB switches route NPU SDMA-driven access requests directly to the target MP Server's DRAM**.
- **Paged KV blocks: "128–512 tokens per block"**, chosen "based on model characteristics and UB transfer efficiency."
- **Content-addressable indexing**: each KV block has "a unique hash key derived from its token sequence and augmented with a **prefix hash**", enabling lookup and **deduplication** (identical blocks stored once).
- **Eviction**: DRAM → **EVS SSD** tier under pressure, then LRU removal; MP Server manages DRAM residency independently with its own LRU + capacity thresholds; persistence by writing all data to EVS, giving fault resilience.
- **EVS bandwidth**: per node via Qingtian card "relatively modest, typically **under 400 Gbps**", but aggregated across all **48 nodes** = "a total EVS access bandwidth of up to **48 × 400 Gbps**"; NPUs concurrently fetch fine-grained blocks from multiple nodes over the UB plane.
- **The key quotable remote-vs-local line**: *"intra-node memory access (e.g., via PCIe at **~256 GB/s**) vastly outpaces inter-node bandwidth (typically at **~25 GB/s or 200 Gbps**). As a result, **remote KV cache loading often incurs substantial latency**."* — this is the paper's argument for cache-aware scheduling.
- **Decode-phase caching**: KV generated during decode can be reused for **non-reasoning** models but **not** for reasoning models like DeepSeek-R1, because intermediate reasoning tokens shift final-response token positions, breaking position-sensitive attention validity.

**§5.4.3 Context Caching ablation** (4K-token inputs, batch of 16K total tokens per NPU, varying token reuse rate, EMS over UB vs VPC):

| Finding | Number |
|---|---|
| Reuse rate 12.5% → 50% | **1.42×** increase in prefill throughput |
| Reuse rate **90%** | **2.28×** throughput vs baseline without EMS |
| **EMS over UB vs EMS over VPC** | **up to 1.52×** prefill throughput ("directly attributable to the significantly higher bandwidth and lower latency of the UB plane") |
| TTFT at **50%** reuse with EMS on UB | **−861 ms (−34%)** vs no context caching |
| TTFT at **90%** reuse with EMS on UB | **−1,505 ms (−59%)** |

**Overall serving performance (DeepSeek-R1)**: **prefill 6,688 tokens/s per NPU**, **decode 1,943 tokens/s per NPU** while maintaining **below 50 ms TPOT**; and **538 tokens/s per NPU** sustained under a stringent **15 ms** latency constraint. ⚠️ `[UNVERIFIED: semantics]` Ratios of **3.18× / 3.75×** appear in the paper's comparison table versus "SGLang on H100 (Default)" and "DeepSeek on H800 (Profile)"; these were read as table row labels and the exact ratio semantics were not fully reconstructed.

**Model-loading context**: loading 671B DeepSeek-R1 from OBS at "a standard **2.5 GB/s** access bandwidth per bucket takes **over five minutes**"; with no caching, 8 instances cold-start at **~2,560 seconds** each.

⚠️ **Caveat**: no **"TB"** figures appear in the paper text. The **128 TB CPU + 48 TB NPU HBM** figure comes from the **MemFabric / A3 SuperPoD** article (§5.6), **not** from the CloudMatrix384 paper. Do not conflate them.

### UB-Mesh

**"UB-Mesh: a Hierarchically Localized nD-FullMesh Datacenter Network Architecture"**, arXiv **2503.20377**, 2025-03-26, 34 authors (first author Heng Liao). `[V-PAPER]` Uses a **hierarchically localized nD-FullMesh** topology rather than symmetrical node-to-node bandwidth, exploiting LLM data locality. Concrete instantiation **UB-Mesh-Pod** based on **4D-FullMesh**, built from **NPU, CPU, Low-Radix-Switch (LRS), High-Radix-Switch (HRS), NICs** over the **Unified Bus (UB)**, which "enables flexible IO bandwidth allocation and hardware resource pooling." Routing: **All-Path-Routing (APR)**. Claims: **2.04× higher cost-efficiency**, **7.2% higher network availability** vs traditional Clos, **95%+ linearity** in LLM training tasks; **64+1 backup design**.

⚠️ UB-Mesh is a **training/datacenter fabric** paper; its KV-cache relevance is indirect (it is the UB fabric family CloudMatrix's pooled-memory KV caching depends on). **No KV-cache-specific claims found in it.**

### What could NOT be verified for CloudMatrix/UB

- `[UNVERIFIED]` A per-NPU UB bandwidth figure such as **"392 GB/s"** — **searching the paper text for "392" returns zero occurrences.** Widely repeated third-party figures for CloudMatrix384 per-NPU UB bandwidth are **not confirmed by the primary source.** The paper's own bandwidth numbers are the EP/Combine per-rank figures (71/131/103 GB/s) and the 256 GB/s PCIe vs 25 GB/s inter-node comparison.
- `[UNVERIFIED]` **"UB-Mesh 2.0"** — no such paper or official page found.
- `[UNVERIFIED]` **Atlas 950 / 960 SuperPod** exact specifications and dates — Chinese news surfaced (e.g. "昇腾950白皮书正式发布") but no primary spec sheet was verified.

## 5.8 openEuler / UB Service Core / UBS / UBS IO MemStore

This is the **"UBS (Unified Bus Service)" / UBStore** thread the brief asked about. It exists — but it is an **OS/infrastructure layer, not an LLM KV-cache system.**

**openEuler 24.03 LTS SP4 "超节点" (supernode) docs** define two layers `[V-DOC]`:
- **UB OS Component (操作系统灵衢组件)**: extends OS memory management, communication, device management and virtualization to support 灵衢 (LingQu) — "heterogeneous hardware unified abstraction decoupling, **unified memory address space**, global resource scheduling, dynamic compute composition, high-performance device-to-device communication."
- **UB Service Core (灵衢系统高阶服务)**: "provides diverse compute management and scheduling for the LingQu system, building **memory pooling**, communication, IO, and virtualization capabilities."

**GitCode `openeuler/ubs-core`** ("UBS Core: The UnifiedBus Service Core") — **Star 4 / Fork 18**, MulanPSL2. Sub-projects `[V-DOC]`:

| Sub-project | Summary |
|---|---|
| **UBS Virt** | super-VM, super-container, super-process, cross-node device passthrough & virtualization |
| **UBS Memory** | very-large memory pool / memory borrowing / memory sharing |
| **UBS COMM** | cross-node data exchange / consistency / application-transparent |
| **UBS IO** | cross-device (xPU) and **cross-medium (HBM, DDR, SSD) passthrough**, supernode IO acceleration / distributed file storage |
| **UBS Engine** | software-defined compute / on-demand resource composition |
| **UBS Atomic** | UB distributed atomic capability |
| **UBS Test** | integration test suite |

**Application adaptation tiers (verbatim, with claimed gains)** `[V-DOC]`: **zero modification** (EulerOS-Matrix native POSIX interfaces) ⇒ **10%**; **SDK/RT adaptation** ⇒ **30%**; **deep rework** for the UB bus ⇒ **50%+**.

**UBSIO-MemStore** (`memstore_deployment_guide`) `[V-DOC]`: *"UBSIO-MemStore is suitable for businesses such as **securities trading** that are latency-sensitive to **in-memory KV access and cross-node replica synchronisation**. Applications access in-memory data through a **KV interface and batch-operation interfaces**, and support data protection and fault recovery via a **multi-replica** mechanism."* Two deployment modes: **融合部署** (co-resident) and **分离部署** (the `mmsd` process hosts memory management). Requires **ZooKeeper** (`mms.cm.zk_host`), `mms.cm.node.num`, `mms.net.rpc.ip_mask`, `mms.net.rpc.listen_port`; hardware includes **TaiShan 200** servers; packages `ubs-io-memstore` + `ubs-io-memstore-devel`.

**Honest assessment**: UBSIO-MemStore is a **general-purpose in-memory KV store** optimised for cross-node replica-sync latency — **its motivating example is securities trading, not LLM serving.** Its KV-cache relevance is as the **DRAM+SSD tiering backend** that the vLLM-Ascend MemCache backend configures via `ubsio.*` parameters (`ubsio.disk.path`, `ubsio.mem.size_in_gb`, `ubsio.standalone.device_count`, `ubsio.standalone.force_new_disk`).

- ⚠️ `[UNVERIFIED]` The semantics of `ubsio.wcache.evict_water_level` (referenced by vLLM-Ascend's KV pool doc). Searched the openEuler MemStore configuration guide for `wcache` — **not found**.
- ❌ `[403]` `https://www.openeuler.org/projects/ub-service-core/` returned **HTTP 403**; the whitepaper PDF link returned HTTP 200 but **served an HTML document, not a PDF** — so the whitepaper could not be read.

## 5.9 `Ascend/TransferQueue` — honest verdict: **NOT a KV-cache system**

| Field | Value |
|---|---|
| Repo | [Ascend/TransferQueue](https://github.com/Ascend/TransferQueue) |
| Description | **"An asynchronous streaming data management module for efficient post-training."** |
| Stars / forks | **151 / 50** |
| License | **Apache-2.0** |
| Created | 2026-01-09T06:55:15Z |
| Last push | 2026-09-14 |
| Latest release | **v0.1.10, 2026-08-21** (v0.1.9 2026-07-12, v0.1.8 2026-06-08, v0.1.7 2026-05-14, v0.1.6 2026-04-07) |

**Verdict: TransferQueue is not a KV-cache management system for inference.** It is a **post-training / RL data-streaming** module. `[V-CODE]`

- Unit of data is a **post-training sample** (multi-column), **not** an attention KV block.
- It exposes a **Redis-style KV interface** — `(async_)kv_put`, `(async_)kv_batch_put`, `(async_)kv_batch_get`, `(async_)kv_list`, `(async_)kv_clear` — but "KV" here means **key-value sample records**, not attention key/value tensors. **This naming is a trap for anyone scanning for KV-cache systems.**
- Primary motivation: "to **alleviate the data transfer bottleneck of the single controller `RayPPOTrainer`**. Currently, all `DataProto` objects must be routed through `RayPPOTrainer`, resulting in a single-point bottleneck."
- **Adoption/impact**: integrated into **verl** — "we achieved an end-to-end performance gain of **49.1%** for multi-modal post-training on a **128 × H100** GPU cluster" (2026-04-10); adopted by **Tencent Hunyuan's UniRL** (2026-06-09).
- **Storage backends**: `KVStorageManager` (Nov 5, 2025) abstracts KV-based backends; first backend **openYuanrong** (`gitcode.com/openeuler/yuanrong-datasystem`); **MooncakeStore** supported in beta. This is the *only* place a KV-cache engine appears, and it is used as a **generic blob store**.
- **Relation to KV cache: essentially none.** Both Yuanrong and Mooncake do appear in `AscendStoreConnector`'s `backend` list — but that is shared *storage-backend* usage, not shared purpose. Mooncake's README independently corroborates this by listing TransferQueue among Mooncake Store's adopters.
- **Provenance note**: the README references PRs/events from Oct–Nov 2025 and links `github.com/TransferQueue/TransferQueue` (a different org), while the GitHub API reports `Ascend/TransferQueue` as **created 2026-01-09**. The repo was **transferred or renamed** into `Ascend` — treat "created" as the **transfer date**, not project inception. (Compare `xllm`, §7.2, which moved orgs in the other direction.)

## 5.10 Gitee / GitCode coverage

- ❌ `[404]` `https://gitee.com/api/v5/orgs/ascend/repos?per_page=100` → HTTP 404 (`{"message":"Group"}`); `/api/v5/users/ascend/repos` → 404. The `ascend` Gitee namespace is **not exposed as a public org/user** via those endpoints.
- ❌ `[UNVERIFIED]` `https://gitee.com/search?q=KV+cache&type=repository` returned HTTP 200 but only **849 bytes** — a **JS-rendered shell containing no repository links**. **Gitee repository search is not scrapeable without a browser or login.**
- ✅ **GitCode, not Gitee, is the ecosystem's actual centre of gravity.** Verified working pages: `gitcode.com/Ascend/memcache`, `gitcode.com/Ascend/memfabric_hybrid`, `gitcode.com/Ascend/MindIE-Motor`, `gitcode.com/openeuler/ubs-core`, `gitcode.com/openeuler/yuanrong-datasystem`.
- ❌ `[404]` `https://gitcode.com/openFuyao/mooncake/blob/v0.3.7-dev/doc/zh/ub_transport.md` → `{"message":"404 Commit Not Found"}`. Referenced by the MemFabric README; the branch/tag no longer exists. Mooncake's UB documentation now lives at `docs/source/design/transfer-engine/kunpeng_ub_transport.md` on `main` — i.e. **the MemFabric↔Mooncake UB integration has since been upstreamed into Mooncake proper.**
- **openEuler**: the relevant work is the UB Service Core / 超节点 stack above. ❌ No openEuler-named *LLM* KV-cache project found separate from it.
- **openGauss**: ❌ `[UNVERIFIED]` **No openGauss KV-cache project found.** The natural inference is that openGauss's relevance would be as a *storage backend* for a tiered KV store, but no such integration was verified.

## 5.11 Huawei/Ascend — consolidated "could NOT verify" list

1. `ubsio.wcache.evict_water_level` semantics — not found in the openEuler MemStore docs. `[UNVERIFIED]`
2. Gitee repository enumeration — JS-rendered search; `/api/v5/orgs/ascend/*` 404. `[UNVERIFIED]`
3. openEuler UB Service Core whitepaper — 403 on the project page; the "PDF" served HTML. `[403/UNVERIFIED]`
4. **MindIE layer-wise KV transfer wire protocol and per-layer latency numbers** — file layout and routing semantics verified; protocol and numbers are **not**. `[UNVERIFIED]`
5. **MindIE KV Cache Pooling performance numbers** — the docs give the memory-cost formulas (4 MB/link, 512-link cap, `(cards−1)×4MB`) but **no hit-rate or latency figures**. `[UNVERIFIED]`
6. MemCache published bandwidth charts — the README references A2/A3 PNG images without inline numbers. `[UNVERIFIED]`
7. MemFabric PrefixCache QPS numbers — the article reports the improvement only as a figure. `[UNVERIFIED]`
8. `Ascend/MindIE-Service` on GitHub — 404; not published as a repo. `[404]`
9. MindIE/MemCache/MemFabric GitHub "created" dates vs content dates — mirror/transfer status undetermined. `[UNVERIFIED]`
10. **CloudMatrix384 per-NPU UB bandwidth ("392 GB/s" etc.)** — zero occurrences of "392" in the paper text. `[UNVERIFIED]`
11. **CloudMatrix384 "48 TB DRAM"** — no TB figure in the paper; that number belongs to A3 SuperPoD/MemFabric. `[UNVERIFIED for the paper]`
12. "UB-Mesh 2.0" — no such page/paper. `[UNVERIFIED]`
13. Atlas 950 / 960 SuperPod specifications — surfaced only in marketing/news. `[UNVERIFIED]`
14. openGauss KV cache — nothing found. `[UNVERIFIED]`
15. CloudMatrix paper throughput ratios (3.18× / 3.75× etc.) — appear as table row labels; exact comparison semantics not reconstructed. `[UNVERIFIED: semantics]`

Additional internal contradictions worth knowing: the vLLM-Ascend **design doc** still says "only DRAM" while the **user guide** documents SSD offload; and the design doc still calls the connector `MooncakeStoreConnectorV1`. The MindIE memory-factor docs disagree between GitHub `master` (0.01) and HiAscend 2.3.0 (0.04).

# 6. Baidu

> **Provenance.** Researched directly from FastDeploy's `develop` branch plus a dedicated deep-dive pass whose full notes are at **`kvcache-research/raw/baidu.md`** (893 lines, 82 source URLs, ~60 raw artifacts). That pass contributed the most important structural finding in this section: **Baidu's own production KV-cache system, AttentionStore, is closed source** — a second instance of the same "open client wrapper over a proprietary service" pattern as Volcengine's EIC (§4.1).

**Summary for Baidu:**
1. **FastDeploy is Baidu's main open-source KV-cache surface** — a three-tier block-based cache (`DEVICE → HOST → Storage`) on a real radix tree, plus prefix caching, **KV quantization (INT8/INT4/FP8/block-wise FP8)**, PD disaggregation with its own RDMA library, a Golang router, and pluggable external backends (`mooncake`, `attention_store`, `file_store`).
2. **Mooncake integration is real and documented** — `--kvcache-storage-backend mooncake` gives "Global Cache Pooling" across instances, with HA multi-master leader election over etcd or Redis.
3. **Baidu's own production KV cache (AttentionStore, Baidu Baige) is NOT open source** — FastDeploy open-sources only a **client wrapper around a proprietary `attentionstore_sdk`** which is **404 on PyPI**. ⚠️ A **separate** `attnstore` connector in the repo is an explicit **stub** (every method body is `# Placeholder implementation`). Do not conflate them.
4. **Name collision to avoid**: Baidu Baige's **AttentionStore** (2026) is a *different system* from the 2024 academic paper also called **AttentionStore** (arXiv **2403.19708**, Bin Gao et al. — −88% TTFT, 8.2× prefill). Same name, different authors, dates and numbers. **Never conflate the figures.**
5. Baidu claims **80–90% KV-cache hit rates** and large TTFT wins on Kunlunxin P800 — ⚠️ **vendor/blog-reported only, from a single press release republished by three outlets** (not three independent confirmations).
6. ❌ **"X-MoE" could NOT be verified as a Baidu system** (§6.7).
7. ❌ **No Baidu/FastDeploy `KVConnector` exists in vLLM** (§6.6) — negative finding.

## 6.1 PaddlePaddle/FastDeploy — repository facts

| Field | Value |
|---|---|
| Repo | <https://github.com/PaddlePaddle/FastDeploy> |
| Description | "High-performance Inference and Deployment Toolkit for LLMs and VLMs based on PaddlePaddle" |
| **Stars / forks** | **3715 / 756** |
| Open issues | 644 |
| License | **Apache-2.0** |
| Language | Python |
| Created | 2022-06-27 |
| Last push | **2026-08-26** |
| Default branch | **`develop`** (not `main`) |
| Latest release | **v2.5.0 (2026-04-09)**; v2.4.0 (2026-01-23), v2.3.0 (2025-11-11), v2.2.0 (2025-09-08) |
| Homepage | <https://paddlepaddle.github.io/FastDeploy/> |
| Topics | `ernie`, `ernie-45`, `ernie-45-vl`, `inference`, `llm`, `llm-serving`, `openai`, `serving`, `vllm` |

## 6.2 Prefix caching and the block-based KV cache

From `docs/features/prefix_caching.md` and the source tree:

- **Enable**: `--enable-prefix-caching` (CLI) / `enable_prefix_caching=True` (Python). "By default, only **first-level caching (GPU cache)** is enabled. To enable **CPU caching**, specify the `swap-space` parameter to allocate CPU cache space (**in GB**)."
- **Real implementation, not just a flag**: `cache_manager/v1/radix_tree.py` defines `class RadixTree` with `find_prefix` and `insert`, and documents the eviction order **`DEVICE → HOST → Storage`** plus an explicit **ref-count contract** (`ref_count == 0` ⇒ evictable). `[V-CODE]`
- **Key parameters**: `block_size` default **64** tokens; `kv_cache_ratio` default **0.75**; `enable_output_caching` (V1 scheduler only).
- ⚠️ **Documented model limitation**: "**The ERNIE-4.5-VL multimodal model currently does not support prefix caching.**"
- Launch example from the doc:
  ```shell
  python -m fastdeploy.entrypoints.openai.api_server \
         --model "baidu/ERNIE-4.5-21B-A3B-Paddle" \
         --port 8180 --engine-worker-queue-port 8181 \
         --metrics-port 8182 --cache-queue-port 8183 \
         --enable-prefix-caching --swap-space 50 \
         --max-model-len 8192 --max-num-seqs 32
  ```
- ⚠️ **No prefix-caching performance numbers exist in any source found.** `docs/benchmark.md` documents *methodology only*, and its example JSON is a synthetic sample line. **There is no published cache-hit-rate figure for FastDeploy prefix caching.**

## 6.3 KV-cache quantization — correcting an initial wrong guess

> ⚠️ **Correction:** my first pass concluded FastDeploy had no KV-cache-specific quantization because `docs/quantization/*.md` are about **weights**. **That was wrong.** The source contains a real KV-cache quantization enum.

`fastdeploy/model_executor/layers/quantization/kv_cache.py` defines enum **`KvCacheQuantzationTypes`**: `int8`, `float8_e4m3fn`, `float8_e4m3`, **`block_wise_fp8`**, `int8_zp`, `int4_zp`, `float8_e4m3fn_zp`. `[V-CODE]`

Set via a dict, e.g.:
```bash
--quantization '{"quantization":"mix_quant","dense_quant_type":"wint8","moe_quant_type":"wint4","kv_cache_quant_type":"block_wise_fp8"}'
```

- **Documented caveat**: "Online quantization of KVCache to `block_wise_fp8` is only supported by the **AppendAttn** backend."
- **Also documented**: KVCache is **not quantized by default** when using `wint4`/`wint8`/`block_wise_fp8`/`wfp8afp8` for weights.
- ⚠️ **Internal inconsistency to flag**: FastDeploy's quantization table lists KVCache precision as only `BF16` (or `INT8/BF16` for MixQuant), yet `--quantization` accepts `kv_cache_quant_type: block_wise_fp8` (FP8 KV). **The README table does not document FP8 KV cache.**

**ERNIE 4.5 Technical Report** additionally documents ERNIE's production KV quantization (extracted from the 27 MB PDF, 2025-06-29): KV cache quantized **4/8-bit, head- and channel-wise**, supporting **FP8/INT8/INT4**, with **static + blocked RHT fused into W_v/W_o**, and **custom FP8-max clipping** giving **~2% accuracy gain on reasoning**. `[V-REPORT]`

**FastDeploy 2.0 blog**: **8-bit KV cache compression → ~40% extra QPS**.

## 6.4 Global Cache Pooling — Mooncake-backed cross-instance KV pool

From `docs/features/global_cache_pooling.md` — the brief did not mention this feature, and it is FastDeploy's most significant ecosystem-facing KV capability.

**What it is**: "Global Cache Pooling allows **multiple FastDeploy instances to share KV Cache through a distributed storage layer**", enabling (a) **cross-instance cache reuse**; (b) **PD disaggregation optimization** — "Prefill and Decode instances can share cache seamlessly"; (c) **reduced computation**.

**Architecture**: a **Mooncake Master Server** provides metadata/coordination; FastDeploy instances (Prefill, Decode, or Standalone) all connect to a **MooncakeStore** shared pool. **Baidu therefore uses the same Mooncake Store substrate as Alibaba, Huawei, Tencent, ByteDance, Ant Group and Moonshot.**

**Integration point**: `--kvcache-storage-backend mooncake` (alternatives: `attention_store`, `file_store`). Related: `--enable-output-caching`, `--cache-transfer-protocol rdma`, `--splitwise-role prefill|decode|mixed`, `--router`.

| Parameter | Description | Default |
|---|---|---|
| `metadata_server` | HTTP metadata server URL | Required |
| `master_server_addr` | Master server address | Required |
| `global_segment_size` | Memory each TP process shares to global shared memory (bytes) | **1 GB** |
| `local_buffer_size` | Local buffer for data transfer (bytes) | **128 MB** (⚠️ three different values appear across FastDeploy docs) |
| `protocol` | `rdma` or `tcp` | **`rdma`** |
| `rdma_devices` | RDMA device names | auto-detect |

**HA deployment — leader election with etcd or Redis.** "**A single master is a single point of failure**; if it crashes, cluster operations pause. For production, run multiple `mooncake_master` instances that perform leader election through a coordination backend."

- **etcd** (`run_ha.sh`): a **3-node etcd cluster** (client ports 12379/22379/32379) does election and metadata storage; **3 HA masters** on rpc 8081/8082/8083; leader published to **`mooncake-store/mooncake_cluster/master_view`**. Both URLs use the **`etcd://`** prefix.
- **Redis** (`run_ha_redis.sh`): a **single Redis instance** (port 6399) does **lease-based election** — "Use this to avoid introducing etcd as an extra component." `master_view` is a Redis HASH. Build flags: `-DSTORE_USE_REDIS=ON -DUSE_REDIS=ON` (+`libhiredis-dev`) or `-DSTORE_USE_ETCD=ON -DUSE_ETCD=ON`.
- **The HA scripts run a genuinely sound failover test**: warm prompt **A** on `server_0`, verify the hit on `server_1`; read the leader's `rpc_port` from the backend and `kill -9` it; then warm a **brand-new** prompt **B** and reuse it on `server_1` — "Using a fresh prompt ensures the hit can only come from the new leader's global pool, **not stale local cache** from step 4." Worth calling out as good methodology.
- **Observability**: `grep -E "storage_cache_token_num" log_*/api_server.log` — "If `storage_cache_token_num > 0`, the instance successfully read cached KV blocks from the global pool."
- Example scripts: `examples/cache_storage/{run.sh, run_03b_pd_storage.sh, run_ha.sh, run_ha_redis.sh}`.

⚠️ **No quantitative performance numbers are published for Global Cache Pooling** — no TTFT, hit-rate or throughput figures. Documented operationally, not benchmarked.

## 6.5 PD disaggregation and the self-developed RDMA KV-transfer library

- **Two transmission paths**: **intra-node** = `cudaMemcpyPeer` between GPUs in one node; **inter-node** = a **self-developed RDMA C++ library** at `cache_manager/transfer_factory/kvcache_transfer/`.
- `--cache-transfer-protocol {rdma, ipc}`, plus `--rdma-comm-ports`, `--pd-comm-port`, `--router`. `KVCACHE_RDMA_NICS` env var (comma-separated) or auto-detection.
- Router = **Golang** (`golang_router`), bundled as a binary in the Python package. ⚠️ **Two different Router launch paths are documented**: `python -m fastdeploy.golang_router.launch` (`disaggregated.md`) vs `python -m fastdeploy.router.launch --splitwise` (newer pooling doc) — an inconsistency worth flagging.
- **Legacy `SplitwiseScheduler` is deprecated**: the doc says *"Using SplitwiseScheduler is not recommended. It is recommended to use the Router."* It used **Redis ≥ 6.2.0**.

### The published `KVTransferManager` vs Mooncake benchmark — Baidu's best concrete number

A **rare case of a Chinese vendor publishing a head-to-head benchmark against another Chinese vendor's open-source component, with exact hardware and parameters stated.**

**Test scenario**: **single Mellanox ConnectX-7 400G NIC (single port)**; `BATCH_SIZE = 1538`; block size 1K–256K; **single pressure thread**. Mooncake measured with `transfer_engine_bench` under **identical hardware and parameters**.

| Block size | KVTransferManager | Mooncake | FastDeploy advantage |
|---|---|---|---|
| 1K | **10.67 GB/s** | 1.54 GB/s | **6.9×** |
| 2K | **17.53 GB/s** | 3.40 GB/s | 5.2× |
| 4K | **28.85 GB/s** | 6.95 GB/s | 4.2× |
| 8K | **36.56 GB/s** | 12.48 GB/s | 2.9× |
| 16K | **41.73 GB/s** | 23.42 GB/s | 1.8× |
| 32K | **43.55 GB/s** | 31.58 GB/s | 1.4× |
| 64K | **44.46 GB/s** | 38.39 GB/s | 1.2× |
| 128K | **44.86 GB/s** | 40.11 GB/s | 1.1× |
| 256K | **45.01 GB/s** | 40.71 GB/s | 1.1× |

README's own conclusion: "**Bandwidth Saturation Capability**: Under multi-threaded high-pressure scenarios, both KVTransferManager and Mooncake can fully utilize the 400G network card bandwidth, achieving transmission performance close to the theoretical hardware limit (**approximately 50 GB/s**)."

**How to read this honestly**: the advantage is **concentrated at small block sizes** (6.9× at 1K) and **vanishes by 128–256K** (1.1×). The fair interpretation is much lower per-transfer overhead / better small-transfer pipelining, with both converging to NIC line rate for large transfers. **Single-thread, single-NIC only** — says nothing about multi-NIC aggregate performance. **Self-published by FastDeploy**; Mooncake's maintainers have not, to my knowledge, responded.

- **Supported architectures**: **Hopper GPUs**, **Kunlun XPU**, **Ampere GPUs** (latter requires `KVCACHE_GDRCOPY_FLUSH_ENABLE`). The Kunlun XPU entry is notable — **Kunlunxin (昆仑芯) is Baidu's own AI-chip arm**.
- Dependencies: `pyzmq`, `pybind11[global]`, `libibverbs-dev`, `librdmacm-dev`.

## 6.6 ⭐ AttentionStore — Baidu's own production KV cache, and it is CLOSED SOURCE

This is the structural counterpart to Volcengine's EIC, and it is the most important finding about Baidu.

**`fastdeploy/cache_manager/transfer_factory/mooncake_store/attention_store.py`** (295 lines; PR **#5823** merged **2026-01-22** by `liyonghua0910`) is a **client wrapper around a proprietary SDK**:

```python
import attentionstore_sdk.api.common.common_pb2 as common_pb2
from attentionstore_sdk.sdk import AttentionStoreSDK, Tokens
from attentionstore_sdk.utils.err import AttentionStoreSDKError
from attentionstore_sdk.client.client import AttentionType
```

If the import fails, `_ATTENTIONSTORE_AVAILABLE = False` and the class raises `ImportError("Please install attentionstore_sdk to run Fastdeploy with attentionstore_sdk.")`.

> ❌ **`attentionstore_sdk` is NOT publicly distributed.** Verified 2026-09-15: `https://pypi.org/pypi/attentionstore-sdk/json` → **HTTP 404**; `https://pypi.org/pypi/attentionstore_sdk/json` → **HTTP 404**. `requirements.txt` lists only `p2pstore`. **Conclusion: Baidu open-sources the AttentionStore *client integration* only; the AttentionStore server + SDK are closed source.**

**⚠️ A second, different `attnstore` connector is a stub.** `fastdeploy/cache_manager/v1/storage/attnstore/connector.py` (140 lines) defines `AttnStoreScheduler(StorageScheduler)` and `AttnStoreConnector(StorageConnector)`, but **every method body is literally `# Placeholder implementation`** returning `False`/`None`/`[]`/`0`. **Do not mistake this scaffold for a working backend.**

**`AttentionStoreConfig` defaults** (leaking the internal data model): `namespace=default_ns`, `pod_name=default_pod`, `model_version=v0`, `shard_id/shard_num=0/1`, `layer_num=1`, **`block_token_size=64`**, `bytes_per_shard_layer_per_block=1024`, `device_id/dp_id=0/0`, `splitwise_role=mixed`. SDK surface: `AttentionStoreSDK(...)`, `sdk.match(tokens, start_match_block_idx, timeout)`, `sdk.read(...)`, `sdk.write(...)`, `sdk.flush_token_index(...)`, `wait_for_sdk_ready(timeout=300, delta_t=5)`. Enable with `--kvcache-storage-backend attention_store`.

### AttentionStore as a production system (Baidu Baige) — ⚠️ vendor-reported

Sources: CSDN (2026-04-02), IT168 (2026-04-02), GeekPark. ⚠️ **All three are press-release republications of the same text — one source, not three.** No paper, no repo, no independent measurement.

**What it is**: "百度智能云旗下**百度百舸团队**近日推出了一套自主研发的KV Cache系统 —— **AttentionStore**", validated on **Kunlunxin P800** with **DeepSeek** models.

| Claim | Value |
|---|---|
| KV Cache **hit rate** | **80% – 90%** |
| TTFT improvement, 8K+ context | **2–5×** (validation detail: **50–80% stable gain**) |
| TTFT, **64K** context | **6.2× lower** vs the engine's default Chunk-Prefill caching |
| Overall throughput, multi-turn | **5.4×** |
| DRAM→HBM transfer efficiency | **4×** vs baseline |

**Validation setup**: PD-disaggregated, **DeepSeek R1 671B**, **Kunlunxin P800**, **2 Prefill nodes, TP4 / DP4**.

**Architecture as described**:
- **Decoupled from the inference engine** — runs as an **independent process on each inference node**, so the KV cache **survives inference-process restart, fault recovery and version upgrades**. This is the same architectural bet as Tair KVCM and EIC.
- Host cache media: **shared memory + SSD**; recovers quickly after restart via a **local index table**.
- **Multi-tier: HBM → DRAM → SSD.**
- **Global KV cache index** aggregating per-node block metadata — **BlockHash**, storage medium (**HBM/DRAM/SSD**), with real-time create/destroy events, forming a **Host → Blocks** mapping.
- **Cache-aware scheduling**: the scheduler narrows to nodes with high expected hit rate, then scores by match length **and** read efficiency of the medium, rather than "available" → "optimal".
- **Read acceleration**: parallelizes reads across tiers (fast + slow media issued concurrently) rather than serially; shared memory marked as **huge pages** to cut page-table entries; **full-lifecycle page-locking (锁页)** to prevent swap-out during transfer.

### 🚨 Name collision — flag prominently

**arXiv 2403.19708** (2024-03-23, Bin Gao et al.) is **ALSO titled "AttentionStore"** — a hierarchical-KV-cache academic contribution with **different** numbers (−88% TTFT, 8.2× prefill, 22×, −56% cost), different authors and a different year. **Baidu Baige's AttentionStore is 2026, Kunlunxin-specific. These are two different systems. Cite them separately; never conflate the figures.**

## 6.7 Baidu AI Cloud: Qianfan / ERNIE prompt caching

**Qianfan (千帆) exposes TWO separate cache features** with different APIs, prices and model coverage:

**(a) Automatic `prompt cache`** (doc updated **2025-04-11**): "系统会自动为所有用户开启 prompt cache 模式，用户无需修改代码即可享受该功能" — **automatic, all users, no code change**. Hits billed at **40% of prompt price**. ⚠️ **Covers `ERNIE-4.0-Turbo-8K` only.** The doc explicitly warns **hit probability is not 100%** even for identical contexts.

**(b) Explicit `前缀缓存` (prefix cache)** (doc updated **2026-01-05**): `POST /v2/caching` returns a `cache_id` (`mode: common_prefix`, `ttl` in seconds), used via `cache_id`. **Invite-only (邀测).** Hits at **20–25% of input price** plus storage at **0.000017 元 / 1K tokens / hour**. Full price table captured (e.g. `deepseek-v3.1-250821`: input 0.004 → hit 0.0008 CNY/1K).

> ⚠️ **Key gap: the explicit Qianfan prefix cache is NOT offered for ERNIE models** as of the 2026-01-05 doc revision, and the automatic prompt cache covers only `ERNIE-4.0-Turbo-8K`. **Any claim that Qianfan offers prefix caching "for ERNIE" is not supported by these docs.**

**ERNIE 4.5 Technical Report serving numbers** (2025-06-29, extracted directly from the PDF):
- ERNIE-4.5-300B-A47B: **56K input / 18K output TPS per H800 node, *without* prompt caching**; 2K in / 400 out; **50 ms TPOT**.
- **EP8 vs EP16 decode: +70%**. **MTP: +60%** output throughput.
- **FastDeploy 2.0 blog**: **56K/21K tok/s**, "**17% improvement in output TPS over the baseline reported in the original ERNIE 4.5 technical report**". **Cross-check performed: 18K → 21K = +16.7% ≈ 17% — the two Baidu documents are numerically consistent**, which strengthens both.
- Deployment supports **KUNLUNXIN P800**, Iluvatar BI-V150, Hygon K100AI, Enflame S60.
- (Adjacent, **not** a KV-cache technique but the numbers most often cited for ERNIE serving: **PLAS sparse attention** (2025-09-12) on InfiniteBench `longbook_sum_eng`, ~113K avg input — ERNIE-4.5-21B-A3B **+48% QPS, +36% decode, −48% TTFT, −46% E2E**; ERNIE-4.5-300B-A47B **+23% QPS, +33% decode, −30% TTFT**.)

## 6.8 Baidu research: LU-KV (ICML 2026) and the `baidu-baige` org

**LU-KV** — *Predicting Future Utility: Global Combinatorial Optimization for Task-Agnostic KV Cache Eviction* — **arXiv 2602.08585**, submitted 2026-02-09 (v2 2026-06-01), authors Ziyao Tang, Pengkun Jiao, Xinhang Chen, Wei Liu, Shiyong Li, Jingjing Chen. **Baidu Baige + Fudan**, accepted at **ICML 2026**. Repo **`baidu-baige/LU-KV`** (6★, Apache-2.0, a **fork of NVIDIA/kvpress**).

| Result | Number |
|---|---|
| 80% compression, relative loss | **0.52%** |
| Mistral-7B + KeyDiff | **40.54 → 46.21** (recovers 84% of the gap to Full-KV) |
| RULER @ 80% | **29.53 → 37.48 (AdaKV) → 69.98** |
| multi-key-3 | **1.00% → 67.40%** |

Also discovered the **`baidu-baige` GitHub org**: `LoongForge` (567★), `LoongFlow` (475★), `LoongSage` (164★), `Loong-Megatron` (8★), `LU-KV` (6★).

**Other Baidu repos checked**: `PaddleNLP` (12,973★, push 2026-05-23) carries a paged-MLA KV kernel `batch_mla_with_paged_kv_cache.cu` and **Kunlun3/P800 KV-block dispatch kernels** (`kunlun3cpp/free_and_dispatch_block.xpu`, `recover_block.xpu` — the `free_and_dispatch`/`recover` pairing being the kind of primitive used for KV-block ownership transfer). `PaddleFormers` (12,985★) has `cache_utils.py`, **HF-derived** (Google/HF/NVIDIA copyright) with **CPU layer offload + non-default prefetch stream** — model-side, not serving-side. `Paddle Serving` (924★): **no KV-cache feature found**.

**`baidu/vLLM-Kunlun`** — **466★ / 102 forks**, Apache-2.0, branch `v0.25.1-dev`, pushed **2026-09-15**. Supports **only Kunlun3/P800**. Its feature matrix lists only TP/EP/Graph/Quantization — **no KV-cache line** — yet real prefix-cache code exists: `vllm_kunlun/tests/test_prefill_attention_prefix_cache.py` (469 lines) exercising `kunlun_ops.prefill_attention(is_prefix_cache=True)`. ⚠️ **Its KV Cache Pool docs are 0-byte placeholders** (`KV_Cache_Pool_Guide.po`, `kv_pool_mooncake.po`, `multi_node_pd_disaggregation_{mooncake,llmdatadist}.po`; no source `.md` on any branch). The path **exactly mirrors `vllm-ascend`**, which *does* have a real published guide — so Kunlun inherited Ascend's documentation skeleton. **Do not cite Kunlun as having a documented KV Cache Pool.**

## 6.9 Baidu — clean negative findings and what could NOT be verified

**Verified negatives (checked, not assumed):**
- ❌ **No Baidu/FastDeploy `KVConnector` in vLLM.** Every connector in `vllm/main` was enumerated: `hf3fs, hisparse, lmcache_integration, mooncake, moriio, nixl, offloading` (+ a flexkv example). **No `paddle`/`baidu`/`kunlun` entry.**
- ❌ **Mooncake does not list Baidu.** Mooncake's README integration timeline mentions SGLang, vLLM, TensorRT-LLM, vLLM-Ascend, LMCache, NIXL, Speculators — **zero** mentions of Baidu, FastDeploy, PaddlePaddle or Kunlunxin. The relationship is **one-way**: FastDeploy *consumes* Mooncake (and benchmarks against it).
- ❌ **No Baidu involvement in SGLang HiCache** (PRs #26560, #38292, #16137 — authors `huanpengchu`, `jojoakm`; no Baidu attribution).

**Could NOT verify:**
- ❌ **"X-MoE" as a Baidu system** — **explicitly unverifiable.** English and Chinese searches found nothing Baidu-authored. The only real `xMoE` is **Microsoft's** `microsoft/unilm/xmoe` (2022 sparse-MoE *architecture* paper, not a serving system, no KV cache). **Decoys identified and debunked**: two `developer.baidu.com` articles titled "XLarge-MoE" with **identical titles but mutually contradictory numbers** (2048 vs 3072 cards; 28 vs 33 days; 330B vs 10T tokens) and "MoE-X" — both say only **"某研究团队"/"某平台研发团队"** (never "Baidu"), cite no repo/arXiv/weights, and the **"MoE-X" article actually describes Ant Group/InclusionAI's Ling-flash-2.0 / Ling-1T / Ming-Flash-Omni**. These are AI-generated content-farm pages. **State that X-MoE is unverifiable and cite LU-KV + FastDeploy as Baidu's actual KV-cache work instead.**
- ❌ **Prefix-caching performance numbers** — none exist in any source found (§6.2).
- ❌ **Official Kunlunxin P800 KV-cache spec sheet** — only FastDeploy code/configs and vendor blogs. P800 benchmark configs do exist in FastDeploy (e.g. `eb45-32k-wint4-p800-tp8.yaml`: `max_model_len: 32768, max_num_seqs: 160, tensor_patch_size: 8`, `quantization: wint4`, `gpu_memory_utilization: 0.9`).
- ❌ **Whether Baidu contributes to Mooncake** — cannot be confirmed or denied; GitHub exposes no employer for contributor accounts.
- ⚠️ **PaddlePaddle/Paddle core** was not verified — flagged as a gap.
- ⚠️ **Doc inconsistencies found**: a multimodal prefix-cache support contradiction, two Router module paths, three different `local_buffer_size` values, and a release-note PR-number mismatch.
- ⚠️ **Research-methodology limits for this section**: the **arXiv API returned HTTP 429 for the entire session** (10+ attempts over ~40 min) and **Semantic Scholar also 429'd**, so **no systematic arXiv sweep was possible** — additional Baidu papers may exist. `pdftotext`/`pypdf` were unavailable and `pip install` was sandbox-blocked, so the 27 MB ERNIE 4.5 PDF was parsed with a hand-rolled zlib/`Tj` extractor; ⚠️ **that PDF's embedded spacing is corrupted, so naive keyword search over it yields false zeros.**

# 7. Moonshot AI, xLLM, and other China-ecosystem systems

## 7.1 Moonshot AI — `checkpoint-engine`

`https://github.com/MoonshotAI/checkpoint-engine` — **1005★ / 108 forks**, 9 open issues, **MIT**, Python, created **2025-09-08**, last push **2026-09-04**. Latest release **v0.4.2 (2026-07-04)**; prior v0.4.1 (2026-06-08), v0.4.0.

> ⚠️ **Important scoping note**: checkpoint-engine is **not a KV-cache system.** It is "a simple middleware to **update model weights** in LLM inference engines — a critical step in reinforcement learning." It appears in this report because it is Moonshot's KV-adjacent infrastructure and because it is the open-sourced, production version of **Mooncake P2P Store**. Do not describe it as KV cache management.

- **Headline result**: in-place update of **Kimi-K2 (1 trillion parameters) across thousands of GPUs in ~20 seconds**. Applied in **K1.5 and K2 production training**.
- **Two update modes**: **Broadcast** (default, fastest, for many instances updating synchronously) and **P2P** (for instances joining dynamically while others serve; uses **`mooncake-transfer-engine`** to P2P-send weights from CPUs in existing instances to GPUs in new instances).
- **Broadcast pipeline** (3 stages): H2D (weights from disk/trainer to GPU) → broadcast among checkpoint-engine workers (results land in a **CUDA IPC buffer shared with the inference engine**) → reload (engine copies the subset it needs). Transfers are arranged in a pipeline with overlapped communication and copy; pipelining costs GPU memory, and the system falls back to serial execution when memory is insufficient. The engine is controlled over a **ZeroMQ socket**.
- **P2P bucket assignment** is optimized per sender-receiver pair to saturate each side's network bandwidth.
- **Published benchmark table** (all with **vLLM v0.10.2rc1**, via `examples/update.py`):

| Model | Device info | GatherMetas | Update (Broadcast) | Update (P2P) |
|---|---|---|---|---|
| GLM-4.5-Air (BF16) | 8×H800 TP8 | 0.12 s | 3.47 s (3.02 GiB) | 4.12 s (3.02 GiB) |
| Qwen3-235B-A22B-Instruct-2507 (BF16) | 8×H800 TP8 | 0.33 s | 6.22 s (2.67 GiB) | 7.10 s (2.68 GiB) |
| DeepSeek-V3.1 (FP8) | 16×H20 TP16 | 1.17 s | 10.19 s (5.39 GiB) | 11.80 s (5.41 GiB) |
| Kimi-K2-Instruct (FP8) | 16×H20 TP16 | 1.33 s | 14.36 s (5.89 GiB) | 17.49 s (5.91 GiB) |
| DeepSeek-V3.1 (FP8) | 256×H20 TP16 | 0.80 s | 11.33 s (8.00 GiB) | 11.81 s (8.00 GiB) |
| Kimi-K2-Instruct (FP8) | 256×H20 TP16 | 1.22 s | 16.04 s (8.00 GiB) | 16.75 s (8.00 GiB) |

Notes the README provides: a "256-GPU TP16 setup" means 16 vLLM instances × 16-way TP; P2P timings were measured for updating **no more than two nodes (16 GPUs)** out of the cluster; each GPU is bound to its NUMA node for stable H2D. FP8 requires additional vLLM patches.
- Related Moonshot claim from the Mooncake README: the checkpoint-engine/Mooncake P2P Store updates Kimi-K2 across thousands of GPUs in **~20 s**.

## 7.2 xLLM — moved to the OpenAtom Foundation

- **`https://github.com/jd-opensource/xllm` → HTTP 301 → `https://github.com/xLLM-AI/xllm`.** The API resolves `repos/jd-opensource/xllm` to `full_name: "xLLM-AI/xllm"`.
- Current metadata: **1570★ / 298 forks**, 213 open issues, **Apache-2.0**, C++, created **2025-08-12**, last push **2026-09-15**. Latest release **v0.10.1 (2026-07-14)**; v0.10.0 (2026-07-01), v0.9.1 & v0.9.0 (2026-04-14).
- Description: "A high-performance inference engine for LLM, VLM, DiT and REC models, optimized for diverse AI accelerators. **It is hosted in OpenAtom Foundation.**" (OpenAtom 开放原子开源基金会 — China's foundation for open-source projects.) This is a **governance** signal: the project has been donated to a foundation, not merely company-hosted.
- **KV-cache feature** (README, 2025-12-05): "🎉 We build **hybrid KV cache management based on [Mooncake](https://github.com/kvcache-ai/Mooncake)**, supporting **global KV cache management with intelligent offloading and prefetching**." Corroborated by Mooncake's README (2025-08-23): "xLLM high-performance inference engine builds hybrid KV cache management based on Mooncake, supporting global KV cache management with intelligent offloading and prefetching."
- ⚠️ No quantitative KV-cache benchmark from xLLM verified. ❌ Not verified whether xLLM exposes a vLLM-style `KVConnector` API.

## 7.3 Zhipu (智谱) — verified upstream SGLang HiCache contribution

This is a genuinely verifiable Chinese-vendor contribution to a mainstream open-source KV-cache subsystem, and it was **not** in the brief.

Source: 证券日报 report dated **2026-04-30** on Zhipu's technical report **《ScalingPain：超大规模 CodingAgent 推理实践》** ("ScalingPain: Large-Scale CodingAgent Inference Practice") — <http://m.zqrb.cn/gscy/gongsi/2026-04-30/A1777483618281.html>.

Verified claims from that report:
- GLM-5 series in **CodingAgent** scenarios: **system throughput up to +132%** (range stated as 10%–132%), and **abnormal-output rate reduced from ~10 in 10 000 to under 3 in 10 000**.
- Zhipu "not only located and fixed the **KVCache cross-node reuse race in a PD-disaggregated architecture** in its own inference stack, but went further and found and fixed in the **SGLang source code** a **missing load-timing issue in the HiCache module**; the fix was **accepted by the SGLang open-source community**."
- Scale context: Zhipu reports "日均数亿次的 CodingAgent 调用规模" (hundreds of millions of CodingAgent calls per day).

> ⚠️ The +132% figure is **self-reported by Zhipu** and is a *system* throughput result, not isolated to KV caching. The SGLang HiCache timing fix being merged is reported by the same article; I did **not** independently locate the specific SGLang PR. Flagging as **partially verified** (the report exists; the PR link does not).

## 7.4 Ant Group's own KV-cache-adjacent open source: `inclusionAI`

Ant Group's AI open-source org is **`inclusionAI`** (confirmed: repos describe themselves as "developed by InclusionAI team, **Ant Group**"). It has **66 public repos**. Scanning all of them for KV/cache/inference relevance, the only KV-cache-relevant item is:

- **`inclusionAI/dInfer`** — **480★ / 49 forks**, **Apache-2.0**, last push **2026-02-11**; "dInfer: An Efficient Inference Framework for **Diffusion Language Models**". Its architecture explicitly includes "model, **diffusion iteration manager**, decoder and **KV-cache manager**" as separate components, and its CLI exposes **prefix caching** (`--cache prefix`, `--cache dual`, `--prefix_look 16`).

❌ **Not verified**: any Ant Group open-source *serving* KV-cache system at the scale of Tair KVCM or FlexKV. Ant Group's verified KV-cache contributions are the **Mooncake integration engineering (§2.2)** and the **DeepSeek-R1-671B HiCache −84% TTFT result (§2.2)**.

Other Ant Group repos that touch memory/transport but **not** KV caching: `inclusionAI/asystem-amem` (119★, "a NCCL extension library, designed to efficiently offload GPU memory allocated by the NCCL"), `inclusionAI/Awex` (176★, RL train↔inference weight sync), `inclusionAI/vllm-ling-v3` (2★, Apache-2.0, a vLLM adaptation for Ling v3 — private-feeling, tiny), `inclusionAI/sglang` (3★ fork).

## 7.5 Accelerator-vendor KV transport backends (the brief's item 7 list)

The strongest evidence for Chinese accelerator vendors in the KV-cache transport layer is **Mooncake's own repo**, which is the single best cross-vendor index:

1. **Mooncake `MAINTAINERS.md` partner/contributor logo list** includes: Alibaba Cloud, **Ant Group**, Approaching AI, **Huawei**, NVIDIA, **Moore Threads (摩尔线程)**, Tencent, **Volcengine (ByteDance)**, AMD, **IEIT Systems (浪潮/Inspur)**, **Sunrise**, **Hygon (海光)**, AWS, **MetaX (沐曦)**, MadSys, Moonshot.
2. **Mooncake's README names the accelerators explicitly — this is the decisive source.** Verbatim: *"**Broad support for heterogeneous transports and accelerators.** Transfer Engine provides unified data transfer across diverse protocols, including TCP, RDMA, AWS EFA, NVMe-oF, NVLink, HIP, Barex, CXL, and Ascend-family transports. When built with the corresponding runtime, Transfer Engine can detect accelerator memory and select suitable transport paths for efficient data movement across **CUDA, MUSA, HIP, MACA, Cambricon MLU, and Ascend-enabled environments**."* — so **Cambricon MLU and MACA (MetaX) ARE explicitly supported**, contrary to my initial expectation.
3. **Mooncake's hardware logo wall** (README) includes, by name: **Cambricon**, **Moore Threads**, **MetaX**, **T-Head (平头哥 — Alibaba's semiconductor arm)**, **Biren Technology**, **Hygon**, **Sunrise**. So Biren and T-Head are partners even though they are absent from the contributor wall.
4. **Mooncake PyPI wheel matrix**: `mooncake-transfer-engine` (CUDA ≤12.9), `-cuda13` (CUDA 13.0/13.1), `-non-cuda`, **`-npu` (Ascend NPU)**, **`-musa` (Moore Threads MUSA)**, `-efa` (AWS), `-rocm` (AMD).
5. **Mooncake's official supported-protocol table** (<https://kvcache-ai.github.io/Mooncake/getting_started/supported-protocols.html>) is the cleanest enumeration of KV data-plane transports in the Chinese ecosystem:

| Protocol | Hardware required | Use case | Maturity |
|---|---|---|---|
| `tcp` | standard network | general purpose | Primary (Python API) |
| `rdma` | RDMA-capable NIC | high-performance, low-latency | Primary |
| `efa` | AWS EFA instance | AWS high-performance (libfabric SRD) | Primary |
| `nvmeof` | NVMe-oF storage | direct NVMe storage access | Advanced |
| `nvlink` | NVIDIA MNNVL | inter-node GPU communication | Advanced |
| **`musa`** | **Moore Threads GPU + MTLink** | **intra-node GPU IPC/P2P** | Advanced |
| `nvlink_intra` | NVIDIA NVLink | intra-node GPU communication | Advanced |
| `hip` | AMD ROCm/HIP | AMD GPU communication | Advanced |
| `barex` | RDMA-capable NIC | bare-metal RDMA extension | Advanced |
| `cxl` | CXL-capable hardware | **memory pooling and sharing** | Advanced |
| `shm` | none (POSIX shm, same host) | same-host DRAM copies without NIC loopback | Advanced |
| **`ascend`** | **Huawei Ascend NPU** | Ascend NPU communication | Advanced |
| `tpu` | Google TPU (PJRT) | TPU KV-cache transfer via host-DRAM staging | Experimental (TENT) |
| `mpcomm` | RDMA-capable NIC(s) | multi-NIC memory pooling with NIC/QP load balancing | — |

   Note that **MUSA is documented as *intra-node* GPU IPC/P2P**, not a cross-node KV transport — a meaningful limitation for KV-cache pooling on Moore Threads hardware. Nothing beyond `tcp`/`rdma`/`efa` is rated "Primary" (fully supported).

6. **Moore Threads MUSA**: a dedicated engineering post exists — "Mooncake Transfer Engine MUSA Wheel 正式发布：从 PyPI 安装到 vLLM-MUSA 与 SGLang 接入" (2026-07-27), <https://blog.mthreads.com/blog/AI/2026-07-27-mooncake-transfer-engine-musa/>. **The page body is JS-rendered; my fetch returned only 417 characters of text, so I could NOT verify any technical numbers from it.** The existence of the post and the `-musa` PyPI wheel are verified; the contents are not.
7. **Cambricon (寒武纪)**: VERIFIED as supported — named explicitly in the README accelerator list ("Cambricon MLU") and present in the hardware logo wall. But there is **no in-tree `cambricon_transport` directory in CODEOWNERS and no dedicated PyPI wheel**, so support is via runtime detection rather than a named transport module. **Do not claim a dedicated Cambricon transport.**
8. **MetaX (沐曦)**: VERIFIED as supported — "**MACA**" in the README accelerator list is MetaX's compute architecture, and `hardwares/MetaX_logo.png` is in the hardware wall. Also supported by the third-party **UCM** project, which lists "MACA (MetaX C500)". No dedicated PyPI wheel verified.
9. **Hygon (海光)**: partner logo in the contributor wall. But **no Hygon/DCU transport appears in CODEOWNERS, the protocol table, or the wheel matrix** — no Hygon DCU KV-transfer backend could be verified in code. Treat as a partnership/ecosystem signal only.
10. **Biren (壁仞)**: partner logo in the hardware wall (`hardwares/biren_logo.png`). **Not in the accelerator list, CODEOWNERS, protocol table, or wheels.** No verified KV-cache work. Partnership signal only.
11. **T-Head (平头哥)**: Alibaba's semiconductor arm appears in Mooncake's hardware logo wall. No transport, protocol or wheel verified.
12. **IEIT Systems (浪潮) and Sunrise**: partner logos only. No verified KV-cache work.

Also relevant:
- **Moore Threads / MUSA and `musa_gpu_support`**: Tair KVCache itself contains `docs/develop/musa_gpu_support.md`, and its Bazel `3rdparty/gpus/musa/` + `musa_configure.bzl` — i.e. **Alibaba's Tair KVCache has explicit Moore Threads MUSA build support** in-tree. This is a concrete, non-obvious finding: Tair KVCM's client/connector is being built for MUSA GPUs.
- **Kunlunxin (昆仑芯, Baidu's chip)**: KsanaLLM lists "Kunlunxin XPU: P800" as supported hardware (§3.2). See also §6 (Baidu).

## 7.6 Other Chinese vendors in the brief's item-7 list — status

| Vendor / project | Status |
|---|---|
| **MiniMax** | ❌ No MiniMax-authored KV-cache system verified. The `fw-ai/minimax-kernels` repo surfaced in search is **Fireworks AI's** kernels *for* MiniMax models — **not** a MiniMax project. Do not misattribute. |
| **Zhipu** | ✅ Verified — see §7.3 (SGLang HiCache timing fix, +132% system throughput claim). |
| **StepFun (阶跃星辰)** | ⚠️ Search surfaced only a model release ("Step 3.7 Flash", up to **400 tokens/s** generation speed, <https://m.it168.com/article_6932343.html>). ❌ **No StepFun KV-cache system verified.** |
| **01.AI (零一万物)** | ❌ No 01.AI KV-cache system verified. |
| **Moore Threads** | ⚠️ Partially verified — dedicated `mooncake-transfer-engine-musa` PyPI wheel, a first-class **`musa`** protocol in Mooncake (**intra-node GPU IPC/P2P only**), and MUSA build support inside Tair KVCache (`3rdparty/gpus/musa/`, `docs/develop/musa_gpu_support.md`). Their MUSA blog post's *contents* are unverified (JS-rendered). See §7.5. |
| **Cambricon (寒武纪)** | ✅ **Verified as supported** — "Cambricon MLU" named in Mooncake's README accelerator list + hardware logo wall. ⚠️ But no dedicated transport module in CODEOWNERS and no PyPI wheel. See §7.5. |
| **Hygon (海光)** | ⚠️ Partner logo only. ❌ No transport, protocol or wheel verified in code. See §7.5. |
| **MetaX (沐曦)** | ✅ **Verified as supported** — "**MACA**" in Mooncake's README accelerator list + `hardwares/MetaX_logo.png`; also "MACA (MetaX C500)" in the third-party UCM project. ⚠️ No dedicated wheel. See §7.5. |
| **Biren (壁仞)** | ⚠️ Partner logo only (`hardwares/biren_logo.png`). ❌ No verified KV-cache work. See §7.5. |
| **T-Head (平头哥)** | ⚠️ Partner logo only (Alibaba's semiconductor arm). ❌ No verified KV-cache work. See §7.5. |
| **Tsinghua / 趋境科技** | ✅ Verified — Approaching.AI (§2.3), KTransformers (19 518★), Mooncake Store codeownership. |

---

# 8. Cross-cutting observations

1. **Two architectural philosophies coexist.** Alibaba's Tair KVCM is a **centralized metadata service** that deliberately does *not* touch KV bytes ("KVCM 只管理'数据在哪、能不能读写'，不经手数据本身") and explicitly **avoids requiring RDMA**. FlexKV is a **library** that owns both control and data planes, using a **distributed RadixTree with per-node snapshots** plus a Redis Global Meta Store, and explicitly rejects centralized indexing to avoid single-point bottlenecks. EIC is a **managed distributed store** with Namespace/QoS isolation. Mooncake Store is an **object store + Transfer Engine** split. These are genuinely different bets about where metadata scale, fault isolation and latency live.

2. **Mooncake is the de-facto Chinese-ecosystem KV transport substrate.** It is integrated into vLLM, SGLang HiCache, TensorRT-LLM, RBG, vLLM-Ascend, FlexKV, xLLM, LMCache, lmdeploy, checkpoint-engine, vLLM-Omni, and SGLang EPD, and ships wheels for CUDA, non-CUDA, Ascend NPU, Moore Threads MUSA, AMD ROCm, and AWS EFA. Both Huawei (`ascend_transport`, owned by `@ascend-direct-dev`) and AMD own in-tree transport modules.

3. **RBG's design choice is the interesting one for KV caching**: it makes the external KV store a **first-class role in a Kubernetes role group**, so that service discovery, startup ordering and lossless updates between inference and cache are handled by the orchestrator rather than by hand. KEP-74's multi-turn numbers (−91.94% TTFT, +39.80% throughput) are among the most concrete and reproducible published KV-offload results from any Chinese vendor.

4. **SGLang HiCache is the common integration point**, with **11 registered backends** (`file, sim, nixl, mooncake, npu_memcache, hf3fs, aibrix, eic, simm, mori, shm`) plus `flexkv`/`lmcache`/`mmap` in-tree. Its minimal contract — `get` / `exist` / `set` — is why so many vendors (Alibaba 3FS, Ant Group + Approaching.AI + Alibaba Mooncake, NVIDIA NIXL, ByteDance EIC, AIBrix/PrisKV, FlexKV) could plug in.

5. **Benchmark discipline varies wildly.** The reproducible end of the spectrum: RBG KEP-74 (exact model, versions, engine versions, cache size, dataset, script), checkpoint-engine (exact model/GPU/TP/bucket sizes), HiSim (MAPE per metric per case), PolarKVCache (hardware/model/context/baseline all named). The non-reproducible end: Tair KVCache's product page (90%/30%/20%/5–10× with no protocol), FlexKV's press-release trio (60%/13%/16%), EIC's throughput triples, Zhipu's +132%. **A report should present these two classes separately.**

6. **The "evaluate-before-you-buy" tooling is an unusual, notable Alibaba contribution.** Tair KVCM ships an Optimizer with LiteHit (capacity-independent exact LRU hit-rate projection from a single replay) and a Pareto capacity-vs-hit-rate tradeoff scan, plus HiSim for predicting engine performance without GPUs. No other vendor in this survey ships an equivalent capacity-planning toolkit. That is arguably Tair KVCache's most differentiated open-source artifact — more so than KVCM itself.

7. **Adoption signals are strongest for Mooncake (Kimi handling 75% more requests), FlexKV (merged into vLLM/Dynamo/TRT-LLM/SGLang mainlines), Tair KVCM (Alibaba Group RTP-LLM production + a `qwen_bailian` trace converter) and KsanaLLM (Tencent-internal Polaris nameserver build path).** Star counts are a poor maturity proxy here — FlexKV (351★) is in four mainstream engine mainlines, while Tair KVCache (255★) is 9 months old. EIC has essentially **zero** public GitHub footprint yet is a production product serving ByteDance's ad-recommendation stack.

8. **A distinctive Chinese-ecosystem governance pattern: donating a company project to foundation or community stewardship.** This happened at least **four** times in this survey — **xLLM** moved `jd-opensource` → **`xLLM-AI`** and is now "hosted in the **OpenAtom Foundation**"; **veRL** moved `volcengine` → **`verl-project`**; **AIBrix** moved from ByteDance → **`vllm-project`**; **TransferQueue** was transferred into the **`Ascend`** org. Practical consequence for anyone citing these: **the `owner/repo` string in older literature is frequently stale**, and GitHub's API "created" date may reflect the **transfer date, not inception** (TransferQueue's "created 2026-01-09" is demonstrably not an inception date — its README references Oct/Nov 2025 work). **Resolve redirects before quoting a repo path.** Two of the brief's own repo paths were already stale (`jd-opensource/xllm`, and `Tencent/AngelPTM` which does not exist).

9. **The open-source / closed-source boundary is not where you would guess — and the dominant commercial pattern is an *open client shim over a proprietary service*.** The Chinese KV-cache systems in this survey split three ways:
   - **(a) Fully open source** — FlexKV, Mooncake, Tair KVCM, MemFabric/MemCache, MindIE, FastDeploy (the framework), AIBrix, InfiniStore, ShadowKV, LU-KV.
   - **(b) Open client shim over a proprietary service** — **two instances, from two different vendors, and they are structurally identical**:
     - **Volcengine EIC**: Apache-2.0 integration code sits in the **SGLang** (PR #10271) and **LMCache** (PR #1930) mainlines while the store itself is a paid Volcengine product — **no public repo**, and `eic`/`eic-client`/`volcengine-eic` on PyPI all **404**.
     - **Baidu AttentionStore** (百度百舸): Apache-2.0 `attention_store.py` in **FastDeploy** wraps a proprietary `attentionstore_sdk` — `attentionstore-sdk` and `attentionstore_sdk` on PyPI both **404**. (Baidu additionally ships a *second* `attnstore` connector that is an honest-to-goodness **placeholder stub** with `# Placeholder implementation` in every method body.)
   - **(c) Commercial-only, no OSS at all** — **Tair KVCache** and **PolarKVCache**.
   **Consequence for the report: counting "in-tree SGLang HiCache backends" or "FastDeploy storage backends" as open-source KV-cache systems over-counts by at least two.** Both affected vendors present these backends in open-source code without prominently disclosing that the backend is a paid service — so the failure mode is easy to hit and worth flagging explicitly. Note also that in **both** cases the merged backend code leaks useful design detail (`eic_storage.py`'s hard-coded H20 GPU↔NIC affinity table; `attention_store.py`'s `block_token_size=64`, shard/layer fields and `splitwise_role`), which is the best available evidence about a system whose documentation is otherwise closed.

10. **Two benchmark traditions coexist and must be cited differently.** The **paper / engineering tradition** states hardware, model, engine versions and baselines — CloudMatrix384's context-caching ablation (1.42× at 50% reuse, 2.28× at 90%, TTFT −861 ms / −1,505 ms, UB vs VPC 1.52×); RBG KEP-74 (−91.94% TTFT / +39.80% throughput / −58.83% ITL on Qwen3-32B with a full config and script); FastDeploy's `KVTransferManager` vs Mooncake table (6.9× at 1K blocks decaying monotonically to 1.1× at 256K, both saturating at ~50 GB/s on a 400G NIC); UCM's TTFT table; HiSim's per-metric MAPE per case; checkpoint-engine's per-model update times; ShadowKV's 6.25% / 0.26% cache fractions; PolarKVCache's named hardware+baseline table. The **marketing tradition** states a single percentage with no protocol — Tair KVCache's 90% / 30% / 20% / 5–10×; FlexKV's 60% / 13% / 16%; EIC's ~3× / −67%; Zhipu's +132%; UCM's "3–10× / up to 8× TTFT". **Report the first class as findings and the second class as vendor claims**, and note that several vendors ship *both* kinds (Alibaba and Tencent both do, which is itself informative about their internal benchmark discipline).

11. **The strongest single number in this whole survey belongs to Ant Group, and it is easy to miss.** A named Ant Group team (Tingwei Huang, Yongke Zhao) contributed the SGLang HiCache Mooncake integration and reported **−84% TTFT on cache hits for DeepSeek-R1-671B under PD-disaggregated deployment on in-house online QA traffic**. That is a larger, more production-shaped result than most Chinese vendors publish, from an organization whose KV-cache contribution the brief initially mis-located (RBG is Alibaba Cloud + Xiaohongshu; Ant Group's contribution is Mooncake/HiCache). Conversely, **RBG's KEP-74 benchmark (−91.94% TTFT) is the most reproducible published KV-offload result from any Chinese source** — exact model, engine versions, cache size, dataset and script are all given.

---

# Sources

### GitHub API metadata (read 2026-09-15 via authenticated `gh api`)
- https://github.com/alibaba/tair-kvcache
- https://github.com/ZhihanYan/tair-kvcache
- https://github.com/li-xiao-qing/tair-kvcache
- https://github.com/taco-project/FlexKV
- https://github.com/Tencent/KsanaLLM
- https://github.com/Tencent/TurboTransformers
- https://github.com/vllm-project/vllm-ascend
- https://github.com/Ascend/TransferQueue
- https://github.com/MoonshotAI/checkpoint-engine
- https://github.com/xLLM-AI/xllm (and https://github.com/jd-opensource/xllm → 301)
- https://github.com/PaddlePaddle/FastDeploy
- https://github.com/sgl-project/rbg
- https://github.com/kvcache-ai/Mooncake
- https://github.com/kvcache-ai/ktransformers
- https://github.com/sgl-project/sglang
- https://github.com/bytedance/InfiniStore
- https://github.com/aibrix/PrisKV
- https://github.com/inclusionAI/dInfer
- https://github.com/ai-dynamo/aiconfigurator
- https://github.com/kunluninsight/LatencyPrism

### Tair KVCache — raw documents (fetched from branch `main`)
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/README.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/README_zh.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/docs/optimizer.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/hisim/README.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/docs/design/module_architecture.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/docs/design/basic_concepts.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/kv_cache_manager/optimizer/README.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/kv_cache_manager/optimizer/liteHit/README.md
- https://raw.githubusercontent.com/alibaba/tair-kvcache/main/hisim/pyproject.toml

### Tair KVCache — product, articles
- https://www.aliyun.com/product/kvcache
- https://cn.aliyun.com/product/kvcache
- https://help.aliyun.com/zh/redis/product-overview/tair-kvcache/
- https://developer.aliyun.com/article/1704765 (即将开源 | 阿里云Tair KVCache Manager)
- https://developer.aliyun.com/article/1703191
- https://developer.aliyun.com/article/1659103 (Tair KVCache：打造以缓存为中心的大模型Token超级工厂)
- https://developer.aliyun.com/article/1717041 (拆墙：Tair KVCache × SGLang × 千问 × NVIDIA)
- https://mp.weixin.qq.com/s/apZIaiI5zazumEYNQHTdHg (Tair KVCM architecture — full text retrieved)
- https://help.aliyun.com/zh/polardb/polardb-for-mysql/user-guide/polarkvcache-inference-acceleration (PolarKVCache)

### SGLang HiCache / Mooncake / Ant Group / RBG
- https://www.lmsys.org/blog/2025-09-10-sglang-hicache/
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/backend_factory.py
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/eic/README.md
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/aibrix_kvcache/README.md
- https://github.com/sgl-project/rbg/blob/main/keps/74-mooncake-integration/README.md
- https://github.com/sgl-project/rbg/blob/main/README.md
- https://rolebasedgroup.github.io/
- https://m.sohu.com/a/936180014_355140/ (SGLang × RBG — attribution + acknowledgement list)
- https://developer.aliyun.com/article/1700851 (基于 SGLang RBG + Mooncake 打造生产级云原生大模型推理平台)
- https://github.com/kvcache-ai/Mooncake/blob/main/MAINTAINERS.md
- https://github.com/kvcache-ai/Mooncake/blob/main/.github/CODEOWNERS
- https://github.com/kvcache-ai/Mooncake/blob/main/README.md
- https://github.com/kvcache-ai/Mooncake/blob/main/docs/source/design/architecture.md
- https://kvcache-ai.github.io/Mooncake/
- https://www.usenix.org/system/files/fast25-qin.pdf (Mooncake FAST'25 paper)
- https://www.usenix.org/system/files/fast25_slides-qin.pdf
- https://vllm.ai/blog/mooncake-store
- https://lmsys.org/blog/2026-04-29-p2p-update/
- https://github.com/kvcache-ai/Mooncake/pull/759 (heterogeneous_ascend NPU↔GPU KV transfer)
- https://zhidx.com/p/575150.html (趋境科技/Approaching.AI Series A — identity + Mooncake co-builders)

### Tencent — FlexKV, KsanaLLM
- https://github.com/taco-project/FlexKV/blob/main/README.md
- https://github.com/taco-project/FlexKV/blob/main/README_zh.md
- https://github.com/taco-project/FlexKV/blob/main/LICENSE
- https://github.com/taco-project/FlexKV/blob/main/docs/dist_reuse/README_en.md
- https://github.com/taco-project/FlexKV/blob/main/docs/eviction_policy/README_en.md
- https://github.com/taco-project/FlexKV/blob/main/docs/vllm_adapter/README_en.md
- https://github.com/taco-project/FlexKV/blob/main/flexkv/integration/sglang/README.md
- https://github.com/vllm-project/vllm/pull/34328 (FlexKV → vLLM mainline)
- https://github.com/ai-dynamo/dynamo/pull/5858 (FlexKV → Dynamo)
- https://github.com/sgl-project/sglang/pull/29701 (FlexKV → SGLang mainline)
- https://github.com/sgl-project/sglang/pull/31781
- https://cloud.tencent.cn/developer/article/2654280 (腾讯这项省Token技术…)
- https://www.donews.com/news/detail/4/6512672.html (腾讯云FlexKV合入全球三大主流大模型推理框架)
- https://github.com/Tencent/KsanaLLM/blob/main/README.md
- https://github.com/Tencent/KsanaLLM/blob/main/README_cn.md

### Moore Threads / accelerator blogs
- https://blog.mthreads.com/blog/AI/2026-07-27-mooncake-transfer-engine-musa/ (body JS-rendered — unverified)
- https://blog.mthreads.com/blog/tags/kv-cache/

### Moonshot / xLLM / Zhipu
- https://github.com/MoonshotAI/checkpoint-engine/blob/main/README.md
- https://arxiv.org/abs/2507.20534 (Kimi-K2 Technical Report)
- https://github.com/xLLM-AI/xllm/blob/main/README.md
- http://m.zqrb.cn/gscy/gongsi/2026-04-30/A1777483618281.html (智谱 GLM-5 ScalingPain — SGLang HiCache fix)

### Huawei / Ascend
- https://github.com/vllm-project/vllm-ascend
- https://docs.vllm.ai/projects/ascend/
- https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/docs/source/user_guide/feature_guide/kv_pool.md
- https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/docs/source/developer_guide/Design_Documents/KV_Cache_Pool_Guide.md
- https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/docs/source/developer_guide/Design_Documents/layerwise_and_sparse_kv_cache_offloading.md
- https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/docs/source/user_guide/feature_guide/ucm_deployment.md
- https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/vllm_ascend/distributed/kv_transfer/__init__.py
- https://raw.githubusercontent.com/vllm-project/vllm-ascend/main/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py
- https://github.com/vllm-project/vllm/issues/48203 (layerwise/sparse KV offload RFC)
- https://raw.githubusercontent.com/kvcache-ai/Mooncake/main/docs/source/design/transfer-engine/ascend_transport.md
- https://raw.githubusercontent.com/kvcache-ai/Mooncake/main/docs/source/design/transfer-engine/ascend_direct_transport.md
- https://raw.githubusercontent.com/kvcache-ai/Mooncake/main/docs/source/design/transfer-engine/heterogeneous_ascend.md
- https://raw.githubusercontent.com/kvcache-ai/Mooncake/main/docs/source/design/transfer-engine/kunpeng_ub_transport.md
- https://github.com/kvcache-ai/Mooncake/pull/619 (Ascend Transport)
- https://github.com/kvcache-ai/Mooncake/pull/740 (ascend direct transport)
- https://github.com/kvcache-ai/Mooncake/pull/759 (heterogeneous_ascend NPU↔GPU KV transfer)
- https://github.com/kvcache-ai/Mooncake/pull/1274, /pull/2499
- https://kvcache-ai.github.io/Mooncake/getting_started/supported-protocols.html
- https://pypi.org/project/mooncake-transfer-engine-npu/
- https://github.com/Ascend/MindIE-LLM
- https://github.com/Ascend/MindIE-Motor
- https://raw.githubusercontent.com/Ascend/MindIE-LLM/master/docs/zh/user_guide/feature/kv_cache_pool.md
- https://raw.githubusercontent.com/Ascend/MindIE-LLM/master/docs/zh/user_guide/feature/mempool.md
- https://raw.githubusercontent.com/Ascend/MindIE-LLM/master/docs/zh/user_guide/feature/prefix_cache.md
- https://raw.githubusercontent.com/Ascend/MindIE-LLM/master/docs/zh/user_guide/feature/kv_cache_int8.md
- https://raw.githubusercontent.com/Ascend/MindIE-Motor/master/docs/zh/user_guide/features/kv_cache_store/README.md
- https://raw.githubusercontent.com/Ascend/MindIE-Motor/master/docs/zh/design/kv_conductor.md
- https://raw.githubusercontent.com/Ascend/MindIE-Motor/master/docs/zh/user_guide/features/kvcache_affinity.md
- https://raw.githubusercontent.com/Ascend/MindIE-Motor/master/docs/zh/design/pd_disaggregation.md
- https://mindie-motor.readthedocs.io/
- https://www.hiascend.com/document/detail/zh/mindie/230/mindiellm/llmdev/mindie_llm0538.html (KV Cache 池化 — authoritative ZH page)
- https://www.hiascend.com/document/detail/en/mindie/300/LLMframe/llmdev/user_guide/feature/kv_cache_pool.md (⚠️ title says pooling, body is the architecture overview — do not cite for pooling)
- https://github.com/Ascend/memfabric_hybrid ; https://github.com/Ascend/memcache
- https://raw.githubusercontent.com/Ascend/memfabric_hybrid/master/README.md
- https://raw.githubusercontent.com/Ascend/memcache/master/README.md
- https://gitcode.com/Ascend/memcache ; https://gitcode.com/Ascend/memfabric_hybrid
- https://pypi.org/project/memfabric-hybrid/ ; https://pypi.org/project/memcache-hybrid/
- https://www.hiascend.com/developer/techArticles/20251203-5 (昇腾超节点百TB级内存语义池化应用实践)
- https://arxiv.org/abs/2506.12708 (Serving Large Language Models on Huawei CloudMatrix384) ; https://arxiv.org/html/2506.12708v3
- https://arxiv.org/abs/2503.20377 (UB-Mesh)
- https://docs.openeuler.org/zh/docs/24.03_LTS_SP4/unifiedbus/unifiedbus/introduction/introduction.html
- https://docs.openeuler.org/zh/docs/24.03_LTS_SP4/unifiedbus/unifiedbus/zh/memstore_deployment_guide.html
- https://docs.openeuler.org/zh/docs/24.03_LTS_SP4/unifiedbus/unifiedbus/zh/memstore_configuration_guide.html
- https://gitcode.com/openeuler/ubs-core ; https://gitcode.com/openeuler/yuanrong-datasystem
- https://www.openeuler.org/projects/ub-service-core/ — HTTP 403
- https://github.com/Ascend/TransferQueue ; https://github.com/verl-project/verl/pull/5401 ; https://github.com/Tencent-Hunyuan/UniRL

### ByteDance / Volcengine
- https://github.com/sgl-project/sglang/pull/10271 (EIC → SGLang HiCache, merged 2025-10-01)
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/eic/eic_storage.py
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/eic/README.md
- https://github.com/LMCache/LMCache/pull/1930 (LMCache `eic://` connector, merged 2025-11-21)
- https://console.volcengine.com/eic ; https://www.volcengine.com/docs/85848/1749188 (JS shell; `未授权访问`)
- https://mp.weixin.qq.com/s/tasDqXf0Gxr3o_WCJ2IJUQ (火山引擎高性能分布式 KVCache（EIC）核心技术解读)
- https://mp.weixin.qq.com/s/b_4YhTa96Zeklh23lv8qBw (火山引擎 EIC 解析：构建以 KVCache 为中心的推理新基建)
- https://github.com/bytedance/InfiniStore ; https://bytedance.github.io/InfiniStore/
- https://github.com/ByteDance-Seed/ShadowKV ; https://ByteDance-Seed.github.io/ShadowKV/
- https://arxiv.org/abs/2410.21465 (ShadowKV, ICML 2025 Spotlight)
- https://arxiv.org/abs/2504.02263 (MegaScale-Infer, SIGCOMM 2025) ; DOI 10.1145/3718958.3750506
- https://arxiv.org/abs/2603.20616 (MixedDimKV) ; https://arxiv.org/abs/2506.11309 (SwiftSpec, ASPLOS'26)
- https://arxiv.org/abs/2502.20766 (FlexPrefill, ICLR 2025 Oral) ; https://arxiv.org/abs/2510.07318 (AHN)
- https://github.com/vllm-project/aibrix ; https://github.com/vllm-project/aibrix/releases
- https://aibrix.readthedocs.io/latest/_sources/designs/aibrix-kvcache-offloading-framework.rst
- https://github.com/aibrix/PrisKV ; https://github.com/vllm-project/aibrix/pull/1807
- https://github.com/verl-project/verl ; verl `docs/perf/rollout_kv_offload.md`
- https://docs.byteplus.com/en/docs/ModelArk/1398933 ; https://docs.byteplus.com/en/docs/ModelArk/1396491 (Ark prompt caching)
- https://github.com/volcengine/ark-runtime-go
- https://github.com/bytedance/flux ; https://github.com/bytedance/xpu-perf (was ByteMLPerf)

### Baidu / FastDeploy
- https://github.com/PaddlePaddle/FastDeploy (branch `develop`)
- https://paddlepaddle.github.io/FastDeploy/
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/features/prefix_caching.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/zh/features/prefix_caching.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/features/global_cache_pooling.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/zh/features/global_cache_pooling.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/features/disaggregated.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/zh/features/disaggregated.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/best_practices/Disaggregated.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/examples/cache_storage/README.md
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/fastdeploy/cache_manager/transfer_factory/kvcache_transfer/README.md (KVTransferManager vs Mooncake benchmark)
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/fastdeploy/cache_manager/transfer_factory/kvcache_transfer/README_CN.md

### Baidu — AttentionStore, Qianfan, LU-KV, Kunlun
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/fastdeploy/cache_manager/transfer_factory/mooncake_store/attention_store.py (closed-SDK client wrapper)
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/fastdeploy/cache_manager/v1/storage/attnstore/connector.py (placeholder stub)
- https://github.com/PaddlePaddle/FastDeploy/pull/5823 (attention_store wrapper, merged 2026-01-22)
- https://pypi.org/pypi/attentionstore-sdk/json → HTTP 404 ; https://pypi.org/pypi/attentionstore_sdk/json → HTTP 404
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/fastdeploy/model_executor/layers/quantization/kv_cache.py (`KvCacheQuantzationTypes`)
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/fastdeploy/cache_manager/v1/radix_tree.py
- https://raw.githubusercontent.com/PaddlePaddle/FastDeploy/develop/docs/parameters.md
- https://www.csdn.net/article/2026-04-02/159761936 ; https://m.it168.com/article_6922635.html ; https://w.geekpark.net/news/362076 (AttentionStore press release — ONE source republished 3×)
- https://arxiv.org/abs/2403.19708 (⚠️ DIFFERENT "AttentionStore" — 2024 academic paper; name collision)
- https://ernie.baidu.com/blog/publication/ERNIE_Technical_Report.pdf (ERNIE 4.5 tech report)
- https://ernie.baidu.com/blog/posts/fastdeploy2.0/ (FastDeploy 2.0 blog)
- https://ernie.baidu.com/blog/zh/posts/plas/ (PLAS sparse attention — not KV cache)
- https://arxiv.org/abs/2602.08585 (LU-KV, ICML 2026) ; https://github.com/baidu-baige/LU-KV
- https://cloud.baidu.com/doc/Qianfan/... (千帆 prompt cache 2025-04-11; 前缀缓存 2026-01-05, 邀测)
- https://github.com/baidu/vLLM-Kunlun ; https://github.com/PaddlePaddle/PaddleNLP ; https://github.com/PaddlePaddle/PaddleFormers
- https://github.com/vllm-project/vllm/tree/main/vllm/distributed/kv_transfer (connector enumeration — negative finding)

### Additional Alibaba systems, Zhipu, Mooncake transports
- https://help.aliyun.com/zh/polardb/polardb-for-mysql/user-guide/polarkvcache-inference-acceleration (PolarKVCache)
- http://m.zqrb.cn/gscy/gongsi/2026-04-30/A1777483618281.html (智谱 GLM-5 ScalingPain — SGLang HiCache fix)
- https://github.com/sgl-project/sglang/blob/main/python/sglang/srt/mem_cache/storage/backend_factory.py
- https://kvcache-ai.github.io/Mooncake/getting_started/supported-protocols.html
- https://blog.mthreads.com/blog/AI/2026-07-27-mooncake-transfer-engine-musa/ (body JS-rendered; unverified)
- https://github.com/aibrix/PrisKV ; https://github.com/vllm-project/aibrix/pull/1807
- https://github.com/bytedance/InfiniStore
- https://github.com/moonshotai/checkpoint-engine ; https://arxiv.org/abs/2507.20534

### Raw artifacts saved during this research
- `kvcache-research/raw/cnv/` — Tair docs, FlexKV docs, Alibaba Cloud page extractions, PolarKVCache extraction, EIC article extractions, FastDeploy docs, Mooncake README/protocol table, SGLang HiCache blog text, RBG KEP-74, Tair WeChat article full text (`wx_tair.txt`)
- `kvcache-research/raw/huawei_ascend.md` — full Huawei/Ascend deep-dive (838 lines, 20-item unverified list, ~65 source URLs)
- `kvcache-research/raw/baidu.md` — Baidu deep-dive (**893 lines, 82 source URLs**, ~60 raw artifacts; source of the AttentionStore closed-source finding and the LU-KV/ICML 2026 result)
- `kvcache-research/raw/bytedance.md` — ByteDance deep-dive (**714 lines, 75-entry source list**, includes the EIC negative results, the ByteDance-Seed paper inventory, and the Ark prompt-caching API verification)
- `kvcache-research/raw/` also contains artifacts written by concurrent sibling agents (e.g. `hw_*`, `fd-*`, `dy_*`, `lmc_*`) — those were **not** authored by this report and were used only as cross-checks.

---

## Method note

Tools used: authenticated `gh api` (GitHub REST, 5000 req/hr) for all repo/file/release/contributor metadata; `curl` + a custom HTML→text extractor for vendor pages; `web_search` with parallel English and Chinese queries. **`curl` against `raw.githubusercontent.com` proved unreliable in this environment** — on timeout it does not create the output file, which silently broke several batch fetches; switching to `gh api <repo>/contents/<path> -H "Accept: application/vnd.github.raw"` was reliable and is the recommended approach for reproducing this work. Several vendor pages (Volcengine docs, Moore Threads blog, Aliyun developer articles, HiAscend docs) are JS-rendered and required the `\uXXXX`-unescaping technique described in §5.5; their bodies could not be fully recovered in some cases and are flagged inline.
