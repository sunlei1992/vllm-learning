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

## 7. 下一步

1. 用这个环境验证 **VA 的调度类补丁**（如 `patch_balance_schedule`、`patch_engine_core`）
   在 CPU 空跑下是否改变调度行为
2. 结合 `sim_policy.py` / `sim_timing.py` 量化收益
3. 把 `patch.worker` 的补丁也纳入（需要模拟一个 `NPUWorker` 形状的 worker，成本更高）

> 注意：这是一套**本地实验脚手架**，不是上游支持的运行方式，不要提交到社区。
