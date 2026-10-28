# 004 — 在空跑环境加载 vllm-ascend（无 NPU）

> 日期：2026-10-26
> 目标：在没有 NPU 的 Linux 容器里加载 **vllm-ascend main**，
> 并让「空跑」（`--simulate-forward`，PR #47922）正常跑完。
> 配套：`wiki/vllm架构笔记/实验B-simulate-forward仿真环境.md`、
> `assets/simulate-forward/va/run_va_dry_run.sh`

---

## 1. 结论

**可以，且已实测跑通。**

```text
EngineCoreProc.run_engine_core: vllm_ascend.patch.platform.patch_engine_core   ← 补丁已生效
kv_cache_utils.get_kv_cache_groups: vllm_ascend.patch.platform.patch_kv_cache_utils

[va-plugin] connector: OK
[va-plugin] model: OK
[va-plugin] model_loader: OK
[va-plugin] service_profiling: OK

[sim] engine init: 13.27s
[sim] generate: 0.25s
[sim] token_ids: [100, 101, 102, 103, 104, 105, 106, 107]
```

也就是说：**VA 的 platform 补丁打上了，空跑仍然正确输出 trace token。**

> 前提是版本对齐：VA main 的 `.github/vllm-main-verified.commit` = `a98247ab`，
> 正是空跑容器里的 vLLM 版本。

## 2. 为什么可行（与 vllm-cloud 的对比）

| | vllm-cloud | vllm-ascend main |
| :-- | :-- | :-- |
| vLLM 版本 | v0.26.0（2026-07-26） | main `a98247ab`（2026-10） |
| 与空跑版本差 | 3926 commits | **完全一致** |
| trace replay | 不存在 | 存在（#46701 已合入） |
| 结论 | 需要移植，成本高 | **可直接加载** |

## 3. 绕过的 6 个点

| # | 报错 | 根因 | 解法 |
| :-- | :-- | :-- | :-- |
| 1 | `No module named 'torch_npu'` | `vllm_ascend/utils.py:34` 顶层 import | `torch_npu` 模块 stub（MagicMock） |
| 2 | `module 'torch' has no attribute 'npu'` | `torch.npu.Event` 在**函数签名**里被求值 | `torch.npu = MagicMock()` |
| 3 | `cannot import name '_build_info'` | 该文件由 `setup.py` 在安装时生成 | 手写 `__device_type__ = 'A2'` |
| 4 | `Failed to resolve Triton op 'insert_slice'` | 依赖 triton-ascend 扩展算子，模块级解析 | 注入 `insert_slice`/`extract_slice`/`get_element` |
| 5 | `cannot import name 'is_hccl_available'` | CPU 版 torch 没有 HCCL | `torch.distributed.is_hccl_available = lambda: False` |
| 6 | `No module named 'torch_npu._C'` | `from torch_npu._C._distributed_c10d import ProcessGroupHCCL` 需要真实子模块 | 往 `sys.modules` 注入两层模块 |

另外两处**行为**改动（不是 stub）：

| 改动 | 原因 |
| :-- | :-- |
| `register()` 无 NPU 时返回 `None` | 否则 vLLM 选中 NPU 平台，`--simulate-forward` 直接拒绝 |
| 伪造 `vllm_ascend-0.0.0.dist-info/entry_points.txt` | 不执行 `pip install`（会触发 CANN 编译），但要让插件被发现 |

## 4. 为什么 stubs 要写在 `sitecustomize.py`

第 2、4、5、6 条都必须在 **vllm_ascend 被 import 之前**生效，
而 `sitecustomize` 由 Python 在解释器启动时自动导入，正好满足时序。

`torch_npu` 本身用一个包目录（`torch_npu/__init__.py`）实现，
因为 `from torch_npu._C...` 这种导入需要真实模块条目，`__getattr__` 不够。

## 5. 边界（必须写清楚）

