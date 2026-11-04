# 003 — layerwise KV buffer 复用（block-key / Mooncake 数据面）

> 日期：2026-10-26
> 分支：`feature/mooncake-layerwise-reuse`（基于 `8237ee6d6`，4 个提交，已推送到
> `git@github.com:sunlei1992/vllm-ascend.git`）
> 上游相关：[vllm-ascend#12852](https://github.com/vllm-project/vllm-ascend/pull/12852)
> （`[Feature][KV Offload] Add layerwise prefill KV buffer reuse`）
> 状态：个人验证阶段，**暂不提交社区**

---

## 1. 背景：layerwise offload 与 buffer 复用

Layerwise KV offload 的做法是**逐层**搬运：

```
第 L 层算完 → D2H 存到 host/远端
下一轮第 L 层算之前 → H2D 取回
```

这样只需要少量 staging buffer 就能省 HBM，但**每层都要一个物理 buffer**，
层数一多，buffer 总量又上去了。

**buffer 复用**的思路：用一条 prefetch 链把"刚 save 完的层"直接交给
"即将 load 的层"使用，物理 buffer 数从 `N`（逻辑层数）降到：

```
I + min(B, R)
```

- `I`：必须独占的层（有依赖关系，不能覆盖）
- `B`：用户配置的共享 buffer 数（`layerwise_num_shared_buffers`）
- `R`：可复用的层数

`prefetch_layer_map`（owner → predecessor）描述"哪一层的 buffer 可以被哪一层接手"。
复用层在加载时必须**重新读取完整的 cached prefix**（因为 buffer 内容已经被覆盖），
不能只补缺失后缀。

## 2. 两个数据面

vllm-ascend 的 KV store 有两套数据面，协议模块上用常量区分：

| 数据面 | 常量 | 后端 | 存储粒度 |
| :-- | :-- | :-- | :-- |
| GVA | `LAYERWISE_DATA_PLANE = "gva"` | memcache | 每个 block 一个 region，内含所有层的 offset |
| block-key | `LAYERWISE_DATA_PLANE = "block_key"` | mooncake（AscendStore） | **每层一个 object key**（`...@layer_id:...`） |

代码位置：

- `ascend_store/backend/memcache_backend.py:83` → `"gva"`
- `ascend_store/backend/mooncake_layerwise.py:27` → `"block_key"`
- `ascend_store/backend/__init__.py:54` → `get_layerwise_data_plane()`

GVA 用 `batch_alloc` / `batch_get_key_info` / lease 管理 region；
block-key 用 session API：

```
batch_put_session_start / batch_put_from_multi_buffer_ranges
batch_put_session_end   / batch_put_session_revoke
batch_get_session_start / batch_get_into_multi_buffer_ranges
batch_get_session_end
```

在 `backend/mooncake_backend.py` 里通过 `_call_layerwise_batch(...)` 转发。

## 3. 缺口：block-key 没有复用

上游 #12852 的复用逻辑挂在 GVA 数据面的 protocol 上：

```python
# 只有返回配置，worker 才会去规划复用
layout = get_layerwise_reuse_config(kv_transfer_config)
```

而 block-key 的 protocol（`mooncake_layerwise.py`）当时**没有返回复用配置**，
所以即使配了 `layerwise_num_shared_buffers`，block-key 也永远走"每层一个 buffer"。

结果是：**Mooncake 后端能跑 layerwise offload，但拿不到复用带来的显存收益。**

## 4. 实现：4 个提交

| commit | 类型 | 改动 |
| :-- | :-- | :-- |
| `2148087ce` | fix | reload shared buffers on the block-key plane（复用层加载完整 prefix） |
| `b56582775` | fix | partial tail key 按 **end token** 作用域 |
| `4e2042140` | feat | planner：在 block-key 上规划复用（scheduler + worker） |
| `13d80c908` | feat | backend opt-in：Mooncake 返回复用配置，打开共享 buffer |

改动规模：

```
2148087ce  pool_worker.py +23/-3,   test_mooncake_layerwise.py +80
b56582775  pool_worker.py +10/-2,   test_mooncake_layerwise.py +31
4e2042140  pool_scheduler.py +51/-34, pool_worker.py +70/-34,
           test_pool_scheduler.py +62, test_pool_worker.py +78
13d80c908  mooncake_layerwise.py +13/-2, test_layerwise_cache_layout.py +35/-…
           + 两篇文档
```

### 4.1 `2148087ce` 复用层必须重载完整 prefix

复用 buffer 的内容已被前一层覆盖，所以加载时不能沿用"只取缺失后缀"的优化，
必须把该请求的**完整 cached prefix** 重新读一遍。

### 4.2 `b56582775` partial tail 的作用域

partial block 的 key 里带长度：

```
{req_id}@{target_token_len}_lastblock     # put
{req_id}@{cached_tokens}_lastblock        # get
```

如果按"起始 token"去匹配，chunked prefill 下会命中错误的块；
改成按 **end token** 作用域后，读写两侧才对得上。

### 4.3 `4e2042140` planner：`prefetch_layer_map`

```python
layout = build_layerwise_reuse_layout(...)   # layerwise_cache_layout.py:249
has_layer_reuse = bool(prefetch_layer_map)   # :332
```

- worker 侧：`_layerwise_reuse_config` / `_validate_layerwise_reuse_layout` /
  `_apply_layerwise_reuse_layout` / `_remap_layout_to_stage_local`
- scheduler 侧：`_layerwise_reuse_config`，并在构造 `ReqMeta` 时携带复用布局

### 4.4 `13d80c908` 后端打开复用

```python
# mooncake_layerwise.py extract_layout_config()
# 当 use_layerwise 时返回布局配置（含 layerwise_num_shared_buffers）
```

## 5. 约束（先看这里，不然会踩坑）

| 约束 | 行为 |
| :-- | :-- |
| hybrid / Mamba / **multi-group** | `NotImplementedError`，直接拒绝 |
| KV group 数 | 只支持**单个** KV group |
| 执行模式 | 必须 **eager**（不支持 graph） |
| `layerwise_num_shared_buffers` | 是 **per-main-cache-spec bucket** 的预算，不是全局 |
| `requires_exists_before_put` | Mooncake 为 `True`（先 exists 再 put）；yuanrong 覆盖为 `False` |

另外：**不要把 block-key store 的复用和 p2p PD connector 混用**。
`AscendStoreConnector.set_external_slot_release_waiter` 在 block-key 下返回 `False`
（`if not self.use_layerwise_transfer`），而 `MooncakeLayerwiseConnectorWorker.wait_for_layer_load`
是 no-op，两者语义对不上。

## 6. 测试

```bash
./tmp/run-ascend-ut.sh tests/ut/distributed/ascend_store -q
# macOS: 761 passed, 12 skipped, 420 subtests
ruff check 通过
```

**Linux 容器（无 NPU）复跑**（2026-10-26）：

```text
761 passed, 12 skipped, 14 warnings, 420 subtests passed in 13.57s
```

与 macOS 结果逐项一致，说明这套 UT 不依赖平台/NPU。

按提交逐个 checkout 也跑过：

| commit | 结果 |
| :-- | :-- |
| `2148087ce` | 142 passed |
| `b56582775` | 143 passed |
| `4e2042140` | 760 passed |
| `13d80c908` | 761 passed |

新增测试：

- `tests/ut/distributed/ascend_store/test_pool_worker.py::TestBlockKeyLayerwiseReuse`
  - 未 opt-in 时不开复用
  - opt-in 后复用生效
  - multi-group 被拒绝
  - 复用层加载完整 prefix
- `tests/ut/distributed/ascend_store/test_pool_scheduler.py::TestBlockKeyLayerwiseReuse`
- `test_mooncake_layerwise.py`：load range、partial key、shared buffer 重载

## 7. 未验证 / 风险

| 项 | 状态 |
| :-- | :-- |
| NPU 实机 e2e | ❌ 本地无 NPU，只跑了 UT |
| 平台无关性 | ✅ Linux 容器复跑 761 passed（与 macOS 一致） |
| 同步 `put()` 的可见性 | ⚠️ 未在真实 store 上验证 |
| 真实时序 / 死锁 | ⚠️ 双线程 + per-layer Event 的时序只在 mock 下验证 |
| HBM 实际节省 | ⚠️ 未测量 |
| token-level parity | ⚠️ 未做 |
| **Signed-off-by** | ✅ 已修（2026-10-26）：`sl <sunclouddev@163.com>`，4 个 commit 已改写并 force push |

## 8. 代码地图

| 文件 | 作用 |
| :-- | :-- |
| `ascend_store/layerwise_cache_layout.py` | 规划器：`build_layerwise_cache_layout` / `build_layerwise_reuse_layout` / `get_layerwise_reuse_config` |
| `ascend_store/pool_worker.py` | worker 侧：复用配置、布局校验、按层加载/保存、session |
| `ascend_store/pool_scheduler.py` | scheduler 侧：复用开关、`ReqMeta`、partial block 策略 |
| `ascend_store/backend/mooncake_layerwise.py` | block-key protocol：数据面常量、`extract_layout_config` |
| `ascend_store/backend/memcache_backend.py` | GVA protocol：数据面常量 |
| `ascend_store/backend/mooncake_backend.py` | session API 转发（`_call_layerwise_batch`） |
| `ascend_store/backend/__init__.py` | `get_layerwise_protocol` / `get_layerwise_data_plane` |
| `ascend_store/backend/layerwise_keys.py` | key 生成（含 pp stage / rank 枚举） |

## 9. 与其它工作的关系

| 工作 | 关系 |
| :-- | :-- |
| 上游 #12852 | 本工作的基础；复用逻辑原本只在 GVA |
| #14046（`supports_layerwise_buffer_reuse`） | 另一条线：给 connector 提供 **per-physical-slot** 的复用 gate，不负责规划 |
| p2p PD connector | **不要混用**（见第 5 节） |

## 10. 推送信息

```
fork:   git@github.com:sunlei1992/vllm-ascend.git
branch: feature/mooncake-layerwise-reuse
head:   13d80c908
```

---

## 8. 完成度与 GLM-5.3 验证（2026-10-28 追加）

### 8.1 完成度

| 项 | 状态 |
| :-- | :-- |
| 功能实现（block-key 平面复用） | ✅ 4 个提交 |
| 单测 | ✅ `ascend_store` 761 passed / 12 skipped（macOS + Linux 一致） |
| 布局单测 | ✅ 41 passed（含新增 GLM-5.3 形状用例） |
| **GLM-5.3 形状验证** | ✅ 本地合成验证通过（见 8.2） |
| NPU 实机 e2e | ❌ 未做 |
| 真实 Mooncake 服务联调 | ❌ 未做 |
| hybrid / 多 group | ❌ 设计上不支持（`NotImplementedError`） |
| release note / 社区 PR | ❌ 暂不需要 |

**结论：功能开发完成，单测完备；缺的是真机数据面验证。**

### 8.2 GLM-5.3 形状验证（本地合成）

构造 78 层、每层两个 spec 的 `UniformTypeKVCacheSpecs`：

```python
main    = AscendMLAAttentionSpec(block_size=32, head_size=576, dtype=bf16)
indexer = AscendSFAIndexerCacheSpec(block_size=32, head_size=192, dtype=uint8, scale_dim=4)
```

结果：

```text
logical cache specs: 156        # 78 主 MLA + 78 indexer
has_layer_reuse: True
buffer_slots: 3                 # 1 independent + 2 shared
slot sizes: [1, 39, 38]
prefetch entries: 75
physical layers: 78  with indexer: 78
uses_hybrid_kv_cache(...) = False
```

- `AscendSFAIndexerCacheSpec` 的文档明确：indexer "share block ids with the MLA cache in
  the same UniformType group" → **GLM-5.3 是单 group**
- 单 group ⇒ `block_key_hybrid=False` ⇒ `_validate_layerwise_reuse_layout` **不会**抛
  `NotImplementedError`
- 78 层 → 3 个物理 buffer，复用生效

新增单测 `test_glm53_sfa_indexer_layers_get_reuse`（VA 提交 `8eb74f2c7`，分支
`local/simulated-ascend-store`）。

### 8.3 真机验证步骤（建议）

1. **backend 用 `mooncake`（block-key 平面）**——我们改的复用只在 block-key 生效；
   `memcache` 是 GVA 平面，复用来自上游 #12852。
2. 参数：

```json
{
  "kv_connector": "AscendStoreConnector",
  "kv_role": "kv_both",
  "kv_connector_extra_config": {
    "backend": "mooncake",
    "use_layerwise": true,
    "layerwise_num_shared_buffers": 2,
    "layerwise_prefetch_layers": 2
  }
}
```

3. 启动后确认三件事：
   - `kv cache group sizes` 只有一组
   - 没有 `NotImplementedError`（复用布局被接受）
   - slot 数 = 1 independent + N shared（远小于 78）
4. 用 140K × 24 前缀 workload 对比 on/off：HBM 峰值、TTFT、Mooncake 读写带宽。

### 8.4 剩余风险

| 风险 | 说明 |
| :-- | :-- |
| indexer 数据面 | 布局支持，但 indexer 的字节/偏移在真机搬运未验证 |
| MTP 额外层 | 若开 MTP，`model.mtp.*` 也要经过 `get_layerwise_physical_layer_index` 映射 |
| 带宽 | 复用层加载要重读完整 prefix，流量比不复用高 |
| 双平面 | memcache(GVA) 与 mooncake(block-key) 的复用行为不同，别混用 |

### 8.5 indexer 数据面：代码分析结论（2026-10-28）

"风险集中在 indexer 数据面"这句话可以进一步收敛。逐层追代码后：

**结论：layerwise 路径确实搬 indexer，而且按物理层 offset 分组，GLM-5.3 的形状是对的。**

| 环节 | 代码 | 结论 |
| :-- | :-- | :-- |
| 布局配对 | `_INDEXER_CACHE_SUFFIX = ".indexer.k_cache"` | indexer 与主 MLA 归到同一物理层 |
| buffer 合并 | `_merge_specs(indexer_specs, indexer=True)` | indexer 单独一个 merged tensor，容量取 `max` |
| 层元数据 | `_infer_cache_group_metadata` 按物理层分组 | `group_num_layers` = 物理层数（78），不是 156 |
| 地址计算 | `LayerBatchBuilder._build_transfer_arrays` | 用 `group_layer_cache_entry_offsets` 的 per-layer 区间 + 内偏移 |
| 键 | `make_block_key` + `KeyMetadata.layer_id` | 每层一个 object，主 MLA 与 indexer 用字节偏移区分 |

**真正残留的三个点**（不是"没搬"，而是边界条件）：

| 风险 | 触发条件 | 影响 |
| :-- | :-- | :-- |
| merged indexer 容量取 `max` | 同一 slot 内 indexer 的 page size 不同 | 小 page 的层会多搬/多写 `max - own` 字节 |
| 非 layerwise 路径的均分假设 | 走 `KVCacheStoreKeyLayerSendingThread`（非 layerwise）时，`prepare_value_layer` 用 `entries_per_layer = entries // num_layers` | 若某些层没有 indexer（entry 数不齐），`layer_id * entries_per_layer` 会错位 |
| indexer 的字节布局 | uint8 + scale（`AscendSFAIndexerCacheSpec.real_page_size_bytes`） | 真机未验证 scale 区与主 MLA 的偏移是否完全对齐 |

**GLM-5.3 为什么大概率安全**：每一层都有 indexer（DSA 在全部注意力层启用），
所以每层 entry 数恒为 2，均分假设成立；且所有层的 indexer spec 相同，`max` 等于自身。

**真机验证的快捷方式**：`_build_transfer_arrays` 有 DEBUG 日志，打开后看：

```text
[KVPOOL] build_transfer layer=L page_size=... caches_per_layer=2
         layer_block_len=[<main_bytes>, <indexer_bytes>] layer_inner_offsets=[0, <main_bytes>]
```

`caches_per_layer=2` 且 `layer_inner_offsets` 等于 `[0, main_bytes]`，就说明主 MLA 和 indexer 都进了同一次传输。

已存在的相关单测（覆盖容量合并）：

- `test_mixed_indexers_share_max_capacity_without_changing_reuse_order`
- `test_reuse_rebuilds_generic_indexer_descriptors_with_physical_capacity`
- `test_reuse_rejects_unknown_indexer_stride`

### 8.6 本机实测：地址/字节这一层已验证（2026-10-28）

用 GLM-5.3 形状（每层主 MLA 8192 B + indexer 1024 B，共 2 层）直接跑 `LayerBatchBuilder`：

```text
== A: 每层都有 main+indexer ==
layer0: addr=[50960, 25120]  size=[8192, 1024]  gva=[1000, 9192]
layer1: addr=[70960, 45120]  size=[8192, 1024]  gva=[10216, 18408]
```

- 地址 = `base + block_id × stride`，主 MLA 与 indexer 各用各的 stride ✅
- `gva` 内偏移 = `[0, 8192]`，说明**两块打包在同一次传输里**，indexer 紧跟主 MLA ✅
- layer1 的 `gva` 基址 = `500+9216`，按层累加 ✅

```text
== B: layer1 没有 indexer（非均匀）==
layer0: addr=[50960, 25120] size=[8192, 1024]
layer1: addr=[70960]        size=[8192]
```

layerwise 路径用 per-layer offset，非均匀也能正确处理 ✅

```text
== C: 非 layerwise 的 prepare_value_layer（均分假设）==
layer0: addr=[50960] size=[8192]
layer1: addr=[25120] size=[1024]   ← 错！取到了 layer0 的 indexer
```

**证实了 8.5 里的第二个风险**：非 layerwise 路径在"各层 entry 数不齐"时会错位。
GLM-5.3 每层都有 indexer（entry 数恒为 2），所以不触发：

```text
== C2: 非 layerwise + 均匀 ==
layer0: addr=[50960, 25120] size=[8192, 1024]  ✅
layer1: addr=[70960, 45120] size=[8192, 1024]  ✅
```

已固化为单测（VA `4df67b2a6`）：

- `test_indexer_entry_is_packed_after_main_for_every_layer`
- 既有的 `test_uses_real_offsets_for_variable_cache_entries_per_layer` 覆盖非均匀

### 8.7 本机能验证 / 不能验证的边界

| 能（纯 Python/NumPy） | 不能（需要 NPU / Mooncake） |
| :-- | :-- |
| 传输地址、字节数、内偏移 | 真实 RDMA/UCX 搬运 |
| 每层 entry 打包顺序 | 零拷贝内存注册是否成功 |
| 非均匀 indexer 的 offset 处理 | NPU kernel 读回 indexer 是否正确（输出正确性） |
| 容量合并（max）后的描述符 | 实际带宽、TTFT/TPOT |

## 11. HBM 节省估算（2026-10-29 追加）

### 11.1 收益从哪来

`apply_layerwise_kv_cache_plan()`（`layerwise_cache_layout.py`）会重写
`kv_cache_config.kv_cache_tensors`：

- **共享槽位**：多个层共用一个 descriptor（`layer_stride=0`）
- **独立层**：各占一个 descriptor
- 函数**只改 descriptor，不改 `num_blocks`**

它是否生效，取决于 `get_layerwise_reuse_config()` → 后端协议的 `extract_layout_config()`。
我们的提交 `13d80c908` 把 Mooncake（block-key）从 `return None` 改成 opt-in。

UT `test_block_key_backend_merges_shared_slots` 直接证明：

```text
4 层 + layerwise_num_shared_buffers=1
→ 2 个 descriptor（1 独立 + 3 共享）
```

### 11.2 公式

```
槽位数 S = layerwise_num_shared_buffers + len(layerwise_independent_layers)
节省比例 = 1 − S / L            （L = 有缓存的层数）
同预算容量倍数 = L / S
```

### 11.3 GLM-5.3（L = 78，独立层默认 [0]）

| `num_shared_buffers` | 槽位 S | 节省比例 | 容量倍数 |
| :-- | :-- | :-- | :-- |
| 1 | 2 | **97.4%** | 39× |
| 2 | 3 | 96.2% | 26× |
| **3**（文档示例） | **4** | **94.9%** | **19.5×** |
| 4 | 5 | 93.6% | 15.6× |
| 8 | 9 | 88.5% | 8.7× |
| 16 | 17 | 78.2% | 4.6× |
| 不设（默认 = 78） | 79 | 0% | 1× |

### 11.4 140K 输入的绝对量

GLM-5.3 每层每 token：`(kv_lora_rank 512 + qk_rope 64) × 2 B = 1,152 B`

```
单层 140K = 140,000 × 1,152 B ≈ 154 MiB
78 层合计 ≈ 12.0 GiB / 请求
```

| 配置 | 140K 请求 KV 足迹 | 节省 |
| :-- | :-- | :-- |
| 不复用 | 12.0 GiB | — |
| N=3（4 槽） | **615 MiB** | **−11.4 GiB（94.9%）** |
| N=8（9 槽） | 1.35 GiB | −10.6 GiB（88.5%） |

同样 8 GiB 的 KV 预算：

| 配置 | 可容纳的 140K KV |
| :-- | :-- |
| 不复用 | 0.67 条 |
| N=3 | **13 条** |
| N=8 | 5.9 条 |

### 11.5 两个口径

| 口径 | 结果 |
| :-- | :-- |
| `num_blocks` 不变 | HBM 占用降到 `S/L`（N=3 时 5.1%），剩余 HBM 释放 |
| 预算重新调大 | 容量变 `L/S` 倍（N=3 时 19.5×） |

因为该函数不改 `num_blocks`，默认看到的是"**占用变少**"；
要变成"**容量变大**"，需同步调大 `--kv-cache-memory-bytes` / `gpu_memory_utilization`。

### 11.6 不节省的部分

| 项 | 是否节省 |
| :-- | :-- |
| 本地 KV 缓冲（prefill offload 的 staging KV） | ✅ 主要收益 |
| **Mooncake 存储池** | ❌ 每层 KV 仍要全存 |
| 权重、激活 | ❌ |
| MTP/draft 层 | ❌ 单独占 descriptor（代码显式排除） |
| 多 group / hybrid / mamba | ❌ 当前不支持复用 |

### 11.7 怎么验证收益

启动日志应出现：

```text
Layerwise KV cache reuse merged N descriptors into M descriptors using K buffer assignments.
```

| 现象 | 结论 |
| :-- | :-- |
| 有 merged 且 M < N | ✅ 复用生效，显存确实降了 |
| 没有这行 | ❌ 没进复用（多半没设 `layerwise_num_shared_buffers`） |
| `NotImplementedError`（hybrid/mamba） | ❌ 布局不支持 |

### 11.8 澄清："不是 GVA，所以拿不到收益"？

这个说法**部分对**：

| 说法 | 判断 |
| :-- | :-- |
| block-key 不是 GVA 平面 | ✅ 对（fence 机制不同：GVA 用显式完成门控，block-key 用 save-finished 事件） |
| 能跑 layerwise offload | ✅ 对 |
| 拿不到复用收益 | ❌ 不准确 |

真正拿不到收益的常见原因：

1. **没显式设置 `layerwise_num_shared_buffers`** —— 默认等于层数，等于不复用（最可能）
2. 把"Mooncake 存储容量"和"本地 KV 缓冲"混为一谈 —— store 侧确实不省
3. 用了 hybrid / mamba / 多 group 布局 —— 代码直接拒绝复用
4. 用了 MTP/draft 层 —— 这些层被排除在复用外


## 12. 图模式与 P/D 边界（2026-11-03 追加）

### 12.1 layerwise 不能用 FULL 图，但也不是"不能开图"

`AscendStoreConnector` 声明了自己的图模式要求：

```python
@classmethod
def requires_piecewise_for_cudagraph(cls, extra_config):
    """AscendStore requires PIECEWISE CUDA graph mode when layerwise
    operations are enabled."""
    return extra_config.get("use_layerwise", False)
```

vLLM 的 `VllmConfig` 会读这个类方法，**自动把 `cudagraph_mode` 从 FULL 降成 PIECEWISE**
（v0.30.0 与 main 都有，`vllm/config/vllm.py`），并打 warning：

```text
KV connector AscendStoreConnector requires PIECEWISE CUDA graph mode
due to layerwise async operations that cannot be captured in CUDA graphs.
Overriding cudagraph_mode from FULL to PIECEWISE.
```

原因是 layerwise 的 save/load 是**层边界上的 host↔device 异步拷贝**，FULL graph
把整个 forward 捕获成一张图，层间没有插入点；PIECEWISE 在 attention/MLA 边界断图才能插。

另外 VA 文档更保守（`layerwise_and_sparse_kv_cache_offloading.md`）：

> Shared-buffer Layerwise Prefill Offload **requires eager mode** and either the
> Memcache backend (GVA plane) or the Mooncake backend (block-key plane).

示例命令也是 `--enforce-eager`。

| 图模式 | 是否可用 | 说明 |
| :-- | :-- | :-- |
| FULL | ❌ | 自动降级 |
| PIECEWISE | ⚠️ | 上游只保证降级，VA 文档未覆盖组合 |
| **eager（`--enforce-eager`）** | ✅ | 文档推荐，最稳 |

对 P 节点代价很小：prefill 是动态 shape，图本来收益就小。

### 12.2 `use_layerwise` 只在 P 节点支持

VA 0.30 的 `kv_cache_pool_ascend_store.md` 写得很直接：

> `use_layerwise` only supported on the **Prefill node** of the Mooncake/Memcache backends.

> it is only supported on the Prefill node.

所以"P 开 layerwise、D 不开"不是 hack，而是**官方形态**。官方组合是：

| 节点 | 连接器 | offload |
| :-- | :-- | :-- |
| **P** | `MultiConnector` = `SfaRemoteD2HConnector`(producer) + `AscendStoreConnector`(producer, `use_layerwise`) | layerwise → memcache（省 HBM） |
| **D** | `SfaRemoteD2HConnector`(consumer) | sparse decode offload（CPU pool） |

### 12.3 P 开 D 不开时，KV 到底怎么传

**不是 P 推给 D，而是 D 来拉。** 代码注释（`sfa_pd_rd2h/worker.py`）：

> It registers P's local KV tensors with memfabric and runs a pull-mode sending thread.
> **P never pushes KV**; it sends READ_READY_BATCH messages so D can read P's source blocks
> and reply with READ_DONE / READ_FAILED.

时序：

```text
P: 算完 layer 0 → save 到 memcache ─┐
   └→ 发 READ_READY(layer 0) ───────┼→ D: RDMA 读 layer 0 → READ_DONE
P: 算完 layer 1 → save 到 memcache ─┤
   └→ 发 READ_READY(layer 1) ───────┼→ D: RDMA 读 layer 1 → READ_DONE
...                                （D 边拉边填 CPU pool，不等 P 全算完）
```

D 侧（`connector.py` 头注释）：

> On the Decode node (kv_consumer), remote Prefill exposes its KV and Decode pulls the bulk MLA
> KV directly into a CPU pinned offload pool; the indexer KV lands in HBM. The CPU pool and
> sparse resident-cache load path are owned by `SparseKVOffloadManager`.

**关键：D 不能"什么都不开"**，构造时有硬断言：

```python
if self.is_producer:   # P
    assert not decode_offload_enabled, \
        "SfaRemoteD2HConnector producer (P) must run with sparse_kv_offload_config.enabled=false."
if self.is_consumer:   # D
    assert decode_offload_enabled, \
        "SfaRemoteD2HConnector consumer (D) must run with sparse_kv_offload_config.enabled=true."
```

| 节点 | `sparse_kv_offload_config` |
| :-- | :-- |
| P | 必须**关闭** |
| D | 必须**开启** |

### 12.4 两个"layerwise"不要混

| 名称 | 在哪 | 含义 |
| :-- | :-- | :-- |
| `AscendStoreConnector.use_layerwise` | **只有 P** | KV buffer 复用（本笔记的特性） |
| D2H connector 的 layer-wise | P 和 D | **传输粒度**逐层（`SfaRemoteD2HConnector` 默认 `use_layerwise=True`） |

### 12.5 配置与约束

P：

```bash
--enforce-eager \
--kv-transfer-config '{
  "kv_connector": "MultiConnector",
  "kv_role": "kv_producer",
  "kv_connector_extra_config": {
    "connectors": [
      {"kv_connector": "SfaRemoteD2HConnector", "kv_role": "kv_producer"},
      {"kv_connector": "AscendStoreConnector", "kv_role": "kv_producer",
       "kv_connector_extra_config": {
         "backend": "memcache",
         "use_layerwise": true,
         "layerwise_num_shared_buffers": 3,
         "layerwise_independent_layers": [0]
       }}
    ]
  }
}'
```

D（不开 buffer 复用，但必须开 sparse offload）：

```bash
--additional-config '{
  "sparse_kv_offload_config": {"enabled": true, "dram_size_per_dp_GB": 110}
}' \
--kv-transfer-config '{
  "kv_connector": "SfaRemoteD2HConnector",
  "kv_role": "kv_consumer",
  "kv_port": 20050
}'
```

| 约束 | 值 |
| :-- | :-- |
| 连接器 | 两端必须 `SfaRemoteD2HConnector`（P 侧包在 `MultiConnector` 里） |
| TP 关系 | P 的 TP ≥ D 的 TP，且能被整除 |
| 端口 | D 从 `kv_port` 起预留 `DP×TP` 个连续端口 |
| D 主机内存 | `dram_size_per_dp_GB`（默认 110 GiB/DP）要能装下完整 KV；TP 共享、DP 独立 |
| proxy | 必须用 **layerwise 专用 proxy**（`load_balance_proxy_layerwise_server_example.py`） |
| 硬件 | Sparse Decode Offload 当前**不支持 950PR&950DT**（文档明确） |

### 12.6 对我们的意义

```
P：layerwise（eager）→ 省 HBM、保 TTFT
D：sparse offload + FULL graph → 保 TPOT
```

正好对应 128K/24 前缀场景的两条痛点。风险：

1. P 的 layerwise 与 D 的 sparse offload 是**两套 host pool**，容量要分别算；
2. 950PR&950DT 上 sparse decode offload 还没支持，D 侧方案要等；
3. 必须用 layerwise proxy，普通 P/D proxy 不通。

## 13. 950DT 对“layerwise buffer reuse”的支持边界（2026-11-03）

社区里有说法“华为 950DT 不支持 layerwise”。这个说法**太宽泛**，需要把三个概念拆开：

| 概念 | 位置 | 950DT |
| :-- | :-- | :-- |
| `AscendStoreConnector.use_layerwise`：Prefill 逐层 KV offload / shared-buffer 复用（本笔记特性） | **只有 P** | 官方没有明确禁止；但 Prefill 部署文档目前只给 A3，950DT 属于**未文档化/未认证** |
| Sparse Decode Offload：D 侧稀疏 KV 卸载 | **只有 D** | **官方明确不支持 950PR&950DT** |
| `SfaRemoteD2HConnector` 的 layerwise：P/D 逐层传输粒度 | P 和 D | 与 buffer 复用不是同一件事；受 TP/CP/PP 约束 |

关键文档原文：

- `kv_cache_pool_ascend_store.md`：硬件支持 **A2/A3/950PR&950DT**；通用 KV pool 的 `use_layerwise` 仅在 **Prefill** 节点支持。最新 main 的 shared-buffer 文档进一步要求 **Memcache**（见 §14）。
- `layerwise_and_sparse_kv_cache_offloading.md`：最新 main 写的是 **shared-buffer Layerwise Prefill Offload requires Memcache and eager mode**；**Sparse Decode Offload is currently not supported on 950PR&950DT Products**。Mooncake 的 layerwise 属于 KVPP pooling，不做跨层 shared-buffer 复用。
- 同一篇文档的 Prefill 准备只有 **A3 series** 页面，没有 950DT 步骤，因此 950DT 的 Prefill layerwise 属于“有代码路径、未官方认证”。

对 GLM-5.3 的局部结论：

- 78 层、主 MLA + `AscendSFAIndexerCacheSpec`、单 UniformType group、无 hybrid；
- 78 个物理层全部配对 indexer，`buffer_slots=3`（1 独立 + 2 共享）的复用布局已在本地 UT 验证；
- 但**缺 950DT 真机的 indexer 数据面验证**。

所以准确表述是：

> 950DT 明确不支持的是 **Decode 的 Sparse KV Offload**；
> **Prefill 的 layerwise shared-buffer reuse** 在 950DT 上不是“文档明确支持”，也不是“硬件明确不支持”，而是“未认证，需要按 connector + 模型 + 拓扑做真机验证”。

验证时注意：

1. 只在 P 开 `use_layerwise=true`，D 保持 `false`；
2. 必须 `--enforce-eager`；
3. 用 **Memcache** backend（shared-buffer）；若测 KVPP layerwise pooling 才用 Mooncake，但它不做跨层 buffer 复用；
4. 若还要 P→D layerwise transfer，官方要求 `SfaRemoteD2HConnector`，不是普通 `MooncakeConnectorV1`；
5. 启动日志确认 `Layerwise KV cache reuse merged ...`；
6. 对比开启前后 HBM 占用 / KV blocks / 输出一致性；失败时区分是 Mooncake API、layout/TP 约束，还是平台能力检查。


## 14. 最新 main 复核（2026-11-03）

复核对象：`vllm-ascend` `origin/main` = `1bf75989c`（本地 fetch 后的最新）。

### 14.1 关键结论：核心限制没有解除，但 shared-buffer 的 backend 要求收紧了

最新 `layerwise_and_sparse_kv_cache_offloading.md` 已把 Prefill 要求改成：

```text
Shared-buffer Layerwise Prefill Offload requires Memcache and eager mode.
```

不再是旧文档里的 “Memcache 或 Mooncake”。
Mooncake 的 `use_layerwise` 现在对应 **KVPP Mooncake layerwise pooling**，文档明确说它 **does not enable cross-layer reuse of persistent owner caches**，和 `layerwise_num_shared_buffers` 的 shared-buffer 复用不是同一个特性。

### 14.2 Sparse Decode Offload 仍然是 950DT 的硬限制

最新代码 `vllm_ascend/ascend_config.py` 增加了：

```python
if is_950():
    raise ValueError("Sparse KV offload is not supported on 950PR&950DT Products")
```

所以不只是文档，代码也会直接拒绝。`SfaRemoteD2HConnector` 的 D 侧仍然要求：

```text
sparse_kv_offload_config.enabled=true
```

因此 “P 开 layerwise shared buffer + D 用 SfaRemoteD2H consumer” 在 950DT 上仍然走不通。

### 14.3 最近的相关合入

| Commit | 内容 | 对我们的意义 |
| :-- | :-- | :-- |
| `74dfd48b0` | `[Doc][main] Update sparse kv offload docs` | shared-buffer 改为 **Memcache + eager**；新增 `is_950()` 拒绝 sparse offload |
| `2f285ddcc` | `Preserve GLM shared slots with layerwise KV transfer` | GLM-5.3-Flash 用 Memcache `use_layerwise=true`、`kv_both`、`--enforce-eager` 跑通；未声明 950DT |
| `23e0e3764` | `Support PCP for Mooncake layerwise pooling` | KVPP / Mooncake layerwise pooling 增强；不是 shared-buffer |
| `9d2f25815` | `Split AscendStore layerwise pool worker and scheduler` | layerwise 代码重构，路径变为 `kv_pool/ascend_store/layerwise/...` |
| `1bebfa67c` | `Wait for layerwise KV loads on all MLA paths` | 修 MLA layerwise load 同步；对 P 侧稳定性有帮助 |
| `1985de9f4` | `Add decode offloading to Mooncake Store consumers` | Mooncake consumer decode offload；不等于 950DT sparse offload 支持 |

### 14.4 对 950DT 的最终判断（更新版）

- **P 节点 shared-buffer reuse**：最新 main 要求 **Memcache + eager**；950DT 没有明确被禁止，但仍缺 950DT 真机验证。
- **Mooncake 上做 shared-buffer reuse**：最新文档不支持；Mooncake 只做 KVPP layerwise pooling，不做跨层复用。
- **P/D 完整链路**：D 仍必须 `SfaRemoteD2HConnector` + sparse offload；而 sparse offload 在 950DT 上被代码拒绝，所以 **完整 P/D 仍不可用**。
- **P-only 验证**：可以用 Memcache + `use_layerwise=true` + `layerwise_num_shared_buffers=3` + eager 做 HBM 降低验证；这不是完整 P/D 服务。
- **替代方案**：KVPP Mooncake layerwise pooling 在 950DT 上有文档支持，但它是 layer-split，不是 `layerwise_num_shared_buffers` 的跨层 buffer 复用。

## 15. 本地自研 P/D 原型（2026-11-04）

这一节记录的是**本地原型**，不是上游 main 的正式能力；分支 `local/layerwise-pd-proto`（基于 `local/simulated-ascend-store`）。

### 15.1 已完成链路

```text
P CPU tensor
  → CPUByteCodec 切 TP shard
  → LayerwisePublisher（shared slot fence）
  → MooncakeSessionTransport
  → LayerwiseConsumer
  → codec 写回 D CPU tensor
```

对应文件：

- `layerwise_pd.py`：publisher/consumer、slot fence、in-memory transport；
- `mooncake_tcp_transport.py`：per-shard fallback + one-object-per-layer session/range；
- `layerwise_pd_codec.py`：CPU tensor ↔ TP-shard bytes；
- `layerwise_pd_connector.py`：`KVConnectorBase_V1` 生命周期骨架 + transport 注入；
- `test_layerwise_glm_shape_e2e.py`：78 层、main MLA + indexer、3 shared slots、多请求复用。

### 15.2 真实 Mooncake TCP 已跑通（Docker）

之前“本机没有 wheel”的判断不成立。Docker Desktop `linux/arm64` 下可直接：

```bash
pip install mooncake-transfer-engine-non-cuda
```

实测版本 `0.3.14`，容器：

```text
python:3.12-slim-trixie
libcurl4 libibverbs1 rdma-core librdmacm1 libnuma1 liburing2
```

先起 `mooncake_master`，再跑 `MooncakeSessionTransport` 的 session/range round-trip，输出：

```text
REAL_MOONCAKE_TCP_OK 25
```

复现脚本：

```text
vllm-ascend-src/tests/ut/distributed/ascend_store/run_mooncake_tcp_docker.sh
```

因此 **Mooncake TCP 不再是本地阻塞项**；它是真实 H2H，不是 fake。

### 15.3 本地能验证 / 不能验证

能验证：

- shared slot 生命周期与 fence；
- TP8→D TP1 的字节聚合（synthetic）；
- session/range put/get；
- CPU tensor round-trip；
- connector producer/consumer 生命周期；
- 78 层 GLM-shaped synthetic e2e。

不能验证：

- GLM-5.3 真实 CPU 推理（W4A4/Ascend 算子、真实 KV/attention/MoE）；
- NPU H2D 和真实 KV layout；
- P 侧真实 `LayerwiseKVPoolWorker` 接入；
- 950DT 性能。

### 15.4 与上游 main 的关系

上游 main 的 shared-buffer 文档要求 **Memcache + eager**；本原型走的是 **Mooncake block-key shared buffer**，属于本地/下游验证分支，不能宣称是 upstream 已支持组合。

### 15.5 当前测试

```text
100 passed, 2 skipped
```

2 个 skipped 是 host venv 没有 Mooncake wheel 的 opt-in pytest；Docker 脚本已独立跑通真实 TCP。

### 15.6 下一步

1. 用同一套 78 层 synthetic 在 Docker 内接真实 Mooncake TCP（而不只是 1 层 smoke）；
2. 实现 Ascend H2D codec；
3. 把 publisher 接到真实 `LayerwiseKVPoolWorker` 的 slot 生命周期；
4. 950DT 上换 URMA 做 24 前缀/128K/40 请求。
