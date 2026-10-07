# VSCode 调试指南（vLLM 源码学习）

> 记录本工作区配好的 VSCode 断点调试环境与用法。
> 核心技巧：**`VLLM_ENABLE_V1_MULTIPROCESSING=0` 让引擎在进程内运行，调试器才能跟到底**。

---

## 1. 已配置内容

| 文件 | 作用 |
|---|---|
| `.vscode/launch.json` | 调试配置（1 个配置：`vLLM 离线推理 (进程内调试)`） |
| `.vscode/settings.json` | Python 解释器指向 `.venv`；排除缓存目录（.uv-cache 等） |
| `.venv` 里的 debugpy 1.8.21 | VSCode 调试器依赖（已装好） |

### launch.json 关键项说明

```jsonc
"program": "${workspaceFolder}/demo_inference.py",   // 调试入口脚本
"python": "${workspaceFolder}/.venv/bin/python",     // 必须用 venv 的 Python
"env": {
  "VLLM_ENABLE_V1_MULTIPROCESSING": "0",            // ★ 关键：关多进程 → 进程内引擎
  "HF_HOME": "${workspaceFolder}/.hf-cache",        // 缓存指到工作区
  ...
},
"justMyCode": true,     // 只进用户代码（vllm 在工作区里算用户代码）
"showReturnValue": true // 函数返回值显示在变量面板
```

---

## 2. 快速上手（F5 三步）

1. **VSCode 打开工作区根目录** `~/code/dsh/vllm`（不是 vllm-src）
2. 在源码里**打断点**（点行号左侧，出现红点）
3. 按 **F5** → 自动用 `vLLM 离线推理 (进程内调试)` 配置启动，停在第一个断点

> 首次启动会加载引擎（约 20~40 秒），耐心等；调试会话结束后引擎正常退出。

### 调试快捷键

| 键 | 功能 |
|---|---|
| F5 | 继续 / 启动调试 |
| F10 | 单步跳过（不进入函数） |
| F11 | 单步进入（进入函数内部） |
| Shift+F11 | 跳出当前函数 |
| Shift+F5 | 停止调试 |
| F9 | 切换断点 |

---

## 3. ★ 为什么必须关多进程（最重要的一节）

VLLM V1 引擎默认是**多进程**架构：

```
你的 Python 进程 (LLM)
   └─ EngineCore 子进程
        └─ WorkerProc 子进程
```

VSCode 调试器默认**只附加到启动时的那个进程**。如果不关多进程：
- `demo_inference.py` 里的断点 ✅ 能停
- `scheduler.py`、`cpu_worker.py` 里的断点 ❌ **停不住**（在子进程里）

`VLLM_ENABLE_V1_MULTIPROCESSING=0` 让引擎改用 **InprocClient**（进程内），
整条链路都在一个进程里跑，调试器全程可跟。

**代价与限制**：
- 与生产（多进程）模式有进程边界差异，但引擎核心代码是同一套
- `vllm serve`（asyncio 模式）**不支持**进程内运行：0.28.0 会报
  `NotImplementedError: Running EngineCore in asyncio without multiprocessing is not currently supported`
  （`vllm/v1/engine/core_client.py:98`）。服务端调试需子进程 attach，暂不研究
- 想回归多进程模式：删掉 launch.json 里那行 `VLLM_ENABLE_V1_MULTIPROCESSING` 即可

### 2.1 现有调试配置清单（launch.json）

| 配置名 | 入口 | 用途 |
|---|---|---|
| `vLLM 离线推理 (进程内调试)` | `demo_inference.py` | 通用小模型调试（opt-125m） |
| `vLLM 调试: GLM-5.2 (3层截断)` | `debug_glm52.py` | GLM-5.2 截断 3 层（dense，看 MLA/引擎） |
| `vLLM 调试: GLM-5.2 MoE (3层全MoE)` | `debug_glm52.py --moe` | GLM-5.2 3 层全 MoE（看路由/专家） |

> GLM-5.2 调试前提：本地补丁（稀疏 `is_v32=False` + PR#51471 的 cpu_sdpa），详见
> `vllm架构笔记/实验A-截断加载GLM52.md`。

---

## 4. 断点地图（学习用，行号已核实 v0.28.0）

按一条请求的生命周期排列，从 `LLM.generate` 一路跟到输出：

