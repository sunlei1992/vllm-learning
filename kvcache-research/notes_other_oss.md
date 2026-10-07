# Open-Source KV-Cache / KV-Centric Inference Serving — Additional Projects

**Report date:** 2026-09-15 (all metrics captured on 2026-09-15 unless stated otherwise).
**Scope:** AIBrix, KServe, LMCache spin-outs (PegaFlow / Inferact / Tensormesh / PrisKV-PrisDB), other named OSS KV-cache projects, serving engines' KV features, 2025–2026 KV-cache papers — plus *discovery* of additional popular projects not in the original list.

> **Method / access notes (important for reproducibility and honesty).**
> * `https://api.github.com` was **rate-limited (HTTP 403)** from this network for the whole session, so all star/fork/pushed-at figures in this report come from **`https://ungh.cc/repos/OWNER/REPO`** (a public GitHub API mirror that returns the same fields) or from GitHub's own HTML pages (`stargazerCount` in the embedded JSON). Release tags/dates come from `https://ungh.cc/repos/OWNER/REPO/releases` and `https://github.com/OWNER/REPO/releases.atom`.
> * `https://raw.githubusercontent.com/...` was **unreachable (timeout)** from this network; raw files were fetched via the mirrors `https://ghfast.top/https://raw.githubusercontent.com/...`, `https://gh-proxy.com/...`, and `https://cdn.jsdelivr.net/gh/OWNER/REPO@BRANCH/PATH`.
> * Star counts move daily. Treat the numbers as "as of 2026-09-15", not as stable facts.
> * ⚠️ **`ungh.cc/releases` is unreliable and was cross-checked against `releases.atom`** — it reported "no releases" for several repos that demonstrably have them (see §8 item 19). Where the two disagreed, the atom feed won.
> * GitHub's **`/search` endpoint is blocked** for anonymous clients from this network, so discovery used topic star-listings plus `web_search`. GitHub **topic pages were thin** (`/topics/kv-cache-offloading` returned exactly one repo) — see §8 item 22 for the resulting bias.
> * Everything I could **not** verify is flagged inline and collected in the final "Could not verify" section. I did not invent any star count, version, date, arXiv ID, or benchmark number.

---

## 0. Quick landscape snapshot (stars as of 2026-09-15)

