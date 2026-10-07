# Emerging Standards and Interfaces for KV Cache in LLM Inference Serving
### Is there convergence in 2026?

**Research date:** 2026-09-15 (all "as of" claims are relative to this date)
**Scope:** KV-cache transfer/offload interfaces, KV-cache event schemas, gateway-level inference routing APIs, and the standardisation status of each.
**Method:** primary sources — project source trees (vLLM `main` tarball, pinned at the commit fetched 2026-09-15), raw docs from `raw.githubusercontent.com`, project release Atom feeds, PyPI JSON, GitHub HTML metadata. Raw artifacts are under `kvcache-research/raw/`.

**Reliability legend used throughout:**
- ✅ **Verified** — read directly from source code, raw doc, release feed, or PyPI at research time.
- ⚠️ **Partial** — verified from a secondary/derived source, or verified for one version only.
- ❌ **Not verified** — could not confirm; explicitly flagged.

**Caveat on measurement:** `api.github.com` was **hard rate-limited (HTTP 403)** from this network for the whole session, so star/fork counts come from scraping the GitHub HTML pages (the `repo-stars-counter-star` / `repo-network-counter` elements) and are accurate to ±(rounding) but not machine-verified via API. Release lists come from each repo's `releases.atom`.

---

## 0. Executive summary

**Verdict: partial convergence, asymmetric.** In 2026 the ecosystem has converged on *three* de-facto interface layers, at very different levels of maturity, and has **not** converged on a single normative KV-cache specification.

| Layer | De-facto standard | Status | Who has converged |
|---|---|---|---|
| **Data plane (KV bytes moving)** | **NIXL** | Strong de-facto, weak de-jure. Apache-2.0, v1.4.1 (2026-09-01), no governance doc, no formal spec, no ABI policy. | vLLM, SGLang, Dynamo, llm-d, TensorRT-LLM, LMCache, Mooncake, TensorRT-LLM-family, plus AWS EFA / WEKA / DDN storage vendors |
| **KV-cache lifecycle events** | **The vLLM `KVCacheEvent` schema** (`BlockStored` / `BlockRemoved` / `AllBlocksCleared`, msgpack) | Converged *schema*, divergent *transport + envelope + sequence semantics*. SGLang adopted it explicitly; llm-d consumes both with two adapters; Dynamo keeps its own `event_id`/`dp_rank` envelope and bridges via ZMQ→NATS. | vLLM, SGLang, llm-d (adapter), Dynamo (bridge) |
| **Control plane (scheduling/routing)** | **Gateway API Inference Extension (GAIE)** for the Kubernetes CRD layer | GAIE's README says "This project is GA'd!". But in v1.6.0 (2026-08) the EPP, InferenceObjective, InferenceModelRewrite and BBR **moved out** to llm-d repos. So the *standard* narrowed; the *implementation* moved to a CNCF Sandbox project. | llm-d, Dynamo, AIBrix, KServe (consumers) |

**The single most important negative finding:** the one explicit standardisation proposal for the KV layer inside vLLM — **RFC #20492 "KV-Cache Interoperability API Standardization"** — was **closed as `not planned`** (labelled `RFC`, `stale`, "Over 90 days of inactivity"). See [§5.1](#51-the-failed-standardisation-attempt-rfc-20492). Its *technical* content partly shipped anyway (reproducible `sha256_cbor` block hashing), but the *contractual* half (versioned public KVEvents schema, language-agnostic reference libraries) did not.

**Second most important finding:** convergence in 2026 is happening **at the connector interface, not the spec**. Everyone now speaks a "KV connector" and a "KV event" language, but each engine defines its own Python/Go/Rust interface with the same shape and no shared header file. vLLM's own base class still warns at construction: *"Initializing KVConnectorBase_V1. This API is experimental and subject to change in the future as we iterate the design."* ✅ (source below)

---

## 1. NIXL (NVIDIA Inference Xfer Library)

**Repo:** <https://github.com/ai-dynamo/nixl>
**Research basis:** `README.md`, `meson.build`, `CONTRIBUTING.md`, `docs/nixl.md`, `docs/BackendGuide.md`, `docs/python_api.md`, `docs/telemetry.md`, release Atom feed, PyPI — all fetched 2026-09-15.

### 1.1 Version, release cadence, licence

| Fact | Value | Source |
|---|---|---|
| Latest release | **v1.4.1** | release feed / PyPI |
| v1.4.1 published | **2026-09-01T23:51:45Z** | `releases.atom` |
| PyPI wheel `nixl` version | **1.4.1**, uploaded 2026-09-01T23:45:05Z | <https://pypi.org/pypi/nixl/json> |
| PyPI licence expression | **`MIT AND Apache-2.0`** | PyPI JSON |
| Source licence | Apache-2.0 (SPDX headers), *but* PyPI wheels bundle NVIDIA-proprietary `libuct_ib_mlx5_*.so` under `LicenseRef-NvidiaProprietary` | `README.md` §Third-Party Components |
| Stars / forks (HTML scrape) | **1,256** stars / **441** forks | GitHub repo HTML |
| Tested UCX | **1.23.x** in README; **v1.22.x** referenced in the 1.4.0 release note ("UCX is updated to v1.22.x to unlock rendezvous PUT/GET protocols") | `README.md`, 1.4.0 notes |

Release cadence from the feed (dates are `published`, UTC):

```
v1.4.1        2026-09-01
v1.4.0-rc3    2026-08-17
v1.4.0-rc2    2026-08-14
v1.4.0        2026-08-14
v1.3.2        2026-07-25
v1.3.1        2026-07-08
v1.3.0        2026-06-15
v1.2.0        2026-05-30
v1.1.0        2026-05-12
v1.0.1        2026-04-14
```