| 能验证 | 不能验证 |
| :-- | :-- |
| `patch.platform` 里所有补丁的**加载与应用** | `patch.worker`（只有 `NPUWorker` 才加载） |
| scheduler / engine core / kv cache 侧的补丁逻辑 | 真实 connector 读写（需要 NPU 内存注册） |
| 空跑下的调度行为、TTFT/TPOT 趋势 | CANN 算子、HCCL 通信、HBM 实测 |

一句话：**能测"补丁有没有把 CPU 路径改对"，不能测"NPU 上跑得快不快"。**

## 6. 一键复现

```bash
./wiki/vllm架构笔记/assets/simulate-forward/va/run_va_dry_run.sh
```

脚本做的事：挂载 VA 源码 → 复制到可写路径 → 生成 `_build_info.py` →
改 `register()` → 写 `va_plugins.py`（每个插件 try/except）→ 伪造 entry points →
验证两个补丁符号 → 跑 `sim_smoke.py`。

## 7. 实测：VA 补丁能否改变调度行为（T-011）

脚本：`assets/simulate-forward/sim_va_compare.py`（`VA_PATCHES=0/1` 两次运行）。

### 7.1 dense 模型（Qwen3-0.6B）：补丁完全 no-op

| 指标 | patches OFF | patches ON |
| :-- | :-- | :-- |
| steps | 13 | 13 |
| kv_total | 145 | 145 |
| peak_kv | 18 | 18 |
| mean TTFT | 90.94 | 90.94 |
| p95 TTFT | 171.10 | 171.10 |
| mean TPOT | 14.98 | 14.98 |
| makespan | 205.45 | 205.45 |

**逐位相同**。原因很直接：这些补丁面向 Mamba / MLA / EPLB / SWA / DP balance，
dense + 标准 KV 的 workload 一条都不触发。

### 7.2 MLA + MoE 模型（DeepSeek-V2-Lite）：补丁 ON 直接崩

```text
patches OFF: {"steps": 8, "kv_total": 38835, "peak_kv": 100, "mean_ttft": 148.85, ...}

patches ON:
  RuntimeError: Ascend config is not initialized.
                Please call init_ascend_config first.
```

`init_ascend_config(vllm_config)` 平时由 **NPU 平台**在 `check_and_update_config`
或 connector/scheduler 构造时调用；CPU 空跑下没有任何人调用它。

### 7.3 为什么不能用它评估 VA 的调度策略

VA 确实自带调度策略：

```
vllm_ascend/core/short_request_first_scheduler.py   # ShortRequestFirstAsyncScheduler
vllm_ascend/core/batch_job_aware_scheduler.py       # 批任务感知
```

但选择条件是：

```python
# platform.py:1095
if vllm_config.scheduler_config.async_scheduling:
    vllm_config.scheduler_config.scheduler_cls = "…ShortRequestFirstAsyncScheduler"
```

而空跑强制 `async_scheduling = False`：

```python
# vllm/engine/arg_utils.py
async_scheduling = False if self.simulate_forward else self.async_scheduling
```

**所以 VA 的调度策略在空跑里根本不会被选中。**

### 7.4 结论

| 用途 | 适合？ |
| :-- | :-- |
| 验证 VA 补丁能加载、不破坏 CPU 路径 | ✅ |
| 评估 VA 补丁/策略的收益 | ❌（no-op 或崩溃或不被选中） |
| 评估调度策略本身 | ✅ 用 `sim_policy.py` 自己实现 |

也就是说：**空跑是"兼容性脚手架"，不是"VA 策略评估器"。**
想评估策略，把它写进 `sim_policy.py` 的排序 key，比硬塞 VA 补丁便宜得多。

## 8. 下一步

1. 用这个环境验证 **VA 的调度类补丁**（如 `patch_balance_schedule`、`patch_engine_core`）
   在 CPU 空跑下是否改变调度行为