| Project | Stars | Forks | Latest release (date) | One-line role |
|---|---|---|---|---|
| [vllm-project/vllm](https://github.com/vllm-project/vllm) | 91,813 | 22,221 | (continuous) | Reference engine; defines the `KVConnector` contract everyone else plugs into |
| [sgl-project/sglang](https://github.com/sgl-project/sglang) | 35,982 | 8,871 | — | RadixAttention + HiCache (L1 HBM / L2 host / L3 shared) |
| [ai-dynamo/dynamo](https://github.com/ai-dynamo/dynamo) | 8,082 | 1,584 | — | NVIDIA datacenter-scale framework; KV Block Manager (KVBM) |
| [kvcache-ai/Mooncake](https://github.com/kvcache-ai/Mooncake) | 6,572 | 1,222 | — | Kimi/Moonshot KV-centric store + transfer engine (the substrate TENT operates on) |
| [kserve/kserve](https://github.com/kserve/kserve) | 5,911 | 1,671 | **v0.20.0 (2026-08-06)**; v0.21.0-rc0 (2026-09-10) | Kubernetes model-serving; `LLMInferenceService` + llm-d |
| [vllm-project/aibrix](https://github.com/vllm-project/aibrix) | **5,089** | **694** | **v0.7.0 (2026-06-18)** | K8s control plane + KVCache offloading + KV-aware gateway |
| [llm-d/llm-d](https://github.com/llm-d/llm-d) | 4,537 | 768 | v0.9.0 (2026-08-17) | K8s-native distributed inference; EPP prefix-cache routing |
| [kubernetes-sigs/gateway-api-inference-extension](https://github.com/kubernetes-sigs/gateway-api-inference-extension) | 768 | 313 | v1.6.1 (2026-09-10) | `InferencePool` + EndpointPicker (GIE) |
| [taco-project/FlexKV](https://github.com/taco-project/FlexKV) | 351 | 73 | — | KV manager merged into vLLM (v0.17.2+), Dynamo and SGLang |
| [bytedance/InfiniStore](https://github.com/bytedance/InfiniStore) | 438 | 44 | 0.2.33 (2025-03-23) | KV store for inference clusters; integrated via LMCache (⚠️ stale since 2025-11) |
| [aibrix/PrisKV](https://github.com/aibrix/PrisKV) | 59 | 8 | none | RDMA + TCP + shared-memory KV store with GDR; AIBrix L2 backend |
| [ByteDance-Seed/ShadowKV](https://github.com/ByteDance-Seed/ShadowKV) | 313 | — | — | ICML'25 Spotlight KV-cache compression (ByteDance Seed) |
| [LMCache/LMCache](https://github.com/LMCache/LMCache) | 11,812 | 1,887 | v0.5.5rc7-xpu (2026-09-12); operator-v0.5.5 (2026-09-15) | The de-facto external KV cache layer |
| [kvcache-ai/ktransformers](https://github.com/kvcache-ai/ktransformers) | **19,518** | — | — | ⚠️ **missed by the original list** — heterogeneous inference/fine-tune framework (KV-cache-derived name), very active |
| [uccl-project/uccl](https://github.com/uccl-project/uccl) | 1,516 | 173 | — | GPU comms library incl. KV transfer |
| [ovg-project/kvcached](https://github.com/ovg-project/kvcached) | 1,386 | 161 | — | Virtualized elastic KV cache for GPU sharing |
| [Zefan-Cai/KVCache-Factory](https://github.com/Zefan-Cai/KVCache-Factory) | 1,380 | 179 | — | Unified KV compression library |
| [ai-dynamo/nixl](https://github.com/ai-dynamo/nixl) | 1,256 | 441 | — | NVIDIA Inference Xfer Library |
| [NVIDIA/kvpress](https://github.com/NVIDIA/kvpress) | 1,209 | 178 | v0.5.4 (2026-07-02) | KV cache compression toolkit |
| [Zefan-Cai/R-KV](https://github.com/Zefan-Cai/R-KV) | 1,212 | 196 | — | NeurIPS'25 KV compression for reasoning models |
| [novitalabs/pegaflow](https://github.com/novitalabs/pegaflow) | 204 | 27 | v0.24.4 (2026-09-09) | **External KV cache service (Rust), vLLM connector** |
| [llm-d/llm-d-kv-cache](https://github.com/llm-d/llm-d-kv-cache) | 177 | 156 | v0.9.0 (2026-06-14) | KV indexer / offloader / event libraries |

---

## 1. AIBrix

**Repo:** https://github.com/vllm-project/aibrix · **as of 2026-09-15:** 5,089 stars, 694 forks, 51 watchers, created 2024-06-10, last push 2026-09-15, default branch `main`, **Apache-2.0**.
**Maintainer:** now developed **under the `vllm-project` GitHub org** (ByteDance-originated; the project was announced through the vLLM project blog as a "Scalable, Cost-Effective Control Plane for vLLM" — https://vllm.ai/blog/aibrix-release). Contributors/leads visible in release notes and blogs: Jiaxin Shan, Haiyang Shi, Le Xu, Varun Gupta, Jingyuan Zhang, Ning Wang, Liguang Xie (ByteDance), plus vLLM-community contributors.

**Releases (all tags/dates from `ungh.cc/repos/vllm-project/aibrix/releases`, verified):**

| Tag | Published | What landed (KV-relevant) |
|---|---|---|
| v0.7.0 | 2026-06-18 | **KV-cache-centric P/D disaggregation** ("the store sits in the middle, backed by PrisKV"), TensorRT-LLM as first-class engine, composable/blendable routing, HA gateway with Redis state-sync, 242 merged PRs |
| v0.6.0 | 2026-03-03 | PD + KVCache routing compatibility, async prefix-cache updates, shared indexers, combined routing across PD and non-PD pods |
| v0.5.0 | 2025-11-09 | KVCache: GDR support, collective comms, block-hash APIs, external cache handles; official vLLM + SGLang KVCache images |
| v0.4.1 | 2025-08-19 | KVCache bugfix cherry-picks |
| v0.4.0 | 2025-08-05 | **KVCache V1 Connector** refactor (CUDA kernel split, compact layout, connectors for **PrisDB** and **InfiniStore w/ TCP**, RDMA auto-detect), **KV event synchronization** (vLLM → gateway), P/D disaggregation `StormService`/`RoleSet` CRDs |
| v0.3.0 | 2025-05-21 | **AIBrix KVCache Offloading Framework introduced** (multi-tier, DRAM + remote), prefix-cache & load-aware routing, Preble routing, VTC fairness routing |
| v0.2.0 | 2025-02-19 | Distributed KV cache (DRAM pool), hybrid K8s+Ray orchestration, heterogeneous serving |
| v0.3.0-rc.2 / rc.1 | 2025-05-13/21 | InfiniStore GID support, radix-tree prefix cache |

*(source: https://github.com/vllm-project/aibrix/releases and the README news list at https://github.com/vllm-project/aibrix)*

### 1.1 The KVCache offloading framework — the core of the project

Announced in v0.3.0. Design doc: https://aibrix.readthedocs.io/latest/designs/aibrix-kvcache-offloading-framework.html · deployment doc: https://aibrix.readthedocs.io/latest/features/kvcache-offloading.html

**Two-tier model, tier independence is explicit:**
* **L1 = DRAM inside the engine pod.** Managed *in-process* by the AIBrix connector loaded by the engine — no extra deployment. Blocks are saved to host memory and reloaded when a matching prefix returns. Default capacity **10 GB** (`AIBRIX_KV_CACHE_OL_L1_CACHE_CAPACITY_GB`), default eviction **S3FIFO** (also `LRU`, `FIFO`).
* **L2 = distributed KV cache cluster outside the engine pods**, shared by replicas so a prefix computed on one replica is reusable by another. Provisioned by the **`KVCache` CRD**.
* You can run **L1 only, L2 only, or both**. With both, the default `HOT` ingestion policy writes L1-hot blocks into L2.

**Where KV lives / transport:**
* L1: host DRAM in the engine process. `AIBRIX_KV_CACHE_OL_DEVICE` = `cpu` (default) or `cuda`.
* L2: remote memory-served KV cluster. Backend connectors shipped: **`INFINISTORE`, `HPKV`, `PRISKV`, `ROCKSDB`, `EIC`, `SHFS`, `MOCK`** (`AIBRIX_KV_CACHE_OL_L2_CACHE_BACKEND`, case-insensitive). InfiniStore supports **RDMA (default) or TCP**; `AIBRIX_KV_CACHE_OL_INFINISTORE_VISIBLE_DEV_LIST` takes `mlx5_0:gid0,...`.
* GDR (GPU Direct RDMA) is supported in the connector feature set (`gdr_put`/`gdr_get` flags in `ConnectorFeature`), and GDR was explicitly added in v0.5.0.
* L2 membership is published through a **meta service** (`AIBRIX_KV_CACHE_OL_META_SERVICE_BACKEND=redis` for a CRD-managed cluster), refreshed every 30 s. Backend-specific keys: `kvcache_nodes` (InfiniStore), `hpkv_cluster_metadata` (HPKV).

**Placement / keying / eviction policy knobs (all documented):**
* Key builders: `RAW`, `ROLLING_HASH` (default), `SIMPLE_HASH` (`AIBRIX_KV_CACHE_OL_L2_CACHE_KEY_BUILDER`).
* Ingestion policy: `ALL`, `HOT` (default), `EVICTED`.
* Block size (finest I/O granularity, in tokens) defaults to the engine's block size; chunk size default 512.
* L2 placement policy (`AIBRIX_KV_CACHE_OL_L2_CACHE_PLACEMENT_POLICY`, default `SIMPLE`) is only used when a meta service is configured — i.e. the framework can coordinate placement centrally to "maximize global KV cache utilization".
* Double-get heuristic (`DOUBLE_GET_THRESHOLD` = `4,0.1`): a second L2 get is issued only if ≥4 blocks are missing and the missing ratio ≥ 10% — an explicit tail-latency guard.
* Per-token L2 timeout `20 ms`; 8 async workers by default.
* Documented caveat: only **FlashAttention and XFormers** are supported (warning in the feature doc).

**API / integration point (this is the important engineering detail):**
* **vLLM:** `--kv-transfer-config '{"kv_connector":"AIBrixOffloadingConnectorV1Type3","kv_role":"kv_both"}'` with `VLLM_USE_V1=1`. Both vLLM V0 and V1 connectors supported since v0.4.0.
* **SGLang:** the AIBrix KVCache is a **native HiCache L3 storage backend**: `--hicache-storage-backend {file,mooncake,hf3fs,nixl,aibrix,dynamic}`. SGLang's HiCache design doc lists "**AIBrix KVCache**: a production-ready KVCache Offloading Framework, which enables efficient memory tiering and low-overhead cross-engine reuse" among its L3 backends (Mooncake, HF3FS, NIXL, AIBrix KVCache, HiCacheFile). See https://docs.sglang.io/docs/advanced_features/hicache_design and https://docs.sglang.io/docs/advanced_features/hicache_best_practices. The integration PR is https://github.com/sgl-project/sglang/pull/10376 ("integrate AIBrix KVcache"). (Context on when HiCache itself landed — SGLang **v0.4.10, 2025-07-31** — and why only L3 is shareable is in §4.4.)
* **Standalone:** the framework "can be used as a standalone component — there's no need to install the entire AIBrix stack".
* New backends are added by implementing the Python `Connector` interface (`open/close/exists/get/put/delete/mget/mput/prefetch/register_slabs`, with `ConnectorFeature{mput_mget,prefetch,rdma,gdr_put,gdr_get}`).

### 1.2 The `KVCache` CRD (and what CRDs actually exist)

CRD: `kvcaches.orchestration.aibrix.ai`, **`orchestration.aibrix.ai/v1alpha1`**, kind `KVCache`, namespaced.
(fetched from https://github.com/vllm-project/aibrix/blob/main/config/crd/orchestration/orchestration.aibrix.ai_kvcaches.yaml)

Notable spec fields (from https://aibrix.readthedocs.io/latest/features/kvcache-offloading.html):
* `spec.mode`: `distributed` | `centralized` — **present in the API but not read by the current controller** (honest doc note).
* `spec.cache`: `replicas` (default 1), `image`, `imagePullPolicy`, `env`, `resources`, or a full pod template.
* `spec.metadata.redis`: runtime block (*image, replicas, resources*) or `externalConnection` (*address*, *passwordSecretRef*) — used by InfiniStore and HPKV.
* `spec.metadata.etcd`: Vineyard backend only; **`externalConnection` is not implemented for etcd**.
* `spec.watcher`: InfiniStore/HPKV only; registers cache members into Redis. Without it engines never learn membership. `replicas` and `template` are **ignored** for the watcher.
* `spec.service`: `type` (default `ClusterIP`) + ports.
* Backend selection is by **annotation**, not a spec field: `kvcache.orchestration.aibrix.ai/backend: infinistore|hpkv|vineyard` (**defaults to `vineyard`** when absent). Other annotations: `pod-affinity-workload`, `pod-anti-affinity`, `node-affinity-key`/`node-affinity-gpu-type` (Vineyard only), `infinistore.kvcache.orchestration.aibrix.ai/link-type|hint-gid-index`, `hpkv.kvcache.orchestration.aibrix.ai/*` (block-size-bytes, block-count, total-slots, virtual-node-count, rdma-port, admin-port).

**Full CRD inventory of AIBrix (from the repo's `config/crd/`):** `kvcaches`, `podsets`, `rayclusterfleets`, `rayclusterreplicasets`, `rolesets`, `stormservices` (group `orchestration.aibrix.ai`); `podautoscalers` (group `autoscaling.aibrix.ai`); `modeladapters`, `modelclaims` (group `model.aibrix.ai`).
⚠️ **There is no `ModelRouter` CRD.** Routing lives in the **gateway plugin** (Envoy Gateway ext-proc) configured by env vars / `routing-strategy` header / a *model config profile* annotation. The v0.7.0 `ModelDeploymentTemplate` is **not a CRD** — it is a Console/API store model (`apps/console/api/store/models/model_deployment_template.go`).

### 1.3 KV-cache-aware routing (the gateway)

Design doc: https://aibrix.readthedocs.io/latest/designs/aibrix-router.html · KV event doc: https://aibrix.readthedocs.io/latest/features/kv-event-sync.html

* The router is an **Envoy Gateway external-processing (ext-proc) plugin**, i.e. an LLM-aware gateway, not an in-engine scheduler. It keeps a **high-frequency local cache of pod metrics** (periodic pulls + subscriptions) so the hot path never blocks on live pod queries.
* **KV-cache-aware strategies:** `prefix-cache` (local hash table, or **KV-sync mode** using a real-time distributed index) and `prefix-cache-preble` (an implementation of **Preble**, [arXiv 2407.00023](https://arxiv.org/abs/2407.00023)).
* Other strategies: `random`, `least-request`, `least-busy-time`, `least-latency`, `least-kv-cache`, `least-gpu-cache`, `least-utilization`, `load-balance`, `throughput`, `power-of-two`, `vtc-basic` (VTC fairness, OSDI'24), `slo`, `slo-pack-load`, `slo-least-load`, `slo-least-load-pulling`, `pd` (P/D disaggregation), `session-affinity`.
* Two implementation details worth quoting because they are unusual and concrete:
  * **Auto-blended capacity awareness:** every strategy except the exclusive ones (`pd`, `slo*`) silently gets `load-balance`'s capacity-aware scoring blended in; disable with `AIBRIX_ROUTING_AUTO_BLEND_LOAD_BALANCE_WEIGHT=0`. A central `ApplyLoadImbalanceGate` restricts candidates to the least-loaded pods when load is severely skewed.
  * `load-balance` scores pods as `running_requests / drain_rate` (observed completion rate) and breaks ties by combined GPU+CPU KV-cache usage.
* **KV event synchronization** (`AIBRIX_PREFIX_CACHE_KV_EVENT_SYNC_ENABLED=true`) is the "precise" path: vLLM instances publish **KV cache events over ZMQ pub/sub** (`--enable-kv-cache-events --kv-events-publisher=zmq --kv-events-endpoint=tcp://*:5557 --kv-events-replay-endpoint=tcp://*:5558 --kv-events-buffer-steps=10000`), the AIBrix cache consumes them into a **global prefix-cache index**, and the gateway routes on real cache state. Requires vLLM ≥ 0.7.0, gateway built `-tags="zmq"`, and a **remote tokenizer** (strict prerequisite — tokenization must match between gateway and engine). Selection = prefix-match % descending, then running requests ascending, with a stddev load filter (`AIBRIX_PREFIX_CACHE_STANDARD_DEVIATION_FACTOR`, default 1); falls back to the globally least-loaded ready pod.
* The docs draw the line explicitly: **KV events sync = "which prefixes each engine holds" (routing); offloading = "moves the cache contents themselves."**

### 1.4 Measured numbers (AIBrix)

* **Whitepaper ([arXiv 2504.03648](https://arxiv.org/abs/2504.03648)):** "AIBrix incorporates a distributed KV cache, boosting token reuse across nodes, leading to a **50% increase in throughput and a 70% reduction in inference latency**."
* **v0.2.0 blog (Bird Text2SQL workload, vs vLLM's built-in prefix caching):** combining the distributed KV cache with prefix caching improves **peak throughput by ~50%**, reduces **average and P99 TTFT by ~60% and ~70%**, and lowers **average and P99 ITL by ~30% and ~70%**. (https://aibrix.github.io/posts/2025-02-05-v0.2.0-release/)
* **PrisKV micro-benchmark (H20, 400 Gbps RDMA; value sizes 512 KB – 8 MB ≈ 16–64 tokens of 8B/30B/70B-class models):** a single PrisKV node sustains **tens of thousands of QPS with sub-millisecond average latency**, and is "unlikely to be the bottleneck for the L2 KVCache path." (https://aibrix.github.io/posts/2025-11-26-priskv-intro/)
* **Single-node P/D disaggregation blog (2026-06-16)** — https://aibrix.github.io/posts/2026-06-16-single-node-pd/:
  * *Random-load benchmark* (Qwen3-32B-FP8, single-node 1P1D TP=4, vLLM v0.11.0, input_len 6000, output_len 80, concurrency 2, RPS 16). TTFT vs hit ratio: 0% → 1564.68 ms baseline; 10% → 1468.18 (−6.17%); 20% → 1362.35 (−12.93%); 30% → 1223.54 (−21.80%); 40% → 1060.78 (−32.20%); 50% → 931.00 (−40.50%); **60% → 805.04 ms (−48.55%)**. TPOT stays flat at ~18–19 ms, so "**KVCache reuse does not introduce additional overhead during the decode phase**"; at 0% hit ratio TTFT/TPOT match baseline (negligible architectural overhead). For a representative production workload (common-prefix ratio ≈ **37%**), "**TTFT can be reduced by approximately 500 ms, corresponding to an improvement of around 30%**."
  * *NVIDIA AIPerf User-Centric Timing* (multi-turn: 10 users, ~4 turns/user, 3000-token shared system prompt, 6000-token user context, 256-token per-turn input, 80 output tokens, Qwen3-32B-FP8, 5 s E2E SLO):

    | Scheme | Avg TTFT (ms) | Avg TPOT (ms) | Avg E2E (ms) | RPS | Speedup |
    |---|---|---|---|---|---|
    | 4 replicas, no prefix cache | 2882.52 | 31.15 | 5205.23 | 0.50 | 1.00 |
    | 4 replicas, w/ prefix cache | 2338.70 | **168.01** | 5193.56 | 0.79 | 1.58 |
    | AIBrix Form 1: 3P1D w/ prefix cache | 2108.81 | 37.47 | 5068.13 | 1.38 | 2.76 |
    | AIBrix Form 2: 3P1D w/o prefix cache | 1580.98 | 40.36 | 4983.35 | 1.35 | 2.70 |
    | AIBrix Form 2: 3P1D w/ prefix cache | 2190.79 | 35.87 | 5071.72 | **1.55** | **3.10** |

    → "approximately **2–3× higher throughput**"; **TTFT 1,581 ms vs 2,883 ms** for the best config; the prefix-cache baseline's **TPOT blows up to 168 ms** (prefill/decode contention). The doc also states the **native vLLM + NIXL connector 3P1D configuration cannot satisfy the 5-second E2E SLO** in this setup at all.
  * *Production deployment claims (same post):* with Qwen3-32B-FP8 on **L20** with **no RDMA**, a **multi-node** P/D disaggregated vLLM v0.11.0 TP4 deployment hit **TTFT 11,494 ms vs 1,500 ms** for single-node colocated (SLO failure), attributed to cross-node KV transfer over TCP. With single-node P/D disaggregation: **QPS +40%** at unchanged P99 E2E, or **−40% GPU usage** at the same QPS/latency — "**saving approximately 1,600 L20 GPUs during peak hours and around 1,000 L20 GPUs on a daily weighted average**." (These are internal production numbers, attributed to the AIBrix team; no public report to audit.)

### 1.5 Relationship to Dynamo / llm-d (and honest separation)

* AIBrix is a **Kubernetes control plane + gateway + KV offloading layer**, engine-agnostic, and explicitly multi-engine: v0.4.0 added "heterogeneous backends including vLLM, SGLang, and Dynamo"; **v0.7.0 made TensorRT-LLM first-class** alongside vLLM/SGLang, with engine-aware metrics and P/D routing.
* The v0.7.0 P/D router was **refactored across three pluggable axes**: engine orchestration (vLLM/SGLang/TRT-LLM), **KV-transfer connector (SHFS / NIXL / Mooncake)**, and worker-selection policy — "*AIBrix scores today, **Mooncake Conductor** next*". So AIBrix consumes the same transfer substrates (NIXL, Mooncake) as Dynamo and llm-d rather than competing with them, and its roadmap explicitly points at Mooncake's scheduler.
* AIBrix also **benchmarks itself against both**: the in-repo `brixbench` harness ships scenario matrix files for `aibrix-routing-*`, `llmd-routing-*` (incl. `llmd-v0.8.1`) and `dynamo-routing-*` (incl. `dynamo-v1.3.1`, `dynamo-v1.4.0`) on Qwen3-8B 4P4D/8P8D multi-node topologies — i.e. head-to-head routing comparisons across the three stacks. (https://aibrix.readthedocs.io/latest/features/brixbench.html)
* ⚠️ I found **no evidence** that AIBrix and llm-d share code or that AIBrix is "part of" llm-d. They are sibling/competing implementations of KV-aware routing + KV offloading on Kubernetes. The distinguishing AIBrix choices are: Envoy Gateway ext-proc (not Gateway API Inference Extension EPP), the `KVCache` CRD for provisioning the L2 tier, and a first-class **SGLang HiCache L3 backend** relationship.
* ⚠️ The AIBrix KVCache benchmark README (`benchmarks/scenarios/kvcache/README.md`) currently says only "**Coming Soon!**" — the kvcache scenario benchmarks are not yet published in-repo.

---

## 2. KServe

**Repo:** https://github.com/kserve/kserve · **as of 2026-09-15: 5,911 stars, 1,671 forks**, created 2019-03-27, last push 2026-09-14, default branch `master`, **Apache-2.0**.

**Releases (tags/dates verified against `ungh.cc` + the release atom feed):** latest **stable = v0.20.0, published 2026-08-06**; newest tag = **`v0.21.0-rc0` prerelease, published 2026-09-10**. ⚠️ There is **no stable v0.21.0** as of 2026-09-15. Full KV-relevant sequence: v0.15.0 (2025-03-31, Envoy AI Gateway first supported) → **v0.16.0 (2025-11-03, `LLMInferenceService` introduced)** → **v0.17.0 (2026-03-13, LLMISVC declared production-ready; `v1alpha2` introduced; GIE v1.3.0)** → v0.18.0 (2026-04-29, multi-node; OpenAI Responses API; llm-d v0.6) → v0.19.0 (2026-06-14, LoRA; model-name routing; graceful drain; llm-d v0.7) → **v0.20.0 (2026-08-06, `spec.kvCacheOffloading`; canary; llm-d v0.8; GIE v1.5.0)** → v0.21.0-rc0. ⚠️ Version-ordering quirk: **v0.18.1 (2026-07-15) was published *after* v0.19.0** — it is a patch on the 0.18 branch. Also ⚠️ **no v0.16 release blog and no v0.21 release blog exist** on the website (verified by listing `kserve/website` `blog/`).

### 2.1 `LLMInferenceService` — the CRD

* **Introduced in v0.16.0 (2025-11-03)** as **`serving.kserve.io/v1alpha1`**; **`v1alpha2` added in v0.17.0 (2026-03-13)** and now the storage version. Both are `served: true` on `master`; ⚠️ no `v1alpha1` removal date is documented. Evidence for the introduction includes file-tree comparison: `files/v0.15.0` contains **0** paths matching `llminference`/`llmisvc`, `files/v0.16.0` contains **141**.
* **Critical structural fact:** `LLMInferenceServiceSpec` **inlines `WorkloadSpec`**, so `replicas`, `template`, `worker`, `parallelism`, `scaling` **and `kvCacheOffloading`** sit **directly under `spec.`**, not under a `spec.workload.` wrapper.
* KV/routing-relevant spec shape (v1alpha2):
  * `spec.model.uri` (`hf://`, `s3://`, `pvc://`, `oci://`), `spec.model.lora.{adapters,maxRank,maxAdapters,maxCpuAdapters}`, `spec.model.confidential` (**new in v1alpha2**).
  * `spec.parallelism.{tensor,pipeline,data,dataLocal,expert}`.
  * `spec.worker` — presence of a worker `PodSpec` triggers a **LeaderWorkerSet** (multi-node).
  * **`spec.kvCacheOffloading`** (`KVCacheOffloadingSpec`) — **new in v1alpha2 / v0.20**.
  * `spec.router.scheduler.pool.{spec,ref}` — inline or referenced GIE `InferencePool`; `.scheduler.config.{inline,ref}` — an `EndpointPickerConfig` inline or from a ConfigMap; `.scheduler.replicas` (EPP HA); `.scheduler.tokenizer.template` — the tokenizer pod (v0.21.0-rc0 replaced the gRPC-over-UDS sidecar with a **vLLM render deployment**).
  * **`spec.prefill`** — a nested `WorkloadSpec`; its presence means **disaggregated P/D**, and it carries **its own `kvCacheOffloading`**.
  * `spec.baseRefs[]` → `LLMInferenceServiceConfig`. Merge precedence: **Well-Known Configs → Explicit BaseRefs → LLMInferenceService Spec**.
* **`LLMInferenceServiceConfig`** is a second CRD holding a full `LLMInferenceServiceSpec`. KServe ships these well-known defaults: `kserve-config-llm-decode-template`, `-decode-worker-data-parallel`, `-prefill-template`, `-prefill-worker-data-parallel`, `-router-route`, `-scheduler`, `-scheduler-eppconfig-default`, `-scheduler-eppconfig-default-pd`, `-scheduler-latency-predictor`, `-template`, `-tokenizer`, `-tracing`, `-worker-data-parallel` (plus an SGLang template).
* v0.17 restructured KServe into **three independently installable components** (`kserve`, `llmisvc`, `localmodel`) and **10 Helm charts** — a **breaking** change: "Users upgrading from v0.16 **cannot** use a simple `helm upgrade`."

### 2.2 KV cache features

**(a) KV cache offloading — `spec.kvCacheOffloading`, new in v0.20.** Verbatim Go type (v1alpha2):

```go
// KVCacheOffloadingSpec configures KV cache offloading via vLLM's OffloadingConnector.
type KVCacheOffloadingSpec struct {
	// CPU is the amount of CPU RAM to allocate as the primary KV cache tier
	// (maps to vLLM kv_connector_extra_config.cpu_bytes_to_use).
	CPU resource.Quantity `json:"cpu"`
	// EvictionPolicy for the primary CPU KV cache tier. Defaults to "lru".
	// +kubebuilder:validation:Enum=lru;arc
	// +kubebuilder:default=lru
	EvictionPolicy string `json:"evictionPolicy,omitempty"`
	// Secondary is an ordered list of secondary KV cache tiers. vLLM cascades
	// through tiers in the order listed. Currently only fileSystem tiers are supported.
	Secondary []SecondaryTierSpec `json:"secondary,omitempty"`
}
```

  * Documented behaviour: cascade is **GPU → CPU RAM → disk**, managed by **vLLM's `OffloadingConnector`** ("When GPU KV cache is full, blocks are evicted to CPU RAM; when CPU RAM is full, they spill to disk. On a cache hit, blocks are promoted back up the chain"); the controller **auto-renders the `--kv-transfer-config` JSON flag**; for P/D you set it on the **prefill** spec. `cpu` is required; `evictionPolicy` is `lru` (default) or **`arc`** (adaptive replacement cache).
  * Secondary file-system tiers: exactly one of `emptyDir` | `pvc.spec` | `pvc.ref`; mount paths assigned as `/mnt/kv-cache-0`, `/mnt/kv-cache-1`, … by list position; `emptyDir` gets an auto-added `ephemeral-storage` request; `pvc.ref` with an **RWX PVC (e.g. CephFS) shares cache across replicas**. Sample: `cpu: "10Gi"`, `evictionPolicy: lru`, `secondary: [{fileSystem: {emptyDir: {size: "100Gi"}}}]`.
  * This **replaced a previous "preset-based approach"** (PRs #5599, #5740).
  * ⚠️ **Documentation bug worth knowing:** the docs page says `spec.workload.kvCacheOffloading`, but the Go type inlines `WorkloadSpec` and the CRD puts `kvCacheOffloading` as a **direct child of `spec`** — the in-repo sample correctly uses `spec.kvCacheOffloading`. The docs page is wrong/aspirational.

**(b) KV-cache-aware routing** — see 2.3. Additional specifics: the v0.17 blog's `EndpointPickerConfig` example used `prefix-cache-scorer` weight **2.0** and `load-aware-scorer` weight **1.0** (`threshold: 100`) with `max-score-picker`. Token-based rate limiting comes via Envoy AI Gateway `AIGatewayRoute.llmRequestCosts` (Input/Output/TotalToken) + `BackendTrafficPolicy` global limits. **Model-name routing** (v0.19, #5521) dispatches on an `X-Gateway-Model-Name` header, with LoRA adapters auto-routed to the base model's backend. Route-only-through-InferencePool for chat/completions (v0.17, #5087); `/v1/responses` (v0.18, #5291); `/v1/messages` (v0.20, #5648).

**(c) P/D disaggregation:** `spec.prefill`, KV transfer via **NixlConnector + RDMA/RoCE**. ⚠️ A v0.21.0-rc0 fix *removed* `NixlConnector` from a prefix-cache-routing e2e sample (#5883), so treat connector choice as version-sensitive.

**(d) Autoscaling driven by KV state:** `spec.scaling.wva` (variant autoscaling, `variantCost` default `"10.0"`, with exactly one of `hpa`/`keda`); v0.21.0-rc0 migrated WVA from a VA CRD to **annotation-based discovery**.

### 2.3 The layering: KServe + llm-d + GIE + vLLM

* **llm-d** (https://github.com/llm-d/llm-d, **4,537 stars / 768 forks**, **CNCF Sandbox since 2026-03-24**) supplies the distributed-scheduling layer. **Gateway API Inference Extension** (https://github.com/kubernetes-sigs/gateway-api-inference-extension, **768 stars / 313 forks**, latest **v1.6.1 (2026-09-10)**, `InferencePool` GA since v1.0.0) supplies the `InferencePool` + **EndpointPicker (EPP)** abstractions. KServe's `LLMInferenceService` renders: a **Gateway route** → **`InferencePool`** → **EPP pod(s)** → vLLM `Deployment`s (or an LWS for multi-node).
* **What "KV-cache-aware routing" concretely means** (llm-d Router / EPP):
  * **Approximate path** — `approx-prefix-cache-producer` (`DataProducer`) + `prefix-cache-scorer` (`Scorer`): no tokenizer in the EPP, so tokens are **approximated from a character-to-token ratio**; the prompt is split into fixed-size blocks (e.g. 16 tokens approximated as characters) and hashed into a **rolling-hash chain**; the EPP keeps an **in-memory LRU index of which prefix hashes were recently sent to which pods** and updates it after each decision, *assuming* the chosen pod now hosts that prefix. Pros: no tokenizer, no ZMQ, no model-server cooperation. Cons: can diverge from real pod state (e.g. after eviction); less precise.
  * **Precise path** — `token-producer` + `precise-prefix-cache-producer` + `prefix-cache-scorer` + a **KV-Cache Indexer**: exact Token IDs come from vLLM's HTTP render endpoint (`/v1/completions/render`, typically a `vllm launch render` sidecar or shared render Service — the legacy gRPC-over-UDS tokenizer backend is deprecated); model servers emit **`KVEvents` over ZeroMQ** on every cache change (blocks added/evicted); the indexer maintains a globally consistent `{ModelName, BlockHash} → {PodID, DeviceTier}` view; the scorer then scores candidates on the **exact Token-ID prefix resident in that global index**. "**Speculative indexing**" closes the blind spot between a routing decision and the arrival of the corresponding `KVEvent`. Pros: 100% precision, handles eviction, natively supports P/D (by identifying specific blocks for transfer). Cons: needs the render endpoint + ZMQ and model-server support.
  * **Composition:** the approximate path is self-contained; the precise path depends on the KV-Cache Indexer and can work with **KV Offloading** to span accelerator/host memory.
  * KServe's **shipped default EPP config** (`config-llmisvcconfig/config-llm-scheduler-eppconfig-default.yaml` on `master`) is the **approximate** path: `apiVersion: llm-d.ai/v1alpha1`, `kind: EndpointPickerConfig`, plugins `approx-prefix-cache-producer`, `inflight-load-producer`, `prefix-cache-affinity-filter`, `token-load-scorer`, with scheduling profile `default`. A separate P/D variant and a latency-predictor variant exist.
  * ⚠️ **Plugin vocabulary is version-dependent and the docs are inconsistent:** the shipped config's names (`prefix-cache-affinity-filter`, `token-load-scorer`, `inflight-load-producer`) do **not** match the v0.17 blog (`prefix-cache-scorer`, `load-aware-scorer`, `max-score-picker`) nor the architecture doc (`prefix-cache-scorer` 2.0 / `load-aware-scorer` 1.0 / `queue-scorer`). `EndpointPickerConfig` also carries a **data layer** with `sources[]`, `discovery` (endpoints/peers), `crossReplicaSyncerPluginRef`, `crossReplicaSyncInterval`, `crossReplicaPublishTimeout` — i.e. **index replication across EPP replicas for HA**.
* **Version pinning:** KServe ships llm-d **v0.6 (0.18) → v0.7 (0.19) → v0.8.0 (0.20)** and GIE **v1.3.0 (0.17) → v1.5.0 (0.20 / `go.mod` on master)**. ⚠️ `v0.21.0-rc0` release notes do **not** state an llm-d version, so whether v0.21 adopts llm-d v0.9 (2026-08-17) is unverified.

### 2.4 Measured numbers — and an important separation

**(a) Tesla's own deployment (the real production datapoint).** Blog *"Production-Grade LLM Inference at Scale with KServe, llm-d, and vLLM"*, 2026-04-21, by **Yuan Tang** (KServe lead / Red Hat), **Scott Cabrinha** (Staff SRE, **Tesla**), **Robert Shaw** (Red Hat), **Sai Krishna** (**Tesla**), cross-posted on the llm-d, KServe and personal blogs. Verbatim:

> "On one deployment, we observed a **3x improvement in output tokens/s** and a **2x reduction in time to first token (TTFT)** after enabling prefix-cache aware routing. These numbers were measured when serving **Llama 3.1 70B** model on **4 MI300X AMD GPUs** with the configuration: `tensor-parallel-size=4`, `gpu-memory-utilization=0.90`, and `--max-model-len=65536`."

⚠️ **Correction to the brief:** the post's vendor mix is **Red Hat + Tesla** — I found **no IBM-authored** version. (IBM's involvement in this ecosystem is via co-authoring the CNCF llm-d Sandbox announcement and via IBM Watson as a KServe adopter.) ⚠️ The post publishes **no absolute tokens/s or TTFT values**, no concurrency, no input/output lengths, no dataset and no load-generator description — any absolute figure attributed to it would be fabricated.

**(b) llm-d's own benchmarks, reproduced by Red Hat** — [Red Hat Developer, 2026-04-21, Table 1](https://developers.redhat.com/articles/2026/04/21/kserve-llm-d-optimized-gen-ai-inference): time-to-first-token (P90) **"up to ~57× faster"**; token throughput **~4,400 → ~8,730 tokens/sec (~2×)**; throughput at scale **sustained 4.5k–11k tok/s**; tail latency **~50% reduction (P95/P99)**; better GPU utilization. ⚠️ The table is captioned by the article itself: *"Results are based on benchmarks published by the llm-d project"* — these are **llm-d benchmarks reproduced by Red Hat**, not an independent Red Hat/Tesla measurement, and **not** the Tesla MI300X deployment. Hardware/setup is not specified in that article.

**Keep these two separated in any report.** The defensible production claim is Tesla's **3× tok/s / 2× TTFT on 4× MI300X** with the stated vLLM flags.

### 2.5 Maturity, adoption, CNCF status

* **CNCF *incubating* project** — TOC vote announced **2025-11-11** (https://www.cncf.io/blog/2025/11/11/kserve-becomes-a-cncf-incubating-project/). ⚠️ That post internally contradicts itself, also saying KServe "moved to CNCF as an incubator in **September 2025**"; I could not resolve which date is authoritative. ⚠️ **No evidence KServe has graduated**; it is incubating as of 2026-09-15.
* **History:** originated **2019 under Kubeflow** (Google, IBM, Bloomberg, NVIDIA, Seldon); donated to **LF AI & Data in Feb 2022**; renamed **KFServing → KServe in Sept 2022**; CNCF incubating 2025.
* **Community (as of the Nov-2025 CNCF post):** 4.6k+ stars, **2,400+ PRs, 2.1k issues, 300+ contributors, 40+ releases, 19 maintainers, 30+ company adopters**.
* **Named production adopters** (from `docs/community/adopters.md`): **Bloomberg, Red Hat (OpenShift AI), NVIDIA (NIM), Tesla, IBM (Watson), AWS, AT&T, Cloudera, CoreWeave, Netflix, Naver, Nutanix, SAP, Zillow, Kubeflow**. ⚠️ The doc disclaims completeness.
* **CNCF integration list explicitly names both**: **llm-d** ("KServe provides the integration with llm-d to support disaggregated serving, pre-fix caching, intelligent scheduling, variant autoscaling… through the new LLMInferenceService CRD") and **LMCache** ("KServe integrates the LMCache library for Distributed Key-Value (KV) Cache").
* **Community cadence:** a **biweekly "KServe WG Meeting"** (⚠️ the brief's "SIG meetings" phrasing does not match — I found no KServe SIG structure), Slack channels `#kserve`, `#kserve-contributors`, `#kserve-oip-collaboration`.
* **Subprojects:** `kserve/website` (113★, docs+blog), `kserve/community` (17★), `kserve/modelmesh-serving` (**245★**) and `kserve/modelmesh` (**190★**) — both **last pushed 2026-04-14** (~5 months stale), while `kserve/kserve` pushes daily. ⚠️ **ModelMesh formal deprecation/EOL status is NOT verified** — the CNCF post still calls ModelMesh a live KServe "technical component"; the Open Data Hub / OpenShift AI removal evidence is search-snippet-only.
* ⚠️ **Also unverified:** whether KServe creates/consumes llm-d's `InferenceObjective` CRD (I found no KServe reference); which GIE API group/version v0.20+ emits by default for `InferencePool` (docs say `inference.networking.x-k8s.io`, vendored types are `…x-k8s.io/v1alpha2`, GIE GA is `v1`, and v0.20 claims migration to `llm-d.ai` CRDs).

### 2.6 Additional verified details

* **Backends:** vLLM is the default; a standalone `InferenceService` vLLM runtime was added in v0.20. **SGLang is a first-class LLMISVC backend** (`kserve-llm-sglang`, image `lmsysorg/sglang:v0.5.14`, `config-sglang-template.yaml`). Triton is supported **only** via `InferenceService`, not `LLMInferenceService`, and is incompatible with multi-node. **⚠️ There is NO Dynamo backend in KServe** — 0 path matches for `dynamo` in `kserve@master`. **LMCache is a *separate* InferenceService-side distributed-KV feature (PR #4320)** and must not be conflated with `spec.kvCacheOffloading`.
* **Autoscaling on KV/queue state:** WVA emits `wva_desired_replicas` to HPA or KEDA; `variantCost` default `"10.0"`; LoRA affinity scorer is auto-injected when `spec.model.lora.adapters` is set; a latency-predictor sidecar variant exists.
* **Multi-node:** via **LeaderWorkerSet**, with `LWS size = data / dataLocal`.
* **llm-d facts:** **4,542 stars / 768 forks, latest v0.9.0 (2026-08-17)**; **CNCF Sandbox since 2026-03-24**. Note upstream renames (KServe's v0.17 blog still links the stale names): **`llm-d-inference-scheduler` → `llm-d-router`**, **`llm-d-workload-variant-autoscaler` → `llm-d-autoscaling`**. **`InferenceObjective` lives in `llm-d-router` (`apix/v1alpha2/`), not in GIE.**
* ⚠️ More stale-docs hazards: the v0.17 blog's YAML uses `template: spec: containers:` while the correct v1alpha2 shape is `template: containers:` (the v0.18 blog is correct).

---

## 3. LMCache ecosystem spin-outs

### 3.1 PegaFlow (Novita AI) — external KV cache service

* **Repo:** https://github.com/novitalabs/pegaflow · **204 stars, 27 forks, created 2026-01-05, last push 2026-09-14, default branch `master`, Apache-2.0.** Latest release **v0.24.4 (2026-09-09)**; releases are frequent (v0.24.0 on 2026-08-28, v0.23.13 on 2026-08-27). PyPI packages `pegaflow-llm` (CUDA 12) and `pegaflow-llm-cu13`.
* **What it is:** "*a high-performance KV cache storage engine for LLM inference*" that offloads KV from GPU to host memory or SSD and shares it across nodes over RDMA. It runs as a **standalone sidecar/daemon** (`pegaflow-server`), i.e. **decoupled from the inference lifecycle**: cache survives engine restarts and is shared across instances.
* **Architecture (from README + https://vllm.ai/blog/2026-05-18-pegaflow + repo `docs/`):**
  * **Rust core, GIL-free** data path; the server owns the pinned host pool, SSD cache, topology metadata, RDMA resources, indexing state and background tasks. vLLM workers talk to the local PegaFlow process over **CUDA IPC on the data path and gRPC on the control path**.
  * **Three-level hierarchy:** **L1 = local pinned DRAM** (local reuse); **L2 = remote DRAM via one-sided RDMA READ** (zero CPU on the remote side after connection setup); **L3 = local SSD** implemented in Rust on **io_uring**.
  * **Placement/admission:** default **LRU**; optional **TinyLFU admission** (`--enable-lfu-admission`) to protect against scan-heavy traffic. NUMA-aware pinned allocation (default on, `--disable-numa-affinity` to turn off), optional hugepages (`--use-hugepages`), `--blockwise-alloc` to reduce fragmentation. Default pool `30gb`; SSD cache default capacity **512gb**, with explicit queue-depth/inflight knobs (`--ssd-write-queue-depth` 8, `--ssd-prefetch-queue-depth` 2, `--ssd-write-inflight` 2, `--ssd-prefetch-inflight` 16, `--max-prefetch-blocks` 800).
  * **Cross-node discovery:** a cluster-wide **MetaServer** (`pegaflow-metaserver`, in-memory, `--ttl-minutes` default 120) holds the **block-hash registry**; namespace is derived from **model name + TP config**, so mismatched models/TP sizes will not share. Transfer locks have a 120 s timeout for crash recovery. P2P is **opportunistic** — MetaServer/node/RDMA failures degrade to single-node operation.
  * **Integration point:** vLLM's **external KV connector**, no fork: `--kv-transfer-config '{"kv_connector": "PegaKVConnector", "kv_role": "kv_both", "kv_connector_module_path": "pegaflow.connector"}'`. The blog stresses this explicitly: usable "without modifying vLLM source code or carrying a long-lived fork." SGLang support is **advertised in the repo description but the README integration table lists only vLLM as "✅ Ready"** — ⚠️ so SGLang support is unverified.
  * **Observability:** Prometheus + OTLP from day one (`:9091/metrics`), plus **HyperLogLog-based online estimate of the theoretical hit-rate ceiling** `r* = (N − U)/N`, with rolling 15 min / 1 h / 24 h windows (<1 MiB memory, ~0.8% error at 24 h) — a genuinely useful operator signal because it separates "cache too small" from "workload has little reuse".
* **Measured numbers (all from the vLLM × Novita blog unless noted):**
  * **2.15× faster vLLM startup**: 8× RTX 5090, Qwen3-8B TP8, dummy weights, eager mode, ~500 GiB host KV pool: **71.4 s → 33.2 s** to ready.
  * **Single-host multi-instance pooling** (8 × Qwen3-8B, same 500 GiB budget): PegaFlow shared pool **11.97 req/s, mean TTFT 5.26 s, 52.35% hit rate** vs in-process 8×62.5 GiB isolated pools **7.68 req/s, 8.22 s, 11.77%** → **+56% throughput, −36% mean TTFT, 4.4× hit rate**.
  * **MLA logical-KV dedup** (DeepSeek-V3.2 MLA, TP8, 500 GiB budget): logical KV stored once **1.81 req/s, 35.66 s, 97.23%** vs per-TP-rank **1.05 req/s, 60.88 s, 65.18%** → **+72% throughput, −41% mean TTFT**.
  * **Cross-node RDMA** (internal cluster, 8×400 Gbps NICs/node, ≥1 GiB prefix pulls): **194 GB/s average, 250 GB/s P99, 261.6 GB/s peak** → a **24 GiB KV segment in ~100 ms**.
  * **SSD tier:** ~**6.9 GB/s peak** read on one SSD, held at **6.5–6.6 GB/s** steady state online (trading ~5% peak for tail stability); **RAID0 scales ≈ linearly**.
  * **README micro-benchmark** (H800, Llama-3.1-8B, 8 prompts, 10K-token prefill, 1-token decode, 4.0 req/s): cold TTFT mean **572.5 ms** / p99 **1113.7 ms** → warm mean **61.5 ms** / p99 **77.0 ms**, i.e. **~9× faster TTFT**.

### 3.2 PrisKV (and "PrisDB") — colocated tiered KVCache store

* **What it is:** an AIBrix-team KVCache store, described in the AIBrix blog **"PrisKV: A Colocated Tiered KVCache Store for LLM Serving"** (2025-11-26, authors Xu Wang, Jinlong Xuan, Yi Wang, Haiyang Shi, Bo Liu, Jiaxin Shan — https://aibrix.github.io/posts/2025-11-26-priskv-intro/).
* **Mechanism:** client–server, **RDMA-first** (dedicated RDMA connection management, CQ processing, SGLists on both ends), supports **GPU Direct RDMA** so KV flows GPU↔fabric with no CPU staging ("what makes sub-millisecond offload/reload operations possible"). In-memory engine = **hash tables with slab + buddy allocators**; under memory pressure **LRU eviction** moves cold entries to pluggable lower tiers: **local filesystem** and **Redis-compatible services** (explicitly positioned for AWS ElastiCache / GCP Memorystore as the cold tier). Cluster mode uses **consistent hashing** with membership/routing metadata (a `priskv_cluster_metadata` key in Redis; e.g. `{"nodes":[{"name":"node0","slots":[{"start":0,"end":4095}]}]}`). HTTP interface for management/monitoring; ACLs for basic multi-tenancy. Full-stack transport support is claimed as **TCP, shared memory, and RDMA** (single-node PD blog).
* **Integration point:** exposed through the **AIBrix KVCache Offloading Framework** as an **L2 backend** (`AIBRIX_KV_CACHE_OL_L2_CACHE_BACKEND=PRISKV`), reachable from both vLLM (`AIBrixOffloadingConnectorV1Type3`) and SGLang HiCache. Published images (Nov 2025): `priskv:v0.0.2`, `vllm-openai:v0.10.2-aibrix0.5.1-nixl0.7.1-priskv0.0.2`, `sglang:v0.5.5.post3-aibrix0.5.1-nixl0.7.1-priskv0.0.2`.
* ⚠️ **Cross-check on the v0.7.0 "zero-copy without RDMA" claim:** PrisKV's own README says it **"solely supports RDMA"** and the repo has **no release artefacts**. The AIBrix blog separately describes PrisKV as supporting *"full-stack communication support across **TCP, shared memory, and RDMA**"*. These two statements are in tension; the L20 single-node story depends on the **shared-memory** path, so read "zero-copy without RDMA" as *without RoCE/RDMA networking*, using intra-node shared memory — not as PrisKV being transport-agnostic.
* **v0.7.0 role:** PrisKV is the store behind the **KV-cache-centric P/D disaggregation** data plane — the P/D transfer *and* the KV reuse happen in one layer, which is what enables single-node P/D **without RDMA on L20-class GPUs** (validated in internal testing per the release blog). Zero-copy path becomes `GPU HBM (prefill) → CPU DRAM (PrisKV) → GPU HBM (decode)` instead of a 6-hop chain, enabled by **shared-memory mapping** between prefill/decode/PrisKV plus **specialized CUDA transfer kernels**.
* ⚠️ **RESOLVED — "PrisDB" is a *team*, not a product.** The SGLang AIBrix-KVCache integration doc states verbatim that AIBrix KVCache *"currently supports multiple distributed KVCache backends, including ByteDance's open-source Infinistore and the not-yet-open source **PrisKV incubated by ByteDance's PrisDB & IAAS & DMI team**."* So **PrisDB = the ByteDance team (PrisDB, together with IAAS and DMI)** that incubated **PrisKV**, the product. That fully explains the AIBrix v0.4.0 release note ("connector integration for PrisDB and InfiniStore") — it was referring to the PrisDB *team's* connector. Source: `python/aibrix_kvcache/.../aibrix_kvcache README` mirrored in the SGLang docs (see Sources).
* ⚠️ **Backend-name inconsistency to watch:** that SGLang integration doc configures the backend as **`AIBRIX_KV_CACHE_OL_L2_CACHE_BACKEND="PRIS"`** with env vars `AIBRIX_KV_CACHE_OL_PRIS_REMOTE_ADDR/PORT/PASSWORD`, whereas the current AIBrix docs use **`PRISKV`** and `AIBRIX_KV_CACHE_OL_PRISKV_*`. Both spellings appear in first-party sources; check the version you deploy.
* ⚠️ **Correction to an earlier tension:** PrisKV's **current README states it "supports RDMA, TCP, and shared-memory transports for efficient cross-host communication, and supports GPU Direct RDMA (GDR)"**, plus **RXE (soft-RDMA)** for development. An older description said it "solely supports RDMA". Take the current README as authoritative: **RDMA + TCP + shared memory**, which is what makes the single-node, no-RDMA-network L20 story in the AIBrix blog coherent.

### 3.2b EIC — "Elastic Instant Cache" (a closed-source Volcengine product, *not* an OSS KV cache)

This matters because SGLang and LMCache both ship an **`eic`** backend, and it is easy to mistake it for an open-source KV cache:
* **EIC = "Elastic Instant Cache"** — a **commercial distributed KV-cache product of Volcengine** (ByteDance's cloud), built by the **Volcengine Storage Team**. It is **not open source**, and its client library is **not publicly distributable**.
* The SGLang `eic` HiCache storage backend (PR #10271, merged 2025-10-01) and the LMCache `eic://` connector (PR #1930, merged 2025-11-21) are **integration shims for a Volcengine-hosted paid service**, not OSS components. AIBrix also has an EIC L2 connector (added 2025-11-06, PR #1718).
* ✅ **Authoritative SGLang backend count:** `--hicache-storage-backend` accepts **12 values — 11 concrete built-ins plus `dynamic`** (from `arg_groups/fields/memory.py`), of which exactly **two are ByteDance-related: `eic` and `aibrix`**. (My §1.1/§4.4 lists show the documented subset, not all 12.)
* ⚠️ **Two negative results worth recording:** there is **no project named "ByteDance KVCache"** (no `kvcache`-named repo in the `bytedance`, `ByteDance-Seed` or `volcengine` orgs), and **no Baidu/FastDeploy vLLM KVConnector** exists.
* **Other ByteDance OSS KV artifacts:** `bytedance/InfiniStore` (438★), `aibrix/PrisKV` (59★), **`ByteDance-Seed/ShadowKV`** (313★, **ICML'25 Spotlight** KV-cache compression), and AIBrix itself (donated to `vllm-project`).
* **`volcengine/verl` has moved to `verl-project/verl`** (23,431★). veRL does have KV relevance: `docs/perf/rollout_kv_offload.md` offloads rollout prefix KV into a **Mooncake** store. But **`hicache` appears nowhere in veRL** (code search: 0 hits) — so veRL does *not* reuse SGLang HiCache.
* **Volcengine Ark / BytePlus ModelArk prompt caching** (API-level, documented): minimum cache block **1024 tokens**, prefix-cache TTL **1 hour – 7 days**, and **per-hour cache storage billing**. The older "Context API" is archived/"Sunsetting".
* Repo (found on the second pass): **https://github.com/aibrix/PrisKV** — "High Performance KV Cache Store for LLM", **59 stars, 8 forks, created 2025-11-11, last push 2026-05-20**, **Apache-2.0**. Standalone server (`priskv-server`, default port 18512) with an HPC-style tuning surface: `--max-inflight-command` (128, max 256), `--max-sgl` (4, max 16), `--max-keys` (65 536 → 16 777 216), `--max-key-length` (128 B → 4 096), `--value-block-size` (4 096 B → 1 MiB), `--value-blocks` (65 536, power of 2), `--threads`, `--busy` busy-poll mode, `--expire-routine-interval` (600 s), `--memfile` persistence from tmpfs/hugetlbfs, plus an HTTP(S) control port. Build flags `PRISKV_USE_CUDA=1` (GDR) and `PRISKV_USE_ACL=1` (Ascend NPU). ⚠️ Maturity is weak relative to its peers — 59 stars and no release artefacts found.
* Also ships as container images on a ByteDance/Volcano Engine registry (`aibrix-container-registry-cn-beijing.cr.volces.com/aibrix/priskv:v0.0.2`).

### 3.3 ⚠️ Corrections to three premises in the brief

These matter, so they are stated up front rather than buried:

* **There is no "LMCache Inc".** The company behind LMCache is **Tensormesh** (see 3.4), founded by the University of Chicago researchers who created LMCache. LMCache's own blog announced this on 2026-06-02 in *"LMCache 与 KV Cache 社区的新篇章"* ("A new chapter for LMCache and the KV Cache community"), authored by **Junchen Jiang** and the LMCache Team, framing the thesis that "KV cache should be an independent data layer". LMCache itself is **Apache-2.0 and joined the PyTorch Foundation in October 2025** (220+ contributors, 30+ industry partners per that post).
* **LMCache has no L3/L4 tiers.** In its current (recommended) **multiprocess mode** it is **two-tier**: **L1 = CPU memory, or an NVMe slab via GPUDirect Storage (`--gds-l1-path`)**, and **L2 = durable storage**. The old multi-tier/16-backend naming belongs to the **deprecated in-process mode**. In MP mode the backend is chosen with **`--l2-adapter`**, and the documented matrix includes `nixl_store`/`nixl_store_dynamic`, `fs`, `fs_native`, `raw_block`, `bigtable`, `sagemaker-hyperpod`, `s3`, `hfbucket`, `mooncake_store`, `resp` (Redis/Valkey), `valkey`, `aerospike`, `dax`, `mock`, `fault_inject`, and `plugin`/`native_plugin`. **InfiniStore is confirmed as an LMCache backend** (present in the legacy backend set and reachable via NIXL in MP mode); **P2P** multi-node CPU-memory sharing was promoted "from experimental to production" in January 2026. Every adapter also accepts `"shared": true` for storage domains shared across instances.
* **Inferact is the vLLM company, not a KV-cache spin-out.** Founded Nov 2025, announced **2026-01-22** with a **$150M seed** (a16z + Lightspeed, with Sequoia, Altimeter, Redpoint, ZhenFund) at a reported **~$800M valuation**; CEO **Simon Mo**, team including Woosuk Kwon, Kaichao You, Roger Wang, Joseph Gonzalez, Ion Stoica. **It has no KV-cache-specific OSS component** that I could verify. Source: https://siliconangle.com/2026/01/22/inferact-launches-150m-funding-commercialize-vllm/

### 3.4 Tensormesh — the actual LMCache spin-out

* **Verified:** **Tensormesh raised $20M with AMD Ventures, CoreWeave and NVentures (NVIDIA's venture arm), launching "Tensormesh Inference"** — press release 2026-05-27: https://www.businesswire.com/news/home/20260527958597/en/ and https://siliconangle.com/2026/05/27/tensormesh-taps-nvidia-amd-coreweave-funding-fix-llm-memory-problems/. This followed a **$4.5M seed (Oct 2025)**. Founders are the University of Chicago LMCache creators.
* ⚠️ **Unverified marketing figures:** its "10x" claim carries its own disclaimer ("peak optimization in controlled environments"), and a "**41× TTFT reduction**" figure appears only as a **customer testimonial quote on the Tensormesh website** — not a reproducible benchmark. Do not cite these as measured results.
* ⚠️ **Not verified:** a distinct open-source component from Tensormesh (beyond its backing of LMCache) and the precise architecture at https://www.tensormesh.ai/.

### 3.5 LMCache itself (context for the spin-outs)

* https://github.com/LMCache/LMCache — **11,812 stars, 1,887 forks**, default branch `dev`, extremely active (nightly releases for cu129/rocm/musa/xpu; `operator-v0.5.5` published 2026-09-15). **Latest stable `v0.5.5` (2026-09-12)** — headline "multiprocess mode grows up — isolated IPC, a durable coordinator, and a rebuilt CacheBlend"; isolated IPC is now default (raw CUDA IPC with a VMM wrapper for `cuMemCreate` allocations), and `blend_v3` replaces the legacy blend path.
* **vLLM integration (file-verified in the vLLM repo):** `vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py` (**`LMCacheConnectorV1`**), `.../v1/lmcache_mp_connector.py` (**`LMCacheMPConnector`**), `.../v1/lmcache_integration/` (`vllm_v1_adapter.py`, `multi_process_adapter.py`). Production config: `--kv-transfer-config '{"kv_connector":"LMCacheMPConnector","kv_role":"kv_both"}'`.
* **Headline benchmark (MP mode):** **Qwen3-235B-A22B-Instruct-2507-FP8**, one 8×H100-80GB server, vLLM 0.18.1, LMCache 0.4.3-dev, DP=8 + EP, multi-round-chat workload, **identical 400 GB host-memory budget in both arms** (8 ranks × 50 GB in-process vs. one `lmcache server --l1-size-gb 400 --eviction-policy LRU`): **TTFT mean 0.29 s vs 3.98 s (~13×)**, **TTFT p99 1.30 s vs 13.55 s (>10×)**, **decode 37.47 vs 9.81 tok/s (~4×)**. The post's own caveat: MP mode was node-level at the time (P2P sharing and PD disaggregation were still upcoming, and v0.5.5 has since shipped P2P).
* Also verified: **NVIDIA Dynamo integrated LMCache** (blog 2025-09-18); LMCache + CoreWeave powering Cohere inference (2025-10-29); an AMD MI300X agentic benchmark (2026-05-12).
* SGLang's HiCache docs position LMCache as "an efficient KV cache layer for enterprise-scale LLM inference" providing "**an alternative solution to HiCache**", selectable with `--enable-lmcache` + `--lmcache-config-file`.

> **Structural conclusion (the single most important finding in this area):** **vLLM's `kv_transfer_config` has become the de-facto external-KV-cache integration contract.** LMCache (both `LMCacheConnectorV1` and `LMCacheMPConnector`), PegaFlow (`PegaKVConnector` via `kv_connector_module_path`) and AIBrix (`AIBrixOffloadingConnectorV1Type3`) all plug in **without forking vLLM**, so these systems no longer compete for the same socket. What differs is ownership (who owns the pool), transport (CUDA IPC vs RDMA vs CXL), admission policy, and observability.

---

## 4. Other named projects — verified

All metrics below were captured **2026-09-15** from `https://ungh.cc/repos/OWNER/REPO` unless noted. ⚠️ Owner corrections are flagged.

### 4.1 KV-cache-specific projects

**FlexKV — `taco-project/FlexKV`** · **351 stars, 73 forks**, created 2025-07-02, **still active (pushed 2026-09-15)**, **Apache-2.0**. *"A KVCache Manager for High-Performance Distributed Inference"*, built by **Tencent Cloud's TACO team** with the community.
* **Mechanism:** a multi-level cache manager + distributed KV store. GPU→CPU→SSD tiers with **GDS (GPU Direct Storage)** for direct SSD→GPU transfers (added Dec 2025); **HugePage-backed host cache**; adaptive multi-path GPU↔CPU transfers; vectored SSD I/O; chunked host-memory registration; **frequency-aware grace-time eviction**; RadixTree indexing. Since **Nov 2025 it is a directly-callable library (v1.0.0 API) rather than a client-server system**, eliminating IPC overhead.
* **Integration points (this is the notable part — it is merged into all three major engines):**
  * **vLLM**: `FlexKVConnectorV1` **built into vLLM mainline since v0.17.2** (PR [vllm#34328](https://github.com/vllm-project/vllm/pull/34328), 2026-03-17) — no patch required.
  * **NVIDIA Dynamo**: native KV-cache offloading option (PR [dynamo#5858](https://github.com/ai-dynamo/dynamo/pull/5858), 2026-03-03), enabling KV-aware routing + multi-level offloading in one pipeline.
  * **SGLang**: connector merged to mainline (PR [sglang#29701](https://github.com/sgl-project/sglang/pull/29701), 2026-07-07), native CPU/SSD offloading via **`--enable-flexkv`**, present upstream in **SGLang ≥ v0.5.16**.
  * **TensorRT-LLM**: supported since Jan 2026 (PR #48), with TP16 for both vLLM and TRT-LLM.
* **Remote tiers:** **Mooncake Transfer Engine** for RDMA cross-node distributed reuse (Jan 2026), and **Mooncake Store as a key-addressed remote cache tier** (Jul 2026) with zero-copy RDMA and DeepSeek-V4 SWA/state sidecar support. DeepSeek-V4 support landed Jul 2026 covering *heterogeneous C4/C128/indexer KV groups, FullKV + SWA dual caches, compress-state sidecars and layerwise restore*; byte-exact **NVFP4 KV offload/reload** for vLLM on Blackwell (Jul 2026).

**InfiniStore — `bytedance/InfiniStore` (also resolves as `bd-iaas-us/InfiniStore`)** · **438 stars, 44 forks**, created 2024-09-06, ⚠️ **last push 2025-11-13 (~10 months stale)**, latest release **0.2.33 (2025-03-23)**. *"KV cache store for distributed LLM inference."*
* **Mechanism:** an RDMA-capable KV store serving (a) **P/D-disaggregated** clusters — transferring KV between prefill and decode node pools — and (b) **non-disaggregated** clusters as an extra-large KV pool beyond GPU and local CPU cache, with cross-node reuse. It can also be used as a standalone KV store. **Apache-2.0.**
* ✅ **Confirmed answer to the brief's question: yes — InfiniStore is listed as an LMCache KV-cache backend.** InfiniStore's own README states: *"Currently InfiniStore has been integrated with vLLM. The integration is done via [LMCache](https://github.com/LMCache/LMCache) for the flexibility purpose."* There is a dedicated `storage_backends/infinistore` page in the LMCache docs (RDMA-only, IB or RoCE). It is **also directly supported by AIBrix** as an L2 backend connector (`INFINISTORE`, RDMA default or TCP), with per-device GID-index selection since InfiniStore 0.2.42. SGLang integration was "in progress" per the README.
* ⚠️ **Important caveat on that answer:** InfiniStore appears only on **LMCache's *deprecated* in-process path**. The **current multiprocess-mode L2 adapter list omits it** (`mp/l2_storage/infinistore` returns **404**); in MP mode you would reach it via NIXL. So "InfiniStore is an LMCache backend" is true of the legacy path and **not** of the recommended one.
* ⚠️ **Staleness is a real adoption signal** — last push **2025-11-13**, last release **0.2.33 (2025-03-23)**. Treat InfiniStore as a mature-but-dormant building block rather than an actively developed one.

**llm-d KV-cache libraries — `llm-d/llm-d-kv-cache`** · **177 stars, 156 forks** (almost as many forks as stars — heavy CI/Ops rather than community popularity), created 2025-04-29, active (pushed 2026-09-08). Releases: **v0.9.0 (2026-06-14)**, v0.8.1 (2026-05-25, prerelease), v0.8.0 (2026-05-01), v0.7.1 (2026-04-02), v0.7.0 (2026-03-30).
* *"Distributed KV cache scheduling & offloading libraries"* — the component that makes llm-d's routing KV-aware: the **KV-Cache Indexer** (subscribes to engine KV events), the **prefix scorer**, the **offloader**, and P2P/remote KV access. Plugs into the Gateway API Inference Extension **EndpointPicker (EPP)** as DataProducer/Scorer plugins (see §2.3).
* ⚠️ **Structural change (important):** the **KV-Cache Indexer has MOVED out of `llm-d-kv-cache` into `llm-d-router`** (PR #1886; `llm-d-router` is 339★, v0.10.0). `llm-d-kv-cache` now states that *"no scheduling-related logic will live here"*. Separately, llm-d's **filesystem offload connector was upstreamed into vLLM** as the **FS tier of `TieringOffloadingSpec`** (final standalone release `llmd-fs-connector==0.23`). So the durable home for llm-d KV scheduling logic is `llm-d-router`, not `llm-d-kv-cache`.
* **Measured numbers (from `benchmarking/37-capacity/README.md`, previously unpublished in this report):** 4× vLLM pods, **Llama-3.1-70B, 4×H100 TP=4, 8k-token prefix** — **precise-scheduling TTFT p90 = 0.275 s vs 84.6 s (random routing) and 78.3 s (load-based routing)**, and **5,650 vs 2,895 output tok/s at equal QPS**. Notably it achieves this while using the **least** KV cache (49.8% vs 76.5%) — i.e. **it is a placement win, not a utilization win**. The exact EPP wiring: `kind: EndpointPickerConfig` with a **`prefix-cache-scorer` plugin in `mode: cache_tracking`** (`blockSizeTokens: 64`, `hashSeed: "42"`), weighted **2.0** against `kv-cache-scorer` and `queue-scorer` at 1.0.

**kvcached — `ovg-project/kvcached`** · **1,386 stars, 161 forks**, created 2025-05-27, active (pushed 2026-09-14), **Apache-2.0**. *"KV cache daemon — make GPU sharing flexible and easy"* (homepage https://kvcached.org/).
* **Mechanism (this is the interesting part):** it brings **OS-style virtual memory abstraction to LLM systems** — it **decouples GPU virtual addressing from physical memory allocation for KV caches**, so an engine first reserves *virtual* memory and only later backs it with physical GPU memory as the cache is actually used. That yields **elastic, demand-driven KV allocation** and safe sharing of one GPU by multiple engines. A **CLI enforces memory limits**; there is a **frontend router plus a sleep mode** that puts idle models to sleep.
* **Prefix caching:** since **2026-04** it supports **automatic prefix caching (APC) for vLLM and RadixCache for SGLang** with a configurable memory bound, i.e. prefix reuse *and* elastic memory at the same time. Pipeline parallelism added 2026-03; MLA (DeepSeek-V2/V3) and GPT-OSS hybrid attention supported in vLLM.
* **Engine support matrix (from the README):** SGLang **≥ v0.4.9 (tested to v0.5.15)**, vLLM **≥ v0.8.4 (tested to v0.24.0)**; attention types MHA/GQA/MLA/sliding-window/hybrid.
* **Adoption signal:** **Red Hat featured it in 2026-04**, and Red Hat's **Sardeenz** (Kubernetes/OpenShift dynamic multi-model serving) is built on kvcached. kvcached is the memory-balloon driver behind **Prism (OSDI 2026)** — [arXiv 2505.04021](https://arxiv.org/abs/2505.04021) — from the **UC Berkeley Sky Computing Lab**, whose headline result is **2–28× TTFT reduction while serving 3× Llama-3.1-8B on a single A100-80G**. It is also the baseline that 2026 research papers beat (e.g. **CrossPool** reports up to **10.4× lower P99 TBT** vs "SOTA kvcached-based multi-LLM serving", [arXiv 2606.24506](https://arxiv.org/abs/2606.24506)). Background papers: [2505.04021](https://arxiv.org/abs/2505.04021) (multi-LLM serving), [2508.08448](https://arxiv.org/abs/2508.08448) (GPU-OS vision).
* ⚠️ **Weak spot:** kvcached's **P/D-disaggregation support is thin** — of vLLM's fifteen connectors, only `NixlConnector` is listed, and it is marked *"under validation"*. ⚠️ Its README is also **internally inconsistent about tested vLLM versions** (the support table says "up to v0.24.0", the Prerequisites section says v0.19.0, and the Docker tags say v0.19.0) — all three are quoted in `raw/discovery.md` rather than picking one.

**Tair KVCache — `alibaba/tair-kvcache`** · **255 stars, 58 forks**, created 2025-12-29, active (pushed 2026-09-15). Alibaba Cloud's high-performance KVCache system (product page https://www.aliyun.com/product/kvcache); open-sourced components are the **Tair KVCache Manager** and the **Tair KVCache HiSim** inference simulator. ⚠️ Only **2 releases, both machine-generated** — the project is young.
* **Tair KVCache Manager** = a **centralized global KV-cache metadata service + client/connector** for inference engines, with a clean **three-plane** split: a **metadata plane** (gRPC + HTTP `Access Layer`), a **data plane** (`TransferClient` on the engine side), and a **control plane** (`AdminService`). **WORKER storage configuration is pushed down from KVCM** rather than configured locally on each worker.
* Internals: **CacheManager** implements multiple matching logics (**prefix matching, sliding-window matching, KV matching**) and a **two-phase write** protocol (obtain write address → notify after write completes) for reliability, with **dynamic storage-backend selection** based on availability metrics; **DataStorage** wraps heterogeneous backends behind one interface and data-location description — **HF3FS, Mooncake, NFS**, etc.; **MetaIndex** persists metadata into an external KV store with sharded locks for atomic batch updates; **Reclaimer/Executor** manages capacity across dimensions such as instance groups, with watermark-based **eviction** driven by quota and storage water levels.
* ⚠️ Note the division of labour: Tair KVCache Manager owns **metadata and capacity**, not the KV bytes on the hot path — the bytes live in the wrapped backends.

**UCM — `ModelEngine-Group/unified-cache-management`** · **334 stars, 114 forks**, created 2025-07-10, active (pushed 2026-09-15). **Huawei ModelEngine's Unified Cache Manager** (docs https://ucm.readthedocs.io/en/latest, site modelengine-ai.net, roadmap issue #679).
* **Mechanism:** a **three-layer plug-in architecture** — `UcmSparseBase` (sparse-attention retrieval methods) / `SparseKVManager` / `KVStoreBase` — built on **vLLM's `KVConnector`**. It persists LLM KV cache and replaces redundant computation through *multiple retrieval mechanisms*: **prefix caching plus training-free sparse-attention retrieval** for very long sequences, and a **PD-disaggregation solution based on a storage-compute separation architecture**.
* **Headline claim:** *"When integrated with vLLM, UCM achieves a **3-10x reduction in inference latency** across various scenarios, including multi-turn dialogue and long-context reasoning tasks."* ⚠️ **This is a vendor-stated figure with no published setup** (no model, hardware, workload or baseline), so treat it as a marketing claim, not a measurement.
* ⚠️ **License discrepancy:** the README claims "MIT with additional conditions" while the `LICENSE` file is **plain MIT** (Huawei copyright). Unresolved.

**CacheRoute — `AstraNetLab/CacheRoute`** · **322 stars, 3 forks**, created 2025-11-17, pushed 2026-08-10. KV-cache-reuse-oriented LLM scheduling.
* ⚠️ **Two corrections.** (1) **The repo publishes no performance numbers and has no paper**: its own roadmap has *"Paper and citation release"* and *"Benchmark scripts and reproducible evaluation"* both **unchecked**. (2) **The 2026 arXiv paper of the same name is NOT this project.** [arXiv 2608.19677](https://arxiv.org/abs/2608.19677) *"CacheRoute: Planned Prefix-Affinity Routing for Large-Scale LLM Serving"* is a **single-author paper by "Huang Cheng"** with no stated affiliation or repo link; its numbers (2.3× best-of-five baselines on 60 H100s, hit rate 64.1%→93.2%) belong to **the paper, not the repo**. Do not merge these two entities in a report.
* ⚠️ **`AstraNetLab` is unresolvable as an identity** — no org description, and no authors or affiliations anywhere in the repo.

**NVIDIA KVBM, inside Dynamo** (`ai-dynamo/dynamo`, **8,082 stars / 1,584 forks**, latest docs **v1.4.2**, KVBM docs at https://docs.nvidia.com/dynamo/components/kvbm) — the **KV Block Manager** is the reference 4-tier design:
* **G1 Device pool** (GPU HBM), **G2 Host pool** (CPU pinned memory), **G3 Disk pool** (local SSD/NVMe), **G4 Remote storage** (opaque blob store over NIXL). Transfers are orchestrated by an async **TransferManager** with per-path queues (D↔H, H↔Disk, Disk↔D); a **Scheduler** gates transfer execution relative to model progress (iteration/layer completion); blocks are deduplicated by **`sequence_hash`**; Disk blocks use **NIXL descriptors exposing file offsets for zero-copy I/O and optional GDS**.
* **KV-event-driven, tier-aware routing** with an explicit support matrix. Dynamo's own README **feature matrix marks KVBM as ✅ for TensorRT-LLM and vLLM and 🚧 (in progress) for SGLang**. Per the offloading matrix: **vLLM** (v0.24.0+ / Dynamo v1.3.0+) supports GPU + CPU-RAM tiers (via `OffloadingConnector` + self-describing KV events), with disk and shared-pool integration *in progress*; **SGLang** (v0.5.11+, v0.5.13+ with Mooncake) supports GPU + HiCache host + **shared pool via `--shared-cache-type hicache`**; **TensorRT-LLM** exposes a merged GPU+RAM view with `--publish-kv-events` but **no native disk tier**. The router credits lower-tier hits weighted by `--router-host-cache-hit-weight` and `--router-disk-cache-hit-weight`, and exposes `kv_cache_events_applied` metric. Dynamo also advertises **Disaggregated Serving**, **KV-Aware Routing**, **SLA-Based Planner** and multimodal support across all three backends. ⚠️ Deep doc URLs under `docs.nvidia.com/dynamo/*` are version-unstable (several `/design-docs/...` paths 404); cite `https://docs.nvidia.com/dynamo/components/kvbm` and the repo README rather than deep links.

**NIXL — `ai-dynamo/nixl`** · **1,256 stars, 441 forks**, created 2025-03-05, active. **NVIDIA Inference Xfer Library**: the transport substrate under Dynamo's KVBM and many others (unified API over plugins incl. DeepSeek 3FS, GDS, S3-compatible object stores). TENT benchmarks against it and reports NIXL *"defaults to two NICs and stripes via static bandwidth rankings"* and lacks real-time queue visibility, losing to TENT for blocks ≥1 MB.

**UCCl — `uccl-project/uccl`** · **1,516 stars, 173 forks**, created 2025-01-06, active. GPU communication library covering collectives, **P2P (e.g. KV cache transfer)** and more; from **UC Berkeley Sky Computing Lab + UC Davis ArtSy**. Positioned as a transport competitor to NIXL/Mooncake TE (TENT compares against `UCCL-P2P`).
* **Measured KV-transfer benchmark (from the project's own KV blog; 2× 8×MI300X plus 8× Thor-2 at 400 G):** **NIXL and UCCL-P2P are the best performers**; **NCCL/RCCL are 30–50% slower in the 256 KB – 1 MB block range**; and **Mooncake TE cannot saturate 50 GB/s even at 100 MB transfers**. This is a useful independent cross-check on TENT's claim that NIXL's static striping is a bottleneck.
* **Adoption:** NVIDIA **NIXL**, **llm-d**, **NeMo**, and AMD's **Primus/TheRock** — i.e. it is being absorbed as a transport layer by several of the same projects it competes with.

**PrisKV — `aibrix/PrisKV`** · **59 stars, 8 forks**, Apache-2.0, created 2025-11-11, last push 2026-05-20. See §3.2 for the full mechanism (RDMA-only HPC KV store with GDR, tiered backends, consistent hashing).

**KV compression/eviction toolkits (usable libraries, not serving systems):**
| Repo | Stars | Forks | Latest | Mechanism & numbers |
|---|---|---|---|---|
| [NVIDIA/kvpress](https://github.com/NVIDIA/kvpress) | **1,209** | 178 | **v0.5.4 (2026-07-02)** | "LLM KV cache compression made easy" — a *press* abstraction with **20+ presses**; actively maintained (pushed 2026-09-15). Downstream presses (`KVzapPress`, `FastKVzipPress`) build on KVzip |
| [Zefan-Cai/KVCache-Factory](https://github.com/Zefan-Cai/KVCache-Factory) | **1,380** | 179 | — | Unified KV cache compression methods (the library behind several compression papers) |
| [Zefan-Cai/R-KV](https://github.com/Zefan-Cai/R-KV) | **1,212** | 196 | — | **NeurIPS 2025** redundancy-aware KV compression for *reasoning* models: **90% KV reduction with 6.6× compression**, **+17–32% tok/s**; pushed 2026-07-20. ⚠️ **No top-level LICENSE file** (only vendored subdirectory licenses) |
| [huawei-csl/KVarN](https://github.com/huawei-csl/KVarN) | **494** | 36 | — | ⚠️ **A vLLM *fork*, not a merged backend** (built on vLLM v0.23.0) despite "native vLLM backend" phrasing. Extends context **313K → 865K tokens** with AIME25 parity. ⚠️ Its headline "~1.3× throughput of FP16" **contradicts its own table, which shows 0.94×** — quote the table, not the headline. Created 2026-05-29 |
| [thu-nics/C2C](https://github.com/thu-nics/C2C) | **447** | 57 | — | **ICLR'26** Cache-to-Cache semantic communication between LLMs: **8.5–10.5%** accuracy gain, **3–5%** latency reduction, **2.0×** speedup on the reported tasks |
| [snu-mllab/KVzip](https://github.com/snu-mllab/KVzip) | **226** | 13 | — | **NeurIPS'25 Oral**, query-agnostic eviction: **3–4× memory reduction** and **2× decrease in decoding latency** (⚠️ the second claim is *latency*, not memory — commonly misquoted) |
| [NoakLiu/PiKV](https://github.com/NoakLiu/PiKV) | 63 | 8 | — | KV cache management for **MoE**. ⚠️ **Badge claims Apache-2.0 but there is no LICENSE file at any depth** |
| [ChuangtaoChen-TUM/KVPacket](https://github.com/ChuangtaoChen-TUM/KVPacket) | 37 | 6 | — | Recomputation-free, **context-independent** KV caching (created 2026-04-16) |
| [Anbeeld/beellama.cpp](https://github.com/Anbeeld/beellama.cpp) | 1,084 | 70 | — | llama.cpp fork with **KVarN** low-bit KV quants |

### 4.2 Master metrics table (all repos verified 2026-09-15)

Stars drift by ~0.5% within minutes (NIXL read 1256 then 1255 in one session) — treat these as point-in-time values.

| Repo | ★ | Forks | License | Latest release | Pushed | KV mechanism, in one line |
|---|---|---|---|---|---|---|
| `kvcache-ai/ktransformers` | 19,518 | 1,572 | Apache-2.0 | v0.7.1 (09-15) | 09-15 | Heterogeneous CPU-GPU inference/fine-tune — **not a KV store** |
| `vllm-project/vllm` | 91,813 | 22,221 | Apache-2.0 | v0.29.0 (09-09) | 09-15 | `KVConnectorBase_V1`; offload specs; 17 registered connectors |
| `sgl-project/sglang` | 35,982 | 8,871 | Apache-2.0 | v0.5.19 (09-05) | 09-15 | HiCache L1 HBM / L2 host (instance-private) / L3 shared |
| `kvcache-ai/Mooncake` | 6,576 | 1,221 | Apache-2.0 | v0.3.14-rc1 (09-07) | 09-15 | RDMA Transfer Engine + KVCache store |
| `vllm-project/vllm-omni` | 6,804 | 1,728 | Apache-2.0 | v0.29.0rc1 (09-10) | 09-15 | Unified AR/DiT **paged KV** runtime |
| `vllm-project/aibrix` | 5,089 | 694 | Apache-2.0 | v0.7.0 (2026-06-18) | 09-15 | L1 DRAM (S3FIFO) + L2 cluster; `KVCache` CRD; KV-aware gateway |
| `llm-d/llm-d` | 4,542 | 768 | — | v0.9.0 (2026-08-17) | — | KV indexer + tiered prefix-cache offload |
| `LMCache/LMCache` | 11,812 | 1,887 | Apache-2.0 | nightly-cu129 (09-15); operator-v0.5.5 | 09-15 (`dev`) | L1 CPU/NVMe (GDS) + L2 adapters |
| `ai-dynamo/dynamo` | 8,083 | 1,586 | **NOASSERTION** | v1.6.0-…-dev.1 (09-12) | 09-15 | KVBM G1–G4 tiers + KV router over NIXL |
| `NVIDIA/kvpress` | 1,209 | 178 | Apache-2.0 | v0.5.4 (07-02) | 09-15 | KV compression aggregator (20+ presses) |
| `ai-dynamo/nixl` | 1,256 | 441 | **NOASSERTION** (Apache-2.0 + NVIDIA-proprietary UCX `.so`) | v1.4.1 (09-01) | 09-15 | **Transport only**; plugins UCX / GDS / POSIX / OBJ / HF3FS / Mooncake / UCCL |
| `taco-project/FlexKV` | 351 | 73 | Apache-2.0 | v1.2.1 (01-13) | 09-15 | CPU/SSD/distributed tiers, RadixTree, logical-LRU, io_uring + GDS |
| `Ascend/TransferQueue` | 151 | 50 | Apache-2.0 | v0.1.10 (08-21) | 09-14 | Post-training/RL data plane — **NOT a serving KV tier** |
| `bytedance/InfiniStore` | 438 | 44 | Apache-2.0 | 0.2.33 (**2025-03-23**) | **2025-11-13 (stale)** | RDMA/TCP cluster KV pool |
| `CurvineIO/curvine` | 945 | 113 | Apache-2.0 | v0.5.1-alpha (09-11) | 09-15 | Rust FS; mem→SSD→HDD cache over object storage |
| `vllm-project/speculators` | 833 | 223 | Apache-2.0 | v0.8.0 (09-03) | 09-14 | Speculative decoding — **no KV tier** |
| `sgl-project/rbg` | 296 | 80 | Apache-2.0 | v0.8.0 (09-05) | 09-13 | K8s `RoleBasedGroup` workload CRD |
| `MoonshotAI/checkpoint-engine` | 1,005 | 108 | **MIT** | v0.4.2 (07-04) | 09-04 | Weight updates — **not KV** |
| `xLLM-AI/xllm` | 1,570 | 298 | Apache-2.0 | v0.10.1 (07-14) | 09-15 | Inference engine (LLM/VLM/DiT/REC) |
| `ModelTC/LightX2V` | 2,818 | 265 | Apache-2.0 | 0.5.0 (09-10) | 09-15 | Diffusion **feature** cache + real KV pool subsystem |
| `sgl-project/sglang-omni` | 1,196 | 483 | Apache-2.0 | v0.1.5 (09-10) | 09-15 | Audio/omni serving |
| `radixark/miles` | 2,877 | 494 | Apache-2.0 | v0.1.0 (08-18) | 09-15 | RL post-training |
| `ovg-project/kvcached` | 1,386 | 161 | Apache-2.0 | — | 09-14 | Virtual-memory KV for GPU sharing |
| `uccl-project/uccl` | 1,516 | 173 | — | — | 09-12 | GPU comms incl. KV transfer |
| `llm-d/llm-d-router` | 339 | — | — | v0.10.0 | — | **New home of the llm-d KV-Cache Indexer** |
| `llm-d/llm-d-kv-cache` | 177 | 156 | — | v0.9.0 (2026-06-14) | 09-08 | Offloader + scorer libs (scheduling logic moving out) |
| `ai-dynamo/kvcr` | 35 | — | — | — | created 2026-08-21 | ⚠️ New; **mechanism inferred, not confirmed** |
| `vllm-project/production-stack` | 2,571 | — | — | — | — | ⚠️ Note: `vllm-project/vllm-production-stack` **404s**; this is the real repo |
| Research code, **frozen** (cite as papers, not components) | | | | | | |
| `FMInference/H2O` | 534 | — | **no license detected** | — | — | Heavy-hitter eviction |
| `FasterDecoding/SnapKV` | 333 | — | — | — | — | Observation-window KV selection |
| `jy-yuan/KIVI` | 432 | — | — | — | — | 2-bit KV quantization |
| `NVlabs/Atom` | 347 | — | **no license detected** | — | — | Mixed-precision low-bit KV |
| `mit-han-lab/omniserve` (QServe) | 859 | — | — | — | — | W4A8KV4 |
| `YaoJiayi/CacheBlend` | 203 | — | **no license detected** | — | — | Non-prefix KV fusion |
| `mit-han-lab/streaming-llm` | 7,268 | — | — | — | frozen 2024-07 | Attention sinks |

⚠️ **Repo-name corrections:** `curvineio/curvine` → **`CurvineIO/curvine`** (case); `jd-opensource/xllm` → **redirects to `xLLM-AI/xllm`**; `Ascend/transfer_queue` **404** (real: `Ascend/TransferQueue`); **`YaoJiayi/CacheGen` 404 — the repo does not exist** (nor does `UChiCADLab/CacheGen`); **`Zefan-Cai/PyramidKV` is not standalone** (it resolves into `KVCache-Factory`); `llm-d-inference-scheduler` → `llm-d-router`; `llm-d-workload-variant-autoscaler` → `llm-d-autoscaling`. ⚠️ Also: **`ungh.cc/releases` is unreliable** — it reported "no releases" for `speculators`, `rbg`, `checkpoint-engine` and `FlexKV`, all of which demonstrably have releases (verified against `releases.atom`).

### 4.3 vLLM's in-tree v1 connectors (enumerated from the file tree)

This is the clearest single picture of what the ecosystem's integration contract now spans: `flexkv_connector`, `lmcache_connector`, `lmcache_mp_connector`, `offloading_connector`, `simple_cpu_offload_connector`, `multi_connector`, `decode_bench_connector`, `example_*`, `ssm_conv_transfer_utils`, plus subpackages `nixl/` (push/pull schedulers, pull worker, TP mapping), `mooncake/` (including `store/`), `hf3fs/`, **`moriio/`**, `hisparse/`, and `offloading/`. ⚠️ **`moriio`'s transport and vendor could not be identified** — an open item (note that AMD's Infera separately names *"MoRI-IO (AI NIC RDMA)"* for KV streaming, which is suggestive but **not** an established link).

### 4.4 SGLang HiCache — the introducing release, pinned

✅ **HiCache was introduced in SGLang `v0.4.10` (2025-07-31)**, established by differential evidence: the `v0.4.9` release notes contain **zero** HiCache mentions, while `v0.4.10` contains **ten** ("Hicache Storage Layer Prototype #7704", "Support l3 cache (mooncake store) #7211", "hf3fs support #7280"). L3 backend choices are `file | mooncake | hf3fs | nixl | aibrix | custom`, exactly as documented at https://docs.sglang.io/docs/advanced_features/hicache_design.
* **Scope fact worth stating explicitly:** **L2 host DRAM is instance-private and node-local.** HiCache *cannot* pool host memory across machines — or even across two instances on the same node. Only **L3** is shareable, and only if every instance points at the same namespace. Raising `--hicache-ratio`/`--hicache-size` only grows one instance's private L2.
* Headline numbers from the LMSYS blog (2025-09-10): **up to 6× throughput improvement and up to 80% reduction in TTFT**; community reports there include Novita AI's **−56% TTFT / 2× throughput / hit rate 40%→80%** (DeepSeek 3FS KVStore) and Ant Group's **84% TTFT reduction** (Mooncake, DeepSeek-R1-671B, P/D-disaggregated).

### 4.5 Adjacent projects named in the brief (with owner corrections)

| Requested | Actual repo | Stars | Created | Pushed | What it actually is (KV relevance) |
|---|---|---|---|---|---|
| `vllm-project/speculators` | ✅ same | **833** | 2025-04-08 | 2026-09-14 | Library for building/evaluating/**storing speculative decoding algorithms**. *KV relevance: indirect* — draft models and KV-cache sharing between draft/target are the connection; not a KV store itself |
| `sgl-project/rbg` | ✅ same | **296** | 2025-08-28 | 2026-09-13 | *"A workload for deploying LLM inference services on Kubernetes"* — a benchmark/workload harness (RBG = "RoleBasedGroup"). ⚠️ Not a KV-cache component |
| `MoonshotAI/checkpoint-engine` | ✅ same | **1,005** | 2025-09-08 | 2026-09-04 | *"Middleware to update model weights in LLM inference engines"* — the **Moonshot Checkpoint Engine** whose parameter-update time TENT improves by **20–26%** ([arXiv 2604.00368](https://arxiv.org/abs/2604.00368)) |
| `jd-opensource/xllm` | ⚠️ **`xLLM-AI/xllm`** | **1,570** | 2025-08-12 | 2026-09-15 | High-performance engine for LLM/VLM/DiT/REC models. **Owner is `xLLM-AI`, not `jd-opensource`** |
| `ModelTC/LightX2V` | ✅ same | **2,818** | 2025-03-24 | 2026-09-15 | Lightweight **image/video/action generation** inference framework (diffusion) — relevant via diffusion KV/feature caching, not transformer KV |
| `vllm-project/vllm-omni` | ✅ same | **6,797** | 2025-09-11 | 2026-09-15 | Framework for omni-modality inference in the vLLM project |
| `sgl-project/sglang-omni` | ✅ same | **1,189** | 2026-01-07 | 2026-09-15 | SGLang serving framework for **audio models (TTS/ASR)** and unified multimodal |
| `radixark/miles` | ✅ same | **2,878** | 2025-10-09 | 2026-09-15 | **RL post-training** framework for LLM/VLM — KV relevance is rollout-time KV/offload (see `verl-rollout-kv-offload` notes) |
| `curvineio/curvine` | ⚠️ **`CurvineIO/curvine`** | **945** | 2025-05-27 | 2026-09-15 | *"AI-Native & Cloud-Native FS: a high-performance file semantic layer for cloud object storage"* — a distributed FS/cache (KV-cache-on-disk tier candidate) |
| `Ascend/TransferQueue` | ✅ same | **151** | 2026-01-09 | 2026-09-14 | ⚠️ **Scope correction: this is a *post-training* data-flow module** — *"an asynchronous streaming data management module for efficient post-training"* ([arXiv 2507.01663](https://arxiv.org/abs/2507.01663)), not a KV-cache offloading layer. Adopted by **verl** (PR #5401: **+49.1% e2e performance on a 128×H100 multi-modal post-training run**), ROLL, UniRL, Relax, Meshy, Dressage (**−91% master-node data-plane peak memory on a 32-node GLM-5.2 setup**) |

⚠️ **Repo-name note:** `qwen38-27b-rtx3090`, `syv-ai/...`, `zengxiao-he/tessera`, `agentic-in/inferoa`, `Linking-ai/SCOPE`, `amy-77/ParisKV`, `cvsp-lab/RestoreKV`, `SiO-2/kvcloak`, `ModelEngine-Group/...` appeared in topic mining; only the substantial ones are characterized here.

---

## 5. Serving engines' KV-cache features beyond the big three

*(Full per-engine detail with 296 cited URLs: `raw/engines.md`. The summary below reflects that research, including three corrections to the brief's framing.)*

> **⚠️ Three corrections to premises in the brief:**
> 1. **"gen-first" is NOT a TensorRT-LLM KV eviction policy.** It is a *disaggregated-scheduling / cache-transceiver* workflow ([PR #11941](https://github.com/NVIDIA/TensorRT-LLM/pull/11941), [PR #12239](https://github.com/NVIDIA/TensorRT-LLM/pull/12239)). The verified eviction policy is **prioritized LRU**.
> 2. **vLLM's `--cpu-offload-gb` offloads MODEL WEIGHTS, not the KV cache.** It lives in `UVAOffloadConfig` in `vllm/config/offload.py`, whose module docstring is *"Configuration for model weight offloading"*, registered under the comment `# Model weight offload related configs`. This has been true for a long time — do not cite it as KV offloading.
> 3. **`llama_kv_cache_*` no longer exists as public API in llama.cpp.** `include/llama.h` contains **zero** `llama_kv_cache` symbols; it is now **`llama_memory_*`** (`llama_get_memory`, `llama_memory_seq_rm/cp/keep/add/div`, …). And **`--defrag-thold` still parses but is DEPRECATED and inert** — it logs `"DEPRECATED: --defrag-thold is deprecated and no longer necessary"` (superseded by PRs #13746, #13988).

### 5.1 NVIDIA TensorRT-LLM
**`NVIDIA/TensorRT-LLM` — 14,626 stars, 2,744 forks**, latest **stable v1.2.1 (2026-04-20)**; the newest tag is the prerelease **v1.3.0rc26 (2026-09-09)** — only **2 of the last 30 releases are stable**, so quote v1.2.1 as "latest release".

**(a) `kv_cache_config` — verified defaults.** Source of truth `tensorrt_llm/llmapi/llm_args.py` (class `KvCacheConfig`) + the [KvCacheConfig API reference](https://nvidia.github.io/TensorRT-LLM/latest/llm-api/reference/KvCacheConfig.html).

| Field | Default | Meaning |
|---|---|---|
| `enable_block_reuse` | `True` | KV blocks reusable across requests |
| `enable_partial_reuse` | `True` | Partially matched blocks reusable |
| `copy_on_partial_reuse` | `True` | Partially matched *in-use* blocks reusable after copy |
| `free_gpu_memory_fraction` | **0.9** | Fraction of **free** GPU memory for KV cache (min() with `max_gpu_total_bytes`) |
| `tokens_per_block` | **32** | Tokens per block |
| `host_cache_size` | off (0) | Host (CPU) cache bytes; offloading disabled at 0 |
| **`secondary_offload_min_priority`** | **35** | *"Only blocks with priority > `secondary_offload_min_priority` can be offloaded to secondary memory."* |
| `dtype` | `'auto'` | `auto`/`float16`/`bfloat16`/`float32`/`fp8`/**`fp8_ds_mla`** (packed FP8 sparse MLA, SM90/SM120/SM121)/**`nvfp4`** |
| `event_buffer_max_size` | `0` | 0 ⇒ no event buffer |
| `use_kv_cache_manager_v2` | `'auto'` | V1 (C++) vs V2 manager |
| `block_reuse_config` | `BlockReuseConfig()` | V2 only: `policy` ∈ `all_reusable`(default)/`per_request`/`per_conversation`; `max_num_turns` default 1 |
| `disk_cache_size` / `disk_cache_path` / `disk_prefetch_num_reqs` | None / None / 0 | **Disk tier, V2 + PyTorch backend only**; prefetch disk→host, 0 disables |
| `kv_cache_event_hash_algo` | `'auto'` | `auto`/`v1_block_key`/`v2_sha256`/`v2_sha256_64` (prototype) |
| `enable_kv_pool_rebalance` | `False` | Opt-in V2 auto-tuner `adjust()`; 2000-sample/120 s cooldown; **incompatible with `dtype='fp8_ds_mla'`** |
| `enable_swa_scratch_reuse` | `False` | V2 SWA scratch reuse during prefill (prototype) |
| `use_uvm` | `False` | **Deprecated** |
| `sink_token_length` | `None` | **Deprecated and silently ignored on the PyTorch backend** — StreamingLLM is not supported by its attention kernels |

The last three are pure-Python, not pybind, and marked **prototype**.

**Two KV cache managers.** Hybrid Mamba (NemotronH, Qwen3-Next), **DeepSeek-V4**, GPT-OSS, Gemma3/Gemma4 default to **V2**; Gemma4 hybrid attention and sparse-attention models are routed to V2 *unconditionally* because their per-layer buffer layouts cannot be expressed by V1's unified pool. ⚠️ **V2 does not support two-model speculative decoding** (e.g. Eagle3 with `eagle3_one_model=False`): under `auto` it falls back to V1, and forcing `use_kv_cache_manager_v2: true` raises an error. V2's cold-storage codec contract is in the [KVCacheManagerV2 Cold-Page Codec design](https://nvidia.github.io/TensorRT-LLM/latest/developer-guide/kv-cache-cold-page-codec.html).

**(b) Reuse & eviction.** Blocks are stored in a **radix search tree** as soon as they are filled and shared among requests. Eviction is **prioritized LRU**: *"All blocks are assigned a priority between 0 and 100 (100 being most important). All blocks of the lowest priority must be evicted before any blocks of the next priority can be evicted. If all blocks have the same priority, the least recently used block is evicted."* On eviction from primary, *"its KV state is copied to a block in secondary memory"* which **stays in the search tree and remains reusable** until evicted from secondary. Documented limitation: *"only **leaf blocks** can be evicted… This design works well for full attention layers, but not for limited attention layers. This will be fixed in a future version."* Blocks leaving a limited attention window are *"freed and placed on the radix search tree."*
**Retention policy:** a list of `TokenRangeRetentionConfig` objects ("assign priority X to tokens 10–61") with optional `duration_ms`; *"**Priority reverts to the default of 35** after a period of `duration_ms`"*. Applies to **input tokens only**; decode tokens use `decode_retention_policy` + `decode_duration_ms`. This is the mechanism behind `secondary_offload_min_priority`.
**Separate scheduler knob:** `scheduler_config.enable_prefix_aware_scheduling` (default `True`) affects *only scheduler-side* prefix-reuse estimates; setting it `False` leaves runtime block reuse intact (docs give `enable_block_reuse: true` + `enable_prefix_aware_scheduling: false`).
**KV cache salting (security):** requests may pass `cache_salt`; *"Only requests with matching cache salt values can share cached KV blocks."* Salt isolation is enforced **purely by block-key hash equality** — blocks are never re-compared token-by-token — so the hash *"is therefore required to be a cryptographic hash with strong collision resistance and a 256-bit digest… substituting a non-cryptographic hash would allow crafted collisions to bypass salt isolation and **must not be done**."* Motivation: prompt-theft attacks.
**Multimodal cache identity:** `multi_modal_uuids` are combined with content as **`BLAKE3(UUID || Content)`** and returned verbatim in KV cache events.

**(c) `kv_cache_config` events — the brief's names are real.** Three publication paths:
* **`KvCacheEventManager`** with event types **Created / Updated / Removed / Stored** ([kv-cache-management](https://nvidia.github.io/TensorRT-LLM/latest/legacy/advanced/kv-cache-management.html)).
* **Buffered poll path:** `event_buffer_max_size` + `llm.get_kv_cache_events(n)` ([example](https://nvidia.github.io/TensorRT-LLM/examples/llm_inference_kv_events.html)). Its sample output shows `'num_blocks_per_cache_level': [101230, 0]` — a **two-level array, i.e. GPU and host tiers side by side**.
* **`kv_events_config` is a real field** (class **`KVEventsConfig`**): `enable_kv_cache_events`, `publisher` (null | `zmq`), `endpoint` (`tcp://*:5557`), `buffer_steps` (10000), `hwm`/`max_queue_size` (100000). It is **V2-manager only and prototype**.

**(d) The KV Cache Connector API** ([docs](https://nvidia.github.io/TensorRT-LLM/latest/features/kv-cache-connector.html)) — stated use cases: offload to CPU RAM / NVMe SSD / network storage; custom disaggregated serving; KV sharing and P2P transfer. Architecture splits **Scheduler (Leader, rank 0 only)** from **Worker (all ranks)**:
* `KvCacheConnectorScheduler`: `build_connector_meta(scheduler_output) -> object` ("the core orchestration method"; note *"block_hashes is read directly from each KV cache block's stored hash… **the value matches the hash that KV cache events will subsequently emit for the same block**"*, and it *"only covers **beam 0**"* — the executor rejects `kv_connector_config` when `max_beam_width > 1`); `get_num_new_matched_tokens(request, num_computed_tokens) -> (int, bool)`; `request_finished(request, cache_block_ids) -> bool` (*"if True, the system waits for the operation to complete before releasing the KV cache blocks"*); `update_state_after_alloc(...)`.
* `KvCacheConnectorWorker`: `register_kv_caches(kv_cache_tensor)`, `start_load_kv(stream)`, **`wait_for_layer_load(layer_idx, stream)`**, **`save_kv_layer(layer_idx, stream)`**, `wait_for_save(stream)`, `get_finished(finished_gen_req_ids, started_loading_req_ids)`. So the contract is **layer-wise and scheduler-integrated** — the same shape as vLLM's V1 connector.
* **`KvCacheConnectorConfig`** (top-level `kv_connector_config`, marked `status="prototype"`): `connector` (a **named preset** — the telemetry allow-list reveals the built-ins: **`lmcache`, `lmcache-mp`, `kvbm`**), `connector_module`, `connector_scheduler_class`, `connector_worker_class`, `server_url` (e.g. `tcp://localhost:5555` for multi-process connectors). Presets auto-populate the module/class fields from a `CONNECTOR_REGISTRY` and raise on unknown presets. This is direct evidence that **LMCache and Dynamo's KVBM are first-class TRT-LLM connector presets.**
* Worked example (`examples/llm-api/llm_kv_cache_connector.py`) implements a `PersistentKvCacheConnector` saving to `.pt` files and demonstrates **cross-instance reuse** — explicitly contrasted with regular block reuse, which "is limited to a single instance".

**(e) Disaggregated serving** (`cache_transceiver_config`): keys `backend`, `max_tokens_in_buffer`, `kv_transfer_timeout_ms`, `kv_cache_bounce_size_mb`. `backend: NIXL` transfers over RDMA/NVLink, and **has no default** — if unset, the worker starts but brings up no transceiver and rejects disaggregated requests. `kv_transfer_timeout_ms` default **60000**. `kv_cache_bounce_size_mb` default **0** (= one message per block); a positive value coalesces a request's blocks into one contiguous buffer per direction and issues a single NIXL write, **requires fabric (MNNVL) memory**. Env var `TRTLLM_NIXL_KVCACHE_BACKEND` = `UCX` (default) | `LIBFABRIC`. Launch: `trtllm-serve disaggregated -c disagg_config.yaml`; verify with `grep "Using KvCacheTransceiverV2" log_ctx_0 log_gen_0`.

### 5.2 LMDeploy
**`InternLM/lmdeploy` — latest v0.17.0 (2026-09-01)**, after v0.14.0 (2026-06-24), v0.16.0 (2026-08-19). **v0.17.0 added a Mooncake Store KV connector** (PR #4903).

**Exact prefix-caching flags and defaults** (PyTorch engine `pt_group`, `lmdeploy/cli/utils.py`, `lmdeploy/cli/serve.py`):

| Flag | Default | Help text |
|---|---|---|
| `--enable-prefix-caching` | **`False`** | "Enable cache and match prefix" |
| `--cache-max-entry-count` | **0.8** | "The percentage of free gpu memory occupied by the k/v [cache]" |
| `--cache-block-seq-len` | **64** | "The length of the token sequence in a k/v block" |
| `--kernel-block-size` | `-1` | kernel block size |
| `--prefix-cache-state-budget` | `0` | "Extra **SSM state-cache** slots budgeted for prefix-cache checkpoints" |
| `--prefix-cache-decode-state-interval` | `0` | "Token interval for SSM decode-state prefix-cache checkpoints" (must be a multiple of `block_size`) |

`CacheConfig` (`lmdeploy/pytorch/config.py`) holds `block_size`, `num_cpu_blocks`, `num_gpu_blocks`, `window_size`, `quant_policy` (**KV quantization is a cache property**, see `docs/en/quantization/kv_quant.md`), `migration_backend`, `kv_transfer_config`, and PD-disaggregation `role`. Two hard constraints in `__post_init__`: **"Prefix caching is not available for window attention"** — with `window_size > 1` LMDeploy logs a warning and forcibly sets `enable_prefix_caching = False`; and `prefix_cache_decode_state_interval` must be a multiple of `block_size`. Scheduler eviction default is `eviction_type: 'recompute'`.

**BlockTrie** (`lmdeploy/pytorch/paging/block_trie/README.md`) is the deepest design doc in the engine section: it *"maps **full token blocks to trie nodes**, keeps the KV-cache references owned by those nodes, and, **for SSM models, associates exact recurrent-state checkpoints with selected nodes**."* Stated ownership split: `BlockTrie` owns adapter roots/block identity/match policy/routed-expert replay/statistics but **not** "Scheduler admission, concrete cache tensors"; each `Node` owns exactly **one trie-owned KV block reference**; `KVBlockLifecycle` owns leaf eviction. Design rules worth quoting: *"Each adapter has a distinct root"*; *"**Python hashes only narrow the search. Token ids and multimodal identities are checked exactly** before a block or state checkpoint is reused"*; *"The trie owns one allocator reference to every attached KV block. Each sequence sharing the block owns another reference"*; and *"**Do not infer a match from the return value of `BlockTrie.match()`**"* — matching writes tentative state to `SchedulerSequence`, with non-local rollback handled by the Scheduler.

### 5.3 Hugging Face TGI — **confirmed maintenance mode**
* **Verified:** the README carries a **CAUTION banner pointing users to vLLM/SGLang**, and there are commits literally titled "Maintenance mode". **Last push 2026-03-21.**
* **Prefix caching is an environment variable (`PREFIX_CACHING`), not a `--prefix-caching` CLI flag**, with four documented auto-disable rules: VLM, seq2seq, LoRA, and paged attention. ⚠️ The version that introduced it is **unpinned**, and the HF docs site returned HTTP 000 from this network.

### 5.4 llama.cpp (`ggml-org/llama.cpp`)
* **Internals:** `llama_kv_cache` is constructed with explicit **`offload`** and **`unified`** flags, `kv_size`, `n_seq_max`, `n_pad`, `n_swa` and a `llama_swa_type` (sliding-window attention), and exposes `init_batch` / `init_full` / **`init_update(lctx, optimize)`** — the `optimize` path is the defragmentation entry point.
* **Flags (verified in `common/arg.cpp`):** `--cache-reuse` (reuse KV for a shared prefix), **KV cache quantization** `-ctk`/`-ctv` (Q8_0, Q4_0, …), `--swa-full`, context-shift behaviour, and **`--defrag-thold` which is now DEPRECATED and inert**.
* ⚠️ **API break to flag:** `llama_kv_cache_*` is gone from public API; use **`llama_memory_*`**. (Corroborated by a downstream breakage report, guidance-ai/guidance #1306.)

### 5.5 vLLM — CPU/offloading and the connector contract
* **`KVConnector` v0 is fully deleted:** `vllm/distributed/kv_transfer/kv_connector/v0/` contains **0 files**, `v1/` contains **70**. **17 registered connectors** exist.
* **Two independent KV-offloading mechanisms:**
  * **Top-level `CacheConfig` switches:** `--kv-offloading-size` (`kv_offloading_size`, GiB, **summed across all TP ranks when TP > 1**; `None` ⇒ offloading disabled) and `--kv-offloading-backend` (`KVOffloadingBackend = Literal["native", "lmcache"]`, default `native`). *"KV offloading is only activated when `kv_offloading_size` is set."*
  * **The `OffloadingConnector` via `--kv-transfer-config`** ([KV Offloading Usage Guide](https://docs.vllm.ai/en/latest/features/kv_offloading_usage/)): *"extends the prefix cache by offloading completed KV blocks to slower but larger tiers (CPU host memory, plus optional secondary tiers) as they are produced. Hits in the offload tiers are promoted back to GPU on demand. Transfers between GPU and CPU use **DMA (`cudaMemcpyAsync`)** and run asynchronously alongside model computation."* Supports **CUDA, ROCm, XPU only**. Unit of operation = a **chunk** (by default one accelerator block).
  * Specs: **`CPUOffloadingSpec`** (default; completed GPU blocks copied to **pinned host memory**) and **`TieringOffloadingSpec`** (CPU primary + secondary tiers) — with the important constraint that *"**Only the CPU primary tier has direct GPU access. Secondary tiers cannot read from or write to GPU memory; all GPU↔secondary transfers are staged through the CPU primary tier.**"*
  * `kv_connector_extra_config` keys: **`cpu_bytes_to_use` (required; total across all workers)**, `spec_name`, `block_size` (multiple of GPU block size, mutually exclusive with `blocks_per_chunk`), `blocks_per_chunk` (1), `eviction_policy` (**`lru`** default / `arc` / custom via `cache_policy_module_path`, resolved by `CachePolicyFactory`), `store_threshold` (0; **values ≥2 are rejected by `TieringOffloadingSpec`**), `max_tracker_size` (64000), `secondary_tiers` (`[]`, consulted in order), `offload_prompt_only` (**`true`**), `self_describing_kv_events` (`false`; opt-in, requires `--kv-events-config` with `enable_kv_cache_events`), `spec_module_path`.
  * **Sizing rule worth quoting:** *"set `cpu_bytes_to_use` larger than the aggregate GPU KV cache. Because offloading is immediate, **a smaller CPU tier just mirrors what the GPU already holds and adds no hit rate**."*
  * **Module layout** (`vllm/v1/kv_offload/`): `cpu/{spec,manager,gpu_worker,shared_offload_region,swap_blocks_triton}.py`, `cpu/policies/{lru,arc,factory}.py`, `tiering/{spec,manager,async_lookup,metrics}.py` plus tier implementations `tiering/fs/`, `tiering/kvcr/`, `tiering/obj/`, `tiering/p2p/` (with `data/nixl.py` and `control/zmq.py`). `CPUOffloadingSpec` exposes `BLOCK_SIZE_ALIGNMENT` and the gauge `CPU_CACHE_USAGE_PERC`. `enable_prefix_caching` defaults **True** in vLLM.
* **The connector contract is the ecosystem's integration point:** `KVConnectorFactory` resolves `kv_connector` by name, and **`kv_connector_module_path` allows dynamic loading of out-of-tree packages**. That one decision is why **LMCache** (`LMCacheConnectorV1`, `LMCacheMPConnector`), **PegaFlow** (`PegaKVConnector`), **AIBrix** (`AIBrixOffloadingConnectorV1Type3`) and **FlexKV** (`FlexKVConnectorV1`, merged upstream in v0.17.2) all plug in **without forking vLLM**. Related docs: [kv_cache_offloading design](https://docs.vllm.ai/en/latest/design/kv_cache_offloading.html), [kv_connectors design](https://docs.vllm.ai/en/latest/design/kv_connectors.html). Tracking RFC: [vllm#26858](https://github.com/vllm-project/vllm/issues/26858).

### 5.6 PaddlePaddle FastDeploy (`PaddlePaddle/FastDeploy`, **3,715 stars**)
* Baidu's main open-source KV-cache surface. It ships a **three-tier block-based cache (`DEVICE → HOST → Storage`) built on a real `RadixTree`**, plus prefix caching, **KV quantization (INT8/INT4/FP8/block-wise FP8)**, PD disaggregation with its own RDMA transfer library, a **Golang router**, and pluggable external storage backends (`mooncake`, `attention_store`, `file_store`).
* **Mooncake integration is real and documented**: `--kvcache-storage-backend mooncake` provides **"Global Cache Pooling"** across instances, with HA multi-master leader election over etcd or Redis.
* ⚠️ **Baidu's own production KV-cache system is "AttentionStore" and is NOT open source** — FastDeploy only open-sources a *client wrapper* around a proprietary `attentionstore_sdk` (confirmed absent from PyPI); a second, different `attnstore` connector in the repo is an explicit **placeholder**. ⚠️ Also note a **name collision**: Baidu Baige's AttentionStore is a *different* system from the 2024 academic AttentionStore paper ([arXiv 2403.19708](https://arxiv.org/abs/2403.19708)).
* ⚠️ Baidu's production claims (**80–90% KV-cache hit rates**, large TTFT wins, on Kunlunxin P800) are **vendor/blog-reported, not peer-reviewed**.

### 5.7 Huawei Ascend / MindIE / MindSpore
* Ascend/MindIE KV-cache-pool work (MemFabric, UCM, Mooncake/UBS + Kunpeng UB transport, **layer-wise and sparse KV-cache offloading**) is documented in `raw/huawei_ascend.md` and the `hw_*`/`mc_*` artifacts.
* ⚠️ **MindSpore PD disaggregation is a genuine gap, not a negative finding.** `mindspore-ai/vllm-mindspore` shows **6 stars / 0 forks, no releases**, and is *not* the canonical home (PyPI homepage points to **`gitee.com/mindspore/vllm-mindspore`**, last upload 0.5.1 on 2026-01-13). Gitee and the MindSpore docs site were **not** consulted. Only inherited vLLM features are verified (Automatic Prefix Caching from the vLLM-v0.7.3 adaptation, PagedAttention, Chunked Prefill).

### 5.8 OpenVINO
* **OVMS** (`openvinotoolkit/model_server`, **930 stars**): **there is no `--cache_dir` server flag** — prefix caching is configured *inside* the LLM graph config. `enable_prefix_caching` defaults **false**; `cache_size` in GB; H2O-style `num_retained_start_tokens_in_cache` / `num_retained_recent_tokens_in_cache`. On **NPU/stateful servables OVMS disables ALL KV knobs** (documented as an explicit list).
* **OpenVINO GenAI** (`openvinotoolkit/openvino.genai`, **585 stars**, 446 forks): `CacheEvictionConfig` with `AggregationMode.ADAPTIVE_RKV` (R-KV attention-mass), **KVCrush clustering**, and `apply_rotation`; the hybrid-attention doc explains `cache_interval_multiplier` (floor 8) for **paged checkpointing of linear-attention caches**.

### 5.9 Diffusion / DiT — separating real KV cache from feature caching
**This distinction matters and is routinely blurred.** Feature/step caching (TeaCache, DeepCache, FBCache, AdaCache, MagCache, DiTFastAttn) stores **no K/V tensors** — it reuses transformer computations between similar denoising timesteps. Genuine *KV* caching exists in only a few diffusion projects:
* **`vllm-project/vllm-omni` (6,797 stars; v0.28.0 released 2026-08-31)** — the standout. v0.28.0 shipped *"a unified AR/DiT paged KV cache runtime"* under `vllm_omni/experimental/ar_diffusion/kv_cache/` (`config.py`, `manager.py`, `paged.py`, `paged_attention.py`, `state.py`). `paged.py` implements the standard PagedAttention mapping **`slot(pos) = block_id(pos) * block_size + (pos % block_size)`**, plus *"**Chunk-window eviction** — a `SlidingWindowSpec` subclass whose unit is a chunk (`sliding_window = window_chunks * chunk_size`)"*, registering into core vLLM via `register_kv_cache_spec`. `ARDiffusionKVConfig` has `enable`, `chunk_size`, `window_chunks`, **`sink_chunks`** (attention-sink retention, StreamingLLM-style), `reset_at_boundary`, `gpu_memory_fraction` (0.1). Separate from that, **online FP8 quantization for diffusion Flash Attention** is configured via `--diffusion-kv-cache-dtype` and is *explicitly not* vLLM's `--kv-cache-dtype`; ⚠️ **it is implemented only for the Ascend NPU FA backend (NVIDIA GPU ❌, ROCm ❌, XPU ❌)**. Also a genuinely unusual accounting problem: `docs/design/feature/model_local_kv_caches.md` documents HF `transformers` caches that bypass the paged manager — *"**No cache is bounded by `max_model_len`**"*, with concrete numbers (Qwen3-TTS codec decoder 4.44 MiB/request ⇒ ~1.1 GiB at `max_num_seqs=256`; MiniCPM-o Whisper encoder 140.62 MiB/session).
* **`ModelTC/LightX2V` (2,818 stars, v0.5.0 2026-09-10)** — has a real KV subsystem at `lightx2v/common/kvcache/`: `BaseKVCachePool` with `[num_layers, cache_size, num_heads, head_dim]` K/V buffers, and **eight pool classes** including `RollingKVCachePool`, `HybridStepRollingKVCachePool`, `SpatialRollingKVCachePool`, `StepRollingKVCachePool`, `FIFOKVCachePool`, `StaticKVCachePool`, and **KIVI-quantized** `KIVIQuantRollingKVCachePool` / `StepKiviQuantRollingKVCachePool`. There is an explicit **`kv_offload`** config switch, and `parse_hybrid_attn_pattern('W2-W2-W2-W2-W21')` encodes **per-layer hybrid local/global attention windows in a DiT**. (Disaggregated deployment via **Mooncake** since 2026-03.)
* **`xdit-project/xDiT` (2,718 stars, 0.6.0 2026-09-01)** — its cache flags (`--use_teacache`, `--use_fbcache`) are **feature caching**, and xDiT's own README warns cache methods are *"only supported for FLUX model with USP… not applicable for PipeFusion."* Its genuine KV cache is for **pipeline parallelism** (caching K/V across pipeline patches), documented only in a **third-party generated wiki** — ⚠️ flagged as secondary evidence.
* **2026 papers (verified on arXiv):** *Future Forcing* ([2605.30083](https://arxiv.org/abs/2605.30083), 2026-05-28) — a training-free **KV cache policy** for autoregressive video generation; *Archer* ([2608.08086](https://arxiv.org/abs/2608.08086), 2026-08-08) — cached-hidden-state reuse for diffusion-LM rollback.
* ⚠️ **Not investigated:** `NVIDIA/TensorRT-Model-Optimizer`, TRT-LLM `visual_gen` caching (docs URL 404), and `chenyangqiqi/ParaAttention` (404 — xDiT points at a *different* owner, `chengzeyi/ParaAttention`).

### 5.10 New / other engines with notable KV features
| Engine | Stars | Latest | KV story |
|---|---|---|---|
| **`dphnAI/sonar`** (⚠️ **renamed** from `aphrodite-engine/aphrodite-engine`) | 1,859 | v0.24.1 (2026-09-11) | vLLM fork; **AGPL-3.0**; ~14 KV flags incl. `--kv-cache-memory-bytes`, `--kv-cache-dtype`, `--enable-prefix-caching`, `--prefix-caching-hash-algo`, `--kv-cache-dtype-skip-layers`, `--kv-sharing-fast-prefill`, `--prefix-match-unit`, `--cp-kv-cache-interleave-size`, Mamba cache knobs, and **`--kv-offloading-size`/`--kv-offloading-backend` mirroring vLLM** (useful cross-check that the vLLM names in §5.5 are current) |
| **`AMD-AGI/Infera`** | **19** | v0.3.0 (2026-09-11) | AMD's 2026 **serving mesh** — *"disaggregated prefill/decode, KV-aware routing, and cache offload"*. Routes by *"how much of the prompt's prefix it already holds"*; streams KV over **Mooncake or MoRI-IO (AI NIC RDMA)**; when HBM fills, **AMD Infinity Context** keeps KV in **local NVMe or remote NFS-backed storage over a direct GPU path avoiding CPU DRAM staging**. Components: `--kv-event-transport zmq`, tiered daemon `infera.kvd` (`rocm/infera:kvd-v0.1.1`). ⚠️ **19 stars** — early AMD-incubated, not production-proven, despite production framing |
| **`ddalcu/mlx-serve`** | 1,275 | — | Apple-Silicon native server: *"KV reuse via prompt-prefix matching; invalidated after tool calls… hot cache spills to SSD tier"* (⚠️ source is an internal `CLAUDE.md`, indicative only) |
| `zml/zml` | 4,043 | zml-smi-v0.3.0 (2026-04-22) | Zig inference stack. **No KV-cache claim made** (⚠️ unverified) |
| `thu-pacman/chitu` | 2,997 | — | PD-disaggregation-oriented engine |
| `alibaba/rtp-llm` | 1,334 | — | Alibaba production engine |
| `GradientHQ/parallax` | 1,374 | — | Distributed serving across heterogeneous nodes |
| `pegainfer-project/pegainfer` | 697 | v0.1.1 (2026-08-26) | Pure Rust + CUDA engine |
| `jjang-ai/vmlx` | 851 | — | MLX serving |
| **`kvcache-ai/ktransformers`** | **19,518** | — | ⚠️ **Major project missed by the original list** — heterogeneous inference/fine-tune optimization framework (KV-cache-derived name); very active (pushed 2026-09-15) |

**Dormancy / death evidence (useful for a maturity narrative):**
* **`ray-project/ray-llm` is ARCHIVED** — the description literally ends "(Archived)"; the README says the repo *"has been archived and is no longer maintained"*, succeeded by `ray.serve.llm` / `ray.data.llm`. Last push **2025-03-13**.
* `intel/neural-speed` dormant since **2024-08-30**; `Tencent/TurboTransformers` since **2025-07-18**; `intel/intel-extension-for-pytorch` since **2026-03-30** (~5.5 months).
* **`bentoml/OpenLLM`** (12,531 stars) is **actively pushed (2026-09-14) but has had no release since v0.6.30 on 2025-04-21** (~17 months) — confirmed against both GitHub releases and PyPI.
* `mistralai/mistral-inference` (10,826 stars): last tagged release **v1.6.0 (2025-03-20)** — ~18 months.
* `dstackai/dstack`: no KV-cache-specific feature found (⚠️ the brief asked; **not found**).

---

## 6. Research papers 2025–2026 on KV-cache management at scale

### 6.0 ⚠️ Four arXiv IDs in the original brief are WRONG

Each was fetched from `arxiv.org/abs/...`; the claimed ID resolves to a **real but completely unrelated paper**:

| Brief said | ID actually is | Correct ID |
|---|---|---|
| Splitwise = 2401.09686 | *"An Empirical Study on the Impact of Positional Encoding in Transformer-based Monaural Speech Enhancement"* | **Splitwise = [2311.18677](https://arxiv.org/abs/2311.18677)** |
| MemServe = 2406.16818 | *"Damping effects of viscous dissipation on growth of symmetric instability"* (physical oceanography) | **MemServe = [2406.17565](https://arxiv.org/abs/2406.17565)** |
| TetriInfer = 2404.01992 | *"Dissecting Paraphrases: The Impact of Prompt Syntax… Knowledge Retrieval"* | **TetriInfer = [2401.11181](https://arxiv.org/abs/2401.11181)** |
| "Infinigen" | — | almost certainly **InfiniGen = [2406.19707](https://arxiv.org/abs/2406.19707)** |
| "InstAttention" | — | the paper was **renamed InstInfer = [2409.04992](https://arxiv.org/abs/2409.04992)** |
| "Taming the Interruption" | could not be verified | **do not cite** |

✅ **Both 2026 IDs the brief flagged as risky are REAL and correct**: `2604.00368` = **TENT**, `2605.10670` = **EEP**. All 15 IDs checked in the 2601–2608 range resolved to real papers, so the September-2026 premise holds.

### 6.1 Core KV-cache / serving systems

| Paper | arXiv | Mechanism | Headline numbers (baseline stated) |
|---|---|---|---|
| **DistServe**: Disaggregating Prefill and Decoding | [2401.09670](https://arxiv.org/abs/2401.09670) | Prefill/decode on **different GPUs**, per-phase resource allocation and parallelism, placement by cluster bandwidth | vs SOTA: **7.4× more requests** or **12.6× tighter SLO**, within latency for **>90%** of requests |
| **Splitwise** | [2311.18677](https://arxiv.org/abs/2311.18677) | Split prompt-computation and token-generation onto separate machines matched to each phase's hardware; optimise state transfer | **1.4× higher throughput at 20% lower cost**; or **2.35× more throughput** at same cost/power |
| **MemServe** (elastic memory pool) | [2406.17565](https://arxiv.org/abs/2406.17565) | **MemPool** elastic distributed memory pool; combines context caching with disaggregated inference; prompt-tree locality-aware global scheduler | ShareGPT: 1P2D improves avg/P99 **JCT 30%/42%** vs PD-colocated; +caching improves JCT a further **17%/29%** and avg/P99 **TTFT 58%/45%**. Prompt-tree scheduling improves **P99 TTFT by 59%** (full text) |
| **TetriInfer** | [2401.11181](https://arxiv.org/abs/2401.11181) | Fixed-size prompt **chunking** to hold compute saturation; disaggregated P/D; two-level scheduler with predicted usage | **38% less resources** while cutting avg **TTFT by 97%** and avg **JCT by 47%** |
| **SGLang / RadixAttention** | [2312.07104](https://arxiv.org/abs/2312.07104) | Radix-tree KV reuse across calls + compressed FSM for structured output | up to **6.4× higher throughput** vs SOTA |
| **Preble** | [2407.00023](https://arxiv.org/abs/2407.00023) | First **distributed** platform targeting prompt sharing; co-optimises KV reuse and load balancing | **1.5×–14.5×** better avg latency, **2×–10×** better p99 (implemented in AIBrix as `prefix-cache-preble`) |
| **Pensieve** | [2312.05516](https://arxiv.org/abs/2312.05516) | Multi-turn serving that caches conversation state; multi-tier GPU+CPU caching; generalises PagedAttention to non-contiguous multi-token attention | **1.14×–3.0×** the throughput of **vLLM and TensorRT-LLM** |
| **CacheBlend** | [2405.16444](https://arxiv.org/abs/2405.16444) | Reuse precomputed KV for **non-prefix** chunks; recompute KV for a small token subset; pipeline recompute with retrieval | vs full recompute: **2.2×–3.3× lower TTFT**, **2.8×–5× higher throughput**, no quality loss |
| **CacheGen** | [2310.07240](https://arxiv.org/abs/2310.07240) | Custom tensor encoder exploiting KV distributions; compression level adapts to available bandwidth | KV size **3.5×–4.3×** smaller; total fetch+process delay **3.2×–3.7×** lower |
| **Mooncake** (included for context only) | [2407.00079](https://arxiv.org/abs/2407.00079) | KVCache-centric scheduler; disaggregated cache over idle CPU/DRAM/SSD | up to **525%** throughput increase in simulation; Kimi handles **75% more requests** |
| **vAttention** | [2405.04437](https://arxiv.org/abs/2405.04437) | Decouples virtual/physical KV allocation via **CUDA VMM APIs** instead of PagedAttention | up to **1.23× higher throughput** vs PagedAttention-based kernels |

### 6.2 Quantization / compression / eviction milestones

| Paper | arXiv | Mechanism | Headline numbers |
|---|---|---|---|
| **KIVI** | [2402.02750](https://arxiv.org/abs/2402.02750) | Tuning-free **2-bit** KV; key per-channel, value per-token | **2.6× less peak memory** at near-identical quality |
| **Atom** | [2310.19102](https://arxiv.org/abs/2310.19102) | Mixed-precision fine-grained low-bit quant on 4-bit integer ops | up to **7.7×** throughput vs **FP16**, **2.5×** vs **INT8** |
| **QServe (W4A8KV4)** | [2405.04532](https://arxiv.org/abs/2405.04532) | 4-bit weights / 8-bit activations / 4-bit KV; progressive quantization; SmoothAttention | Llama-3-8B **1.2× A100 / 1.4× L40S**; Qwen1.5-72B **2.4× A100 / 3.5× L40S** vs **TensorRT-LLM**; **3× lower dollar cost** |
| **SnapKV** | [2404.14469](https://arxiv.org/abs/2404.14469) | Training-free; select clustered important KV positions per head from an **observation window** | **3.6× faster generation**, **8.2× better memory efficiency** at 16K; up to **380K tokens on one A100-80GB** |
| **H₂O (Heavy-Hitter Oracle)** | [2306.14048](https://arxiv.org/abs/2306.14048) | Evict with a balance of recent + heavy-hitter tokens (dynamic submodular, with guarantees) | at **20% heavy hitters**, up to **29× / 29× / 3×** throughput over DeepSpeed Zero-Inference / HF Accelerate / FlexGen |
| **StreamingLLM (attention sinks)** | [2309.17453](https://arxiv.org/abs/2309.17453) | Keep initial tokens' KV as **attention sinks** + rolling recent window → infinite streaming, no fine-tuning | stable to **4M+ tokens**; **22.2× speedup** vs sliding-window recomputation |
| **KVQuant** | [2401.18079](https://arxiv.org/abs/2401.18079) | Per-channel + **pre-RoPE** key quant; per-layer sensitivity-weighted non-uniform datatypes; per-vector dense-and-sparse | **<0.1 perplexity degradation at 3-bit**; LLaMA-7B to **1M context on one A100-80GB** (10M on 8 GPUs); up to **~1.7×** kernel speedup vs fp16 mat-vec |
| **GEAR** | [2403.05527](https://arxiv.org/abs/2403.05527) | Ultra-low-bit quant + **low-rank** residual + **sparse** outlier matrix | near-lossless **4-bit**; up to **2.38× throughput**, **2.29× lower peak memory** |
| **MiniCache** | [2405.14366](https://arxiv.org/abs/2405.14366) | Compresses KV **across layers** (depth): disentangle magnitude/direction, interpolate | **5.02× compression** at 4-bit, **~5× throughput**, **41% lower memory** vs FP16 |
| **PyramidKV** | [2406.02069](https://arxiv.org/abs/2406.02069) | **Layer-wise** KV budget from pyramidal information funneling | matches full-KV with only **12%** of KV (LongBench); **128 KV entries → 100.0 Acc** for LLaMA-3-70B on Needle-in-a-Haystack |
| **InfiniGen** | [2406.19707](https://arxiv.org/abs/2406.19707) | **Speculates** which KV entries the next layer needs via minimal rehearsal, then prefetches only those | up to **3.00×** better overall performance than prior offloading-based KV management, at better accuracy |
| **InstInfer** (ex-"InstAttention") | [2409.04992](https://arxiv.org/abs/2409.04992) | Offloads decode attention **and** KV to **Computational Storage Drives**, with GPU↔CSD P2P | 13B on A6000: up to **11.1× throughput** vs **FlexGen** |
| **KVzip** | [2505.23416](https://arxiv.org/abs/2505.23416) | Query-agnostic KV eviction with context reconstruction (NeurIPS'25 Oral) | repo claims **3–4× memory reduction, 2× latency decrease** (ID verified on arXiv; the numeric claims come from the repo README) |

### 6.3 2025–2026 systems and surveys — where the field actually is

| Paper | arXiv | Mechanism | Headline numbers |
|---|---|---|---|
| **TENT: A Declarative Slice Spraying Engine…** ✅ | [2604.00368](https://arxiv.org/abs/2604.00368) | Decouples transfer **intent** from execution; interconnects as a unified pool; path resolution moves from init-time to **slice-time late binding**, "spraying" slices across rails via telemetry + predictive cost modelling. Built from running **Mooncake Transfer Engine on thousands of GPUs**; NVLink as first-class transport | see 6.4 |
| **EEP (Surviving Partial Rank Failures…)** ✅ | [2605.10670](https://arxiv.org/abs/2605.10670) | Reframes partial-failure tolerance as a **live EP validity problem**; membership as explicit mutable runtime state; repairs only invalidated state; integrated with SGLang | see 6.5 |
| **From Tensor Buffer to Distributed Memory Hierarchy: A Survey of KV Cache Management for LLM Serving** | [2607.02574](https://arxiv.org/abs/2607.02574) | Classifies **30+** systems on **locality, lifetime, ownership, substrate** → five archetypes (local-paged, disaggregated-pipeline, shared-store, memory-pool, hybrid-tier). Finds **ownership** explains most remaining design variance; identifies **seven missing KV-specific measurements** | survey; thesis: KV cache "has become a first-order memory object… rather than a temporary per-request tensor" |
| **Towards Efficient LLM Serving: A Survey on System-Aware KV Cache Optimization** | [2607.08057](https://arxiv.org/abs/2607.08057) | **sKis** taxonomy: temporal (scheduling/overlap/hardware-aware), spatial (placement/migration), structural (compression/retention); cross-behaviour co-design | ACL 2026 Findings; companion list at [jjiantong/Awesome-KV-Cache-Optimization](https://github.com/jjiantong/Awesome-KV-Cache-Optimization) |
| **SAC: Disaggregated KV Cache for Sparse Attention with CXL** | [2606.19746](https://arxiv.org/abs/2606.19746) | Argues RDMA disaggregation is **wrong for sparse attention** (fetches whole prefixes when only top-k entries are active); uses **CXL** cache-line-granularity load/store for on-demand top-k | DeepSeek-V3.2 + SGLang vs RDMA baselines: **2.1× throughput**, **9.7× lower TTFT**, **1.8× lower TBT** |
| **KVServe: Service-Aware KV Compression for Disaggregated Serving** | [2605.13734](https://arxiv.org/abs/2605.13734) | Adaptive compression: modular strategy space + Bayesian Profiling Engine → 3D Pareto set + online bandit controller. Shows a **static** compression setting is unsafe | **50× less offline search**; in **vLLM**: up to **9.13× JCT speedup** (PD-separated) and **32.8× TTFT reduction** (KV-disaggregated) |
| **CacheRoute: Planned Prefix-Affinity Routing** | [2608.19677](https://arxiv.org/abs/2608.19677) | Periodic routing **plan**: admit high-rate keys to a stable warm set, place by expected load — resolving cache-blind balancing vs fixed affinity | Llama-3.3-70B fp8, **60 H100s: 176 ± 11 QPS at a 3.5 s p99 SLO = 2.3× the strongest of five baselines**; hit rate **64.1% → 93.2%**. Reports **counterexamples** on two 32B workloads; recommends **shadow-replay** gating |
| **CrossPool: Multi-LLM Serving via KV-Cache and Weight Disaggregation** | [2606.24506](https://arxiv.org/abs/2606.24506) | Separate FFN **weight pool** (cold models) and **KV pool**; KV planner/virtualizer, layer-wise pipeline, persistent kernels | vs SOTA **kvcached**-based multi-LLM serving: **P99 TBT reduced up to 10.4×** |
| **ScoutAttention: KV Offloading via Layer-Ahead CPU Pre-computation** | [2603.27138](https://arxiv.org/abs/2603.27138) | GPU–CPU block-wise sparse attention where the CPU starts one layer early; async periodic recall | accuracy within **2.4% of baseline**, **2.1× speedup** vs existing offloading |
| **Metronome: Bound the Cache, Keep the Beat** | [2607.02640](https://arxiv.org/abs/2607.02640) | Bounds each session's resident KV so latency becomes a truthful load signal for an admission controller | eliminates **catastrophic collapse: 0/20 vs 14/20 collapsed runs**; a **metastable, silent** serving cliff |
| **Learning to Evict from Key-Value Cache** | [2602.10238](https://arxiv.org/abs/2602.10238) | **RL** eviction: per-head agents rank tokens by predicted future usefulness, trained on traces, no LLM change | beats strong baselines on RULER (128K) and OASST2-4k; zero-shot to BoolQ/LongBench/GovReport (⚠️ no numeric deltas in the abstract) |
| **HillInfer** | [2602.18750](https://arxiv.org/abs/2602.18750) | CSD-assisted hierarchical KV eviction for memory-constrained AI PCs; only token-importance evaluation is offloaded to a SmartSSD | ⚠️ specific ratios not captured; treated as unverified |
| **IBP: Lossless Compression (Invariant Bit Packing)** | [2605.30728](https://arxiv.org/abs/2605.30728) | Eliminates invariant bits across tensor groups; warp-parallel GPU decompression | **+24% LLM inference** (KV-cache and weight offloading tested), **+74% GNN training**, **+180% DLRM embedding lookup** |

⚠️ **Also flagged:** arXiv 2602.18750 is **HillInfer**, not a "persistence of importance" paper — a search snippet circulating that claim is misleading.

### 6.4 TENT (2604.00368) — headline numbers in detail

*Correct citation:* 19 authors — **Tsinghua, Moonshot AI, Alibaba Cloud, Zhejiang University, Ant Group, Approaching.AI, 9# AISoft** + an independent researcher; corresponding author **Mingxing Zhang** (Tsinghua). v1 2026-04-01, v2 2026-07-24, cs.DC.
**Mechanism:** declarative orchestration decoupling intent from execution; three phases (dynamic orchestration / telemetry-driven slice spraying / proactive dual-layer resilience); elevates **NVLink** to a first-class transport for local slices while aggregating multi-rail RDMA inter-node. Claims **sub-50 ms self-healing**.

*Evaluation — LLM inference with SGLang HiCache.* 10-turn agentic conversation; **Qwen3-235B-A22B-Instruct-2507**, **H800, TP=8/node, 60 clients × 2048 input tokens, identical 600 GB KVCache budget** for all caching variants:

| Metric | Baseline (non-cached) | Mooncake TE | **TENT** |
|---|---|---|---|
| Input throughput (tok/s) | 20,757 | 58,006 | **78,759** |
| Average TTFT (s) | 2.12 | 0.72 | **0.53** |
| P90 TTFT (s) | 4.02 | 0.90 | **0.67** |
| Round-10 avg TTFT (s) | 4.09 | 0.97 | **0.66** |

→ vs non-cached: **3.79× throughput, 83.4% lower P90 TTFT**. vs **Mooncake TE**: **1.36× throughput, 26.4% better P90 TTFT** — attributed *entirely* to transport-layer optimisation, since caching policies are identical.
**Production:** "nearly all" traffic on a **thousand-GPU cluster**, **>50M tokens/min at peak**, typical **90% cache hit rate**, effective user billing cost **25% of standard market price**.
**RL (Moonshot Checkpoint Engine v0.2.0):** 8×H800 TP=8 FP16 checkpoint-apply time **12.87 s → 10.34 s (−19.7%)** for Qwen3-235B-A22B; **7.17 s → 5.30 s (−26.1%)** for GLM-4.5-Air. Semi-production at **256×H20** synchronises trillion-parameter models within tens of seconds.
**Microbenchmarks:** two H800 nodes over **eight 200 Gbps RoCE NICs** — **+33.7% write throughput** and **−27.6% P99 latency** vs Mooncake TE; beats **NIXL** and **UCCL-P2P** for blocks ≥1 MB (NIXL stripes via static bandwidth rankings on two NICs; UCCL-P2P binds to a single NIC).
**Reliability:** NIC fail-stop during continuous 64 MB transfers → dip **<50 ms**, reintegration **within 26 ms**, **zero application-visible failures**.

### 6.5 EEP (2605.10670) — headline numbers in detail

*Correct citation:* 21 authors — **Tsinghua, ByteDance, Approaching AI, Alibaba Cloud, JD.com, Georgia Tech**; corresponding author Mingxing Zhang. 2026-05-11, cs.DC.
**Mechanism:** membership as explicit mutable runtime state; (1) restore peer reachability without rebuilding the communication substrate (GPU-resident peer table, GPU-side failure detection, in-place updates); (2) repair expert coverage via a bandwidth-aware hierarchy (local weights → surviving replica → DRAM-backed expert backups); (3) reintegrate ranks **without forcing healthy ranks to recapture CUDA graphs** (deferred process-group join). Implemented with **SGLang**; baseline is fixed-membership **DeepEP**.
**Numbers:** **within 4.4%** of the fixed-membership baseline under static serving; a local rank fault becomes **two bounded interruptions** instead of whole-instance downtime; **11 s recovery pause + 8 s reintegration pause**, back to **95% throughput within 52 s**; the fixed-membership full-restart baseline is **unavailable until 348 s**.

### 6.6 The three shifts that define 2026

1. **KV cache has been reclassified from runtime state to an owned, first-class data asset.** [2607.02574](https://arxiv.org/abs/2607.02574) states KV "has become a first-order memory object… rather than a temporary per-request tensor", and finds **ownership** explains most remaining design variance — exactly the argument PegaFlow makes ("KV cache should be a long-lived serving asset, not temporary state tied to one inference process") and exactly why LMCache and PegaFlow both plug into `kv_transfer_config` without forking vLLM.
2. **The critical path has moved from computation to KV *movement*.** TENT attacks path selection, [KVServe](https://arxiv.org/abs/2605.13734) attacks adaptive compression (and shows *static* compression is unsafe), and [SAC](https://arxiv.org/abs/2606.19746) argues the memory fabric itself should be chosen per attention pattern (CXL for sparse attention, not RDMA).
3. **Routing, admission and fault tolerance are now first-class KV problems — and negative results are being published.** [CacheRoute](https://arxiv.org/abs/2608.19677) reports counterexamples where prefix affinity *hurts*; [Metronome](https://arxiv.org/abs/2607.02640) documents a metastable, silent serving cliff; [EEP](https://arxiv.org/abs/2605.10670) turns rank failure into bounded interruptions. RL-learned eviction ([2602.10238](https://arxiv.org/abs/2602.10238)) is emerging as a principled replacement for recency/attention-score heuristics.

**Cross-check:** the 2024 papers established the mechanisms (disaggregation, prefix reuse, tiering, compression); the 2026 papers **operate, orchestrate and harden** them at cluster scale and report on transport, routing and failure semantics. This matches Part A, where the differentiators are no longer "do you cache KV" but ownership boundaries, transport (CUDA IPC vs RDMA vs CXL), admission policy, and hit-rate-ceiling observability.

---

## 7. Discovery — popular KV-cache / inference-serving projects **not** in the original list

Found by mining GitHub topic pages sorted by stars (`/topics/kv-cache`, `/topics/kvcache`, `/topics/kv-cache-offloading`, `/topics/kv-cache-quantization`, `/topics/llm-serving`, `/topics/llm-inference`, each with `?o=desc&s=stars`) plus the ACL-2026 KV-cache survey's curated list.

### 7.1 High-relevance, high-star finds

| Repo | Stars | Forks | Created | Mechanism (one line) |
|---|---|---|---|---|
| [ovg-project/kvcached](https://github.com/ovg-project/kvcached) | **1,386** | 161 | 2025-05-27 | "Virtualized **Elastic** KV Cache for Dynamic GPU Sharing and Beyond" — virtualizes/multiplexes KV cache memory so multiple models share one GPU; still active (pushed 2026-09-14) |
| [uccl-project/uccl](https://github.com/uccl-project/uccl) | **1,516** | 173 | 2025-01-06 | GPU communication library covering collectives and **P2P (e.g. KV cache **transfer**)** — a transport competitor to NIXL/Mooncake TE (TENT benchmarks against it) |
| [ModelEngine-Group/unified-cache-management](https://github.com/ModelEngine-Group/unified-cache-management) | **334** | 114 | 2025-07-10 | "Persist and reuse KV Cache to speedup your LLM" — Huawei ModelEngine unified cache manager (see engine notes for the UCM/HiCache-style design) |
| [AstraNetLab/CacheRoute](https://github.com/AstraNetLab/CacheRoute) | **322** | 3 | 2025-11-17 | "an innovative LLM scheduling scheme dedicated to enabling flexible KV cache reuse" — KV-cache-aware routing/scheduling |
| [alibaba/tair-kvcache](https://github.com/alibaba/tair-kvcache) | **255** | 58 | 2025-12-29 | "Alibaba Cloud's high-performance KVCache system for LLM inference, with components for global c..." — Tair-backed global KV cache |
| [thu-nics/C2C](https://github.com/thu-nics/C2C) | **447** | 57 | 2025-10-03 | **ICLR'26** "**Cache-to-Cache**: Direct Semantic Communication Between LLMs" — transfers *semantic* cache between models instead of raw KV |
| [huawei-csl/KVarN](https://github.com/huawei-csl/KVarN) | **494** | 36 | 2026-05-29 | "a **native vLLM KV-cache quantization backend** for your agents: 3-5x more context" |
| [Zefan-Cai/R-KV](https://github.com/Zefan-Cai/R-KV) | **1,212** | 196 | 2025-05-29 | **NeurIPS 2025** — redundancy-aware KV cache compression for **reasoning** models |
| [Zefan-Cai/KVCache-Factory](https://github.com/Zefan-Cai/KVCache-Factory) | **1,380** | 179 | 2024-06-05 | Unified KV cache compression methods for autoregressive models |
| [snu-mllab/KVzip](https://github.com/snu-mllab/KVzip) | **226** | 13 | 2025-05-28 | **NeurIPS'25 Oral** — query-agnostic KV eviction; "3–4× reduction in memory and 2× decrease in ..." |
| [Amy-77/ParisKV] | 35 | 4 | 2026-01-29 | **ICML'26** "Fast and Drift-Robust KV-Cache Retrieval for Long-Context LLMs" |
| [ChuangtaoChen-TUM/KVPacket](https://github.com/ChuangtaoChen-TUM/KVPacket) | 37 | 6 | 2026-04-16 | Recomputation-free, **context-independent** KV caching |
| [NoakLiu/PiKV](https://github.com/NoakLiu/PiKV) | 63 | 8 | 2025-04-07 | KV cache management system **for MoE** |
| [pegainfer-project/pegainfer](https://github.com/pegainfer-project/pegainfer) | **697** | 107 | 2026-02-17 | Pure **Rust + CUDA** LLM inference engine (no PyTorch), OpenAI-compatible, Qwen3→Kimi-K2; v0.1.1 (2026-08-26). ✅ **Not a coincidence: its KV infrastructure *is* PegaFlow** — the project's design doc references `PegaflowHost` / `pegaflow-core`, i.e. PegaInfer (Novita AI) and the `novitalabs/pegaflow` repo are the same product family |
| [Anbeeld/beellama.cpp](https://github.com/Anbeeld/beellama.cpp) | **1,084** | 70 | 2026-05-05 | llama.cpp fork with **KVarN** low-bit KV quants for longer context |
| [quantumaikr/quant.cpp](https://github.com/quantumaikr/quant.cpp) | 401 | 44 | 2026-03-28 | "LLM inference with 7x longer context. Pure C, zero dependencies. **Lossless KV cache compression**" |
| [huiliyi37/Tianshu-harness](https://github.com/huiliyi37/Tianshu-harness) | 733 | 48 | 2026-06-09 | Terminal coding-agent runtime with **prefix-cache engineering for DeepSeek V4** — claims **97–99% steady-state hit rate on long sessions** (Chinese description) |
| [rh-aiservices-bu/sardeenz](https://github.com/rh-aiservices-bu/sardeenz) | 64 | 8 | 2025-11-19 | Red Hat AI-services proof-of-concept for loading multiple models per GPU |

### 7.2 Adjacent engines/frameworks that surfaced (KV-relevant)

| Repo | Stars | KV-relevant note |
|---|---|---|
| [kvcache-ai/ktransformers](https://github.com/kvcache-ai/ktransformers) | **19,518** | ⚠️ **The largest project the original list omitted.** Heterogeneous inference/fine-tune optimization framework (the org and name are KV-cache-derived: `kvcache-ai` also hosts Mooncake). Very active (pushed 2026-09-15). Support for CPU/GPU hybrid expert offload is its signature feature — **not** a KV cache store |
| [AMD-AGI/Infera](https://github.com/AMD-AGI/Infera) | 19 | AMD's 2026 KV-aware serving mesh (`infera.kvd` tiered cache daemon, AMD Infinity Context, Mooncake/MoRI-IO KV streaming) — see §5.10 |
| [dphnAI/sonar](https://github.com/dphnAI/sonar) | 1,859 | ⚠️ **renamed** from `aphrodite-engine/aphrodite-engine`; vLLM fork, AGPL-3.0, ~14 KV flags — see §5.10 |
| [thu-pacman/chitu](https://github.com/thu-pacman/chitu) | 2,997 | High-performance engine (Tsinghua PACMAN), PD-disaggregation oriented; active 2026-09-10 |
| [PaddlePaddle/FastDeploy](https://github.com/PaddlePaddle/FastDeploy) | 3,715 | Ships prefix caching, cache storage, **global cache pooling** and disaggregated PD (see engine notes) |
| [MoonshotAI/MoBA](https://github.com/MoonshotAI/MoBA) | 2,190 | Mixture-of-Block Attention for long context — **reduces KV footprint** at the attention level (⚠️ last push 2025-04-03, i.e. dormant) |
| [SemiAnalysisAI/InferenceX](https://github.com/SemiAnalysisAI/InferenceX) | 1,695 | Open-source continuous **inference benchmark research platform** (Kimi K3 2.8T, MiniMax M3, DeepSeek…) — useful neutral ground truth for KV/offload claims |
| [GradientHQ/parallax](https://github.com/GradientHQ/parallax) | 1,374 | Distributed model serving across heterogeneous nodes (pushed 2026-07-01) |
| [alibaba/rtp-llm](https://github.com/alibaba/rtp-llm) | 1,334 | Alibaba's production LLM engine |
| [vllm-project/vllm-ascend](https://github.com/vllm-project/vllm-ascend) | 2,826 | Ascend hardware plugin for vLLM (Ascend KV transfer lives here) |
| [openvinotoolkit/model_server](https://github.com/openvinotoolkit/model_server) | 930 | OpenVINO Model Server (330+ forks on genai sibling) |
| [NVIDIA/kvpress](https://github.com/NVIDIA/kvpress) | 1,209 | See §4/§5 — KV compression toolkit, v0.5.4 (2026-07-02) |

### 7.3 Additional leads (flagged, low confidence)

* **`opendatahub-io/llm-d-kv-cache`** — only **2 stars / 3 forks** (created 2026-02-12), but it is **Red Hat's Open Data Hub build** of `llm-d-kv-cache` (Konflux `Dockerfile.konflux`, UDS tokenizer service). Low stars, **high signal**: it shows llm-d's KV-cache libraries being **productised into OpenShift AI**. Do not read the 2-star count as lack of adoption.
* **"TPU Raiden"** — press coverage (2026-08-10) says **Google open-sourced a TPU inference library called Raiden** ([dataconomy](https://dataconomy.com/2026/08/10/google-open-sources-tpu-raiden-for-faster-ai-inference/)). ⚠️ **Unverified:** I could not find an official Google repo (`google/raiden` does not resolve), could not confirm whether it has any KV-cache/prefix-cache feature, and the article text was paywall/JS-blocked. `google/tpu-sync` (**132 stars**, created 2026-05-09, active) is a separate and equally uncharacterized lead.
* **`d-tietjen/shard-kv`** — "thread-per-core layer cache implementation" (surfaced by search; ⚠️ metrics/mechanism not verified).
* **`kvcache-ai/*`** also contains **Mooncake** (6,572★) and related repos; Mooncake itself is treated as known context rather than a discovery here.

### 7.4 Curated lists worth mining

* [jjiantong/Awesome-KV-Cache-Optimization](https://github.com/jjiantong/Awesome-KV-Cache-Optimization) — **406 stars**, companion to the **ACL 2026 Findings** survey *"Towards Efficient Large Language Model Serving: A Survey on System-Aware KV Cache Optimization"* ([arXiv 2607.08057](https://arxiv.org/abs/2607.08057), [ACL Anthology](https://aclanthology.org/2026.findings-acl.1916/); Jiang, Yang, Zhang, Liu — Univ. of Melbourne + HUST). Taxonomy: **Temporal** (KV-centric scheduling, pipelining/overlap, hardware-aware execution), **Spatial** (memory-hierarchy orchestration, compute-device orchestration), **Structural** (compression, retention management), plus cross-behavior co-design analysis. I harvested its **Memory-Hierarchy KV Orchestration** table; the 2025–2026 entries there include arXiv **2510.18586, 2511.20172, 2512.18194, 2601.13684, 2602.07721, 2602.18750, 2604.19769, 2604.26557, 2605.03375, 2605.22850** and openreview IDs `6i1jVAYbHs`, `5Iw1nDtYmT`, `8z3cOVER4z`, `PQIrsaIQdn`, `oa7MYAO6h6`. ⚠️ I extracted IDs but not per-paper headline numbers.
  * ⚠️ **Important gap in that survey:** it does **not** cover **kvcached, UCM, Tair KVCache, CacheRoute, FlexKV, PegaFlow or Dynamo KVBM** — the *production/engineering* systems in this document. The academic taxonomy and the production landscape are therefore **complementary, not overlapping**; do not use the survey as evidence about any of those seven.
  * ⚠️ **Naming collision to avoid:** the survey's *"PRISM: Fast Online LLM Serving via Scheduling-Memory Co-design"* ([arXiv 2605.08581](https://arxiv.org/abs/2605.08581)) is **unrelated** to the kvcached-based **Prism (OSDI 2026)** discussed in §4.1.
* [Zefan-Cai/Awesome-LLM-KV-Cache](https://github.com/Zefan-Cai/Awesome-LLM-KV-Cache) — 466 stars, curated KV cache papers with code.
* [sihyeong/Awesome-LLM-Inference-Engine](https://github.com/sihyeong/Awesome-LLM-Inference-Engine) — inference-engine list (surfaced via search; ⚠️ stars not captured).

---

## 8. Could not verify (explicit)

1. ~~**`PrisDB`** — appears only in the AIBrix v0.4.0 release-note text…~~ ✅ **RESOLVED (see §3.2).** PrisDB is a **ByteDance team name** ("ByteDance's **PrisDB** & IAAS & DMI team"), not a product; the product it incubated is **PrisKV**, which is open source at `aibrix/PrisKV`. The v0.4.0 release note referred to the team's connector.
2. **Inferact** — the $150M launch to commercialize vLLM is sourced (SiliconANGLE), but **no LMCache lineage, no OSS KV-cache component, no product architecture** could be verified. The framing "LMCache spin-out" is **unconfirmed**.
3. **Tensormesh** — $20M raise (AMD Ventures, CoreWeave, NVentures) and a memory-focused pitch are sourced; **no OSS component or verifiable KV-cache architecture** was obtained from a primary source.
4. **AIBrix L2/Cache benchmark numbers** — `benchmarks/scenarios/kvcache/README.md` in-repo says "**Coming Soon!**"; only blog/presentation numbers exist (cited above).
5. **AIBrix production GPU-savings figures** (1,600 L20 GPUs at peak) come from the project's own blog with no reproducible artifact.
6. **AIBrix `ModelRouter` CRD** — does not exist; routing is gateway-plugin configuration. (Correcting the premise rather than reporting a number.)
7. **GitHub API `forks_count`/`license` fields** — `ungh.cc` (the only reachable metadata source) returns stars/forks/watchers/dates but **not license**; licenses stated in this document come from repo pages/README badges, and I flag any I inferred rather than read.
8. **Topic-page star parsing** — the `/topics/*` HTML I scraped did not yield per-repo star numbers reliably (only repo names); the star numbers in §7.1/§7.2 therefore come from `ungh.cc` per-repo lookups, not from the topic listing.
9. **`sihyeong/Awesome-LLM-Inference-Engine`** and several lower-star topic hits (e.g. `SiO-2/kvcloak`, `cvsp-lab/RestoreKV`, `agentic-in/inferoa`) — names captured, metrics/mechanisms not all verified.

### 8.1 Additional items flagged by the engine research

10. **MindSpore PD disaggregation — a genuine gap, not a negative result.** The GitHub mirror `mindspore-ai/vllm-mindspore` is 6 stars / 0 forks with no releases and is **not** the canonical home (PyPI homepage = `gitee.com/mindspore/vllm-mindspore`, last upload 0.5.1 on 2026-01-13). Gitee and the MindSpore docs site were not consulted. Only inherited vLLM features are verified.
11. **There is no OVMS `--cache_dir` flag** — OpenVINO prefix caching is configured inside the LLM graph config. (Correcting an expectation in the brief rather than reporting a value.)
12. **TGI's prefix-caching introduction version is unpinned**, and no `--prefix-caching` CLI flag exists (it is the `PREFIX_CACHING` env var). The HF docs site returned HTTP 000 from this network.
13. **`NVIDIA/TensorRT-Model-Optimizer` was not investigated at all**; **TRT-LLM `visual_gen` caching could not be verified** (docs URL 404); **`chenyangqiqi/ParaAttention` returns 404** — note xDiT points at a *different* owner, `chengzeyi/ParaAttention`.
14. **`Alibaba PAIServing` / `BladeLLM`: no repository located**, nothing reported. Also unverified: `--kv-cache-dtype` for ipex-llm, KV-cache-aware routing in `dstack` (**not found**), any `zml` KV cache, `garlic-inference` internals.
15. **xDiT's pipeline-parallel KV cache strategies** rest on a **third-party generated wiki** (DeepWiki) because no primary design doc was reachable — flagged as secondary evidence in §5.9.
16. **"TPU Raiden"** (Google, Aug 2026): no official repo found and no confirmation of any KV-cache feature (§7.3). `google/tpu-sync` (132 stars) is an equally uncharacterized lead.
17. **`opendatahub-io/llm-d-kv-cache`** has only 2 stars but is Red Hat's Konflux build of `llm-d-kv-cache` — treat its star count as **not** an adoption signal (§7.3).
18. **Source-type caveats:** all stars/`pushedAt` are `ungh.cc` mirror snapshots from **2026-09-15** and will drift; `api.github.com` was rate-limited (403) throughout this session; `raw.githubusercontent.com` was unreachable and mirrored; arXiv's Atom API returned **429 "Rate exceeded"** so all arXiv verification used `arxiv.org/abs/...` HTML instead; llama.cpp's `ungh.cc` releases endpoint also returned 403, so its release data came from `releases.atom`. Linux `date` reported 2026-09-15, and all fetched sources are consistent with that date.
19. **`ungh.cc/releases` is unreliable** and must be cross-checked against `releases.atom`: it reported "no releases" for `vllm-project/speculators`, `sgl-project/rbg`, `MoonshotAI/checkpoint-engine` and `taco-project/FlexKV`, all of which demonstrably have releases (v0.8.0 / v0.8.0 / v0.4.2 / v1.2.1). Of the whole set, only **KVarN** genuinely has no tagged releases.
20. **Licenses "not detected" ≠ unlicensed.** `FMInference/H2O`, `NVlabs/Atom` and `YaoJiayi/CacheBlend` have **no SPDX id and no LICENSE file** reachable on `main`/`master` through two proxies. Reported as "no license detected", **not** as unlicensed. Likewise `ai-dynamo/nixl` and `ai-dynamo/dynamo` report **NOASSERTION** — NIXL bundles an NVIDIA-proprietary UCX shared object alongside Apache-2.0 code.
21. **Unresolved open items:** `moriio` (a vLLM in-tree connector subpackage) — transport and vendor unidentified; **`ai-dynamo/kvcr`** (35★, created 2026-08-21) — no README retrieved, so its mechanism is **inferred, not confirmed**; **Dynamo's latest release is a `dev` pre-release** (v1.6.0-…-dev.1), so it should not be quoted as stable GA; **LMCache has no plain stable semver tag** in the head of its release feed (nightly-* only), so its last stable version is not reported here.
22. **Methodology bias to disclose:** GitHub **topic pages were thin** (`/topics/kv-cache-offloading` returned exactly **one** repo), and `github.com/search` is blocked for anonymous clients from this network. Discovery therefore leaned on topic star-listings plus `web_search`. A discovery pass with `api.github.com` search-by-stars available (it was 403 all session) would likely surface more.

---

## Sources

*(complete list — every URL used for a non-trivial claim)*

**GitHub repos & APIs**
- https://github.com/vllm-project/aibrix · https://ungh.cc/repos/vllm-project/aibrix · https://ungh.cc/repos/vllm-project/aibrix/releases · https://github.com/vllm-project/aibrix/releases.atom
- https://github.com/vllm-project/aibrix/blob/main/config/crd/orchestration/orchestration.aibrix.ai_kvcaches.yaml
- https://github.com/vllm-project/aibrix/blob/main/config/samples/orchestration_v1alpha1_kvcache.yaml · https://github.com/vllm-project/aibrix/blob/main/development/tutorials/kvcache/kvcache.yaml
- https://github.com/vllm-project/aibrix/blob/main/benchmarks/scenarios/kvcache/README.md
- https://github.com/novitalabs/pegaflow (README on `master`) · https://ungh.cc/repos/novitalabs/pegaflow · https://ungh.cc/repos/novitalabs/pegaflow/releases
- https://github.com/novitalabs/pegaflow/blob/master/docs/server.md · /docs/p2p.md · /docs/goals.md · /docs/pd.md · /docs/metrics.md
- https://github.com/LMCache/LMCache · https://ungh.cc/repos/LMCache/LMCache
- https://github.com/kserve/kserve · https://github.com/llm-d/llm-d · https://github.com/llm-d/llm-d-kv-cache · https://github.com/kubernetes-sigs/gateway-api-inference-extension
- https://github.com/ai-dynamo/dynamo · https://github.com/ai-dynamo/nixl · https://github.com/kvcache-ai/Mooncake · https://github.com/sgl-project/sglang · https://github.com/vllm-project/vllm
- https://github.com/ovg-project/kvcached · https://github.com/uccl-project/uccl · https://github.com/ModelEngine-Group/unified-cache-management · https://github.com/AstraNetLab/CacheRoute · https://github.com/alibaba/tair-kvcache · https://github.com/thu-nics/C2C · https://github.com/huawei-csl/KVarN · https://github.com/Zefan-Cai/R-KV · https://github.com/Zefan-Cai/KVCache-Factory · https://github.com/Zefan-Cai/Awesome-LLM-KV-Cache · https://github.com/snu-mllab/KVzip · https://github.com/ChuangtaoChen-TUM/KVPacket · https://github.com/NoakLiu/PiKV · https://github.com/pegainfer-project/pegainfer · https://github.com/Anbeeld/beellama.cpp · https://github.com/quantumaikr/quant.cpp · https://github.com/huiliyi37/Tianshu-harness · https://github.com/rh-aiservices-bu/sardeenz · https://github.com/jjiantong/Awesome-KV-Cache-Optimization · https://github.com/NVIDIA/kvpress
- https://github.com/thu-pacman/chitu · https://github.com/PaddlePaddle/FastDeploy · https://github.com/MoonshotAI/MoBA · https://github.com/SemiAnalysisAI/InferenceX · https://github.com/GradientHQ/parallax · https://github.com/alibaba/rtp-llm · https://github.com/vllm-project/vllm-ascend · https://github.com/openvinotoolkit/model_server · https://github.com/openvinotoolkit/openvino.genai
- Topic listings mined: https://github.com/topics/kv-cache · https://github.com/topics/kvcache · https://github.com/topics/kv-cache-offloading · https://github.com/topics/kv-cache-management · https://github.com/topics/kv-cache-quantization · https://github.com/topics/prefix-cache · https://github.com/topics/disaggregated-inference · https://github.com/topics/llm-serving · https://github.com/topics/llm-inference · https://github.com/topics/inference-server · https://github.com/topics/llm-router

**AIBrix docs & blogs**
- https://aibrix.readthedocs.io/latest/designs/aibrix-kvcache-offloading-framework.html
- https://aibrix.readthedocs.io/latest/features/kvcache-offloading.html
- https://aibrix.readthedocs.io/latest/designs/aibrix-router.html
- https://aibrix.readthedocs.io/latest/features/kv-event-sync.html
- https://aibrix.readthedocs.io/latest/features/brixbench.html
- https://aibrix.github.io/posts/2026-06-16-v0.7.0-release/ · https://aibrix.github.io/posts/2026-06-16-single-node-pd/ · https://aibrix.github.io/posts/2025-11-26-priskv-intro/ · https://aibrix.github.io/posts/2025-02-05-v0.2.0-release/ · https://aibrix.github.io/sitemap.xml
- https://vllm.ai/blog/aibrix-release

**PegaFlow**
- https://vllm.ai/blog/2026-05-18-pegaflow · https://blog.vllm.com.cn/2026/05/18/pegaflow.html

**SGLang HiCache**
- https://docs.sglang.io/docs/advanced_features/hicache_design · https://docs.sglang.io/docs/advanced_features/hicache_best_practices
- https://lmsys.org/blog/2025-09-10-sglang-hicache/ · https://github.com/sgl-project/sglang/pull/10376

**llm-d KV management**
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/prefix-cache-aware-routing.md

**Papers**
- https://arxiv.org/abs/2504.03648 (AIBrix whitepaper) · https://ar5iv.labs.arxiv.org/html/2504.03648
- https://arxiv.org/abs/2607.08057 (sKis survey) · https://aclanthology.org/2026.findings-acl.1916/ · https://arxiv.org/abs/2607.02574 (KV-management survey)
- https://arxiv.org/abs/2604.00368 (TENT) · https://arxiv.org/abs/2605.10670 (EEP) · https://arxiv.org/abs/2407.00023 (Preble)
- https://arxiv.org/abs/2401.09670 (DistServe) · https://arxiv.org/abs/2311.18677 (Splitwise) · https://arxiv.org/abs/2406.17565 (MemServe) · https://arxiv.org/abs/2401.11181 (TetriInfer) · https://arxiv.org/abs/2312.07104 (SGLang) · https://arxiv.org/abs/2312.05516 (Pensieve) · https://arxiv.org/abs/2405.16444 (CacheBlend) · https://arxiv.org/abs/2310.07240 (CacheGen) · https://arxiv.org/abs/2407.00079 (Mooncake) · https://arxiv.org/abs/2405.04437 (vAttention)
- https://arxiv.org/abs/2402.02750 (KIVI) · https://arxiv.org/abs/2310.19102 (Atom) · https://arxiv.org/abs/2405.04532 (QServe) · https://arxiv.org/abs/2404.14469 (SnapKV) · https://arxiv.org/abs/2306.14048 (H2O) · https://arxiv.org/abs/2309.17453 (StreamingLLM) · https://arxiv.org/abs/2401.18079 (KVQuant) · https://arxiv.org/abs/2403.05527 (GEAR) · https://arxiv.org/abs/2405.14366 (MiniCache) · https://arxiv.org/abs/2406.02069 (PyramidKV) · https://arxiv.org/abs/2406.19707 (InfiniGen) · https://arxiv.org/abs/2409.04992 (InstInfer) · https://arxiv.org/abs/2505.23416 (KVzip)
- https://arxiv.org/abs/2606.19746 (SAC/CXL) · https://arxiv.org/abs/2605.13734 (KVServe) · https://arxiv.org/abs/2608.19677 (CacheRoute) · https://arxiv.org/abs/2606.24506 (CrossPool) · https://arxiv.org/abs/2603.27138 (ScoutAttention) · https://arxiv.org/abs/2607.02640 (Metronome) · https://arxiv.org/abs/2602.10238 (RL eviction) · https://arxiv.org/abs/2602.18750 (HillInfer) · https://arxiv.org/abs/2605.30728 (IBP) · https://arxiv.org/abs/2507.01663 (TransferQueue)
- ❌ Non-existent as cited: 2401.09686, 2406.16818, 2404.01992 resolve to unrelated papers (see §6.0)

**KServe**
- https://github.com/kserve/kserve · https://ungh.cc/repos/kserve/kserve · https://github.com/kserve/kserve/blob/master/pkg/apis/serving/v1alpha2/llm_inference_service_types.go · https://github.com/kserve/kserve/blob/master/config/crd/full/llmisvc/serving.kserve.io_llminferenceservices.yaml · https://github.com/kserve/kserve/blob/master/config/llmisvcconfig/config-llm-scheduler-eppconfig-default.yaml
- https://kserve.github.io/website/blog/kserve-0.17-release · /blog/kserve-0.18-release · /blog/kserve-0.19-release · /blog/kserve-0.20-release · /blog/production-grade-llm-inference-kserve-llm-d-vllm · /blog/cloud-native-ai-inference-kserve-llm-d
- https://kserve.github.io/website/docs/next/model-serving/generative-inference/llmisvc/kv-cache-offloading · https://kserve.github.io/website/docs/next/concepts/architecture/control-plane-llmisvc
- https://llm-d.ai/blog/production-grade-llm-inference-at-scale-kserve-llm-d-vllm · https://developers.redhat.com/articles/2026/04/21/kserve-llm-d-optimized-gen-ai-inference · https://terrytangyuan.github.io/2026/04/21/production-grade-llm-inference-at-scale-kserve-llm-d-vllm/
- https://www.cncf.io/blog/2025/11/11/kserve-becomes-a-cncf-incubating-project/ · https://github.com/kserve/website/blob/main/docs/community/adopters.md
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/prefix-cache-aware-routing.md

**Engines (all fetched 2026-09-15; 296 further URLs in `raw/engines.md`)**
- TensorRT-LLM: https://nvidia.github.io/TensorRT-LLM/latest/llm-api/reference/KvCacheConfig.html · /latest/features/kvcache.html · /latest/features/kv-cache-connector.html · /latest/features/disagg-serving.html · /latest/developer-guide/kv-cache-cold-page-codec.html · /latest/legacy/advanced/kv-cache-management.html · /examples/llm_inference_kv_events.html · https://github.com/NVIDIA/TensorRT-LLM/blob/main/tensorrt_llm/llmapi/llm_args.py · /blob/main/examples/llm-api/llm_kv_cache_connector.py · PRs #11941, #12239
- LMDeploy: https://github.com/InternLM/lmdeploy/blob/main/lmdeploy/cli/utils.py · /blob/main/lmdeploy/cli/serve.py · /blob/main/lmdeploy/pytorch/config.py · /blob/main/lmdeploy/pytorch/paging/block_trie/README.md · /blob/main/docs/en/quantization/kv_quant.md
- TGI: https://github.com/huggingface/text-generation-inference
- llama.cpp: https://github.com/ggml-org/llama.cpp/blob/master/common/arg.cpp · /blob/master/include/llama.h · /blob/master/src/llama-kv-cache.h
- vLLM: https://github.com/vllm-project/vllm/blob/main/vllm/config/cache.py · /blob/main/vllm/config/offload.py · /blob/main/vllm/engine/arg_utils.py · /blob/main/vllm/v1/kv_offload/cpu/spec.py · /blob/main/vllm/v1/kv_offload/cpu/policies/factory.py · https://docs.vllm.ai/en/latest/features/kv_offloading_usage/ · /design/kv_cache_offloading.html · /design/kv_connectors.html · issue https://github.com/vllm-project/vllm/issues/26858
- OpenVINO: https://github.com/openvinotoolkit/model_server · https://github.com/openvinotoolkit/openvino.genai · https://docs.vllm.ai/projects/ascend/en/v0.23.0/user_guide/feature_guide/kv_cache_cpu_offload.html
- Diffusion: https://github.com/vllm-project/vllm-omni/blob/main/vllm_omni/experimental/ar_diffusion/kv_cache/paged.py · /blob/main/vllm_omni/experimental/ar_diffusion/kv_cache/config.py · /blob/main/docs/user_guide/quantization/quantized_kvcache.md · /blob/main/docs/design/feature/model_local_kv_caches.md · /blob/main/docs/design/module/cache_management.md · /blob/main/docs/user_guide/diffusion/cache_acceleration/teacache.md
- LightX2V / xDiT: https://github.com/ModelTC/LightX2V/blob/main/lightx2v/common/kvcache/base.py · /blob/main/lightx2v/common/kvcache/manager.py · /blob/main/docs/EN/source/method_tutorials/cache_source.md · https://github.com/xdit-project/xDiT/blob/main/README.md · https://deepwiki.com/xdit-project/xDiT/4.2-fast-attention-and-kv-cache (⚠️ secondary source)
- New engines: https://sonar.dphn.ai/reference/server-arguments/ · https://github.com/AMD-AGI/Infera · https://github.com/AMD-AGI/Infera/blob/main/README.md · https://github.com/ddalcu/mlx-serve · https://github.com/kvcache-ai/ktransformers · https://github.com/ray-project/ray-llm/blob/master/README.md · https://docs.ray.io/en/latest/serve/llm/overview.html · https://pypi.org/pypi/openllm/json

**Discovery research (full detail: `raw/discovery.md`, 80 artifacts in `raw/discovery/`)**
- kvcached: https://kvcached.org/ · https://github.com/ovg-project/kvcached · https://yifanqiao.notion.site/Solve-the-GPU-Cost-Crisis-with-kvcached-289da9d1f4d68034b17bf2774201b141 · https://arxiv.org/abs/2505.04021 (Prism, OSDI'26) · https://arxiv.org/abs/2508.08448 · https://www.redhat.com/en/blog/running-llms-dynamically-production-limited-resources-hard-we-think-theres-room-another-approach · https://github.com/rh-aiservices-bu/sardeenz
- llm-d KV: https://github.com/llm-d/llm-d-kv-cache (incl. `benchmarking/37-capacity/README.md`) · https://github.com/llm-d/llm-d-router · PR https://github.com/llm-d/llm-d-kv-cache/pull/1886
- UCCL: https://github.com/uccl-project/uccl
- Tair KVCache: https://www.aliyun.com/product/kvcache · https://github.com/alibaba/tair-kvcache/blob/main/README_zh.md
- UCM: https://ucm.readthedocs.io/en/latest · https://modelengine-ai.net/#/ucm · https://github.com/ModelEngine-Group/unified-cache-management/issues/679
- Others: https://github.com/AstraNetLab/CacheRoute · https://github.com/huawei-csl/KVarN · https://github.com/Zefan-Cai/R-KV · https://github.com/thu-nics/C2C · https://github.com/snu-mllab/KVzip · https://github.com/NVIDIA/kvpress · https://github.com/NoakLiu/PiKV · https://github.com/pegainfer-project/pegainfer · https://arxiv.org/abs/2605.08581 (PRISM naming-collision check)

**Vendor / org sweeps (full detail: `raw/bytedance.md`, `raw/baidu.md`, `raw/huawei_ascend.md`)**
- PrisDB attribution + EIC: https://github.com/vllm-project/aibrix/blob/main/python/aibrix_kvcache/README.md (mirrored in SGLang's AIBrix-KVCache integration doc) · https://github.com/sgl-project/sglang (PR #10271, `eic` HiCache backend) · https://github.com/LMCache/LMCache (PR #1930, `eic://` connector) · https://github.com/vllm-project/aibrix (PR #1718, EIC L2 connector)
- PrisKV transports: https://github.com/aibrix/PrisKV (README)
- ByteDance orgs: https://github.com/bytedance/InfiniStore · https://github.com/ByteDance-Seed/ShadowKV · https://github.com/verl-project/verl · https://github.com/verl-project/verl/blob/main/docs/perf/rollout_kv_offload.md
- Baidu/FastDeploy: https://github.com/PaddlePaddle/FastDeploy · https://arxiv.org/abs/2403.19708 (AttentionStore name collision)

**Other repos (metrics + READMEs fetched 2026-09-15)**
- Companion research files with full detail: `raw/repos_verify.md` (470 lines; 179 artifacts across 54 repos in `raw/repos/`), `raw/engines.md` (1,058 lines, 296 URLs; 118 artifacts in `raw/engines/`), `raw/discovery.md` (741 lines; 80 artifacts in `raw/discovery/`), `raw/spinouts_papers.md` (495 lines; artifacts in `raw/spinouts/`), `raw/kserve.md` (811 lines; 45 artifacts in `raw/kserve/`)
- https://github.com/taco-project/FlexKV (README + PRs #34328 vllm, #5858 dynamo, #29701 sglang) · https://github.com/bytedance/InfiniStore · https://github.com/llm-d/llm-d-kv-cache · https://github.com/llm-d/llm-d-router · https://github.com/ovg-project/kvcached · https://github.com/ModelEngine-Group/unified-cache-management · https://github.com/AstraNetLab/CacheRoute · https://github.com/alibaba/tair-kvcache · https://github.com/uccl-project/uccl · https://github.com/aibrix/PrisKV · https://github.com/NVIDIA/kvpress · https://github.com/Zefan-Cai/R-KV · https://github.com/Zefan-Cai/KVCache-Factory · https://github.com/huawei-csl/KVarN · https://github.com/thu-nics/C2C · https://github.com/snu-mllab/KVzip · https://github.com/NoakLiu/PiKV · https://github.com/ChuangtaoChen-TUM/KVPacket · https://github.com/Anbeeld/beellama.cpp · https://github.com/kvcache-ai/ktransformers · https://github.com/ai-dynamo/kvcr
- https://github.com/vllm-project/speculators · https://github.com/sgl-project/rbg · https://github.com/MoonshotAI/checkpoint-engine · https://github.com/xLLM-AI/xllm · https://github.com/ModelTC/LightX2V · https://github.com/vllm-project/vllm-omni · https://github.com/sgl-project/sglang-omni · https://github.com/radixark/miles · https://github.com/CurvineIO/curvine · https://github.com/Ascend/TransferQueue · https://github.com/pegainfer-project/pegainfer · https://github.com/thu-pacman/chitu · https://github.com/PaddlePaddle/FastDeploy · https://github.com/alibaba/rtp-llm · https://github.com/GradientHQ/parallax · https://github.com/SemiAnalysisAI/InferenceX · https://github.com/MoonshotAI/MoBA
- NVIDIA Dynamo KBVM + offloading matrix: https://docs.nvidia.com/dynamo/ (KVBM design; Offloading Support Matrix; `llms.txt` index) · https://github.com/ai-dynamo/dynamo · https://github.com/ai-dynamo/nixl

**Companies / press**
- https://siliconangle.com/2026/01/22/inferact-launches-150m-funding-commercialize-vllm/ (Inferact)
- https://www.businesswire.com/news/home/20260527958597/en/ · https://siliconangle.com/2026/05/27/tensormesh-taps-nvidia-amd-coreweave-funding-fix-llm-memory-problems/ (Tensormesh)
