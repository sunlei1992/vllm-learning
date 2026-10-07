# vLLM 架构学习笔记

> 学习方式：**跟读源码 + 断点实验 + 按模板沉淀笔记**。
> 环境：v0.28.0 / CPU 后端 / VSCode 进程内调试（`VLLM_ENABLE_V1_MULTIPROCESSING=0`）。
> 配套：`../环境搭建记录.md`、`../git使用指南.md`。

---

## 学习路线（建议顺序，由外到内）

每个模块对应一个笔记文件，从 `模板.md` 复制。**编号规则**：
- `00-xxx` / `01-xxx`…：路线图学习模块（数字 = 建议学习顺序，`00` 是前置知识）
- `实验X-xxx`：实际做的实验记录（不占学习顺序编号）

| # | 模块 | 核心问题 | 源码入口 | 断点位置 |
|---|---|---|---|---|
| 00 | **模型加载与 dummy 机制** ✅已写 | 没有权重怎么跑通 vLLM？`load_format` 有哪些？ | `vllm/model_executor/model_loader/` | `dummy_loader.py:36` |
| 01 | **进程模型与入口** | 一个 `LLM.generate()` 调用经历了哪些进程/对象？ | `vllm/entrypoints/llm.py` → `vllm/v1/engine/llm_engine.py` → `vllm/v1/engine/core.py` | `core.py:1271` `run_engine_core` |
| 02 | **调度器 Scheduler** | 连续批处理怎么决定"这轮跑谁"？chunked prefill 怎么拆？ | `vllm/v1/core/sched/scheduler.py` | `scheduler.py:476` `schedule` |
| 03 | **KV Cache 与注意力** ✅已写 | MLA 怎么做到 57 倍 KV 压缩？GLM-5.2 注意力怎么算？ | `layers/mla.py`、`deepseek_v2.py:948`、`cpu_sdpa.py`/`cpu_mla.py` | `trace_mla.py` |
| 04 | **模型执行 Worker** | Worker 每步做什么？输入输出长什么样？ | `vllm/v1/worker/cpu_worker.py` | `cpu_worker.py:146` `execute_model` |
| 05 | **模型前向** | 一个 transformer 层怎么算的？（看最小模型 OPT） | `vllm/model_executor/models/opt.py` | `opt.py:114` `forward` |
| 06 | **采样 Sampler** | logits 怎么变成 token？有哪些采样策略？ | `vllm/v1/sample/sampler.py` | `sampler.py:73` `forward` |
| 07 | **服务层（可选）** | `vllm serve` 的 OpenAI API 怎么映射到引擎？ | `vllm/entrypoints/openai/api_server.py` | —（进程内模式不支持 serve，看代码即可） |
| 08 | **进阶特性（可选）** | 前缀缓存、投机解码、多模态各自怎么实现？ | `vllm/v1/core/sched/`、`vllm/spec_decode/` | — |
| 实验A | **截断加载实验 GLM-5.2** ✅已写 | 大模型怎么本地跑？dense/MoE 两种调试模式怎么配？ | `models/zai-org_GLM-5.2` + 本地补丁 | `debug_glm52.py --moe` |

---

## 一次"最小推理"的全链路（先建立整体认知）

```
demo_inference.py
  └─ LLM.generate("Hello")                    entrypoints/llm.py
       └─ LLMEngine.add_request / run_engine   v1/engine/llm_engine.py
            └─ EngineCore 主循环               v1/engine/core.py
                 ├─ Scheduler.schedule()       v1/core/sched/scheduler.py   ← 决定 batch
                 ├─ Worker.execute_model()     v1/worker/cpu_worker.py      ← 算前向
                 │    ├─ Attention (KV cache)  v1/attention/backends/cpu_attn.py
                 │    └─ OPT 模型 forward      model_executor/models/opt.py
                 └─ Sampler.forward()          v1/sample/sampler.py         ← 出 token
```

> 提示：进程内模式下（`VLLM_ENABLE_V1_MULTIPROCESSING=0`）这条链全在一个进程里，
> VSCode 从 `demo_inference.py` 一路 F10/F11 就能走完。

---

## 学习方法建议

1. **先跑后读**：`python demo_inference.py` 跑通，再在关键点打断点单步。
2. **一次只追一条线**：比如"第一个 token 是怎么产生的"，不要同时追多条。
3. **用 git 看演进**：`git log --follow -p -- <文件>` 看模块怎么变成现在这样（见 git使用指南.md）。
4. **每个模块写一篇笔记**：从 `模板.md` 复制，回答模板里的问题就算掌握。
5. **疑问先记后查**：模板里有"疑问清单"小节，攒一批再统一查。
