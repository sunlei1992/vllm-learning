# 00 模型加载与 dummy 机制学习笔记

> 触发场景：环境里没有真实模型权重，却成功跑通了 vLLM 推理（输出乱码）。
> 本笔记回答：**vLLM 没有权重是怎么"执行"的？**

## 0. 元信息

| 项目 | 值 |
|---|---|
| 日期 | 2026-08-27 |
| 源码路径 | `vllm-src/vllm/model_executor/model_loader/` |
| 核心类/函数 | `DummyModelLoader`、`initialize_dummy_weights`、`_LOAD_FORMAT_TO_MODEL_LOADER` |
| 断点位置 | `dummy_loader.py:36` `load_weights`（看随机填充过程） |
| 状态 | ☑ 已掌握 |

## 1. 核心问题

1. **vLLM 运行一个模型需要什么？** —— 架构（config.json，几 KB）+ 权重（几百 MB 参数文件）
2. **`load_format="dummy"` 做了什么？** —— 架构照常加载，权重用 [-1e-3, 1e-3] 的均匀随机数填充，跳过权重下载
3. **为什么输出是乱码？** —— 随机权重 = 没训练过的模型，next-token 概率近似随机
4. **这个功能有什么用？** —— 性能评测/CI 测试：计算量与真实权重完全相同，省去下载加载开销

## 2. 一句话总结

> **dummy = 下载架构、跳过权重、随机填充**：模型结构和推理链路（调度/KV cache/采样）全部走真实代码，只是参数值是随机数，所以输出是乱码——用来"无权重跑通全链路"。

## 3. 关键概念速记

| 概念 | 一句话解释 | 对应代码位置 |
|---|---|---|
| load_format | 指定模型权重加载方式，0.28.0 共 14 种 | `model_loader/__init__.py:32-47` |
| 加载器注册表 | load_format → 加载器类的映射 | `__init__.py:48-63` `_LOAD_FORMAT_TO_MODEL_LOADER` |
| DefaultModelLoader | 默认加载器：下载/读取真实权重（auto/hf/safetensors 等 10 种格式共用） | `model_loader/default_loader.py` |
| **DummyModelLoader** | 随机权重加载器：`download_model` 直接 pass | `model_loader/dummy_loader.py` |
| initialize_dummy_weights | 把参数填成 [-1e-3,1e-3] 均匀随机数，seed=1234，每参数独立 seed | `model_loader/weight_utils.py:1289` |
| 随机值范围的意义 | 太小→无意义；太大→激活爆炸产生 NaN，前向挂掉。-1e-3~1e-3 是经验安全值 | `weight_utils.py:1289` 注释 |
| 固定 seed 的意义 | 多卡分片时各卡生成的 dummy 权重一致，可复现 | `weight_utils.py:1289` docstring |
| 量化与 dummy | 量化层走 `process_weights_after_loading` 特殊处理 | `dummy_loader.py:46-62` |

## 4. 数据流 / 时序

```
demo_inference.py: LLM(model="facebook/opt-125m", load_format="dummy")
  └─ 1. 下载 config.json + tokenizer（几 KB → .hf-cache）
  └─ 2. 按 config 构建模型结构（OPTForCausalLM：12 层、768 hidden…）
  └─ 3. LoadConfig.load_format="dummy"
  └─ 4. 查注册表 → DummyModelLoader            __init__.py:48
  └─ 5. download_model() → pass（不下载权重）  dummy_loader.py:33
  └─ 6. load_weights()：遍历所有模块           dummy_loader.py:36
  │      ├─ 量化层 → process_weights_after_loading
  │      └─ 普通层 → initialize_dummy_weights()   weight_utils.py:1289
  │                   （torch.rand 填 [-1e-3,1e-3]，seed=1234）
  └─ 7. 前向计算（真实代码）→ 输出乱码 ✓
```

## 5. 代码走读记录

