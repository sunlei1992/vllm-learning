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
