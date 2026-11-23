# 006 — layerwise KV buffer 复用：内网开发指南

> 更新：2026-11-21
>
> 面向：在内网昇腾环境继续开发的 agent / 工程师
>
> 配套：[003 设计与本地验证](003-layerwise-KV-buffer复用.md)（细节与实验数据）

---

## 1. 一页纸总览

**特性**：在 vllm-ascend 的 `AscendStoreConnector` 上，给 **block-key（Mooncake）数据面**开启
**跨层 KV buffer 复用**——多个层分时复用同一块物理 KV 槽位，用 save-finished 事件做 fence。

**收益**（GLM-5.3，78 层，3 个共享槽 + 1 个独立槽）：

```text
本地 KV 占用：78 层 → 4 槽，省 94.9%，同预算容量约 19.5×
140K 单请求：12.0 GiB → 615 MiB
```

**当前状态**：代码已推到 vllm-ascend fork 的 v0.30.0 分支；UT 881 passed；CPU 参考实现端到端验证通过；
**NPU 真机 e2e / indexer 数据面 / RDMA 性能尚未验证**。

### 1.1 仓库与分支矩阵

| 仓库 | 分支 / 提交 | 内容 | 用途 |
| :-- | :-- | :-- | :-- |
| [`sunlei1992/vllm-ascend`](https://github.com/sunlei1992/vllm-ascend) | **`layerwise/v030-ascend-store` @ `72081f546`**<br>base `origin/releases/v0.30.0` @ `5cb68ba64` | **生产特性代码**（4 提交） | 内网验证主分支 |
| 同上 | `feature/mooncake-layerwise-reuse` @ `13d80c908`<br>base `8237ee6d6`（main） | 同特性，main 基线 | 后续上游 PR / main 合入 |
| [`yeshenye19992/mxllm`](https://gitcode.com/yeshenye19992/mxllm) | **`layerwise/shared-buffer-v030` @ `e8b9630`** | handoff 包 + `patches-v0.30.0/` + bundle | 内网任务包 / 补丁载体 |
| 同上 | `layerwise/shared-buffer-fix` @ `ba677de` | handoff 包（main 基线） | 参考 |
| 本 workspace wiki | `003` / `006` | 设计、验证记录、本指南 | 文档 |
| 本 workspace assets | `assets/qwen_cpu_kv/shared_buffer/` | CPU 参考 connector + UT | 契约参考，不是产品代码 |

> **重要**：mxllm 仓本身不包含 vllm-ascend。内网验证 = mxllm 的 handoff 包 + vllm-ascend 的
> `layerwise/v030-ascend-store` 分支，两件事。

### 1.2 四个提交（v0.30.0 版）

| 提交 | 作用 |
| :-- | :-- |
| `05e01d002` | fix: 复用层必须重载完整 prefix |
| `09cd233cf` | fix: partial tail 按结束 token 划定作用域 |
| `31c2de735` | feat: block-key 平面规划层复用（`prefetch_layer_map`） |
| `72081f546` | feat: Mooncake 后端打开共享 KV buffer |

---

### 1.3 详细设计在哪里（读完本节后按需跳转）

006 是**入口**：一页纸 + 方案摘要 + 内网步骤 + 验收。更细的内容在：

| 想看什么 | 去哪里 |
| :-- | :-- |
| 设计细节、实验数据、边界条件 | [003 §1–§12](003-layerwise-KV-buffer复用.md)（两个数据面、槽位规划、fence、partial tail、indexer、P/D） |
| CPU 端到端验证、hook 顺序修复 | 003 §23（4 层/28 层验收、6 条 UT） |
| v0.30.0 移植、冲突处理、881 passed | 003 §24 |
| HBM 收益推导（公式 + GLM-5.3 数字） | 003 §11 |
| 类关系、数据结构、不变量、agent 边界 | mxllm `handoff/layerwise_pd/ARCHITECTURE.md` |
| NPU 实现说明（event / codec / transport） | mxllm `handoff/layerwise_pd/PSEUDOCODE.md` |
| 内网任务与预期输出（T00–T09） | mxllm `handoff/layerwise_pd/TASKS.md` |
| 结果记录模板 | mxllm `handoff/layerwise_pd/RESULTS_TEMPLATE.md` |
| 2026-11-21 CPU 验收数据 | mxllm `handoff/layerwise_pd/RESULTS-2026-11-21.md` |
| 代码地图（文件/函数） | 本文件 §3 |

> 简记：**006 看入口与步骤，003 看设计与实验，handoff 看任务与接口。**

## 2. 方案设计

> 本节是摘要；完整推导、实验和边界条件见 [003 §1–§12](003-layerwise-KV-buffer复用.md)。

### 2.1 问题

layerwise KV offload 是**逐层**搬运：一层算完 D2H 存走，下一轮该层算之前再 H2D 取回。
如果每层一个物理 buffer，78 层就是 78 份 staging buffer，HBM 又不够了。

### 2.2 两个数据面

| | GVA 平面（Memcache） | **block-key 平面（Mooncake）** |
| :-- | :-- | :-- |
| key 粒度 | 整层对象 | 每个 block 一个 key |
| 共享 buffer 的 fence | 显式完成门控 | **save-finished 事件**（同步 publish 后置位） |
| 我们的改动 | 原本已支持 | 本次打开复用（`extract_layout_config` opt-in） |

### 2.3 槽位规划

```text
layerwise_num_shared_buffers = N     # 默认 = 层数（等于不复用！）
layerwise_independent_layers = [0]   # 独立层，默认第 0 层

槽位数 S = N + len(independent_layers)
层 L 共享 N 个槽：按 main spec 分桶，桶内 round-robin 分配
prefetch_layer_map：每个复用层 L → 它前一个 owner 层（用于预取）
```

`apply_layerwise_kv_cache_plan()` 把每层一个 `KVCacheTensor` 改写成每槽一个 descriptor：

```text
layers = [同槽的层...]
layer_stride = 0                 # 同槽的层 alias 同一块
block_stride = page_size_bytes
offset = 槽的累积偏移
size   = 所有槽之和（upstream 单 backing 语义）
```

> vllm-ascend 的 GLM-Next 路径是**每个 descriptor 单独分配**（`size == num_blocks * block_stride`，
> `offset == 0`），所以 Ascend 侧 offset 不参与寻址；上面的 `size/offset` 主要影响 pure-vLLM 的
> `allocate_kv_cache`（单 backing + offset 切片）。

### 2.4 生命周期

```text
prefill（新请求）：
  第 L 层：wait_for_layer_load(L) → 无历史，zero_（可选）
           → KV update 写入 prompt
           → attention
           → save_kv_layer(L)  （提交到 store）

decode（有历史）：
  第 L 层：wait_for_layer_load(L) → 从 store 取回 L 的历史 KV
           → KV update 写入新 token
           → attention
           → save_kv_layer(L)
```

**顺序不变量（必须遵守）**：

1. **load 必须在 KV update 之前**（否则历史 KV 会覆盖新 token 的行）
2. **request key 在 forward 之前绑定**（不要依赖 `start_load_kv`，它在 `post_forward` 才跑）
3. **同一 (step, layer) 的 load 去重**（通用 hook 可能触发两次）

> Ascend 生产路径审计结论：`mla_v1.py:2517`、`sfa_v1.py:2010/2053`、`dsa_v1.py:1887` 都是
> **先 wait、后写 KV**，且 worker 由 scheduler 的 `layer_load_tasks` 驱动，不依赖 `start_load_kv` 的
> key。**生产路径不需要额外改顺序**（§24.4）。

### 2.5 fence：共享 buffer 何时可以覆盖

block-key 平面的发送线程**同步 publish** 该层保存，完成之后才置该层的 `save_finished` 事件。
复用层在 overwrite 之前等待前一个 owner 的事件，因此不需要额外的 completion gate。
`attention_fence.py` 负责把"attention 开始/结束"与搬运窗口对齐。

### 2.6 partial tail

chunked prefill 的最后一层可能只写了一部分 block。partial tail 的 key 必须按**结束 token**
（而不是起始 token）划定作用域，否则会读到不属于自己的尾部数据。

### 2.7 indexer（SFA）共享

GLM-5.3 每层除主 MLA cache 外还有 `AscendSFAIndexerCacheSpec`。复用布局会同时为主 cache 和
indexer 建槽：indexer 只共享 **raw backing 容量**，各层保留自己的 data/scale 视图。
真机 indexer 数据面（读写、scale layout、DCP 复制维度）**尚未验证**。

### 2.8 P/D 边界

- `use_layerwise` **只在 P 节点**支持（v0.30.0 文档）
- P：`MultiConnector`（`SfaRemoteD2HConnector` producer + `AscendStoreConnector` layerwise）
- D：`SfaRemoteD2HConnector` consumer，且 `sparse_kv_offload_config.enabled=true`（P 侧必须 false）
- 传输是 **D 拉 P**（memfabric `READ_READY_BATCH` / `READ_DONE`，P 不 push）
- bulk MLA KV 进 D 的 CPU pinned pool，indexer KV 进 HBM
- 950PR & 950DT 暂不支持 sparse decode offload

### 2.9 配置参数

| 参数 | 默认 | 说明 |
| :-- | :-- | :-- |
| `backend` | `mooncake` | 必须是 Mooncake block-key |
| `use_layerwise` | `false` | 打开 layerwise |
| `layerwise_num_shared_buffers` | **层数** | **不设 = 不复用**；GLM-5.3 建议 3 |
| `layerwise_independent_layers` | `[0]` | 独立层；`"all"` = 全部独立（不复用） |
| `layerwise_prefetch_layers` | `min(N, 8)` | 预取深度 |

### 2.10 收益公式

```text
S = layerwise_num_shared_buffers + len(layerwise_independent_layers)
节省 = 1 − S/L
容量倍数 = L/S
```

GLM-5.3（L=78）：

| N | S | 节省 | 容量倍数 |
| :-- | :-- | :-- | :-- |
| 1 | 2 | 97.4% | 39× |
| 3 | 4 | **94.9%** | **19.5×** |
| 8 | 9 | 88.5% | 8.7× |

- `apply_layerwise_kv_cache_plan` **只改 descriptor，不改 `num_blocks`**：默认是"占用变少"；
  要"容量变大"，同步调大 `--kv-cache-memory-bytes` / 显存预算
- **Mooncake 存储池不省**：每层 KV 仍要全存

---

### 2.11 Mooncake TE PullTransport 原型（本地已跑通，2026-11-23）

为了评估"Mooncake 版 SfaRemoteD2H"（D 单边读 P 的 HBM），先在本地做了
**transport 层原型**：Mooncake TE + TCP + host 内存。

```text
assets/mooncake_te_pull/
  pull_transport.py   PullTransport 接口 + MooncakeTransport
  p_side.py           register_memory + 控制面发布地址 + 等 READ_DONE
  d_side.py           batch_transfer_sync_read + 校验 + READ_DONE
  run_demo.sh         一键起 metadata server + P + D
```

本地结果：

```text
RESULT PASS bytes=6291456 time=8.38ms
```

结论：**Mooncake TE 的 register/read/完成语义可以抽象成 PullTransport**；
昇腾侧只需替换 `protocol="tcp" -> "ascend"`、host 内存 -> HBM、
以及处理 NPU wheel 的 `batch_transfer_sync_read(session_id, ...)` 签名差异。

**类级注入（同日追加）**：用真实的 `MembPullReadThread._do_read_batch`
（VA v0.30.0 源码）配 `MooncakeTransport`，2 个 block 的 K/V 校验 **PASS**：

```text
block=0 k_match=True v_match=True
block=1 k_match=True v_match=True
RESULT PASS
```

说明 `_do_read_batch` 的指针计算 + `engine.batch_transfer_sync_read` 契约
可以直接换成 Mooncake transport，**不需要改 read_thread**。
复现：`assets/mooncake_te_pull/run_read_thread_demo.sh`。

下一步（详见 `assets/mooncake_te_pull/README.md`）：

1. 注入 `sfa_pd_rd2h/read_thread.py` 的 `engine`（已是 duck-typed）
2. 地址/会话接进 ZMQ `LayerMetadata`
3. layerwise 双 fence：`store commit + READ_DONE`
4. 失败注入 + 昇腾 HBM 注册

## 3. 代码地图（v0.30.0 分支）

| 位置 | 作用 |
| :-- | :-- |
| `vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/layerwise_cache_layout.py` | `apply_layerwise_kv_cache_plan`、`build_layerwise_reuse_layout`、`get_layerwise_reuse_config` |
| `.../ascend_store/backend/mooncake_layerwise.py` | `extract_layout_config`（opt-in）、block key |
| `.../ascend_store/pool_scheduler.py` | 复用规划、`prefetch_layer_map`、lookup |
| `.../ascend_store/pool_worker.py` | `_layerwise_reuse_config`、`_apply_layerwise_reuse_layout`、层次 load/save、fence |
| `.../ascend_store/attention_fence.py` | attention 窗口与搬运 fence |
| `vllm_ascend/worker/model_runner_v1.py`、`worker/v2/model_runner.py` | 启动时调用 `apply_layerwise_kv_cache_plan` |
| `vllm_ascend/attention/{mla_v1,sfa_v1,dsa_v1}.py` | `wait_for_kv_layer_from_connector` / `maybe_save_kv_layer_to_connector` 调用点 |
| 测试 | `tests/ut/distributed/ascend_store/{test_layerwise_cache_layout,test_mooncake_layerwise,test_pool_scheduler,test_pool_worker}.py` |

---

## 4. 开发进度

### 4.1 已完成

| 项 | 结果 |
| :-- | :-- |
| 生产代码（v0.30.0） | 4 提交 rebase 完成，推 fork |
| UT（v0.30.0） | **881 passed / 12 skipped / 406 subtests** |
| UT（main 基线） | 761 passed / 12 skipped |
| GLM-5.3 形状 | 78 层 × (MLA + SFA indexer) 单 group，4 槽布局可用 |
| CPU 端到端（4 层） | `[6212, 6212]` == baseline |
| CPU 端到端（28 层） | `[87630, 87630]` == baseline |
| 顺序契约 UT | 6 passed（`test_layerwise_wait_order.py`） |
| P0–P5 本地验证 | alias / slot fence / 跨容器 Mooncake / P/D / 失败注入 |
| 24 前缀 fake store | 16 GiB → 80.0% 命中；8 GiB → 54.2% |
| hook 顺序审计 | mla/sfa/dsa 均 load-before-update，生产路径无需改 |

### 4.2 未验证 / 风险

| 项 | 风险 |
| :-- | :-- |
| NPU 真机 e2e（event、H2D、URMA） | **最高**，所有 CPU 结论都要在 950 上复核 |
| indexer 数据面（读写/scale/DCP） | 中高 |
| RDMA / Mooncake 真实带宽 | 中 |
| hybrid / Mamba 布局 | 代码直接拒绝复用（NotImplemented） |
| MTP / draft 层 | 被排除在复用外，各占 descriptor |
| KVPP 组合 | KVPP + Mooncake layerwise 时**不启用**跨层复用，且要求 `load_async=false` |

---

## 5. 内网开发步骤（按顺序做）

### Step 0 — 获取代码

**vllm-ascend（主）**，三选一：

```bash
# A. fetch 分支（若网络可达 GitHub）
git fetch https://github.com/sunlei1992/vllm-ascend.git \
  layerwise/v030-ascend-store:layerwise/v030-ascend-store
git checkout layerwise/v030-ascend-store

# B. 用 mxllm 里的 patch 系列
git checkout -b layerwise/v030-ascend-store 5cb68ba64
git am handoff/vllm_ascend/patches-v0.30.0/000*.patch

# C. 用 mxllm 里的 bundle
git fetch handoff/vllm_ascend/layerwise-v0.30.0.bundle \
  layerwise/v030-ascend-store:layerwise/v030-ascend-store
```

**mxllm（任务包）**：

```bash
git fetch origin layerwise/shared-buffer-v030
git checkout layerwise/shared-buffer-v030
export HANDOFF="$PWD/handoff/layerwise_pd"
export PYTHONPATH="$PWD"
```

### Step 1 — 基线

```bash
# vllm-ascend UT
pytest tests/ut/distributed/ascend_store -q
# 预期：881 passed, 12 skipped（v0.30.0 环境）

# handoff 契约
python -m pytest -q handoff/layerwise_pd/tests          # 6 passed
python handoff/layerwise_pd/experiments/shared_buffer/test_layerwise_wait_order.py  # ALL PASS
```

任何一条不过，**停**，先修环境，不要往下走。

### Step 2 — 单机 prefill 冒烟（不涉及 P/D）

单机验证只需要 `AscendStoreConnector`（本地 offload / reload），**不需要**
`SfaRemoteD2HConnector`——后者只在 P/D 组合里用（见 Step 4）。

```bash
export MOONCAKE_CONFIG_PATH=/path/to/mooncake.json

python -m vllm.entrypoints.openai.api_server \
  --model /path/to/GLM-5.3 \
  --tensor-parallel-size 8 \
  --enforce-eager \
  --kv-transfer-config '{
    "kv_connector": "AscendStoreConnector",
    "kv_role": "kv_both",
    "kv_connector_extra_config": {
      "backend": "mooncake",
      "use_layerwise": true,
      "layerwise_num_shared_buffers": 3,
      "layerwise_independent_layers": [0],
      "layerwise_prefetch_layers": 2
    }
  }'
```

说明：

- `kv_role` 用 **`kv_both`**（单机既存又取）；P/D 时才拆 producer/consumer
- `layerwise_num_shared_buffers` 不设 = 不复用（默认等于层数）
- 第一次硬件验证建议 **TP=1、`layerwise_prefetch_layers=1`**，再逐步放大 TP/预取深度
  （官方 Mooncake layerwise 指南的建议）
- Mooncake client 必须含 PR #2881 的 7 个 session/range 方法（>= 0.3.13），
  否则启动即报 `Missing methods`

启动后检查三件事：

| 检查项 | 预期 |
| :-- | :-- |
| 启动日志 | `Layerwise KV cache reuse merged N descriptors into M descriptors using K buffer assignments` |
| descriptor 数 | GLM-5.3：78 层 → **4 个**（1 独立 + 3 共享） |
| KV 容量 | 同预算下容量约为原来的 **19.5×**（或占用降到 ~5%） |

然后发一个 128K/140K 的单请求（`max_tokens=1`），确认：

- 不报错、TTFT 与关闭 layerwise 时同量级（不应显著变差）
- 输出 token 与关闭时一致（greedy、同 seed）
- KV 峰值/日志里的 blocks 符合预期

### Step 3 — 多轮 / 24 前缀容量

按你的真实业务：24 个 128K 公共前缀 + 多轮。

记录：

```text
APC 命中率（每轮）
TTFT p50/p99
KV blocks / 容量
是否出现驱逐（num_preemptions / eviction 日志）
```

若命中率不升：先检查
`layerwise_num_shared_buffers` 是否真的设了（默认 = 层数 = 不复用）、
日志里 merged 的 M 是否小于 N。

### Step 4 — P/D 组合（Mooncake store 路径，P 开 layerwise，D 不开）

先分清两个连接器的分工，别再混：

| 连接器 | 通道 | 作用 |
| :-- | :-- | :-- |
| `AscendStoreConnector` | **Mooncake store** | layerwise offload / 前缀池；`use_layerwise` 只在 P |
| `MooncakeConnectorV1` | P↔D 直传（Mooncake 传输） | P/D KV 直传，**不走 memfabric** |
| `SfaRemoteD2HConnector` | **memfabric** | 仅用于 sparse decode offload 的 P→D 直拉，**不是 Mooncake P/D 的默认路径** |

#### 4.1 推荐：MultiConnector（MooncakeConnectorV1 直传 + AscendStoreConnector layerwise）

P：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model /path/to/GLM-5.3 \
  --tensor-parallel-size 8 \
  --enforce-eager \
  --kv-transfer-config '{
    "kv_connector": "MultiConnector",
    "kv_role": "kv_producer",
    "kv_connector_extra_config": {
      "connectors": [
        {"kv_connector": "MooncakeConnectorV1", "kv_role": "kv_producer",
         "kv_port": 20001,
         "kv_connector_extra_config": {
           "prefill": {"dp_size": 1, "tp_size": 8},
           "decode":  {"dp_size": 1, "tp_size": 8}}},
        {"kv_connector": "AscendStoreConnector", "kv_role": "kv_producer",
         "kv_connector_extra_config": {
           "backend": "mooncake",
           "lookup_rpc_port": "0",
           "use_layerwise": true,
           "layerwise_num_shared_buffers": 3,
           "layerwise_independent_layers": [0]}}
      ]
    }
  }'
```

D：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model /path/to/GLM-5.3 \
  --tensor-parallel-size 8 \
  --kv-transfer-config '{
    "kv_connector": "MultiConnector",
    "kv_role": "kv_consumer",
    "kv_connector_extra_config": {
      "connectors": [
        {"kv_connector": "MooncakeConnectorV1", "kv_role": "kv_consumer",
         "kv_port": 20002,
         "kv_connector_extra_config": {
           "prefill": {"dp_size": 1, "tp_size": 8},
           "decode":  {"dp_size": 1, "tp_size": 8}}},
        {"kv_connector": "AscendStoreConnector", "kv_role": "kv_consumer",
         "kv_connector_extra_config": {
           "backend": "mooncake",
           "lookup_rpc_port": "1",
           "use_layerwise": false}}
      ]
    }
  }'
```

要点：

- `use_layerwise` **只在 P 的 AscendStoreConnector 子项**打开；D 必须 `false`
- `lookup_rpc_port` P/D 用不同值（示例 0 / 1）
- `MooncakeConnectorV1` 的 `kv_port` P/D 也要不同（示例 20001 / 20002）
- dp/tp 按实际部署填

#### 4.2 简化：只用 AscendStoreConnector（store 中转，无直传）

P：

```json
{"kv_connector": "AscendStoreConnector", "kv_role": "kv_producer",
 "kv_connector_extra_config": {"backend": "mooncake", "lookup_rpc_port": "0",
   "use_layerwise": true, "layerwise_num_shared_buffers": 3,
   "layerwise_independent_layers": [0]}}
```

D：

```json
{"kv_connector": "AscendStoreConnector", "kv_role": "kv_consumer",
 "kv_connector_extra_config": {"backend": "mooncake", "lookup_rpc_port": "1",
   "use_layerwise": false}}
```

> 这条路径没有 P↔D 直传，KV 全部经 Mooncake store。官方 KV Pool 文档的 P/D 示例是
> 4.1 的 `MultiConnector`；4.2 更简单，但**建议先小规模验证 D 的加载行为**，
> 异常就回到 4.1。

#### 4.3 可选：sparse decode offload（MemFabric 直拉，另一条通道）

只有当你需要 **SFA 稀疏 decode offload**、并且环境有 **memfabric** 时才用这条；
它不是 Mooncake P/D 的默认配置。

P：

```json
{"kv_connector": "MultiConnector", "kv_role": "kv_producer",
 "kv_connector_extra_config": {"connectors": [
   {"kv_connector": "SfaRemoteD2HConnector", "kv_role": "kv_producer"},
   {"kv_connector": "AscendStoreConnector", "kv_role": "kv_producer",
    "kv_connector_extra_config": {"backend": "mooncake", "use_layerwise": true,
      "layerwise_num_shared_buffers": 3, "layerwise_independent_layers": [0]}}
 ]}}
```

D：

```json
{"kv_connector": "SfaRemoteD2HConnector", "kv_role": "kv_consumer", "kv_port": 20050}
```

外加：

```json
--additional-config '{"sparse_kv_offload_config": {"enabled": true, "dram_size_per_dp_GB": 110}}'
```

约束：

- `SfaRemoteD2HConnector` **只支持 memfabric**；没有 memfabric 就不要走这条
- P 的 TP ≥ D 的 TP 且可整除
- D 侧必须开 `sparse_kv_offload_config.enabled=true`；P 侧不要设
- `SfaRemoteD2HConnector` 是 v0.30.0 现成组件（`sfa_pd_rd2h/`），不是本特性新增的

### Step 5 — 失败注入 / 边界

| 场景 | 预期 |
| :-- | :-- |
| store 不可用 / put 失败 | 不推进 slot，重试；不产生半层数据 |
| partial tail（chunked prefill 最后一层） | 只作用于本请求尾部的 block |
| 复用层 overwrite 时机 | 前一个 owner 的 save-finished 之后 |
| hybrid / mamba 模型 | 启动即 `NotImplementedError`（预期） |

### Step 6 — 性能

对比 on/off（同模型、同并发、同输入）：

```text
TTFT p50/p99
吞吐（tok/s）
KV 容量 / blocks
HBM 峰值
```

注意：收益是**容量**，不是免费吞吐；TTFT 可能有几个百分点波动（文档数据 128K 约 +3.4%）。

### Step 7 — 回传结果

在 mxllm `handoff/layerwise_pd/RESULTS-*.md` 里按 `RESULTS_TEMPLATE.md` 记录：
命令、日志片段、指标、PASS/FAIL、异常。

---

## 6. 不变量与常见坑

| 坑 | 说明 |
| :-- | :-- |
| 不设 `layerwise_num_shared_buffers` | 默认 = 层数 → **完全不复用** |
| `independent_layers="all"` | 全部独立 → 不复用 |
| hybrid / mamba | 直接拒绝；不要试图绕过 |
| 图模式 | layerwise 需要 **eager**；`requires_piecewise_for_cudagraph` 会把 FULL 降为 PIECEWISE |
| KVPP + Mooncake layerwise | 不启用跨层复用；且要求 `load_async=false` |
| DCP + KVPP | 互斥（KVPP 不支持 DCP） |
| Mooncake 存储池 | **不省**容量；省的是本地 KV buffer |
| 只改 descriptor | 不改 `num_blocks`；要容量变大需调预算 |
| decode 无 LOAD/SAVE 日志 | 先查 key 绑定与 load 顺序，不要先怀疑 attention 路径（003 §22.6/§23） |

---

## 7. 验收标准（Checklist）

- [ ] `pytest tests/ut/distributed/ascend_store -q` 全绿（v0.30.0：881 passed）
- [ ] handoff T00 / T00b 全过
- [ ] 启动日志出现 `Layerwise KV cache reuse merged ...`，且 M < N
- [ ] GLM-5.3 descriptor 数 = 4（N=3 + 独立 1）
- [ ] 128K 单请求输出与关闭 layerwise 一致
- [ ] 24 前缀多轮命中率/TTFT 有记录
- [ ] P/D：D 能加载 P 的 KV，输出一致
- [ ] 失败注入不产生半层/脏 KV
- [ ] RESULTS 文档回传

---

## 8. 问题定位速查

| 现象 | 先查 |
| :-- | :-- |
| 没有 merged 日志 | `use_layerwise`、`layerwise_num_shared_buffers`、是否 hybrid |
| merged 了但 M == N | 独立层配置成 all / 只有一个桶 |
| 显存没降 | 看的是 Mooncake 池还是本地 buffer；`num_blocks` 是否重算 |
| decode 输出错 | load 顺序、key 绑定、slot 覆盖 fence |
| P/D D 侧无命中 | D 的 `sparse_kv_offload` 是否开；P 的 MultiConnector 角色 |
| 启动 OOM | `layerwise_num_shared_buffers` 太大或预算没调 |

---

## 9. 参考

- [003 设计与本地验证](003-layerwise-KV-buffer复用.md)（§11 收益、§12 P/D 边界、§15 P0–P5、§23 hook 修复、§24 v0.30.0 移植）
- [handoff 包](https://gitcode.com/yeshenye19992/mxllm/tree/layerwise/shared-buffer-v030/handoff/layerwise_pd)
- [v0.30.0 特性分支](https://github.com/sunlei1992/vllm-ascend/tree/layerwise/v030-ascend-store)
- 历史 upstream 分支：`feature/mooncake-layerwise-reuse`（`8237ee6d6`，4 提交）