- [x] `__init__.py:32-47` —— `LoadFormats` 是 Literal 类型，14 种格式：auto/hf/dummy/fastsafetensors/instanttensor/mistral/modelexpress/npcache/pt/runai_streamer(+sharded)/safetensors/sharded_state/tensorizer。**注意：老版本的 `dummy_hf` 在 0.28.0 已被移除**
- [x] `__init__.py:48-63` —— 注册表映射：只有 `dummy` 用 DummyModelLoader，`modelexpress`/`runai_streamer`/`sharded_state`/`tensorizer` 各有专属，其余全走 DefaultModelLoader
- [x] `dummy_loader.py:33-34` —— `download_model` 空实现，这就是"不下载权重"的落点
- [x] `dummy_loader.py:36-44` —— `load_weights` 遍历 `model.modules()`；注释提到"为准确性能评测赋随机值"（NOTE(woosuk)）
- [x] `weight_utils.py:1289-1311` —— 默认 low=-1e-3, high=1e-3, seed=1234；docstring 解释 NaN 问题与固定 seed 的意义
- [x] `weight_utils.py:1313` —— `initialize_single_dummy_weight` 带 `@torch.no_grad()`，逐参数用独立 seed 生成（`torch.rand` + 缩放）

## 6. 实验 / 断点记录

| 实验 | 怎么做的 | 观察到的现象 | 说明了什么 |
|---|---|---|---|
| dummy 跑 opt-125m | `demo_inference.py`（默认 dummy） | 输出乱码 `' spite proficiency Thompson...'`，exit 0 | 全链路真实执行，仅权重是随机数 |
| **横向基准：4 模型对比** | `vllm bench latency` + dummy + 本地 config（batch=4, 16+16 tokens, fp16） | opt-125m **0.20s** / Qwen2.5-0.5B **0.67s** / Qwen3-0.6B **0.81s** / TinyLlama-1.1B **1.25s** | 延迟随参数量近似线性（CPU compute-bound 特征）；只下载 config 即可比较任意架构 |
| Qwen3 长上下文报错 | 直接跑 Qwen3-0.6B | `max seq len 40960, 4.38GiB KV cache needed > 4.3GiB available` | 长上下文模型的 KV cache 需求大；加 `--max-model-len 4096` 解决（自动降到 40,576 tokens 容量） |
| 对比真实模式 | 把 `--load-format` 改 auto | （未实测；需先解决 HF 下载，见环境搭建记录.md） | 只有加载来源不同 |
| 内存校验 | 默认 0.35 跑 | `Available memory 8.23G < 8.4G` 报错 | 引擎启动有内存预留校验（见环境搭建记录.md） |

## 7. 疑问清单（待解决）

- [ ] dummy 模式下量化（如 AWQ/GPTQ）能测出真实性能吗？`_process_online_quant_layer` 会跑量化处理，但随机权重下的量化误差参考价值有限？
- [ ] 不同模型架构（MoE、MLA）的 dummy 权重生成是否有特殊分支？
- [ ] `npcache`、`modelexpress` 这些新格式是什么场景用的？（0.28.0 新增，可 git log 查引入提交）

## 8. 与其他模块的关系

| 依赖/被依赖 | 模块 | 关系说明 |
|---|---|---|
| 被调用 | `vllm/config/load.py` LoadConfig | 用户配 `load_format` 后由 LoadConfig 持有，加载时查注册表 |
| 调用 | `model_loader/reload/meta.py` materialize_layer | 量化层先物化再填随机值 |
| 调用 | `model_loader/weight_utils.py` | 随机权重生成工具 |
| 上游 | `vllm/entrypoints/llm.py` → `LLMEngine` | 引擎初始化时根据 LoadConfig 构造加载器 |
| 后续 | 前向推理链路（scheduler/worker/attention） | 权重加载完成后，推理链路无感知（不关心权重怎么来的） |

---

> 相关文档：`../环境搭建记录.md`（dummy 验证步骤）、`../vscode调试指南.md`（断点地图）。
> 下一步建议：进入路线图模块 01「进程模型与入口」，看权重加载完成后引擎怎么跑起来。