→ **~1 minor release per month through 2026**, with patch releases between. `v1.0.0` landed in the **April 2026** window (v1.0.1 on 2026-04-14). ⚠️ The *exact* v1.0.0 GA date could not be fetched (the releases page beyond the 10 most recent entries, and `v1.0.0` specifically, were not retrievable in this session). A Dynamo PR comment corroborates the ≥1.0.0 threshold: *"Abseil source-build prereq that NIXL >= 1.0.0 requires"* ([ai-dynamo/dynamo#9705](https://github.com/ai-dynamo/dynamo/pull/9705)).

Note the disagreement worth flagging: the README says *"NIXL was tested with UCX version 1.23.x"* while the 1.4.0 notes say UCX was updated to v1.22.x. Both are quoted verbatim; I did not resolve which is stale. ❌

### 1.2 Plugin / backend list (exact, from `meson.build` at v1.4.1)

```meson
all_plugins = ['UCX', 'LIBFABRIC', 'POSIX', 'OBJ', 'GDS', 'GDS_MT', 'MOONCAKE',
               'HF3FS', 'GUSLI', 'GPUNETIO', 'UCCL', 'AZURE_BLOB', 'INFINIA',
               'TELEMETRY_DOCA']
```

That is **14 built-in plugins**. Differences against the list in the research brief:

- ✅ Present: `UCX`, `POSIX`, `GDS`, `GDS_MT`, `OBJ`, `AZURE_BLOB`, `HF3FS`, `MOONCAKE`, `GUSLI`, `UCCL`, `LIBFABRIC`, `GPUNETIO`.
- ⚠️ **`NVSHMEM` is NOT a NIXL plugin.** It does not appear in `all_plugins` at v1.4.1. The README's ROCm "Known gaps" section explicitly confirms the absence and frames it as a gap: *"No NVSHMEM-equivalent backend yet (rocSHMEM analog is a candidate for a future plugin)."*
- 🆕 Two plugins **not** in the brief: **`INFINIA`** and **`TELEMETRY_DOCA`**.
- Separate from the transfer plugins, there is a **tracing plugin** framework: `nixl::trace` with a loadable NVTX backend (`libtrace_backend_nvtx.so`), added in 1.4.0.
- Plugins are built as separate `.so` modules and can be statically linked via `-Dstatic_plugins=...` (which defines `-DSTATIC_PLUGIN_<NAME>`).

Backend selection is dynamic and memory-type driven: *"NIXL determines the optimal transfer backend based on the memory types used in a transfer, as well as common backends available in both agents"* (`docs/nixl.md`). Segment/mem types are `DRAM`, `VRAM`, `BLK`, `FILE`, `OBJ` (`docs/BackendGuide.md` table).

**Failure-mode caveat, verified:** the GDS/GDS_MT, GPUNETIO and LIBFABRIC plugins **silently skip** when their CUDA/cuFile/DOCA deps are missing, and are disabled on ROCm pending header refactors. So "NIXL supports X plugin" is not portable across builds — backend availability is a build-time property. This matters for anyone treating NIXL as an ABI.

### 1.3 API model

Three abstractions (`docs/nixl.md` §Design): **Transfer Agent**, **Memory Section**, **Metadata Handler**.

```
create_agent(name, optional_devices)
create_transfer_backend(backend_init)          # per backend
register_memory(desc_list)                     # Memory Section registration

get_local_metadata() / load_remote_metadata()  # side channel
send_local_metadata() / fetch_remote_metadata() # central metadata (etcd/Redis)
make_connection(remote_agent_name)             # optional pre-connect

hdl = create_xfer_req(op RD|WR, local_descs, target_descs, target_agent_name, notif_msg)
post_transfer_request(hdl)
get_xfer_status(hdl)                           # non-blocking poll
```

- **Notifications** are first-class in the transfer API: a `notif_msg` can be attached at handle-creation time, at post time, or changed per repost. Receivers use `send_notif` / `get_new_notifs`.
- **`QueryMem` API** — query memory/storage information and accessibility (Python API feature list).
- **Python bindings**, pybind11: agent management, memory registration, transfer ops, QueryMem, backend management. Entry point: `nixl.nixl_agent('agent1')`, `nixl_agent_config(backends=[])`, `agent.get_plugin_params("UCX")`, `agent.create_backend("UCX", params)`.
  - **Backend init params are discoverable at runtime** via `get_plugin_params(backend)` returning defaults — this is the closest thing to a dynamic capability-negotiation mechanism in the whole NIXL API. Documented example: `ucx_error_handling_mode` ∈ {`peer`, `none`}, *"influences UCP transport lane selection in addition to error reporting."*
- **Rust bindings** exist (`nixl-sys`, built with `-Drust=true`, consumed as `nixl-sys = { path = "..." }` in `Cargo.toml`).
- **Metadata distribution** via ETCD is supported out of the box: `NIXL_ETCD_ENDPOINTS`, `NIXL_ETCD_NAMESPACE` (default `/nixl/agents`). `docs/nixl.md` also names Redis as a candidate central metadata service.

### 1.4 "NIXL Connect" (the Dynamo Python layer)

The file `docs/api/nixl-connect/README.md` **exists** in the Dynamo repo per search results and a Dynamo commit *"docs: Update nixl_connect README (#2320)"* ([fa4a7f1](https://github.com/ai-dynamo/dynamo/commit/fa4a7f1e71479cbf2bb735551296862c4399c418)) and a pinned-commit copy at [5a1e655](https://github.com/ai-dynamo/dynamo/blob/5a1e6556526340897bdaa372f1a44309a1998141/docs/api/nixl-connect/README.md). ⚠️ **I could not fetch its contents**: `raw.githubusercontent.com/ai-dynamo/dynamo` was consistently unreachable from this network (connection timeouts on every attempt, while `llm-d`, `sglang`, `vllm-project` raw fetches succeeded). So the description below is from file *existence and provenance*, not its text:
- It is part of Dynamo (not NIXL), under `docs/api/nixl-connect/`, i.e. Dynamo exposes `nixl_connect` as a **documented public API surface** for its Python components.
- ❌ I did not verify its class/function names, its relationship to `nixl.nixl_agent`, or whether it defines any schema of its own. **Treat any claim about `nixl_connect` internals as unverified.**

### 1.5 Who implements or consumes NIXL

✅ Verified consumers:

| Consumer | How | Evidence |
|---|---|---|
| **vLLM** | `NixlConnector`, `NixlPullConnector`, `NixlPushConnector` registered in `KVConnectorFactory`; `NixlTransport` in the tiering P2P data plane; `vllm/distributed/nixl_utils.py` (`NixlWrapper`) | vLLM `main` source |
| **vLLM dependency pin** | `requirements/kv_connectors.txt` contains **`nixl == 1.4.1`** — an exact `==` pin | vLLM `main` source |
| **SGLang** | HiCache L3 storage backend `nixl` (`--hicache-storage-backend nixl`), `class HiCacheStorage(ABC)` plugin | SGLang HiCache doc |
| **Dynamo** | NIXL is Dynamo's transfer layer; `nixl-sys` bump PRs; NIXL version pinned via `NIXL_REF` | Dynamo PRs #9265, #12217 |
| **LMCache** | Storage/transport backends include NIXL | LMCache README |
| **TensorRT-LLM** | ⚠️ *Partial*: search results show `"backend": "NIXL"` in TensorRT-LLM's `test_disaggregated_serving.py` and a series of "Python KV transceiver" PRs (#11136, #11978). I did **not** read TensorRT-LLM source directly (fetch timed out), so treat as strongly suggested but not source-verified. |
| **AWS** | *"AWS adds support for NIXL with EFA... AWS supports NIXL version 1.0.0 or higher with EFA installer version 1.47.0 or higher on all EFA-enabled EC2 instance types in all AWS regions at no additional cost."* Posted **Mar 19, 2026** | <https://aws.amazon.com/about-aws/whats-new/2026/03/aws-support-nixl-with-efa/> |
| **Storage vendors** | WEKA ("WEKA accelerates AI inference with NVIDIA Dynamo and NVIDIA NIXL"); DDN claims *"first storage vendor natively integrated into NVIDIA KV cache management"* | vendor blogs (secondary) |
| **AMD ROCm** | README documents building NIXL for ROCm: `-Dwheel_variant=rocm` → wheel `nixl_rocm`; `UCX` is the primary transport for AMD GPU memory (requires UCX built `--with-rocm`). ❌ No NVSHMEM-equivalent. | NIXL README |
| **llm-d** | ⚠️ Partial: llm-d is a heavy NIXL consumer in its P2P/KV-transfer paths, but I could not fetch a single llm-d doc that states NIXL as its transport in this session. llm-d's own `networking-for-distributed-inference-llm-d` blog page 404'd. |

**The strongest "de-facto standard" evidence is the AWS announcement sentence itself:** *"NIXL is interoperable with all EFA-enabled EC2 instances and integrates natively with frameworks including NVIDIA Dynamo, SGLang, and vLLM."* That is a hyperscaler naming NIXL as *the* KV-transfer abstraction for three independent engines.

### 1.6 Is there a formal spec, ABI, or versioning policy? Is it moving to open governance?

**Answers, all negative except one:**

| Question | Answer | Evidence |
|---|---|---|
| Formal interface specification? | **No.** No SPEC.md / versioned protocol document. Design intent lives in `docs/nixl.md` (`docs/BackendGuide.md` is a *how to write a plugin* guide, not a normative spec). | file checks |
| Semantic-versioning policy? | **No.** `VERSIONING.md` → HTTP 404. | direct fetch |
| ABI stability policy? | **No explicit policy.** Closest statement is in `CONTRIBUTING.md`: *"NIXL is used in performance-critical environments where reliability is paramount. We maintain backward compatibility and stable APIs for our users."* Declarative, unversioned, with no compatibility matrix. | `CONTRIBUTING.md` |
| GOVERNANCE.md? | **404 — does not exist.** | direct fetch |
| ROADMAP.md? | **404 — does not exist.** | direct fetch |
| Foundation affiliation / open governance? | **❌ None found.** No mention in the repo, no LF AI & Data / PyTorch Foundation / CNCF listing surfaced. NIXL is hosted at `github.com/ai-dynamo/nixl` — the `ai-dynamo` org, i.e. inside NVIDIA's Dynamo project. The README presents NIXL as *"targeted for accelerating point to point communications in AI inference frameworks such as NVIDIA Dynamo."* | repo + README |
| Is it *treated* as a standard? | **Yes, in practice** — but by adoption and by ecosystem investment (AWS EFA integration; storage-vendor integrations; three engines), not by any formal standardisation act. | AWS / vendor sources |
| Versioning in practice | **Exact pinning by consumers.** vLLM pins `nixl == 1.4.1`. That is the opposite of an ABI-stability signal: it says consumers expect breakage. | `requirements/kv_connectors.txt` |

**Interpretation.** NIXL is the **most standardised piece of the KV stack by adoption** and the **least standardised by process**. There is no governance, no spec, no semver policy, and no foundation. The API-evolution discipline that exists is one sentence in a contributor guide plus a plugin ABI that is explicitly build-configuration-dependent. This is the sharpest divergence between "standard" and "widely used" in the whole report.

---

## 2. vLLM KV connector API

**Research basis:** vLLM `main` tarball (fetched 2026-09-15 via `codeload`), i.e. the code that will become the next release after **vLLM 0.29.0** (PyPI, uploaded **2026-09-09T08:58:32Z**, Apache-2.0).

⚠️ **Documentation-status finding:** the URL in the brief, `https://docs.vllm.ai/en/latest/design/kv_connector.html`, **no longer exists as a design page.** The docs site catch-all serves `HTTP 200` with a redirect to `https://docs.vllm.ai/en/latest/contributing/` for any unknown path (verified with a deliberately bogus path, which behaved identically). `docs/design/` in the repo contains no `kv_connector.md`. The KV connector's "design doc" is therefore **the docstring of `vllm/distributed/kv_transfer/kv_connector/v1/base.py`**, which is reproduced in §2.1 below. Related current pages that *do* exist: `docs/features/nixl_connector_usage.md`, `docs/features/nixl_connector_compatibility.md`, `docs/features/disagg_prefill.md`, `docs/features/kv_offloading_usage.md`, `docs/design/nixl_kv_cache_lease.md`, `docs/design/nixl_kv_push_connector.md`.

### 2.1 `KVConnectorBase_V1` — the abstract interface

Located at `vllm/distributed/kv_transfer/kv_connector/v1/base.py` (760 lines at fetch time). Constructor:

```python
KVConnectorBase_V1(vllm_config: VllmConfig,
                   role: KVConnectorRole,
                   kv_cache_config: KVCacheConfig)
```

and it emits, **at every construction**:

> `"Initializing KVConnectorBase_V1. This API is experimental and subject to change in the future as we iterate the design."`

**So: there is no "KV connector API 1.0", no stabilization, and no versioned connector ABI in vLLM as of 2026-09-15.** The `_V1` suffix refers to the v1 *engine*, not to an interface version number. This is the direct answer to the brief's question about a 2026 "API 1.0"/stabilization milestone: **it has not happened in vLLM.** (See §5 for the *separate* claim that llm-d/GAIE moved toward standardisation.)

**Scheduler-side methods** (run in the scheduler process):

| Method | Contract |
|---|---|
| `get_num_new_matched_tokens(request, num_computed_tokens) -> (int \| None, bool)` | `@abstractmethod`. Returns tokens loadable beyond `num_computed_tokens`; `None` = "ask me again later"; second element = async? *"Must be 'False' if the first element is 0."* Must be **side-effect free**, may be called multiple times per request. Only the largest prefix actually available may be reported. |
| `update_state_after_alloc(request, blocks, num_external_tokens)` | `@abstractmethod`. **May be called twice** for one request (once for connector tokens, once after transfer completes). Explicit warning: *"Decide whether to load based on `num_external_tokens`, not on whether `blocks` is empty"* — because a non-chosen `MultiConnector` sub-connector still receives real blocks. |
| `build_connector_meta(scheduler_output) -> KVConnectorMetadata` | `@abstractmethod`. Must **not** mutate `scheduler_output`; **resets connector state**. |
| `update_connector_output(connector_output: KVConnectorOutput)` | From worker-side output back to scheduler state. |
| `request_finished(request, block_ids) -> (bool, dict \| None)` | Called **exactly once**, before blocks are freed. `True` = connector takes over async freeing. Second element is optional KV transfer params surfaced in request outputs. |
| `request_finished_all_groups(request, block_ids: tuple[list[int], ...])` | On `SupportsHMA` only — hybrid memory allocator variant. |
| `register_finished_partial_tail(request, block_ids, partial_tail_offloads)` | Finish-time partial-tail sources registered *before* block cleanup. |
| `take_events() -> Iterable[KVCacheEvent]` | New KV events since last call. |
| `bind_kv_cache_manager(kv_cache_manager)` / `bind_gpu_block_pool(gpu_block_pool)` | *"Bind the GPU block pool to the connector for per-GPU block status tracking. For example, inc/dec ref counts, or iterate over the prefix cache blocks."* |
| `on_new_request(request)` | New hook — the lease-renewal design depends on it (heartbeating must start when the request *enters the scheduler*, not when scheduled). |
| `has_pending_push_work()`, `has_pending_block_frees()` | Keep-alive / preemption signals for push-mode and async-free connectors. |
| `reset_cache()`, `get_finished_count()` | Reset; expected send/recv completion count for `KVOutputAggregator`. |

Class-level capability negotiation:
- `get_required_kvcache_layout(vllm_config) -> str | None` — e.g. `"HND"` or `"NHD"`.
- `requires_piecewise_for_cudagraph(extra_config) -> bool` — connectors doing layer-by-layer async ops **must** return `True`; otherwise CUDA-graph replay causes data races.
- `supports_divergent_local_hybrid_hits` (property, default `False`), `requires_kv_delivery` (property; **defaults to `self._kv_transfer_config.is_kv_producer`** — best-effort caches return `False`).

**Worker-side methods:**

| Method | Contract |
|---|---|
| `register_kv_caches(kv_caches: dict[str, torch.Tensor])` | *"Useful for pre-registering the KV Caches in the KVConnector (e.g. for NIXL)."* |
| `set_host_xfer_buffer_ops(copy_operation: CopyBlocksOp)` | xPU-specific H2D/D2H copy op; needed when a host buffer is used (e.g. `NixlConnector`). `CopyBlocksOp` signature: `(s_tensor_list, d_tensor_list, s_indices, d_indices, direction: Literal["h2d","d2h"])`. |
| `start_load_kv(forward_context, **kwargs)`, `wait_for_layer_load(layer_name)`, `save_kv_layer(layer_name, kv_layer, attn_metadata, **kwargs)`, `wait_for_save()` | The four `@abstractmethod`s. Layer-pipelining friendly. |
| `get_finished(finished_req_ids) -> (sending, recving)` | Legacy pair. |
| `get_transfer_results(finished_req_ids) -> KVConnectorTransferResults` | Newer snapshot form: `finished_sending`, `finished_recving`, **`failed_recving`**. *"Failed receives also appear in `finished_recving` so the scheduler can release the request from its transfer wait state."* |
| `get_block_ids_with_load_errors() -> set[int]` | Failed blocks reported **no later than** the pass in which the req id is returned by `get_transfer_results()`. |
| `handle_preemptions(kv_connector_metadata)` | *"Handle preempted requests or evicted blocks BEFORE they are overwritten. Needed for connectors which use async saves (e.g., OffloadingConnector)."* |
| `build_connector_worker_meta() -> KVConnectorWorkerMetadata \| None` | Worker→scheduler metadata; each worker emits its own, aggregated via `KVConnectorWorkerMetadata.aggregate(other)`. |
| `get_handshake_metadata()` / `set_xfer_handshake_metadata()` / `set_xfer_handshake_metadata_pp_aware()` | **Out-of-band P/D handshake.** The `_pp_aware` variant is keyed by `(pp_rank, tp_rank)` and raises `ValueError` if a connector doesn't support PP-disaggregated KV transfer: *"received pp_rank > 0 handshake metadata but does not support PP-disaggregated KV transfer."* |
| `get_kv_connector_stats()`, `get_kv_connector_kv_cache_events()`, `build_prom_metrics(...)`, `finish_forward()`, `reset_capture_state()`, `shutdown()` | Observability + lifecycle. |

Supporting metadata ABCs: `KVConnectorMetadata` (scheduler→worker), `KVConnectorWorkerMetadata` (worker→scheduler, with `aggregate`), `KVConnectorHandshakeMetadata` (*"needs to [be] serializable"*).

### 2.2 Role / `kv_role`

From `vllm/config/kv_transfer.py`:

```python
KVProducer = Literal["kv_producer", "kv_both"]
KVConsumer = Literal["kv_consumer", "kv_both"]
KVRole = Literal[KVProducer, KVConsumer]
```

Separately, `KVConnectorRole` (the *process* role) is an enum: `SCHEDULER = 0`, `WORKER = 1` — *"v1 connector is explicitly separated into two roles... We build separately to enforce strict separation."*

`is_kv_producer` / `is_kv_consumer` are derived properties, and `KVTransferConfig.has_connector(name)` transparently inspects `MultiConnector` children.

**Deprecation in flight:** `kv_role="kv_both"` for `NixlConnector` is deprecated in favour of explicit producer/consumer, with a stated future removal ([vLLM#33702](https://github.com/vllm-project/vllm/issues/33702), PR #43874 *"[NixlConnector] Initiate deprecation cycle for `kv_both` role"*). ⚠️ PR number from search metadata; the deprecation text itself is ✅ verified in `docs/features/nixl_connector_usage.md`.

### 2.3 `kv_transfer_params` and P/D disaggregation

The P/D path is *not* carried in `kv_transfer_params` alone; it is a combination:

1. `request_finished(...)` returns optional `KVTransferParams` that vLLM surfaces in **request outputs**.
2. A **proxy/router** is required. The NIXL usage doc ships `examples/disaggregated/disaggregated_serving/disagg_proxy_multiturn.py` and states plainly: *"Requires a stateful proxy (or equivalent router) to track and forward `kv_transfer_params` between turns."*
3. For multi-turn reuse, **vLLM introduces a non-standard request field `conversation_id`** (*"a non-standard extension to the OpenAI API. It is consumed by the proxy and not forwarded to the vLLM engine."*). This is a concrete example of a *KV-cache-driven* wire-protocol extension that no standard covers.
4. Out-of-band P/D connection info is exchanged via `KVConnectorHandshakeMetadata`, not via `kv_transfer_params`.
5. Side-channel ports: `VLLM_NIXL_SIDE_CHANNEL_PORT` (default 5600) and `VLLM_NIXL_SIDE_CHANNEL_HOST` (default `localhost`); for TP/DP, *"each worker's port on a node is computed as: base_port + dp_rank"*.

**Bidirectional KV transfer (P pulls from D for multi-turn)** is now a first-class documented feature (`bidirectional_kv_xfer: true` on both sides), with `kv_recompute_threshold` (default 64) and `decoder_kv_blocks_ttl` (default 480 s). Documented correctness limitation: with reasoning models whose thinking traces the client strips, *"the block-alignment logic assumes P's prompt is a prefix of D's sequence"* and pulling D's blocks "transfers cache computed for the wrong token positions, producing incorrect results" ([vLLM#43094](https://github.com/vllm-project/vllm/issues/43094)).

**NIXL KV cache lease renewal** (new, `docs/design/nixl_kv_cache_lease.md`, introduced in PR #41383) replaces the single large timeout (`VLLM_NIXL_ABORT_REQUEST_TIMEOUT`, 480 s default) with: initial lease `kv_lease_duration` (default **30 s**), extended by heartbeats sent **from D to P**, each extending by `lease_duration * 2/3` (~20 s), heartbeat interval `lease_duration // 6` (~5 s), `"HB:"` prefix on the message, routed through `_get_new_notifs()` / `_handle_heartbeat()` using `max(old_expiry, now + lease_extension)`. Heartbeats deliberately **reuse NIXL's `send_notif`/`get_new_notifs`** rather than adding a channel, and run **in the forward loop, not a background thread**. Bidirectional mode instead uses a fixed `decoder_kv_blocks_ttl` because turn timing is client-dependent; D communicates expiry back and P *"estimates the clock offset to D from the handshake round-trip"* to compare `perf_counter` values across processes.

⚠️ Note this is a **vLLM-specific protocol riding on NIXL notifications** — the notification *carrier* is the de-facto standard, the *payload semantics* are vLLM-only and undocumented outside vLLM. No counterpart exists in SGLang or Dynamo as far as I could verify.

### 2.4 `MultiConnector`

`MultiConnector` composes N child connectors from `kv_connector_extra_config["connectors"]`. Key semantics verified:

- It itself implements `SupportsHMA`, but *"effective support depends on every configured child"* — `MultiConnector.all_children_support_hma(kv_transfer_config)`.
- Non-selected children still receive the request's real blocks, which is why `update_state_after_alloc` must branch on `num_external_tokens`, not on `blocks` being empty.
- Documented example: `MultiConnector` wrapping `NixlConnector` + `ExampleConnector` for simultaneous P/D transfer and shared-storage offload.
- A guard exists for `HiSparseConnector`: *"Only one HiSparseConnector may be configured"*, and it requires `host_pool_gib`.

### 2.5 Registered connectors and out-of-tree registration

`KVConnectorFactory` (`vllm/distributed/kv_transfer/kv_connector/factory.py`) — full registry as of fetch:

```
ExampleConnector  ExampleHiddenStatesConnector  LMCacheConnectorV1  LMCacheMPConnector
NixlConnector  NixlPullConnector  NixlPushConnector  MultiConnector
HiSparseConnector  MoRIIOConnector  OffloadingConnector  DecodeBenchConnector
MooncakeConnector  MooncakeStoreConnector  FlexKVConnectorV1
SimpleCPUOffloadConnector  HF3FSKVConnector
```

**Out-of-tree registration mechanism** (this is the closest thing to an "external KV connector contract" that exists):

```python
KVConnectorFactory.register_connector(name, module_path, class_name)   # programmatic
# or, via config, no registration needed:
kv_connector_module_path = "my_package.my_module"   # takes priority over the internal registry
kv_connector        = "MyConnectorClass"
```

And — critically — a **hard, enforced constructor contract** for external connectors:

> *"Connector {cls} uses deprecated 2-argument constructor signature. External v1 KV connectors must accept `kv_cache_config` as the third constructor argument and pass it to `super().__init__()`."* → raised as `ValueError`, logged at `error` level.

This is the single most "contract-like" artefact in the vLLM KV surface: an enforced signature for third-party connectors, but **no version number attached to it**.

Also verified: **`SharedStorageConnector` was renamed to `ExampleConnector`** — this matters because external tutorials and older blog posts reference the old name. Search surfaced [vLLM#49399](https://github.com/vllm-project/vllm/issues/49399) (*"Post-#30201 SharedStorage→ExampleConnector rename still lacks migration docs and stale public examples"*, open) and [PR #49868](https://github.com/vllm-project/vllm/pull/49868) (docs migration note). ⚠️ Issue/PR numbers from search; the *current name* `ExampleConnector` is ✅ verified in the registry and `docs/features/disagg_prefill.md`.

### 2.6 The v1 Offloading API (`vllm/v1/kv_offload/`)

This is the newest and most "standardisable" surface in vLLM. Tree at fetch time:

```
vllm/v1/kv_offload/
├── base.py        config.py  factory.py  file_mapper.py
├── cpu/           spec.py manager.py gpu_worker.py common.py shared_offload_region.py
│                  swap_blocks_triton.py policies/{base,lru,arc,factory}.py
└── tiering/       spec.py base.py manager.py factory.py metrics.py async_lookup.py
                   example/manager.py
                   fs/{io,manager,thread_pool}.py
                   kvcr/manager.py
                   obj/{config,manager}.py
                   p2p/{manager.py, control/{base,zmq}.py,
                        data/{base,nixl}.py, session/{client,server,session,protocol}.py}
```

**Two specs, both registered in `OffloadingSpecFactory`:**

```python
OffloadingSpecFactory.register_spec("CPUOffloadingSpec",    "vllm.v1.kv_offload.cpu.spec",    "CPUOffloadingSpec")
OffloadingSpecFactory.register_spec("TieringOffloadingSpec", "vllm.v1.kv_offload.tiering.spec", "TieringOffloadingSpec")
```

`TieringOffloadingSpec` **subclasses `CPUOffloadingSpec`**; the CPU tier is the mandatory primary tier and secondary tiers must route through it:

> *"Secondary tiers cannot directly access GPU memory. All data transfers must go through the CPU (primary) tier: Store: GPU → CPU (primary) → secondary (cascade); Load: secondary → CPU (primary) → GPU (promotion)."*

**Key abstractions in `base.py`:**

| Name | Meaning |
|---|---|
| `OffloadKey` (NewType over `bytes`) | *"combines a block hash with its KV cache group index, encoded as raw bytes to avoid tuple GC overhead."* Helpers: `make_offload_key(block_hash, group_idx)` (`block_hash + group_idx.to_bytes(4, "big")`), `get_offload_block_hash`, `get_offload_group_idx`. |
| `Medium` (Enum) | `CPU = "CPU"`, `STORAGE = "STORAGE"` |
| `Locality` (Enum) | `LOCAL`, `REMOTE` — *"relative to the publishing instance"* |
| `TierMatcher` / `TierFilter` | Per-request tier filtering; `TierFilter.ALL` sentinel; `matchers: tuple[TierMatcher, ...]`; `allows(medium, locality)` |
| `ReqContext` | `req_id`, `kv_transfer_params`, `load_tier_filter`, plus per-request `_state` scratch keyed by value type so a tier parses `kv_transfer_params` once in `on_new_request` |
| `LookupResult` | `MISS`, `HIT`, **`HIT_PENDING`**, **`RETRY`** |
| `OffloadPolicy` | `CHUNK_LEVEL` (*"Offload only newly-computed chunks as they arrive; prefix-hit chunks ... are skipped"*), `REQUEST_LEVEL` (*"Used by tiers that need the complete KV context for a request"*) |
| `OffloadingManager` | Scheduler-side: `lookup()`, `prepare_load()` (protects from eviction), `touch()` (recency), `complete_load()`, `prepare_store()` (returns `PrepareStoreOutput(keys_to_store, store_spec, evicted_keys)`), `complete_store()` |
| `OffloadingWorker` | Worker-side: `submit_store(job_id, src_spec, dst_spec)`, `submit_load(...)`. **One worker per medium**; *"Direction is explicit via submit_store / submit_load, so there is no (src_medium, dst_medium) routing."* |
| `OffloadingEvent` | `keys`, `medium`, `removed: bool`, `locality`, `ownership`, `removal_expected` |
| `GPULoadStoreSpec` | carries `block_ids`, `group_sizes`, `block_indices`, with a long docstring about offloaded blocks **larger than GPU blocks** and the need to skip part of the first matching offloaded block when the first GPU block is unaligned |
| `OffloadingKVEventsConfig` | `enable_kv_cache_events`, **`self_describing_kv_events`** |

**Chunk semantics:** `OffloadingCacheConfig` has `tokens_per_hash` and **`blocks_per_chunk`**; `CPUOffloadingSpec` computes `num_chunks = cpu_bytes_to_use // round_up(kv_bytes_per_chunk, BLOCK_SIZE_ALIGNMENT)` and documents the layout:

```
|--- W0-C0---|---- W1-C0---| ... |---- Wn-C0---| *** maybe-pad *** |
or |--- C0 (single copy) ---| *** maybe-pad *** |
```

i.e. a chunk packs one copy per worker rank, or a single copy under `replicated_layout`.

**Cache policies — lru / arc, and out-of-tree policies.** `vllm/v1/kv_offload/cpu/policies/factory.py`:

```python
CachePolicyFactory.register_cache_policy("lru", "vllm.v1.kv_offload.cpu.policies.lru", "LRUCachePolicy")
CachePolicyFactory.register_cache_policy("arc", "vllm.v1.kv_offload.cpu.policies.arc", "ARCCachePolicy")
```

`CachePolicy` (ABC) methods: `get(key)`, `insert(key, chunk)`, `remove(key)`, `touch(keys, req_context)`, `evict(n, protected) -> list | None`. Its docstring is a genuine design rationale worth quoting: *"Encapsulates both chunk organization (data structures) and replacement decisions (which chunk to evict). LRU and ARC differ in both dimensions — ARC's ghost lists and target_t1_size live at the intersection of storage and eviction, so they cannot be separated cleanly."* `evict` is **atomic**: returning `None` means no state changes. `ChunkStatus` is a `ctypes.Structure` (`ref_cnt`, `chunk_id`) where `ref_cnt == -1` means "not yet ready to be read".

**Out-of-tree policies and tiers (two escape hatches, both with the same warning):**

```jsonc
// policy
{ "eviction_policy": "MyPolicy", "cache_policy_module_path": "my_pkg.my_mod" }
// tier
{ "secondary_tiers": [ { "type": "MyTier", "module_path": "my_pkg.my_mod", "...": "..." } ] }
// spec
{ "spec_name": "MySpec", "spec_module_path": "my_pkg.my_mod" }
```

Each logs: *"Loading out-of-tree … This API is experimental and subject to change in the future as we iterate the design."* So the out-of-tree extension points are **explicitly non-stable**, three times over.

**`self_describing_kv_events`:** a boolean in `kv_connector_extra_config` folded into `OffloadingKVEventsConfig`. It is *required* by some tiers — tests contain `test_kvcr_tier_requires_self_describing_inventory_events` expecting `pytest.raises(ValueError, match="self_describing_kv_events")`. The concept: when enabled, the tier emits **inventory** events that describe the tier's own contents (so a consumer can reconstruct state) rather than only incremental deltas. ⚠️ I verified the flag, its default (`False`), its requirement enforcement, and its wiring; I did **not** find prose documentation of the mechanism, so the precise semantics of "self-describing" are inferred from the flag name, `offloading/` code paths, and the "inventory" wording in a test name. **Flag as not fully verified.**

**Secondary tier interface** (`tiering/base.py`, `SecondaryTierManager` ABC): class var `medium: ClassVar[Medium | None]`, instance `locality`, and methods `lookup(key, req_context) -> LookupResult`, `submit_store(job_metadata: TransferJob) -> None`, `submit_load(job_metadata: TransferJob) -> None`, plus job polling. Documented hard constraint: *"All methods run in the Scheduler process and must be lightweight and non-blocking."* Implementations ship for `example`, `fs`, `obj`, `p2p` (with `kvcr` also present in the tree). Registered via `SecondaryTierFactory` or via `module_path`.

**The `p2p` tier is where NIXL re-enters vLLM** — `tiering/p2p/data/nixl.py` defines `NixlTransport(DataTransport)` wrapping "the NIXL C library behind a Python interface so the rest of the P2P tier code never touches NIXL types directly", with `agent_name`, a `memoryview` of the primary tier, `backends` defaulting to `["UCX"]`, and `num_threads=4`. Control plane is separate (`control/zmq.py`), and session management is its own package (`session/{client,server,session,protocol}.py`).

**Canonical layout (this is the most spec-like thing vLLM has):** `CanonicalKVCaches` is *"A canonicalized block-level representation of the KV caches"* composed of unique tensors of shape `(num_blocks, ...)` and per-group `CanonicalKVCacheRef`s. `CanonicalPageMapping` + `CopyRun` describe *"How this worker's page maps into a canonical (parallelism-free) page"*, with an explicit `parallelism_agnostic` flag meaning the bytes are *"identical under any parallel config with this block span"*. `OffloadingParallelConfig.is_parallelism_agnostic` is described as: *"True when the bytes that will be persisted for a block are portable across parallelism configurations."* Cited RFC: **#42082 ("standardized layouts")** and issue **#48408** (per-layer replication metadata).

→ **This is the closest the ecosystem has to a "portable KV block" contract: a canonical, parallelism-agnostic byte layout for an offloaded block, with a declared mapping from each worker's physical layout.** It is vLLM-internal, but it is exactly the abstraction a cross-vendor sharing format would need. Flagged as *the* candidate convergence point that is currently single-project.

**Offloading metrics** (names verified in source, exported as Prometheus):
`vllm:kv_offload_tiering_lookup_sync_delay_seconds`, `..._lookup_async_delay_seconds`, `..._read_bytes`, `..._read_time`, `..._write_bytes`, `..._write_time`, `..._promotion_job_failures`, `..._cascade_job_failures`, `..._chunk_queries`, `..._chunk_hits`, `..._primary_write_usage_perc`, `..._primary_read_usage_perc`, `..._promotion_allocation_failures`, `..._active_promotion_jobs`, `..._active_cascade_jobs`. `CPUOffloadingMetrics` adds `CPU_CACHE_USAGE_PERC`, `CPU_CACHE_WRITE_USAGE_PERC`, `CPU_CACHE_READ_USAGE_PERC`, `CPU_ALLOCATION_SIZE`, and conditionally `STORES_SKIPPED`.

### 2.7 Is there a versioned / stable connector ABI?

**No.** Summary of the evidence:

- `KVConnectorBase_V1.__init__` logs *"This API is experimental and subject to change."* on **every** construction.
- Out-of-tree spec / policy / tier loaders each log the same warning.
- `docs/contributing/deprecation_policy.md` **does** cover *"Public Python APIs for the `vllm` library"* and ties deprecations to minor (`Y`) releases — but the KV connector explicitly opts out of that promise by declaring itself experimental.
- There is **one** enforced signature contract (3-arg constructor with `kv_cache_config`) and **no** version constant, no `KV_CONNECTOR_API_VERSION`, and no capability-negotiation protocol beyond class-level predicates (`supports_hma`, `requires_piecewise_for_cudagraph`, `get_required_kvcache_layout`).
- Evolution is by *hook accretion*: `get_transfer_results`, `on_new_request`, `register_finished_partial_tail`, `has_pending_push_work`, `finish_forward`, `reset_capture_state`, `bind_kv_cache_manager` are all recent additions to the same class. There is even a TODO acknowledging this: `TODO(NickLucche): group model-runner lifecycle hooks in the interface.`
- `requirements/kv_connectors.txt` pins `nixl == 1.4.1`, `lmcache >= 0.3.9`, `mooncake-transfer-engine >= 0.3.12`, `cupy-cuda13x != 14.1.0` — mixed pinning discipline.

**2026 changes summary for vLLM's KV surface** (all ✅ unless noted):

| Change | Where |
|---|---|
| NIXL KV cache lease renewal via heartbeats (replaces 480 s single timeout) | `docs/design/nixl_kv_cache_lease.md`, PR #41383 |
| NIXL **push**-mode KV transfer | `docs/design/nixl_kv_push_connector.md`; `NixlPushConnector` in registry |
| `NixlPullConnector` / `NixlPushConnector` split out of `NixlConnector` | `factory.py` |
| Bidirectional (D→P) KV transfer for multi-turn | `docs/features/nixl_connector_usage.md` |
| `kv_both` role deprecated for NixlConnector | same doc + #33702 |
| Tiered offloading with secondary tiers (fs/obj/p2p/kvcr/example) + p2p NIXL data plane | `vllm/v1/kv_offload/tiering/` |
| ARC eviction policy beside LRU, pluggable via `cache_policy_module_path` | `cpu/policies/` |
| Canonical / parallelism-agnostic KV layout for offload | `base.py`, RFC #42082 |
| `SharedStorageConnector` → `ExampleConnector` rename | registry + `docs/features/disagg_prefill.md` |
| Reproducible prefix-cache block hashing `sha256_cbor` | `vllm/config/cache.py`, PR #20511 (merged) |
| **RFC "KV-Cache Interoperability API Standardization" closed as not planned** | vLLM#20492 |

---

## 3. KV cache events

### 3.1 vLLM: the reference schema

`vllm/distributed/kv_events.py` (574 lines at fetch). Encoding: **`msgspec`** with `array_like=True, omit_defaults=True, gc=False, tag=True`.

```python
class EventBatch(msgspec.Struct, array_like=True, omit_defaults=True, gc=False):
    ts: float
    events: list[Any]
    data_parallel_rank: int | None = None

class KVCacheEvent(msgspec.Struct, omit_defaults=True, gc=False, tag=True):
    """Base class for all KV cache-related events"""

MEDIUM_GPU = "GPU"; MEDIUM_CPU = "CPU"; MEDIUM_STORAGE = "STORAGE"

class BlockStored(KVCacheEvent):
    block_hashes: list[ExternalBlockHash]
    parent_block_hash: ExternalBlockHash | None
    token_ids: list[int]
    block_size: int
    lora_id: int | None            # Deprecated: use lora_name for KV block key hash. Retained for backward compatibility.
    medium: str | None
    lora_name: str | None
    extra_keys: list[tuple[Any, ...] | None] | None = None
    group_idx: int | None = None
    kv_cache_spec_kind: str | None = None
    kv_cache_spec_sliding_window: int | None = None
    locality: str | None = None    # LOCAL or REMOTE relative to the publisher
    ownership: str | None = None   # Secondary offloading tier identifier, if generated by one
    session_id: str | None = None

class BlockRemoved(KVCacheEvent):
    block_hashes: list[ExternalBlockHash]
    medium: str | None
    group_idx: int | None = None
    locality: str | None = None
    ownership: str | None = None

class AllBlocksCleared(KVCacheEvent):
    pass

class KVEventBatch(EventBatch):
    events: list[BlockStored | BlockRemoved | AllBlocksCleared]
```

Semantics verified from docstrings:
- **`medium`** — the device tier (`GPU`/`CPU`/`STORAGE` constants in vLLM).
- **`locality`** — *"LOCAL or REMOTE relative to the publisher; None means unspecified."*
- **`ownership`** — *"Secondary offloading tier identifier, if generated by one."*
- **`extra_keys`** — *"Extra keys used in block hash computation, one entry per block in `block_hashes`. Each entry contains MM identifiers, LoRA name, cache_salt, prompt embedding hashes, etc. ... Exposed for external KV cache consumers to reconstruct block hashes."* This is the field llm-d uses for multimodal block keys.
- **`session_id`** — *"This identifies the request context that emitted the event, not exclusive ownership of the underlying block, which may be shared across sessions."*
- **`group_idx` + `kv_cache_spec_kind` + `kv_cache_spec_sliding_window`** — hybrid-attention / multi-group awareness. Store events carry cache-spec metadata, *"Remove events only need group_idx+hash."*
- Both `BlockStored` and `BlockRemoved` define `__hash__` over all fields — the basis of `KVEventAggregator`.

**Publisher: `ZmqEventPublisher`** — *"Reliable PUB/ROUTER publisher with an in-memory replay buffer"*:
- PUB socket (default `tcp://*:5557`) + optional ROUTER **replay** socket. Binds if the endpoint contains `*`, `::`, `ipc://` or `inproc://`, otherwise connects (*"bind stable, connect volatile convention"*).
- Wire format is **3 frames**: `(topic_bytes, seq_bytes(8-byte big-endian), payload)`; payload is msgpack via `msgspec.msgpack.Encoder()`.
- **Sequence numbers**: `itertools.count()` monotonic, per publisher.
- **Replay**: `deque[tuple[int, bytes]](maxlen=buffer_steps)` with `buffer_steps` default **10,000**; a subscriber sends the starting sequence number as an 8-byte big-endian int over ROUTER and gets buffers streamed back, terminated by sentinel `END_SEQ = (-1).to_bytes(8, "big", signed=True)`. Lookup is a **linear scan**.
- Defaults: `hwm=100_000`, `max_queue_size=100_000`, `SHUTDOWN_TIMEOUT = 1.0` s.
- Runs a **separate daemon thread** (`"zmq-publisher"`).
- **Delivery contract, quoted:** *"Implementations should guarantee at-least-once delivery and monotonic ordering (e.g., via sequence numbers)."*

**Multi-process / multi-rank publishing:** `EventPublisher(data_parallel_rank)`; `offset_endpoint_port(endpoint, dp_rank)` shifts the TCP port by the DP rank (`base_port + data_parallel_rank`) or suffixes `_dpN` for inproc; publishers annotate each batch's `data_parallel_rank`. `EventPublisherFactory` has a registry (`"null"` → `NullEventPublisher`, `"zmq"` → `ZmqEventPublisher`) **plus `register_publisher(name, ctor)` — an out-of-tree publisher extension point** (e.g. a NATS publisher could be registered by a downstream project without patching vLLM).

**Aggregation:** `KVEventAggregator` tracks a `Counter[KVCacheEvent]` and returns *"events that appeared in all workers"* (`get_common_events`), with `increment_workers`, `reset_workers`, `get_all_events`. `KVConnectorKVEvents` is an ABC container with `add_events`, `aggregate`, `increment_workers`, `get_all_events`, `get_number_of_workers`, `clear_events`, `merge`.

### 3.2 SGLang: deliberately the same schema

Source: `python/sglang/srt/disaggregation/kv_events.py` (fetched from `main`, 2026-09-15). CLI surface is `--kv-events-config` → `KVEventsConfig(BaseModel)` with `from_cli`.

SGLang's `KVCacheEvent` docstring is the single most explicit convergence statement I found anywhere in the ecosystem — quoting verbatim:

> *"Events are tagged msgpack maps: `type` carries the class name and every other key is a field name. Optional fields left at `None` are omitted, so adding an optional field never changes the shape an older consumer sees. **This is the same encoding vLLM uses for its `KVCacheEvent`, so a consumer such as Dynamo decodes both engines with one code path.** `EventBatch` stays a positional array `[ts, events, attn_dp_rank]`."*

```python
class EventBatch(msgspec.Struct, array_like=True, gc=False):
    ts: float
    events: list[Any]
    attn_dp_rank: Optional[int] = None        # <- name differs from vLLM's data_parallel_rank

class KVCacheEvent(msgspec.Struct, omit_defaults=True, gc=False, tag=True): ...

class StorageMedium(str, enum.Enum):
    GPU = "GPU"              # L1: device HBM
    CPU = "CPU_PINNED"       # L2: host pinned memory
    DISK = "DISK"            # L3: SSD / NVMe
    EXTERNAL = "EXTERNAL"    # L4: shared / remote pool (e.g. Mooncake)

class BlockStored(KVCacheEvent):
    block_hashes: list[int]; parent_block_hash: Optional[int]
    token_ids: list[int]; block_size: int; lora_id: Optional[int]
    medium: Optional[str] = None
    cache_salt: Optional[str] = None       # <- vLLM has this inside extra_keys instead
    session_id: Optional[str] = None       # <- vLLM has session_id at top level too

class BlockRemoved(KVCacheEvent):
    block_hashes: list[int]; medium: Optional[str] = None

class AllBlocksCleared(KVCacheEvent): pass
class KVEventBatch(EventBatch):
    events: list[Union[BlockStored, BlockRemoved, AllBlocksCleared]]
```

`ZmqEventPublisher` is a near-copy of vLLM's: `_seq_gen = count()`, `seq_bytes = seq.to_bytes(8, "big")`, `send_multipart((topic_bytes, seq_bytes, payload))`, the same `deque` replay buffer, the same `END_SEQ = (-1).to_bytes(8, "big", signed=True)` sentinel, and the same `_service_replay` shape (`recv_multipart()`, require `len(frame) == 3`, `client_id, _, start_seq_bytes = frame`, linear scan for `seq >= start_seq`).

**Replay reply format differs in one frame** (✅ verified by reading both sources side by side, 2026-09-15):

```python
# vLLM   (vllm/distributed/kv_events.py:502-506)
self._replay.send_multipart((client_id, b"", self._topic_bytes, seq.to_bytes(8,"big"), buf))   # 5 frames
self._replay.send_multipart((client_id, b"", b"", self.END_SEQ, b""))                          # 5 frames

# SGLang (python/sglang/srt/disaggregation/kv_events.py:540-544)
#   "[identity, empty_delim, seq_bytes, payload]  (identity, empty_delim) are stripped off by the router"
self._replay.send_multipart((client_id, b"", seq.to_bytes(8, "big"), buf))                     # 4 frames
self._replay.send_multipart((client_id, b"", self.END_SEQ, b""))                               # 4 frames
```

So vLLM's replay reply **carries the topic** and SGLang's does not, and the end-of-sequence marker lands in a **different frame position** (vLLM frame index 3, SGLang frame index 2). A single replay *client* implemented against one engine would mis-parse the other's replies. ⚠️ I read both sources carefully but did **not** execute either, so this is a source-level (not runtime-verified) divergence. This is a good illustration of the section's thesis: even where two engines copy each other, the copy is not byte-identical, and nothing tests the cross-engine path.

SGLang also has DP-attention naming (`attn_dp_rank`, `is_kv_publisher_rank`, `select_kv_publisher_dp_rank`) rather than vLLM's `data_parallel_rank`.

### 3.3 llm-d KV-Cache Indexer: adapter layer, and the clearest evidence of schema convergence

`llm-d/llm-d-kv-cache` ships `pkg/kvevents/engineadapter/` with **one adapter per engine**: `vllm_adapter.go`, `sglang_adapter.go`. From `docs/architecture.md`:

> *"`kvevents.EngineAdapter` — Parses engine-specific wire formats into domain events. **vLLM (msgpack) and SGLang (msgpack) adapters ship today.**"*

```go
type EngineAdapter interface { ... ShardingKey(), ParseMessage() ... }
```

- `VLLMAdapter` doc comment (verbatim, and the most precise interop statement in the ecosystem):
  > *"vLLM emits events either as positional msgpack arrays with trailing defaults omitted (`msgspec array_like=True`) or, **since vllm-project/vllm#42892, as field-name maps tagged under `"type"`**. Both decode into the same positional `[]any` layout, extracted with length guards instead of fixed structs, so the converters stay encoding-agnostic and tolerate appended or omitted fields."*
  → **vLLM changed its KV event wire encoding in 2026 (PR #42892) from positional arrays to tagged maps, and the only reason llm-d survived it is defensive length-guarded decoding.** This is the single best concrete example of *why* the absence of a spec costs real engineering effort. ⚠️ PR number is as stated by llm-d's source comment; I did not open vLLM#42892.
  Field positions documented in the adapter: `[0] tag, [1] block_hashes, [2] parent_block_hash, [3] token_ids, [4] block_size, [5] lora_id, [6] medium, [7] lora_name, [8] extra_keys, [9] group_idx ...` with *"Trailing fields may be absent in older vLLM versions. Extra trailing fields from newer vLLM versions are silently ignored."*
- `SGLangAdapter` constants confirm the shared format explicitly:
  > *"SGLang uses the same positional wire format as vLLM but may omit trailing optional fields via `omit_defaults=True` in msgspec. See: `sglang/srt/disaggregation/kv_events.py`."*
  `sglangBlockStoredFieldCount = 9`, `sglangBlockRemovedFieldCount = 3`, minimums 5 and 2.
- **Topic format is shared:** `"kv@<pod-id>@<model-name>"` — the SGLang adapter's `ShardingKey` doc says *"Expected topic format: `kv@<pod-id>@<model-name>` (same as vLLM)."*
- Sharding: `EngineAdapter.ShardingKey()` → pod id → **FNV-1a** hash → worker queue, guaranteeing per-pod ordering.

**Indexer behaviour** (from llm-d's KV-Cache Indexer doc):
- Consumes `BlockStored` / `BlockRemoved` / `AllBlocksCleared` over ZMQ.
- **Tier weighting in scoring: `gpu = 1.0`, `cpu = 0.8` by default**; when a block is on multiple tiers, the **max** weight is taken. Raw scores normalized to `[0,1]` then combined in the EPP filter→score→pick pipeline.
- Requires **longest consecutive prefix**, not scattered blocks (documented with a worked example: a pod holding B3/B4 but not B0 scores 0).
- Two delivery modes: **centralized** (all model servers `zmq.PUB` → EPP binds `tcp://*:5557`) and **pod discovery** (each pod binds; each EPP replica subscribes to all — the mode for active-active multi-EPP).
- Index backends: **In-Memory two-level LRU** (default; *"default 100M keys × 10 pod entries"*), **Cost-Aware Memory** (Ristretto, byte budget e.g. `2GiB`), **Redis / Valkey**.
- **Speculative indexing** (`speculativeIndexing: true`, default TTL **2 s**) — *"Confirmed KV-events arrive after a request has been routed. Back-to-back requests with the same prefix can be scheduled before KVEvents have propagated, breaking affinity."*
- **Data Producer** role: `token-producer` plugin tokenizes by calling vLLM's **`/v1/completions/render` and `/v1/chat/completions/render`** HTTP endpoints (*"served by `vllm serve <model>` or by the GPU-less `vllm launch render <model>`"*). The older gRPC-over-UDS tokenizer sidecar (`udsTokenizerConfig`) is **deprecated and will be removed**.
- **Hybrid attention scoring is explicitly WIP**: *"Hybrid-attention-aware scoring is a work in progress."*

### 3.4 Dynamo: a *different* envelope, bridged to vLLM's

Dynamo's own documentation ("KV Event Publishing for Custom Engines", `docs.nvidia.com/dynamo/dev/integrations/`) defines a **Dynamo-native schema**:

> *"Each event contains: `event_id`: Monotonically increasing identifier per worker; `dp_rank`: Data parallel rank (0 if DP not enabled); `data`: One of `Stored`, `Removed`, or `Cleared`."*

`BlockStored` fields per Dynamo: `token_ids`, `block_hashes` (*"sequence block hashes ... cumulative hashes that incorporate all tokens from the start of the sequence up to and including the current block"*), `num_block_tokens` (*"should all equal `kv_block_size`"*), `parent_hash`, `lora_id`.

Transport and schema divergence, verified from Dynamo docs:
- Two publishing pathways: **direct NATS** (`KvEventPublisher`, *"Recommended... Simplest approach for custom engines"*) and **ZMQ → NATS** (`ZmqKvEventPublisher`, *"For engines with ZMQ event output (like vLLM)"*).
- So Dynamo **translates** vLLM ZMQ events into its own NATS `RouterEvent` domain model. The vLLM schema is an *input format*, not Dynamo's internal contract.
- Field-name differences vs vLLM: Dynamo `num_block_tokens` vs vLLM `block_size`; Dynamo `parent_hash` vs vLLM `parent_block_hash`; Dynamo `event_id` per worker vs vLLM's per-publisher sequence number in the ZMQ frame (not in the payload); Dynamo `dp_rank` vs vLLM `data_parallel_rank` (batch field) vs SGLang `attn_dp_rank`.

**Replay semantics differ fundamentally.** From the Dynamo-vs-vLLM comparison doc (Dynamo docs, "KV Event Replay — Dynamo vs vLLM"):

| | vLLM Replay Buffer | Dynamo Local Indexer |
|---|---|---|
| Core buffer | `collections.deque[tuple[int, bytes]]` with `maxlen` | `VecDeque<RouterEvent>` with `max_buffer_size` |
| Event ordering | Monotonic sequence number (8-byte int) | Monotonic `event_id` with consecutive-ID validation |
| Lookup | Linear scan | Binary search |
| Fallback when buffer too old | Consumer must rebuild externally | **Full RadixTree snapshot** |
| Initial sync | Not built in | Tree dump (request with `start_event_id=None`) |
| Transport | ZMQ PUB/SUB + ROUTER/REQ | Dynamo service RPC (request/response) |
| Recovery states | buffer only | `Events`, `TreeDump`, `TreeDumpFailed`, `TooNew`, `InvalidRange` |

Dynamo's `LocalKvIndexer` = `KvIndexer` (RadixTree) + circular `event_buffer` + `max_buffer_size`. Dynamo's tier-aware routing consumes SGLang's `medium` field: the Dynamo SGLang-HiCache guide states *"SGLang's `HiRadixCache` emits `BlockStored` / `BlockRemoved` events carrying a `medium` field on every tier transition"*, using the value **`CPU_PINNED`** for host-tier blocks, and requires **SGLang ≥ 0.5.11** for it (PR sgl-project/sglang#22894, *"fix(hicache): emit KV events for L2 host cache insertions"*); *"The Dynamo 1.3.0 SGLang runtime image ships with SGLang 0.5.15."*

⚠️ I could not fetch `ai-dynamo/dynamo` raw sources (network), so Dynamo's schema statements above come from its **rendered documentation pages**, which I did fetch. Treat struct/field names as documentation-verified, not source-verified.

### 3.5 Do the four use the SAME schema? Verdict

**Not one schema — one *kernel* schema plus three lossy wrappers.** Precisely:

| Aspect | vLLM | SGLang | llm-d | Dynamo |
|---|---|---|---|---|
| Event type names | `BlockStored`/`BlockRemoved`/`AllBlocksCleared` | **same** | **same** (internal domain events) | `Stored`/`Removed`/`Cleared` variants |
| Encoding | msgspec msgpack | msgspec msgpack (**same**, per its own docstring + llm-d adapter) | decodes both | own + ZMQ bridge |
| Tag style | was positional array, **moved to tagged map in 2026 (#42892)** | tagged map | handles both defensively | own |
| Batch shape | `[ts, events, data_parallel_rank]` | `[ts, events, attn_dp_rank]` | re-derives | own |
| DP rank field name | `data_parallel_rank` | `attn_dp_rank` | normalizes | `dp_rank` |
| Ordering token | seq in ZMQ frame | seq in ZMQ frame | per-pod ordering | `event_id` in payload |
| Recovery | bounded replay buffer, no initial sync | same design | inherits vLLM limits | buffer **+ tree snapshot** |
| Transport | ZMQ PUB + ROUTER replay | ZMQ PUB + ROUTER replay | ZMQ SUB | ZMQ→NATS, or NATS direct |
| Tier vocabulary | `GPU`/`CPU`/`STORAGE` (constants) + `locality` + `ownership` | `GPU`/`CPU_PINNED`/`DISK`/`EXTERNAL` | consumes `medium`, weights gpu 1.0 / cpu 0.8 | consumes `medium`, `CPU_PINNED` |
| Block hashes | `list[ExternalBlockHash]` | `list[int]` | re-derives/normalizes | `list[int]`, cumulative sequence hashes |

**So: SGLang↔vLLM is genuine schema-level convergence (deliberate, documented, and load-bearing — Dynamo and llm-d both rely on it). llm-d is the interoperability broker (two adapters). Dynamo is an adapter/consumer, not a converger.** Nobody has published a versioned KV-event spec, and the `medium` vocabulary is *already divergent* (`CPU` vs `CPU_PINNED`, plus SGLang's `DISK`/`EXTERNAL` which have no vLLM constant).

**Searches for a shared spec — all negative.** Queries for `"KV cache events standard"`, `"kv_events protocol"`, `"KVEventBatch spec"`, `"kv cache events SIG"` returned no specification document. There is **no KV-cache-events SIG** in vLLM, SGLang, llm-d, Dynamo, CNCF, or the PyTorch Foundation that I could find. The nearest thing is llm-d's `EngineAdapter` interface, which is a *de facto* normalisation layer inside one project.

---

## 4. Gateway API Inference Extension / InferencePool / EPP

**Repo:** <https://github.com/kubernetes-sigs/gateway-api-inference-extension> — **768 stars / 313 forks** (HTML scrape).

### 4.1 Version and GA status

| Fact | Value |
|---|---|
| Latest release | **v1.6.1**, published **2026-09-11T23:41:33Z** |
| Prior | v1.6.0 (2026-08-17), **conformance/v1.6.1** (2026-09-10), conformance/v1.6.0 (2026-08-10) |
| Earlier | v1.5.0 (2026-04-20), conformance/v1.5.0 (2026-04-18) |
| GA claim | ✅ README: **"This project is GA'd! The latest release can be found here."** |
| Conformance artefacts | ✅ Separate `conformance/vX.Y.Z` releases exist — real conformance testing is part of the standard. |

⚠️ Tension worth flagging: the README says GA'd, but the same README's **Roadmap** section is written as pre-GA future work (*"As Inference Gateway builds towards a GA release. We will continue to expand our capabilities, namely: ..."*), and the roadmap's first item is *"Prefix-cache aware load balancing with interfaces for remote caches"* — i.e. prefix-cache-aware routing is listed as **future work in the standard**, even though llm-d ships it. The README is internally inconsistent about GA; I report both verbatim. ❌ Could not find a KEP or SIG doc formalising the GA milestone.

### 4.2 What it standardises

Verbatim definitions from the README:

- **Inference Gateway (IGW)**: *"A proxy/load-balancer which has been coupled with an `Endpoint Picker`. It provides optimized routing and load balancing for serving Kubernetes self-hosted generative Artificial Intelligence (AI) workloads."*
- **Inference Scheduler**: *"An extendable component that makes decisions about which endpoint is optimal (best cost / best performance) for an inference request based on `Metrics and Capabilities` from [Model Serving]."*
- **Metrics and Capabilities**: *"Data provided by model serving platforms about performance, availability and capabilities to optimize routing. Includes things like [Prefix Cache] status or [LoRA Adapters] availability."*
- **Endpoint Picker (EPP)**: *"A data-plane component that communicates via the Envoy external processing protocol, and acts as the `Router`. ... This repository provides a reference **Lightweight Endpoint Picker (lwepp)** for conformance test purposes."*

Mechanism: Envoy **ext-proc**. Deployment targets named: Envoy Gateway, kgateway, GKE Gateway. Higher-level AI gateways named: LiteLLM, Solo AI Gateway, Apigee.

APIs: **`InferencePool`** (with `spec.endpointPickerRef` — *"now optional"* as of v1.6.0), plus a documented **model server protocol** proposal (`docs/proposals/003-model-server-protocol`), which is the piece that makes a non-vLLM server a first-class GAIE citizen.

### 4.3 ⚠️ THE BIG 2026 CHANGE: the EPP moved OUT of the standard

This is the most consequential 2026 event in the *control-plane standardisation* story, and it goes **against** convergence at the EPP layer while **strengthening** convergence at the CRD layer.

From the GAIE README (verbatim):

> *"**The Endpoint Picker (EPP), InferenceObjective and InferenceModelRewrite APIs, and Body Based Router (BBR) packages have moved to new repositories:***
> *- EPP and associated APIs: [llm-d/llm-d-router](https://github.com/llm-d/llm-d-router)*
> *- BBR: [llm-d/llm-d-inference-payload-processor](https://github.com/llm-d/llm-d-inference-payload-processor)*
> *No new code will be accepted to these packages in this repository, and they will be archived soon. This move was proposed and discussed in [issue #2430](https://github.com/kubernetes-sigs/gateway-api-inference-extension/issues/2430).*
> *This repository will continue to host the **lightweight EPP (LWEPP)** and the **InferencePool API**, and will remain the primary location for the development and maintenance of **conformance tests**."*

v1.6.0 release highlights confirm and quantify:

> *"**Component Migration to llm-d.** Full-featured Endpoint Picker (EPP), Body-Based Routing (BBR), and Latency Predictor components have moved to the llm-d repository to live in their dedicated ecosystem. GAIE now focuses on core Kubernetes Gateway API inference specifications, CRDs, and conformance definitions."*
> *"Removed Alpha APIs: The following experimental APIs have been removed from GAIE (migrated to llm-d): InferenceObjective (`inference.networking.x-k8s.io/v1alpha2`), InferenceModelRewrite (`inference.networking.x-k8s.io/v1alpha2`), EndpointPickerConfig (`config.inference.networking.k8s.io/v1alpha1`)."*
> *"**Introduction of Lightweight EPP (LWEPP)**: ... a minimal, fast reference ext-proc implementation designed specifically for running and validating Gateway API conformance tests. Container image is officially promoted and available at `registry.k8s.io/gateway-api-inference-extension/lwepp:v1.6.0`."*

Also verified: *"Community meetings have moved to the llm-d Router community meeting."*

**Consequences:**
1. The Kubernetes-sigs standard **shrank** to: `InferencePool` + LWEPP + conformance + the model-server protocol proposal. That is a genuine narrowing of scope, and a *net win* for standardisation hygiene — but it means **InferenceObjective and InferenceModelRewrite are no longer standardised APIs**, they are llm-d APIs.
2. The **reference implementation of the EPP now lives in a CNCF Sandbox project** (`llm-d/llm-d-router`), not in kubernetes-sigs.
3. It resolves the "who owns the EPP" ambiguity by making the *extension point* standard and the *implementation* ecosystem-owned.

`llm-d/llm-d-router` metrics: **339 stars / 370 forks** (note: more forks than stars — typical of a vendored/derived repo), releases v0.10.0 (2026-08-17), v0.9.0 (2026-06-23).

### 4.4 Is prefix-cache-aware routing part of the standard or a vendor plugin?

**Both, in different senses — and this is the key nuance for the report:**

- **In the standard:** the *concept* is standard — `Metrics and Capabilities` explicitly names "Prefix Cache status", the Inference Scheduler is defined to consume it, and the **DataProducer plugin interface** (moved through the v1.6.0 changelog as *"consolidate requestdataproducer into dataproducer"*, *"feat(epp): Implement generic request data producer auto-configuration"*, and *"fix(prefixcache): hash trailing bytes to prevent multimodal URL hotspotting"*) is standard vocabulary inside the (now llm-d-owned) EPP.
- **Not in the standard:** the **scorer implementation**. `precise-prefix-cache-producer`, `prefix-cache-scorer`, `token-producer` are llm-d router plugins; the KV-event index is `llm-d-kv-cache`. The GAIE roadmap still lists *"Prefix-cache aware load balancing with interfaces for remote caches"* as a future capability.
- **Therefore:** the *interface* is standardised (or was, before the move), the *algorithm and the KV-event ingestion* are an llm-d implementation. Anyone claiming "prefix-cache-aware routing is a Kubernetes standard" is overstating it. ✅ This is directly supported by the roadmap + the migration notice.

### 4.5 How llm-d, Dynamo, AIBrix, KServe relate

- **llm-d** — *"Acting as a primary implementation of the Kubernetes Gateway API Inference Extension (GAIE), llm-d utilizes the Endpoint Picker (EPP) for programmable, prefix-cache-aware routing"* (CNCF blog, 2026-03-24). Now also the **home of the EPP**. llm-d was **accepted as a CNCF Sandbox project** on 2026-03-24, launched May 2025 by Red Hat, Google Cloud, IBM Research, CoreWeave, NVIDIA; joined by AMD, Cisco, Hugging Face, Intel, Lambda, Mistral AI; academic supporters UC Berkeley, University of Chicago. Quote: *"By joining the CNCF, llm-d secures the trusted stewardship and open governance of the Linux Foundation, giving organizations the confidence to build upon a truly neutral standard."* Also: *"llm-d plans to work with the CNCF AI Conformance program to ensure critical capabilities like disaggregated serving are interoperable across the ecosystem"* and *"we are committed to increasing collaboration with the PyTorch Foundation."* And notably for benchmarking: *"llm-d aims to be the neutral, de facto standard for defining and running inference benchmarks."* (~120k tok/s, Qwen3-32B, 8×vLLM pods, 16×H100.)
- **Dynamo** — integrates with GAIE via a plugin: GAIE v1.6.0 changelog contains *"fix(dynamo integration): reorder mutate place so that jsonPayload can be mutated by preRequest plugins"* (#2854). Dynamo also has its own Kubernetes Gateway API path (*"KV-Aware Routing on Kubernetes"* in its docs). ⚠️ So Dynamo is *both* a GAIE consumer and a competitor router. I could not determine how the two paths are reconciled.
- **AIBrix** — **5,089 stars / 694 forks**. 2026 has been an **integration-heavy** year: *"[[Feature] vLLM integration by DwyaneShi · PR #2060"*, *"[[RFC]: vLLM v0.19 patch + dynamic packaging refactor · Issue #2104"*. AIBrix KVCache is also an **SGLang HiCache L3 backend** (`--hicache-storage-backend aibrix`). ⚠️ Whether AIBrix implements GAIE is **not verified** — its README describes "Distributed KV Cache" but I did not find a GAIE statement. Do not assert AIBrix↔GAIE without checking.
- **KServe** — positioned by the CNCF blog as the *"high-level control plane"* that llm-d bridges: *"a pre-integrated, Kubernetes-native distributed inference framework that bridges the gap between high-level control planes (like KServe) and low-level inference engines (like vLLM)."* ✅

---

## 5. Convergence / divergence in 2026

### 5.1 The failed standardisation attempt: RFC #20492

**The central data point.** [vllm-project/vllm#20492](https://github.com/vllm-project/vllm/issues/20492), *"**[RFC]: KV-Cache Interoperability API Standardization**"*, opened by `vMaroon` on **Jul 4, 2025**, is **closed as `not planned`**, labelled `RFC`, `stale`, *"Over 90 days of inactivity"*. No milestone, no assignee, no linked PRs at close.

Its stated goals (verbatim, condensed):

> *"**KVEvents Internal API as a Public Contract** — This RFC proposes formalizing KVEvents as the public contract for any component emitting or consuming KV-Cache lifecycle events - including external indexers, routers, and engines."*
> *"**Ensure Reproducible Block Hashing Across Languages** — Prefix cache block keys must be computed the same way across runtimes (e.g., Python, Go). This requires: Canonical serialization (e.g., CBOR); Consistent hashing algorithms (e.g., SHA256, xxHash); Defined structure for input objects (e.g., token arrays, `extra_keys`); Explicit rules for special cases like `NONE_HASH` root; Alignment on security features such as per-request hash-salting."*
> *"**Enable Language-Agnostic Interop** — Develop shared guidance and reference libraries in Python, Go, and other widely used languages. These utilities do not need to reside within vLLM, but should remain consistent with its specifications."*
> Motivation: *"vLLM already ships with internal KVEvents contributed by the NVIDIA Dynamo team - that's a strong foundation. But as external systems aim for cache-aware inference, we need to treat these internal mechanisms as public contracts to support broader adoption and interop."*
> Self-noted weakness: *"in the current KVEvents schema, the token-ids are sent along their block-hashes ... this requires complex indexing and lookups, along with the networking overhead of passing the 32bit token-ids in every event."*
> Explicit dependency: *"to support the development of **llm-d's vLLM-native global KV-Cache indexer**, prefix-cache block hashing must be reproducible."*

**What survived (`sha256_cbor`, merged):** [vLLM PR #20511](https://github.com/vllm-project/vllm/pull/20511), *"[Prefix Cache] Add reproducible prefix-cache block hashing using SHA-256 + CBOR (64bit)"* — **Merged**. Verified in `main`:

```python
# vllm/config/cache.py
PrefixCachingHashAlgo = Literal["sha256", "sha256_cbor", "xxhash", "xxhash_cbor"]
prefix_caching_hash_algo: PrefixCachingHashAlgo = "sha256"
```

`sha256_cbor` *"serializes input objects using canonical CBOR (via `cbor2`) and hashes them with SHA-256"*, truncated to 64 bits *"to align with the current KVEvents schema, ensuring reproducibility across different systems and programming languages."* `NONE_HASH` initialization was refactored into `init_none_hash`, with `DEFAULT_NONE_HASH_SEED = "vllm-none-hash"` and a helper `resolve_none_hash_seed(hash_fn)`; the docstring notes *"Components that must agree on NONE_HASH across processes (the P2P tier ...)"*. Measured cost from the PR: `sha256` mean 0.0054 s vs `sha256_cbor` mean 0.0171 s per 50,000 tokens (~3.2×).

**Interpretation:** the *mechanical* precondition for cross-language block identity (canonical serialization + standard hash) **shipped**; the *contractual* precondition (a versioned public schema with reference libraries in Go/Python) **did not**. That is precisely why llm-d's Go adapter has to be defensive about array-vs-map encodings and why the ecosystem still ships two adapters instead of one spec.

### 5.2 Counter-attempt: an external spec with no adoption

**[openhivesai/kv-first](https://github.com/openhivesai/kv-first)** — *"KV-first: A Cache-Centric Architecture for LLM Inference"*, single author (Mahabot, Mickael), 2026, dual-licensed Apache-2.0 + CC BY 4.0. **0 stars, 0 forks** at fetch time.

It specifies precisely the things the ecosystem lacks: a **KV Manifest** (*"metadata binding KV segments to model, tokenizer, positional encoding, layout, and policy"*), **Compatibility contracts (KVCC)** with three levels, protocols (*"handoff, streaming, leasing, and invalidation"*), composition operators (*"append, splice, and fusion"*), and conformance testing.

| Level | Name | Constraint | Use case |
|---|---|---|---|
| L0 | Strict | Same model, weights, tokenizer, layout, dtype | Disaggregated serving, remote prefill |
| L1 | Runtime-canonical | Same model family; layout/dtype canonicalized | **Cross-runtime reuse (vLLM, TensorRT-LLM, llama.cpp)** |
| L2 | Cross-model approximate | Different models; learned projections; opt-in | Research (DroidSpeak, C2C) |

Its own framing of the problem is the best one-sentence statement of the gap: *"Every LLM inference system produces KV caches. None of them agree on how to describe, validate, share, or compose them. The result: KV caches are single-runtime, single-model, single-node artifacts that cannot be reused, handed off, or governed."*

⚠️ **Status: self-published white paper, zero adoption signal, no vendor backing, no conformance implementations.** Notably, **`kv-first`'s L0 is a formalisation of what NIXL+vLLM already do informally**, while its L1 (cross-engine canonical layout) is very close in spirit to vLLM's `CanonicalKVCaches` / `parallelism_agnostic` work — but there is **no evidence the two are aware of each other**. Flag as convergent *ideas*, disconnected *projects*.

### 5.3 Cross-project integrations that DO exist

| Integration | Evidence | Direction |
|---|---|---|
| **LMCache ↔ Dynamo** | LMCache blog, **2026-03-16**: *"LMCache + NVIDIA Dynamo 1.0: A Match Made in Inference Heaven"*. Three layers claimed: inference (vLLM + SGLang; TensorRT-LLM "coming soon"), routing (*"LMCache integrates at this level by implementing the message protocol that lets Dynamo's router understand cache state across the cluster"*), storage (*"full support for NIXL"* + *"LMCache's storage plugin interface is fully wired into Dynamo"*). | LMCache plugs into Dynamo |
| **LMCache ↔ vLLM** | `LMCacheConnectorV1` and `LMCacheMPConnector` are **in-tree** vLLM connectors; `requirements/kv_connectors.txt` pins `lmcache >= 0.3.9`. | First-class |
| **LMCache ↔ SGLang** | SGLang HiCache lists **LMCache** as *"an alternative solution to HiCache"* with an in-tree backend path `srt/mem_cache/storage/lmcache`. | First-class-ish |
| **SGLang HiCache ↔ Dynamo** | Dynamo ships `docs/integrations/sglang-hicache.md`: *"Dynamo passes [HiCache flags] through unchanged"*, and adds tier-aware routing via SGLang's `medium` events. Requires SGLang ≥ 0.5.11. | Dynamo consumes SGLang tiers |
| **SGLang HiCache ↔ NIXL / Mooncake / 3FS / AIBrix / LMCache** | `--hicache-storage-backend {file,mooncake,hf3fs,nixl,aibrix,dynamic}`. | SGLang as hub |
| **Dynamo ↔ SGLang / vLLM / TensorRT-LLM** | LMCache blog: *"Dynamo supports all major frameworks including vLLM, SGLang, NVIDIA TensorRT-LLM"*. | Dynamo as hub |
| **llm-d ↔ vLLM** | vLLM's NIXL/offloading work repeatedly cites llm-d as the consumer (RFC #20492: *"llm-d's vLLM-native global KV-Cache indexer"*; PR #20511 *"to support the development of llm-d's vLLM-native global KV-Cache indexer"*). vLLM roadmap: a whole team *"responsible for interfacing with ecosystem projects such as llm-d, Dynamo, and AMD team."* | Intentional co-design |
| **llm-d ↔ CNCF** | CNCF blog 2026-03-24: llm-d accepted as **CNCF Sandbox**. | Governance |
| **llm-d ↔ GAIE** | llm-d now hosts the EPP, BBR, InferenceObjective, InferenceModelRewrite; GAIE hosts InferencePool + LWEPP + conformance. | Split of concerns |
| **NIXL ↔ AWS EFA** | 2026-03-19 AWS announcement, NIXL ≥ 1.0.0, EFA installer ≥ 1.47.0, "all EFA-enabled EC2 instance types in all AWS regions at no additional cost". | Cloud platform |
| **NIXL ↔ storage vendors** | WEKA blog: *"WEKA accelerates AI inference with NVIDIA Dynamo and NVIDIA NIXL"*; DDN: *"first storage vendor natively integrated into NVIDIA KV cache management"* (blog, secondary). | Vendor |
| **Tensormesh ↔ LMCache** | Tensormesh Operator (TMO) helm chart `0.5.2`/`0.5.3` with pinned **LMCache Operator `v0.5.2`/`v0.5.3`** and **"LMCache vLLM `v0.5.2`/`v0.5.3`"** rows. CacheBlend plugin shipped as a private image (`cacheblend-plugin`) requiring a contact-form access token. | **Tensormesh is built on LMCache** |
| **vLLM roadmap ↔ ecosystem** | Q2 2026 roadmap (#39749) lists: *"KV cache manager rethink for complex KV cache layout"*, *"Offloading: CPU offloading + Disk + overall connector API on this part of the path"*, *"Bidirectional KV transfers"*, and a team interfacing with llm-d/Dynamo/AMD. | Directional |

**Tensormesh** deserves a specific note since it was called out in the brief: <https://www.tensormesh.ai/> / `docs.tensormesh.ai`. Verified: it is an **operator** (TMO) whose KV layer is LMCache plus a proprietary `cacheblend-plugin`; it supports CacheBlend (non-prefix reuse, arXiv 2405.16444) and a **Peer-to-Peer KV Transfer** config page. Its supported-model table lists GLM-5.2, MiniMax M3/M2.5, Gemma3, gpt-oss-20b/120b, llama 3.1. ❌ Its own KV interfaces beyond the LMCache dependency could not be established (the CacheBlend plugin image is behind an access token, and I found no public schema).

### 5.4 Explicit standardisation proposals found (and their state)

| Proposal | State |
|---|---|
| **vLLM RFC #20492** KV-Cache Interoperability API Standardization | **Closed as not planned** (stale). ✅ |
| **vLLM PR #20511** reproducible `sha256_cbor` block hashing | **Merged.** ✅ |
| **GAIE `conformance/vX.Y.Z` releases** | Active; real conformance suite + promoted LWEPP image. ✅ |
| **GAIE model-server-protocol proposal** (`docs/proposals/003-model-server-protocol`) | Exists; the closest thing to a model-server *interface* standard. ✅ |
| **llm-d `EngineAdapter` interface** | Ships with 2 adapters; the only cross-engine KV-event normalisation point. ⚠️ Single-project, undocumented as a public spec. |
| **`kv-first`** (KV Manifest, KVCC L0/L1/L2, conformance) | Self-published white paper, 0 stars, no implementers. ✅ |
| **vLLM RFC #42082** standardized KV cache layouts → `CanonicalKVCaches` | Implemented in `vllm/v1/kv_offload/base.py`. ⚠️ RFC number cited from source comments; RFC text not fetched. |
| **"KV cache events SIG" / "KV cache interoperability spec"** | ❌ **Not found anywhere.** No SIG, no KEP, no CNCF/PyTorch Foundation KV-cache working group. |
| **PyTorch Foundation KV-cache effort** | ❌ Only weak signals: an llm-d statement of intent to *"increase collaboration with the PyTorch Foundation"*, and a PyTorch Conference talk *"Scaling KV Caches for LLMs: How LMCache + NIXL Handle Network and Storage Heterogeneity"* (PyTorch Conference hosted files). No working group, charter, or specification. |
| **CNCF AI Conformance program (disaggregated serving)** | Announced as a plan by llm-d: *"llm-d plans to work with the CNCF AI Conformance program to ensure critical capabilities like disaggregated serving are interoperable across the ecosystem."* ⚠️ Whether a disaggregated-serving conformance profile exists yet: **not verified.** |

### 5.5 Verdict: convergence or divergence?

**Convergence is real but shallow and unspecific; divergence persists exactly where it costs money.**

Evidence **FOR** convergence (2026):
1. **SGLang deliberately adopted vLLM's event schema and wire topic format**, and says so in its source docstring, naming Dynamo as the beneficiary consumer.
2. **llm-d normalises both engines through a single Go interface**, and its adapter comments treat vLLM and SGLang as "the same positional wire format".
3. **NIXL is the transfer layer for vLLM, SGLang, Dynamo, LMCache, and (probably) TensorRT-LLM**, and AWS named NIXL + those three frameworks in one sentence.
4. **GAIE shipped conformance releases and a promoted reference image**, and shrank its own scope on purpose to become a cleaner standard.
5. **llm-d entered the CNCF** with explicit "open governance / neutral standard" framing and an explicit plan to work with CNCF AI Conformance.
6. **Cross-project integrations are shipping, not aspirational**: LMCache↔Dynamo, SGLang HiCache↔Dynamo, Tensormesh→LMCache, AIBrix→SGLang L3, Mooncake↔NIXL↔vLLM/SGLang.
7. **vLLM's canonical/parallelism-agnostic KV layout** is a genuine portable-block abstraction, and reproducible hashing landed.

Evidence **AGAINST** convergence:
1. **The one KV-interop RFC was closed as stale/not planned.** No replacement.
2. **No versioned KV connector ABI anywhere.** vLLM's base class still self-declares experimental; NIXL has no spec, no semver policy, no governance file, and is consumed via exact pins (`nixl == 1.4.1`).
3. **The event schema is unfrozen and moving**: vLLM changed encoding mid-2026 (#42892 positional→map) and llm-d survived only via defensive length-guarded parsing. Divergent field names persist (`data_parallel_rank` / `attn_dp_rank` / `dp_rank`; `block_size` / `num_block_tokens`; `parent_block_hash` / `parent_hash`).
4. **Divergent tier vocabularies already**: vLLM `CPU` vs SGLang `CPU_PINNED`; SGLang has `DISK`/`EXTERNAL` with no vLLM constant. llm-d hard-codes weights (`gpu=1.0`, `cpu=0.8`) because there is no shared tier metric.
5. **Two independent replay/recovery protocols** (vLLM buffer-replay vs Dynamo buffer+RadixTree snapshot), with **6 documented response variants** in Dynamo that vLLM has no notion of. A consumer must implement both.
6. **NIXL notification payloads are being used as a private protocol.** vLLM's lease-renewal heartbeats ride NIXL `send_notif` with a `"HB:"` string prefix and vLLM-specific expiry semantics. That is a de-facto standard being extended in an unstandardised way — the classic failure mode of standards-by-adoption.
7. **The control plane just got *less* standard.** InferenceObjective / InferenceModelRewrite / EndpointPickerConfig were **removed** from kubernetes-sigs and moved to a CNCF Sandbox project. Vendor-neutrality is arguable; Kubernetes-sigs-standard status is not.
8. **Divergent offload plugin interfaces**: vLLM's `OffloadingSpec`/`SecondaryTierManager`+`CachePolicyFactory` vs SGLang's `HiCacheStorage(ABC)` — same problem, two incompatible plugin contracts, both with out-of-tree loaders that each log "experimental".
9. **The only complete KV-cache spec written in 2026 has 0 stars**, and the only shipped reproducible-hashing contract is opt-in (`prefix_caching_hash_algo` defaults to `"sha256"`, not `"sha256_cbor"`).

**Bottom line.** 2026 produced **interoperability through adapters** rather than **standards through specification**. The convergence is concentrated in (a) NIXL as the byte mover, (b) the vLLM event *kernel* as the event lingua franca, and (c) GAIE's `InferencePool`/conformance as the Kubernetes contract. It is absent exactly where it would require someone to own a version number: connector ABIs, KV-event versioning, tier vocabularies, and block layout. The most likely 2027 path — given RFC #20492's death and the EPP's migration — is further de-jure drift with continued de-facto consolidation around NIXL + the vLLM event schema + GAIE CRDs.

---

## 6. KV block / offload abstractions compared

Is a common "KV block" abstraction emerging? **A common *shape*, yes. A common *interface*, no — and the closest thing to a portable block contract is vLLM-internal.**

| Project | Block identity | Block storage/manager | Tier ladder | Offload plugin contract | Notes |
|---|---|---|---|---|---|
| **vLLM** | `BlockHash` / `ExternalBlockHash`; chain hash with `NONE_HASH` root; hash input = tokens + `extra_keys` (MM ids, LoRA name, cache_salt, prompt embedding hashes); algos `sha256` (default), `sha256_cbor`, `xxhash`, `xxhash_cbor`. Offload identity = **`OffloadKey` = block_hash bytes ‖ group_idx (4B big-endian)**. | `KVCacheManager` + `BlockPool` (scheduler-side, bindable by connectors for per-GPU ref counts/iteration); `KVCacheBlocks`; `KVCacheConfig` groups. | `Medium` = {`CPU`, `STORAGE`} + `Locality` = {`LOCAL`,`REMOTE`} + free-form `ownership`. Tiering = CPU primary (mandatory) + N secondaries. | `OffloadingSpec` ABC → `get_manager()` / `get_worker()`; `OffloadingManager` (lookup/prepare_load/touch/complete_load/prepare_store/complete_store); `SecondaryTierManager` (lookup/submit_store/submit_load); `CachePolicy` (get/insert/remove/touch/evict); each with an out-of-tree `module_path` escape hatch. | Chunk = `blocks_per_chunk` blocks coalesced, `BLOCK_SIZE_ALIGNMENT`-rounded, one copy per rank or single copy if `replicated_layout`. **`CanonicalKVCaches`** = `(num_blocks, ...)` int8 tensors + `CanonicalPageMapping`/`CopyRun` with `parallelism_agnostic` flag. **This is the most spec-like block contract in the ecosystem.** |
| **SGLang** | Radix tree node span → **HiRadixTree** nodes record tier residency. Page-oriented API (`batch_get_v1`/`batch_set_v1`) alongside legacy tensor `get`/`set`. Page size = `--page-size` tokens. | `RadixCache` → `HiRadixCache`; L1 GPU / L2 host / L3 storage. L2 = *"each instance's own private L2"* (cannot pool host memory across machines). | `StorageMedium` = **`GPU` / `CPU_PINNED` / `DISK` / `EXTERNAL`**, emitted in `medium` on BlockStored/BlockRemoved on every tier transition. | **`class HiCacheStorage(ABC)`** — *"a set of simple and consistent interfaces"*; `--hicache-storage-backend {file,mooncake,hf3fs,nixl,aibrix,dynamic}`; `dynamic` takes `backend_name`/`module_path`/`class_name`. Write policies: `write_through` / `write_back`. Prefetch policies: `best_effort`/`wait_complete`/`timeout`. IO backends: `direct`/`kernel`. | *"to reduce overhead, HiRadixTree does not store or continuously synchronize metadata for L3 ... it queries the backend in real time."* Zero-copy: passes memory addresses+sizes to the L3 backend. |
| **LMCache** | `CacheEngine` / `StorageManager` / `LMCacheEngine` (per brief; ⚠️ I verified only the *existence* of pluggable storage+transport from the README, **not** these class names from source). | `LMCacheEngine` with a pluggable `StorageManager`; **LMCache Operator** factors management out into its own container. | CPU RAM, local disk (SSD), Redis/Valkey, Mooncake, InfiniStore, S3-compatible, NIXL, GDS. | *"Pluggable storage and transport backends ... through a unified interface"*; *"storage plugin interface is fully wired into Dynamo"*. | Tensormesh TMO pins LMCache Operator as its KV layer. ⚠️ **Exact class names unverified** — README-level claims only. |
| **Dynamo KVBM** | **Blocks with typed handles (mutable/immutable)** + metadata (e.g. priority) + views by layer/outer dims; **matched by `sequence_hash`**; lifecycle = allocate → register (immutable) → match. | `KvBlockManager` (public facade) → `KvBlockManagerState` owning layouts, storage backends, pools, `OffloadManager`, metrics, event hooks. `Scheduler` gates transfer execution *"relative to model progress (iteration/layer completion) when integrated with a framework connector (e.g., vLLM V1)."* | **Explicit 4-tier ladder: G1 device (GPU) / G2 host (CPU pinned) / G3 disk (local NVMe) / G4 remote-oblivious.** | Framework integration *"via the connector API"*; `LayoutConfig`/`LayoutType` (layer-separated or fully-contiguous); `TransferManager` with per-path queues (D→H, H→Disk, H→D, Disk→D). | *"The design of the KVBM takes inspiration from the KV block managers used in SGLang and vLLM, with added influence from historical memory tiering strategies common in general GPU programming."* **G4 is deliberately opaque**: *"KVBM treats G4 as an opaque blob store accessed through NIXL, unaware of internal layout optimizations."* |
| **AIBrix KVCache** | ⚠️ *"a production-ready KVCache Offloading Framework, which enables efficient memory tiering and low-overhead cross-engine reuse"* — verified from SGLang's HiCache doc, which also describes it as enabling *"low-overhead cross-engine reuse"*. | ❌ Its block abstraction was **not** verified; I could not fetch AIBrix source. | ❌ not verified | Integrates as **SGLang HiCache L3 backend** `aibrix`; also has a vLLM integration PR (#2060). | **Flagged as unverified.** Do not compare its block model. |

### 6.1 Where the abstractions actually agree

Five genuine points of agreement, and five real gaps:

**Agreement:**
1. **Chained/cumulative hashes as block identity.** vLLM's `parent_block_hash` chain, SGLang's `parent_block_hash`, Dynamo's `parent_hash` + *"sequence block hashes ... cumulative hashes"*, llm-d's *"block key chain"*. Everyone treats a block as only reusable if its whole ancestry is resident — llm-d states the reason explicitly (causal attention).
2. **A `medium` string field on store/remove events** as the tier signal — present in vLLM, SGLang, and consumed by llm-d and Dynamo.
3. **Block admission is post-completion, not on allocation.** vLLM's `ChunkStatus.ref_cnt == -1` ("not yet ready to be read"); Dynamo's *"Allocates mutable GPU blocks, registers completed blocks (immutable)"*; SGLang's write-back; the KVEvents rule that `BlockStored` fires after the store completes. Universal.
4. **Three-to-four tiers with the same semantic ladder**: GPU → host/CPU-pinned → local disk → remote/opaque. Dynamo names them G1–G4; SGLang L1–L3 (+EXTERNAL = L4); vLLM `GPU`/`CPU`/`STORAGE` + `Locality.REMOTE`; llm-d weights `gpu`/`cpu`.
5. **A primary tier as gateway for all secondary traffic.** vLLM: *"Secondary tiers cannot directly access GPU memory. All data transfers must go through the CPU (primary) tier."* Dynamo: same shape (G2 host as the hub for G1↔G3↔G4). This is a genuine architectural convergence.

**Gaps:**
1. **Tier vocabulary is not shared.** `CPU` (vLLM) vs `CPU_PINNED` (SGLang); `STORAGE` (vLLM) vs `DISK`+`EXTERNAL` (SGLang); `G1..G4` (Dynamo). llm-d resorting to hard-coded weights is the symptom.
2. **No shared block-uniqueness contract.** vLLM's `OffloadKey` implicitly pairs block hash with `group_idx` because of hybrid attention; nothing equivalent is standard.
3. **No shared offload-plugin interface.** `OffloadingSpec`/`SecondaryTierManager`/`CachePolicy` vs `HiCacheStorage(ABC)` vs Dynamo's connector API vs LMCache's storage plugin interface — four contracts, all marked experimental or undocumented.
4. **Cross-parallelism portability is solved by exactly one project.** vLLM's `parallelism_agnostic` canonical pages + `CopyRun` mapping. Dynamo's G4 is deliberately layout-ignorant; SGLang's L3 is queried live. This is the capability that a *shared* KV pool would require, and it exists in one codebase.
5. **No shared eviction-policy interface.** vLLM has a pluggable `CachePolicy` with `lru`/`arc`; Dynamo has `--router-approximate-cache-policy {ttl,lru}` on the *router* side; llm-d has index backends with LRU/Ristretto/Redis. Three different places where "eviction policy" is a plugin boundary, none shared.

**Answer to the brief's question.** A common KV *block* abstraction is **not** emerging as an interface. What is emerging is a common **block lifecycle vocabulary** (hash-chain identity → store on completion → tier-tagged residency event → prefix-chain-aware lookup) that four independent projects each implemented, plus **one** project (vLLM) prototyping the hard part (canonical, parallelism-agnostic page layout) that cross-engine sharing would require. The absence of that layout in everyone else's design is the concrete reason a cross-engine KV pool is still a research prototype rather than a product feature.

---

## 7. Snapshot table (all verified 2026-09-15)

| Project | Version | Date | Stars | Forks | Licence |
|---|---|---|---|---|---|
| nixl | **1.4.1** | 2026-09-01 | 1,256 | 441 | MIT AND Apache-2.0 (PyPI); Apache-2.0 source |
| vllm | **0.29.0** | 2026-09-09 | 91,813 | 22,221 | Apache-2.0 |
| sglang | **0.5.19** | 2026-09-04 | 35,982 | 8,871 | Apache-2.0 |
| LMCache | **0.5.5** | 2026-09-12 | 11,812 | 1,887 | Apache-2.0 |
| dynamo | **1.4.2** (PyPI `ai-dynamo`) | 2026-08-28 | 8,083 | 1,586 | Apache-2.0 |
| aibrix | — | — | 5,089 | 694 | Apache-2.0 |
| llm-d | v0.5.5 | 2026-09-13 | 4,542 | 768 | Apache-2.0 |
| gateway-api-inference-extension | **v1.6.1** | 2026-09-11 | 768 | 313 | Apache-2.0 |
| llm-d-router | v0.10.0 | 2026-08-17 | 339 | 370 | Apache-2.0 |
| openhivesai/kv-first | — | 2026 | **0** | **0** | Apache-2.0 + CC BY 4.0 |

Star/fork counts are HTML-scraped (GitHub API was rate-limited); versions/dates are from PyPI JSON or release Atom feeds.

---

## 8. Explicitly unverified / could not confirm

1. **`nixl_connect` internals.** The Dynamo file `docs/api/nixl-connect/README.md` exists (confirmed via a Dynamo commit and a pinned-commit GitHub URL), but **`raw.githubusercontent.com/ai-dynamo/dynamo` was unreachable all session** (connection timeouts; other orgs' raw fetches worked). No class/function names, no API description. ❌
2. **NIXL v1.0.0 exact release date.** The releases feed returned only the 10 most recent entries; v1.0.1 was 2026-04-14, so v1.0.0 was in the April 2026 window. ❌
3. **NVSHMEM.** Absent from `all_plugins` at v1.4.1. The README's remark about "no NVSHMEM-equivalent backend yet" is in the **ROCm** section, so it is possible a CUDA NVSHMEM plugin exists under a different build gate I did not inspect. Treated as "not a NIXL plugin" but flagged. ⚠️
4. **Dynamo's `KVEvent` Rust struct and `LocalKvIndexer` source.** All Dynamo schema statements come from rendered docs pages, not source. `lib/kv-router/src/indexer/mod.rs` fetched, but `zmq.rs` and `publisher.rs` did not. ⚠️
5. **LMCache class names** (`CacheEngine`, `StorageManager`, `LMCacheEngine`) — taken from the brief, not verified from LMCache source. ❌
6. **AIBrix block abstraction and GAIE relationship** — not verified. ❌
7. **TensorRT-LLM's NIXL integration** — evidence is test-config strings and PR titles from search; source not read (fetch timed out). ⚠️
8. **llm-d's use of NIXL** — asserted by ecosystem context but not pinned to an llm-d doc I could fetch (its networking blog 404'd). ⚠️
9. **SGLang vs vLLM replay reply framing** — ✅ source-verified as divergent (vLLM 5 frames incl. topic; SGLang 4 frames; `END_SEQ` at different frame index). Runtime cross-engine replay was **not** executed, so the practical impact is inferred, not measured. ⚠️
10. **vLLM PR #42892** (positional→tagged-map event encoding change) — referenced only by llm-d's adapter comment; PR not opened. ⚠️
11. **vLLM RFC #42082** (standardized KV cache layouts) and issue **#48408** — referenced in vLLM source comments; RFC text not fetched. ⚠️
12. **GAIE GA vs pre-GA inconsistency** — README says GA'd; its own Roadmap reads as pre-GA. No KEP found. ❌
13. **CNCF AI Conformance program for disaggregated serving** — announced as a plan by llm-d; existence of an actual profile not verified. ❌
14. **Whether Dynamo's GAIE integration and Dynamo's own Gateway API router are reconciled** — not determined. ❌
15. **The exact semantics of `self_describing_kv_events`** — flag, default (`False`), requirement enforcement and wiring verified; no prose documentation found, so semantics inferred. ⚠️
16. **NIXL UCX version discrepancy** (README "1.23.x" vs 1.4.0 notes "v1.22.x") — unresolved. ⚠️

---

## Sources

### NIXL
- https://github.com/ai-dynamo/nixl
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/README.md
- https://raw.githubusercontent.com/ai-dynamo/nixl/v1.4.1/meson.build
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/CONTRIBUTING.md
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/docs/nixl.md
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/docs/python_api.md
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/docs/BackendGuide.md
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/docs/telemetry.md
- https://raw.githubusercontent.com/ai-dynamo/nixl/main/docs/doxygen/nixl_doxygen.md
- https://github.com/ai-dynamo/nixl/releases.atom
- https://github.com/ai-dynamo/nixl/releases/latest
- https://pypi.org/pypi/nixl/json
- https://aws.amazon.com/about-aws/whats-new/2026/03/aws-support-nixl-with-efa/
- https://www.amazonaws.cn/en/new/2026/nixl-with-efa-to-accelerate-llm-inference-at-scale-is-available/
- https://www.weka.io/article/weka-accelerates-ai-inference-with-nvidia-dynamo-and-nvidia-nixl
- https://www.ddn.com/blog/ddn-becomes-the-first-storage-vendor-natively-integrated-into-nvidia-kv-cache-management/
- https://github.com/ai-dynamo/dynamo/pull/9705
- https://github.com/ai-dynamo/dynamo/pull/9265
- https://github.com/ai-dynamo/dynamo/pull/12217

### vLLM
- https://github.com/vllm-project/vllm
- https://pypi.org/pypi/vllm/json
- https://github.com/vllm-project/vllm/tree/main/vllm/distributed/kv_transfer/kv_connector/v1
- vLLM source at `main` (fetched 2026-09-15): `vllm/distributed/kv_transfer/kv_connector/v1/base.py`, `v1/__init__.py`, `factory.py`, `multi_connector.py`, `example_connector.py`, `nixl/*`, `vllm/distributed/kv_events.py`, `vllm/v1/kv_offload/{base,config,factory}.py`, `vllm/v1/kv_offload/cpu/{spec,policies/*}.py`, `vllm/v1/kv_offload/tiering/{spec,base}.py`, `vllm/v1/kv_offload/tiering/p2p/data/nixl.py`, `vllm/config/kv_transfer.py`, `vllm/config/cache.py`, `vllm/v1/core/kv_cache_utils.py`, `requirements/kv_connectors.txt`
- vLLM docs at `main`: `docs/features/nixl_connector_usage.md`, `docs/features/nixl_connector_compatibility.md`, `docs/features/disagg_prefill.md`, `docs/features/kv_offloading_usage.md`, `docs/design/nixl_kv_cache_lease.md`, `docs/design/nixl_kv_push_connector.md`, `docs/contributing/deprecation_policy.md`
- https://docs.vllm.ai/en/latest/ (and the catch-all behaviour of https://docs.vllm.ai/en/latest/design/kv_connector.html)
- https://docs.vllm.ai/en/latest/api/vllm/distributed/kv_events.html
- https://github.com/vllm-project/vllm/issues/20492 (RFC: KV-Cache Interoperability API Standardization — closed as not planned)
- https://github.com/vllm-project/vllm/pull/20511 (sha256_cbor reproducible block hashing — merged)
- https://github.com/vllm-project/vllm/issues/39749 (vLLM Roadmap Q2 2026)
- https://github.com/vllm-project/vllm/issues/49399
- https://github.com/vllm-project/vllm/pull/49868
- https://github.com/vllm-project/vllm/issues/33702
- https://github.com/vllm-project/vllm/issues/43094
- https://github.com/vllm-project/vllm/issues/39696

### SGLang
- https://github.com/sgl-project/sglang
- https://pypi.org/pypi/sglang/json
- https://raw.githubusercontent.com/sgl-project/sglang/main/python/sglang/srt/disaggregation/kv_events.py
- https://raw.githubusercontent.com/sgl-project/sglang/main/python/sglang/srt/mem_cache/storage/nixl/README.md
- https://docs.sglang.io/docs/advanced_features/hicache_design
- https://docs.sglang.io/docs/advanced_features/hicache_best_practices
- https://lmsys.org/blog/2025-09-10-sglang-hicache/
- https://github.com/sgl-project/sglang/issues/29709 (RFC: KV Cache Events for HiCache L3 Storage Backends)
- https://github.com/sgl-project/sglang/pull/6098
- https://github.com/sgl-project/sglang/pull/26387
- https://github.com/sgl-project/sglang/pull/22894

### llm-d and KV indexer
- https://github.com/llm-d/llm-d
- https://github.com/llm-d/llm-d-kv-cache
- https://github.com/llm-d/llm-d-router
- https://raw.githubusercontent.com/llm-d/llm-d-kv-cache/main/docs/architecture.md
- https://raw.githubusercontent.com/llm-d/llm-d-kv-cache/main/docs/configuration.md
- https://raw.githubusercontent.com/llm-d/llm-d-kv-cache/main/pkg/kvevents/engineadapter/vllm_adapter.go
- https://raw.githubusercontent.com/llm-d/llm-d-kv-cache/main/pkg/kvevents/engineadapter/sglang_adapter.go
- https://llm-d.ai/docs/0.8/architecture/advanced/kv-management/kv-indexer
- https://github.com/llm-d/llm-d/blob/main/docs/architecture/advanced/kv-management/kv-offloader.md
- https://github.com/llm-d/llm-d/blob/main/guides/tiered-prefix-cache/storage/README.md
- https://www.cncf.io/blog/2026/03/24/welcome-llm-d-to-the-cncf-evolving-kubernetes-into-sota-ai-infrastructure/
- https://cloud.google.com/blog/products/containers-kubernetes/llm-d-officially-a-cncf-sandbox-project
- https://www.techzine.eu/news/infrastructure/139839/llm-d-joins-the-cncf/

### Dynamo / KVBM / KV events
- https://github.com/ai-dynamo/dynamo
- https://pypi.org/pypi/ai-dynamo/json
- https://docs.nvidia.com/dynamo/llms.txt
- https://docs.nvidia.com/dynamo/dev/knowledge-base/modular-components/router/overview.md
- https://docs.nvidia.com/dynamo/dev/knowledge-base/modular-components/router/configuration-and-tuning.md
- https://docs.nvidia.com/dynamo/dev/knowledge-base/concepts/system-architecture/kv-aware-routing.md
- https://docs.nvidia.com/dynamo/dev/knowledge-base/concepts/communication-planes/request-plane.md
- https://docs.nvidia.com/dynamo/dev/integrations/kv-events-for-custom-engines.md
- https://docs.nvidia.com/dynamo/dev/knowledge-base/modular-components/router/kv-event-replay.md (KV Event Replay — Dynamo vs vLLM)
- KVBM Design page — ⚠️ contents fetched into `raw/dy_kvbm_design.md` earlier in this workspace, but the exact canonical URL was **not** re-confirmed at research time; the KVBM material is from that saved page.
- https://github.com/ai-dynamo/dynamo/blob/main/docs/integrations/sglang-hicache.md
- https://github.com/ai-dynamo/dynamo/blob/main/docs/api/nixl-connect/README.md
- https://github.com/ai-dynamo/dynamo/commit/fa4a7f1e71479cbf2bb735551296862c4399c418
- https://blogs.nvidia.com/blog/dynamo-1-0/
- https://blog.lmcache.ai/en/2026/03/16/lmcache-nvidia-dynamo-1-0-a-match-made-in-inference-heaven/
- https://blog.lmcache.ai/en/2025/09/18/nvidia-dynamo-integrates-lmcache-accelerating-llm-inference/
- https://github.com/ai-dynamo/dynamo/issues/3169

### Gateway API Inference Extension
- https://github.com/kubernetes-sigs/gateway-api-inference-extension
- https://raw.githubusercontent.com/kubernetes-sigs/gateway-api-inference-extension/main/README.md
- https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases.atom
- https://github.com/kubernetes-sigs/gateway-api-inference-extension/issues/2430
- https://github.com/kubernetes-sigs/gateway-api-inference-extension/pull/2906
- https://github.com/kubernetes-sigs/gateway-api-inference-extension/tree/main/docs/proposals/003-model-server-protocol
- https://gateway-api-inference-extension.sigs.k8s.io/concepts/api-overview/
- https://gateway-api-inference-extension.sigs.k8s.io/implementations/model-servers/
- https://github.com/llm-d/llm-d-inference-payload-processor

### LMCache, Mooncake, AIBrix, Tensormesh, other
- https://github.com/LMCache/LMCache
- https://raw.githubusercontent.com/LMCache/LMCache/main/README.md
- https://pypi.org/pypi/lmcache/json
- https://blog.lmcache.ai/en/2026/01/21/p2p-1/
- https://blog.lmcache.ai/en/2026/06/23/vllm-lmcache-a-starter-guide-no-gpu-required/
- https://github.com/kvcache-ai/Mooncake
- https://github.com/vllm-project/aibrix
- https://github.com/vllm-project/aibrix/pull/2060
- https://github.com/vllm-project/aibrix/issues/2104
- https://github.com/vllm-project/production-stack
- https://www.tensormesh.ai/
- https://docs.tensormesh.ai/configuration/cacheblend
- https://docs.tensormesh.ai/configuration/p2p
- https://docs.tensormesh.ai/llms.txt
- https://arxiv.org/abs/2405.16444 (CacheBlend)
- https://static.sched.com/hosted_files/pytorchconference/88/LMCache%20and%20NIXL.pdf
- https://github.com/taco-project/FlexKV/blob/main/docs/vllm_adapter/README_en.md
- https://github.com/NVIDIA/TensorRT-LLM/pull/11136
- https://github.com/NVIDIA/TensorRT-LLM/pull/11978
- https://github.com/NVIDIA/TensorRT-LLM/pull/16524

### Standardisation proposals
- https://github.com/vllm-project/vllm/issues/20492
- https://github.com/openhivesai/kv-first
- https://raw.githubusercontent.com/openhivesai/kv-first/main/README.md
- https://cseweb.ucsd.edu/~yiying/cse291a-fall25/reading/cacheblend.pdf
