# 实验A 截断加载实验：GLM-5.2 在 M3 CPU 上跑通（3/78 层）

> 日期：2026-08-27 ｜ 环境：v0.28.0 / Mac M3 24GB / CPU 后端 / dummy 权重
> 结论：**大模型"下载 config + 截断层数 + 随机权重"本地跑通完全可行**，但需要修补 vLLM 0.28.0 的 3 个 CPU 缺陷。
> 最终结果：GLM-5.2（78 层截断为 3 层）在 CPU 上完整推理，**平均延迟 2.52s/批**（batch=4, 16+16 tokens）。
> 📌 **2026-09-12 复跑通过**（GLM-5.2 3 层 + DeepSeek-V2-Lite 缩层 MLA），新增 2 个坑（内存门槛、indutor PCH 缓存）→ 见 [§7 复跑记录](#7-复跑记录2026-09-12环境完好两个实验通过--2-个新坑)。

---

## 1. 思路与内存账

**思路**：大模型（如 GLM-5.2，504B 参数 ≈ 1TB fp16）本地跑不了，但模型参数主要在层上。
把 `num_hidden_layers` 从 78 截到 3，内存占用降到 ~1/26，架构（hidden size、词表、注意力结构）保持真实，
用于调试/学习引擎逻辑。

**GLM-5.2 真实 config 内存账（fp16）**：

| 部分 | 计算 | 内存 |
|---|---|---|
| embedding + LM head（不共享） | 154880 × 6144 × 2 × 2B | ≈ 3.8 GB |
| dense 层（前 3 层） | 注意力(MLA) + MLP | ≈ 0.53 GB/层 |
| MoE 层（后 75 层） | + 256 experts | ≈ 12.4 GB/层 |
| **截断 3 层（恰好全 dense）** | 3×0.53 + 3.8 | **≈ 5.4 GB** ✅ |

**关键巧合**：GLM-5.2 的 `first_k_dense_replace=3`，前 3 层正好是 dense——截断 3 层躲开了 12.4GB/层的 MoE。

## 2. 完整步骤（可复现）

```bash
# 1. 只下载 config + tokenizer（26MB，不含权重）
./dl_model.sh zai-org/GLM-5.2

# 2. 修改 config.json（models/zai-org_GLM-5.2/config.json）：
#    num_hidden_layers: 78 -> 3
#    mlp_layer_types:   截断为前 3 项（校验器要求长度=层数）
#    删除 index_* / indexer_* 字段（稀疏注意力，见坑 1）
cp models/zai-org_GLM-5.2/config.json /tmp/backup.json   # 留备份

# 3. 跑基准
.venv/bin/vllm bench latency --model models/zai-org_GLM-5.2 --load-format dummy \
  --dtype float16 --gpu-memory-utilization 0.3 --enforce-eager \
  --max-model-len 4096 --input-len 16 --output-len 16 --batch-size 4 \
  --num-iters-warmup 1 --num-iters 3
```

## 3. 踩过的坑与修复（vLLM 0.28.0 的 CPU 缺陷）

### 坑 1：稀疏注意力 CPU 不支持
```
NotImplementedError: Sparse Attention is not supported on CPU.
```
- 触发：`deepseek_v2.py` 的 `self.is_v32 = hasattr(config, "index_topk")`
- **删 config 字段没用**：`GlmMoeDsaConfig.__init__` 默认参数就是 `index_topk=2048`，属性永远存在
- **修复**：`deepseek_v2.py` 两处 `self.is_v32 = False`（见文件内注释）

### 坑 2：fa_utils.py CPU 分支缺失
```
ImportError: cannot import name 'compile_flash_attn_varlen_func_from_specs' from 'fa_utils'
```
- 原因：fa_utils 只在 CUDA/XPU/ROCm 分支定义符号，CPU 分支缺失
- **修复**：补 CPU 分支占位（None）

### 坑 3：MLA prefill 后端选择器在 CPU 上选错
```
AssertionError: FlashAttnPrefillBackend requires flash_attn_varlen_func
```
- 原因：`selector.py` 的 `device_capability is None` 早退 → 不检查可用性直接选 FLASH_ATTN；
  `is_flash_attn_varlen_func_available()` 对 CPU 返回 False → 导入被置 None
- **修复**：availability 函数补 CPU 分支返回 True（配合坑 4 的实现）

### 坑 4：CPU 没有 MLA prefill 计算实现（真正缺的零件）
- CPU_MLA 后端只有 decode kernel（`torch.ops._C.mla_decode_kvcache`），
  prefill 文档说用 "plain PyTorch SDPA" 但**没有实现**
- **修复**：在 `fa_utils.py` 写了 ~60 行 `flash_attn_varlen_func` 的 **SDPA varlen 参考实现**
  （按 cu_seqlens 分段循环 + `F.scaled_dot_product_attention`），复用 FlashAttnPrefillBackend 全套机制

**⭐ git 考古结论（回答"是不是以前有 SDPA 被删了"）：是！**

| 提交 | 内容 |
|---|---|
| `58d1b2aa77` [Attention] MLA support for V1 (#13789) | **最初的 MLA V1 支持**：`vllm/v1/attention/backends/mla/common.py`（1022 行）包含完整的 **SDPA 实现**（4 处 `scaled_dot_product_attention`，含 chunked + LSE 版本） |
| `2263d44b68` [4/N] Move MLA common to model_executor (#32060) | **重构时丢弃了 SDPA**：common.py 移到 `model_executor/layers/attention/mla_attention.py`，但新文件 **0 处 SDPA**——通用 SDPA prefill 被 prefill_backend 抽象（flash_attn/flashinfer/trtllm，全是 GPU 后端）取代 |
| `13726c80fe` [CPU] Add MLA backend (#49453) | 2026-08 加 CPU MLA 后端：只实现了 decode kernel，docstring 继承旧版"prefill 用 SDPA"的说法，**但 SDPA 代码已不存在**——悬空承诺 |

**佐证**：官方 `tests/v1/attention/test_cpu_mla_backend.py::test_cpu_mla_backend_smoke` 用 DeepSeek-V2-Lite + `hf_overrides` 缩到 2 层 4 专家（思路与我们一致！），实测**没有我们的补丁必挂**（FlashAttnPrefillBackend 断言），**有补丁通过**（顺带验证了 CPU 上 MLA+MoE 全链路）。

### 📌 main 分支现状（2026-08-27 检查，vllm-main.zip）
**main 只修了一半，Apple Silicon 上仍然坏的**：

| main 的改动 | 状态 |
|---|---|
| `selector.py`：CPU → 返回 `CPU_NATIVE`（不再选 FlashAttnPrefillBackend） | ✅ 修了"选错后端" |
| 新增 `mla/prefill/cpu_native.py`：`CPUNativeMLAPrefillBackend` 占位（满足 metadata builder 的 clone 要求），`run_prefill_new_tokens` 直接 `raise AssertionError("unreachable")` | ⚠️ 占位而非实现 |
| 新增 `mla/amx_mla.py`：**AMX 高性能后端**（x86+AMX 硬件），`forward_mha` 覆写 + `extend_attention_cpu` kernel，直接对分页 latent KV cache 做 prefill | ✅ 真正的修复（仅限 AMX 机器） |
| `cpu_mla.py`（引用后端，Apple Silicon 用这个）：与 v0.28.0 **零差异**，无 forward_mha 覆写 | ❌ **没修** |

**结论**：main 上非 AMX 的 CPU（含 M3）走引用后端 `CPUMLAImpl` → prefill 时
`MLACommonImpl.forward_mha` 调用 `CPU_NATIVE.run_prefill_new_tokens` → **AssertionError**——
只是报错信息从 `requires flash_attn_varlen_func` 换成了 `unreachable`，故障本质没变。
`cpu_native.py` docstring 声称 "CPUMLAImpl.forward_mha fully overrides" 与实际代码矛盾
（实际覆写的是 `AMXMLAImpl`）——文档错误。

**对比我们的方案**：官方 AMX 方案（高性能 kernel，仅 AMX 硬件）+ 占位断言；我们的 SDPA 方案
（通用 torch SDPA，任何 CPU 可用，慢但正确）。在 M3 上我们的补丁仍是必要的。

### 坑 5：内存校验连环卡
- 启动校验 `available >= ratio×24GB`；KV 分配校验 `budget - weights - overhead >= 0`
- GLM-5.2 3 层权重 5.4GB + 开销 0.6GB ≈ 6.0GB → ratio 至少 0.27，实测 0.3 稳定
- 另外：GLM-5.2 的 context 是 **1M**，必须 `--max-model-len`（否则 KV 校验必炸）

### 🆕 坑 6：想断 MoE？用 hf_overrides 把截断层变成 MoE 层
- 默认截断 3 层全是 dense（`first_k_dense_replace=3`），MoE 代码路径跑不到
- 直接改 `first_k_dense_replace=0` 让层 0-2 变 MoE 也不行——**一层全量 MoE = 256 专家 × 3 × 6144 × 2048 ≈ 19.3GB fp16，单层都放不进 24GB**
- **解法**（官方 `test_cpu_mla_backend_smoke` 同款思路）：`hf_overrides` 缩小专家数，保留真实架构形状：

```python
hf_overrides = {
    "first_k_dense_replace": 0,   # 层 0-2 全部变 MoE
    "n_routed_experts": 8,        # 256 → 8（内存：3 层 ≈ 5.6GB）
    "num_experts_per_tok": 2,     # top-2 路由
}
```

- 实测跑通：日志依次出现 `Using CPU Unquantized MoE backend` → `MoEPrepareAndFinalizeNoDPEPMonolithic` → `CPUUnquantizedExperts`——MoE 全链路（路由/专家/合并）真实执行
- 用法：`debug_glm52.py --moe`，或 VSCode 配置 `vLLM 调试: GLM-5.2 MoE (3层全MoE)`
- **MoE 断点地图**：`deepseek_v2.py:279 DeepseekV2MoE`（router/topk/专家分发）、`fused_moe/experts/cpu_moe.py`（专家计算）、`fused_moe/oracle/unquantized.py`（后端选择）

## 4. 修改文件清单（git diff 可见，随时可还原）

> 当前状态 = PR #51471 的修复（cpu_sdpa 方案）+ 我们的稀疏补丁。fa_utils hack 已废弃还原。

| 文件 | 改动 | 来源 |
|---|---|---|
| `vllm/model_executor/models/deepseek_v2.py` | 2 处 `is_v32 = False`（稀疏注意力，PR 未覆盖） | 我们 |
| `vllm/v1/attention/backends/mla/prefill/cpu_sdpa.py` | **新增**：CPU SDPA prefill 后端 | PR #51471 |
| `.../mla/prefill/registry.py` | 加 `CPU` 枚举 | PR #51471 |
| `.../mla/prefill/selector.py` | CPU 分支选 CPU 后端 | PR #51471 |
| `vllm/_custom_ops.py` | +`gather_mla_context_cache_cpu`（纯 Python） | PR #51471 |
| `vllm/model_executor/layers/attention/mla_attention.py` | +CPU gather 分支 | PR #51471 |
| `models/zai-org_GLM-5.2/config.json` | 层数/列表截断、删稀疏字段 | 我们 |

## 5. 边界与限制

- ✅ 引擎全链路（调度、MLA 注意力、KV cache、采样）用 GLM-5.2 真实 shape 跑通
- ✅ **MoE 路径可测**：`--moe` 模式（`first_k_dense_replace=0` + 专家缩到 8）——路由/topk/专家计算真实执行，只是专家数缩小（内存限制）
- ⚠️ 稀疏注意力（DSA/1M context）被关闭——那是 GLM-5.2 的核心卖点，CPU 上本来也跑不了
- ⚠️ 输出是乱码（dummy 权重）；性能数字 ×26 ≈ 全量估算（仅层数线性部分）
- ⚠️ 本地补丁仅用于学习；若向 vLLM 提 PR 需按 AGENTS.md 规范重写（当前改动是"实验性 hack"）

## 6. 经验总结

1. **"只下载 config + 截断层数"是学习大模型架构的通用方法**：任何 vLLM 支持的模型都能这么玩
2. **vLLM 0.28.0 的 CPU MLA 路径不完整**：参考后端（CPU_MLA）缺 prefill 实现，两个小 bug（fa_utils、selector）
3. **看代码时先找 config 字段与代码的耦合**：`hasattr(config, "index_topk")` 这种模式，改 config 没用，得看 config 类默认参数
4. **git 的价值**：所有改动 `git diff` 一目了然，随时还原

---

## 7. 复跑记录（2026-09-12）：环境完好，两个实验通过 + 2 个新坑

> 距首次实验 16 天，同机同环境（v0.28.0 / M3 24GB / CPU 后端 / dummy 权重）。
> 结论：**config、补丁、脚本全部完好，GLM-5.2 与 DeepSeek-V2-Lite 都能直接复跑**；
> 但本次遇到 2 个首次实验没出现的新问题（内存门槛、torch inductor 缓存），解法见坑 7 / 坑 8。

### 7.1 复跑一：GLM-5.2 截断 3 层（dense）

复跑前核对（都还完好）：

| 项 | 状态 |
|---|---|
| `models/zai-org_GLM-5.2/config.json` | `num_hidden_layers=3`、`mlp_layer_types` 长度 3（全 dense）、`index_topk` 已删 ✅ |
| `vllm-src` 补丁 | `git diff --stat` = 5 files, +51/-2；`cpu_sdpa.py` 存在；`is_v32=False` 在 1082/1377 行 ✅ |
| `models/` 下 5 个模型 | config + tokenizer 齐全，0 个权重文件（dummy 模式够用）✅ |
| `/tmp/backup.json`（原始 config 备份） | ❌ 已随 /tmp 清理丢失 |

```bash
source env.sh
TORCHINDUCTOR_CACHE_DIR="$PWD/.torchinductor-cache" VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  .venv/bin/python -c "
from vllm import LLM
llm = LLM(model='models/zai-org_GLM-5.2', load_format='dummy', enforce_eager=True,
          max_model_len=512, dtype='float16', gpu_memory_utilization=0.3,
          kv_cache_memory_bytes=256*1024*1024)      # ← 见坑 7，绕过内存校验
print(repr(llm.generate(['Debug this GLM-5.2 on M3'])[0].outputs[0].text[:80]))
"
```

关键日志：
```
INFO [selector.py:111] Using CPU SDPA MLA prefill backend.     ← 我们补丁的 CPU MLA prefill 路径生效
INFO [cpu_worker.py:255] Explicitly set (0.25/24.0) GiB for KV cache on node 0.
INFO [kv_cache_utils.py:1869] GPU KV cache size: 77,664 tokens
WARNING [deepseek_v2.py:1773] DeepSeekV2: No DeepseekV2MoE layer found in model.layers.
[init done in 34.8s]  [generate done in 6.4s]     # output 2.52 tok/s
```

结果：输出乱码（dummy 权重，正常）；耗时与首次笔记的 2.52s/批同量级。
`No DeepseekV2MoE layer found` 也符合预期——截断的 3 层正好全是 dense（`first_k_dense_replace=3`），
要跑 MoE 路径用 `debug_glm52.py --moe`。

### 7.2 复跑二：DeepSeek-V2-Lite 缩层（2/27 层）走 MLA + MoE

🆕 新增脚本 `debug_dsv2lite_mla.py`（风格同 `debug_glm52.py`，含 MLA 断点地图）。
缩层参数与官方 `tests/v1/attention/test_cpu_mla_backend.py::test_cpu_mla_backend_smoke` 一致：

```python
hf_overrides = {
    "num_hidden_layers": 2,      # 27 -> 2
    "n_routed_experts": 4,       # 64 -> 4
    "first_k_dense_replace": 0,  # 让 2 层都变 MoE（默认第 0 层 dense，MoE 路径跑不到）
    "num_experts_per_tok": 2,    # 6 -> 2
}
llm = LLM(model="models/deepseek-ai_DeepSeek-V2-Lite", trust_remote_code=True,
          load_format="dummy", enforce_eager=True, max_model_len=128,
          max_num_seqs=2, block_size=16, dtype="float16",
          gpu_memory_utilization=0.2, hf_overrides=hf_overrides)
```

```bash
source env.sh
TORCHINDUCTOR_CACHE_DIR="$PWD/.torchinductor-cache" VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  .venv/bin/python debug_dsv2lite_mla.py
```

关键日志（MLA + MoE 全链路证据）：
```
INFO [cpu.py:348] MLA is enabled on a non-GPU platform; forcing chunked prefill and prefix caching to be disabled.
INFO [selector.py:111] Using CPU SDPA MLA prefill backend.                 ← prefill：CPU SDPA 后端
INFO [unquantized.py:319] Using CPU Unquantized MoE backend out of potential backends: ['CPU']
INFO [unquantized.py:400] Using MoEPrepareAndFinalizeNoDPEPMonolithic
INFO [unquantized.py:401] Using CPUUnquantizedExperts MoE backend          ← MoE 路由/专家真实执行
```

结果：两个 prompt 各精确生成 4 tokens（`token_ids=4`，形状/链路正确），文本乱码属正常。

### 7.3 🆕 坑 7：内存门槛卡死（启动校验）

现象：
```
ValueError: Available memory on node 0 (5.84/24.0 GiB) on startup is less than desired
CPU memory utilization (0.25, 6.0 GiB).
```
- 本机可用内存在 **5.8~6.2GB 波动**（实测 Safari/WebKit 单进程就占 2.96GB），而 GLM-5.2 3 层权重 ~5.4GB + 开销 0.6GB ≈ 6.0GB
- 于是 `0.3 / 0.27 / 0.25` **全部失败**：既要 `可用 ≥ ratio×24`，又要 `ratio×24 ≥ 权重+开销` → 可用内存必须 ≥ ~6.0GB
- **解法：显式指定 KV 大小，直接跳过该校验**。校验条件在 `vllm/v1/worker/cpu_worker.py:75`：

```python
if (vllm_config.cache_config.kv_cache_memory_bytes is None      # ← 只要给了值，整个校验不执行
        and self.requested_cpu_memory > available_memory):
    raise ValueError(...)
```

显式分支（`cpu_worker.py:213`）只检查"KV 大小 ≤ 可用内存"，宽松得多：

```python
LLM(..., gpu_memory_utilization=0.3, kv_cache_memory_bytes=256*1024*1024)  # 256MB KV 对 512 上下文绰绰有余
# CLI: --kv-cache-memory-bytes（字节）；env: VLLM_CPU_KVCACHE_SPACE（MB）
```

日志印证：`Explicitly set (0.25/24.0) GiB for KV cache on node 0.`（0.25 GiB = 256 MB）

### 7.4 🆕 坑 8：torch inductor 预编译头（PCH）缓存过期

现象（首次实验没遇到，隔天复用默认临时缓存目录才出现）：
```
fatal error: file '.../torchinductor_sunlei/precompiled_headers/xxx.h' has been modified since
the precompiled header '...xxx.h.pch' was built: mtime changed
torch._inductor.exc.InductorError: CppCompileError: C++ compile error
```
- 原因：默认 indutor 缓存在 `$TMPDIR/torchinductor_<user>`，PCH 与头文件 mtime 不同步（跨会话/跨天复用即触发）
- **解法**：清掉旧缓存 + 把缓存固定到工作区内

```bash
rm -rf "$TMPDIR"/torchinductor_$(whoami)
mkdir -p .torchinductor-cache
export TORCHINDUCTOR_CACHE_DIR="$PWD/.torchinductor-cache"    # 之后所有 vLLM 命令都带上
```
（本仓库已建 `.torchinductor-cache/`，体积可随时 `rm -rf` 重建）

### 7.5 ⚠️ 复跑的重要发现：CPU + MLA 会强制关闭 prefix caching

```
INFO [cpu.py:348] MLA is enabled on a non-GPU platform; forcing chunked prefill and prefix caching to be disabled.
```
含义：**本机（CPU 后端）跑 MLA 模型时，prefix caching 与 chunked prefill 都被 vLLM 强制关闭**。对后续工作的影响：
- KV connector / 前缀复用 / chunked prefill 相关逻辑**无法在 Mac 上验证**；本地只能验证 connector 骨架
  （握手、KV 存/取、加载失败回退、异步加载）
- 想看真实前缀复用行为，必须回 NPU 环境（或在 CPU 上改用非 MLA 模型）

### 7.6 复跑涉及的文件变化

| 文件 | 状态 |
|---|---|
| `debug_dsv2lite_mla.py` | 🆕 新增（DeepSeek-V2-Lite 缩层 MLA 脚本 + MLA 断点地图） |
| `.torchinductor-cache/` | 🆕 新增（indutor 缓存固定目录，可删） |
| `models/zai-org_GLM-5.2/config.json` | 仍是截断版（3 层）；原始备份 `/tmp/backup.json` 已丢失 |
| `vllm-src` 5 个补丁文件 | 仍未提交，`git diff` 可见（与 §4 清单一致） |