| 阶段 | 断点位置 | 观察什么 |
|---|---|---|
| 入口 | `vllm-src/vllm/entrypoints/llm.py` → `LLM.generate` | 请求进入引擎 |
| 加请求 | `vllm-src/vllm/v1/engine/llm_engine.py:218` `add_request` | EngineInput → EngineCoreRequest 的转换 |
| 引擎主循环 | `vllm-src/vllm/v1/engine/core.py:1271` `run_engine_core` | 请求生命周期、批处理迭代 |
| **调度** | `vllm-src/vllm/v1/core/sched/scheduler.py:476` `schedule` | ★ 连续批处理/chunked prefill 决策 |
| 模型执行 | `vllm-src/vllm/v1/worker/cpu_worker.py:146` `execute_model` | 每步前向的输入（positions/KV）输出（logits） |
| 注意力 | `vllm-src/vllm/v1/attention/backends/cpu_attn.py:345` `forward` | KV cache 读写 |
| 采样 | `vllm-src/vllm/v1/sample/sampler.py:73` `forward` | logits → token |
| 模型前向 | `vllm-src/vllm/model_executor/models/opt.py:114` `forward` | 单层 transformer 计算 |

> 推荐路线：先在 **入口** 打断点 F5 启动 → 一路 F10/F11 顺着走；
> 第二遍再直奔 `scheduler.py:476` 看批处理逻辑。

### 4.1 GLM-5.2 专属断点地图（MLA + MoE）

GLM-5.2（`glm_moe_dsa`）走 **deepseek_v2 实现 + CPU MLA 后端**，断点和普通模型不同：

| 关注点 | 断点位置 | 看什么 |
|---|---|---|
| **MLA 注意力** | `model_executor/models/deepseek_v2.py`（层前向） | MLA 组装、q/k/v 投影 |
| CPU MLA prefill | `v1/attention/backends/mla/prefill/cpu_sdpa.py` `_ragged_sdpa` | ★ PR#51471 新代码：逐请求 dense attention |
| CPU MLA decode | `v1/attention/backends/mla/cpu_mla.py:156` `forward_mqa` | decode kernel 路径 |
| **MoE 路由** | `model_executor/models/deepseek_v2.py:279` `DeepseekV2MoE`（forward 393） | router 线性层、topk、专家分发、共享专家 |
| MoE 后端选择 | `layers/fused_moe/oracle/unquantized.py` | 日志 "Using CPU Unquantized MoE backend" 出处 |
| 专家计算 | `layers/fused_moe/experts/cpu_moe.py` | CPU 专家矩阵乘 |

> MoE 断点要求 `debug_glm52.py --moe`（3 层全 MoE + 8 专家，见 09 笔记坑 6）。
> 完整调用链日志：`CPU Unquantized MoE backend` → `MoEPrepareAndFinalizeNoDPEPMonolithic` → `CPUUnquantizedExperts`。

---

## 5. 实用调试技巧

### 5.1 变量面板看什么

- **EngineCoreRequest**：`request_id`、`input_token_ids`、`sampling_params`
- **SchedulerOutput**：本轮 batch 选了哪些 request、`scheduled_requests`
- **KV cache**：`kv_cache_manager` 的 `block_pool`（页分配情况）

### 5.2 监视表达式（Watch）

在监视面板添加，随时看：
```
len(vllm_config.scheduler_config)   # 调度配置
llm.llm_engine.engine_core          # 引擎核心对象
```

### 5.3 条件断点

行号红点右键 → "Add Conditional Breakpoint"：
```
# 只在生成长度超过 10 时停
len(output_token_ids) > 10
```

### 5.4 多请求调试

改 launch.json 的 `args` 或多个请求：
```jsonc
"args": ["--prompt", "Hello world. Tell me a story."]
```
或用代码方式（改 demo_inference.py）：
```python
llm.generate(["请求1", "请求2"])   # 两个并发请求，看调度器怎么 batch
```

---

## 6. 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 引擎内部断点不停 | 多进程模式 | 确认 launch.json 里有 `VLLM_ENABLE_V1_MULTIPROCESSING: "0"` |
| 断点显示"未绑定"（空心红点） | 文件路径与解释器不匹配 | 确认打开的是工作区根目录、`.venv/bin/python` 被选中（右下角解释器） |
| 启动报 `Available memory ...` | 内存不足 | 改 launch.json 的 `args` 加 `--mem 0.2` |
| 停不进第三方库（transformers） | `justMyCode: true` | 改成 `false` 可进任意库代码 |
| F5 提示装 Python 扩展 | 未安装 | 扩展市场搜 "Python"（ms-python.python）安装 |
| 调试启动很慢（20-40s） | 引擎初始化 | 正常，模型加载+KV cache 分配需要时间 |

---

## 7. 推荐调试流程（学习用）

1. **预热**：`source env.sh && .venv/bin/python demo_inference.py` 跑通一次
2. **追第一遍**：入口断点 → F5 → 一路 F10/F11 走完一条请求（约 20 分钟）
3. **追第二遍**：直奔 `scheduler.py:476`，观察连续批处理（改 demo 发两个请求）
4. **记笔记**：把看到的东西填进 `wiki/vllm架构笔记/` 的对应模块笔记

> 完整断点地图也同步在 `wiki/vllm架构笔记/README.md` 的路线图里。