2. 结合 `sim_policy.py` / `sim_timing.py` 量化收益（推荐路线）
3. 把 `patch.worker` 的补丁也纳入（需要模拟一个 `NPUWorker` 形状的 worker，成本更高）

> 注意：这是一套**本地实验脚手架**，不是上游支持的运行方式，不要提交到社区。

---

## 9. GLM-5.3（MoE）下的额外要求（2026-10-28 追加）

纯 vLLM 跑 GLM-5.3 只需要 `is_v32 = False`（见实验B 第 17 节）。
加上 vllm-ascend 之后，还需要 3 个额外处理。

### 9.1 四个必要改动

| # | 改动 | 原因 |
| :-- | :-- | :-- |
| 1 | `is_v32 = False`（镜像 `sim030:glm53`） | CPU 不支持稀疏注意力 |
| 2 | 跳过 `register_model`（`VA_SKIP_MODEL=1`） | VA 的 `models/deepseek_mtp.py` 在建模型时就要 `AscendConfig` |
| 3 | 在 `Worker.load_model` 里调 `init_ascend_config`（`VA_INIT_CONFIG=1`） | `patch_fused_moe._ascend_FusedMoE` 读 `get_ascend_config().eplb_config` |
| 4 | 给 `RoutedExperts.__init__` 加 shim，丢掉 `n_shared_experts` | VA 往 `routed_experts_args` 里塞了这个 kwarg，GLM-5.3 的类不接收 |

第 2、3 条是同一个根因：**CPU 平台没有任何人调用 `init_ascend_config`**（它平时由 NPU 平台调用）。
第 3 条的钩子必须挂在 `Worker.load_model` 上——挂 `VllmConfig.__post_init__` 无效，
因为 worker 里的 config 不走 `__post_init__`。

### 9.2 结果

```text
[va-plugin] connector: OK / model: SKIPPED / model_loader: OK / service_profiling: OK
[va-plugin] init_ascend_config: OK (worker)
[sim] engine init: 13.87s
[sim] generate: 0.40s
[sim] token_ids: [100, 101, 102, 103, 104, 105, 106, 107]
```

KV 指标与**纯 vLLM 完全一致**：

| 配置 | tokens | blocks | 并发度 |
| :-- | :-- | :-- | :-- |
| 纯 vLLM（0.30 / main） | 23,888 | 1,493 | 11.66x |
| **vLLM + VA 0.30** | 23,888 | 1,493 | 11.66x |

说明 VA 的 `patch_kv_cache_utils` 在 GLM-5.3 这条路上没有改变 KV 布局。

### 9.3 边界

- `VA_SKIP_MODEL=1` 意味着 **VA 的模型侧补丁没有生效**（只验证了 platform 层补丁共存）
- 空跑不执行 forward，所以 MoE 路由/专家计算没有被真正验证
- 这 4 条都是**本地 shim**，不是上游支持的组合

脚本：`assets/simulate-forward/va/run_va_glm53.sh`

### 9.4 验证脚本自身的两个坑

归档脚本第一次复跑时出现过一个**假阳性**：`[sim]` 输出正确，但一条 `[va-plugin]` 都没有——
说明插件根本没加载，实际跑的是纯 vLLM。原因是脚本有两处 bug：

| bug | 表现 | 修复 |
| :-- | :-- | :-- |
| `ROOT` 多上溯了一层 | 挂载目录为空，`cp -a /ascend /va` 后 `/va/vllm_ascend` 不存在 | 按脚本所在层级改成 5 层 |
| 生成 `va_plugins.py` 的模板少了 `except` | `SyntaxError: expected 'except' or 'finally' block`，插件加载失败但被 vLLM 静默跳过 | 补上 `except` |

**教训**：判断"VA 是否真的生效"，不能只看空跑有没有输出，
必须确认日志里有 `[va-plugin] ... OK` 和 `patch_engine_core` / `patch_kv_cache_utils`
这些行。否则可能只是纯 vLLM 在跑。

