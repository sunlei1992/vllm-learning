# vllm-ascend 对照学习笔记

> 定位：与主仓 `vllm-src/` **对照阅读**，理解"vLLM 硬件插件"如何接入主仓。
> 环境：vllm-ascend **v0.23.0**（2026-08-16）@ `../vllm-ascend-src/`；vLLM v0.28.0 @ `../vllm-src/`
> ⚠️ Mac 无法运行（依赖 torch-npu/triton-ascend），本目录**纯代码研究**。

## 笔记索引

| # | 笔记 | 对照主题 |
|---|---|---|
| 001 | [PCP对照-主仓vsAscend](001-PCP对照-主仓vsAscend.md) ✅ | PCP 是重写还是复用？为什么？（V1 vs V2 runner） |
| 002 | [MLA对照-NPUvsCPU](002-MLA对照-NPUvsCPU.md) ✅ | MLA 注意力：参考实现（CPU）vs 性能实现（NPU） |
| 003+ | 待写 | platform / DSA 稀疏注意力 / 插件注册机制… |

## 1. 这是什么

vllm-ascend 是 vLLM 官方插件生态的**华为昇腾 NPU 支持**（Hardware Plugin）：
不改主仓一行代码，通过 vLLM 的插件机制把 NPU 平台、注意力后端、算子等注册进去。
参考官方博客：*Introducing vLLM Hardware Plugin, Best Practice from Ascend NPU*。

## 2. 目录结构对照表（核心学习方法）

| vllm-ascend（`vllm_ascend/`） | vLLM 主仓 | 对照看点 |
|---|---|---|
| `platform.py` | `vllm/platforms/`（cuda.py/cpu.py…） | ★ 插件如何注册"平台"（NPUPlatform） |
| `attention/` | `vllm/v1/attention/backends/` | NPU 注意力后端怎么实现/替换 |
| `worker/` | `vllm/v1/worker/` | NPU worker 与 CPU/GPU worker 的差异 |
| `model_executor/` `models/` | `vllm/model_executor/` | Ascend 专属模型实现 |
| `ops/` | `vllm/_custom_ops.py` + `csrc/` | NPU 算子封装 |
| `distributed/` | `vllm/distributed/` | NPU 通信（HCCL） |
| `compilation/` | `vllm/compilation/` | NPU 编译/图模式 |
| `quantization/` | `vllm/model_executor/layers/quantization/` | NPU 量化支持 |
| `csrc/` | `vllm-src/csrc/` | C++/自定义算子（含 catlass submodule） |

## 3. 插件接入机制（先看这里建立框架）

vLLM 的插件发现：vllm 启动时扫描注册的插件 → 调用其注册函数：

```python
# vllm_ascend/__init__.py:38
def register():
    """Register the NPU platform."""
    return "vllm_ascend.platform.NPUPlatform"   # ★ 告诉 vLLM："我的平台类在这"
```

对照主仓找 vLLM 侧怎么消费这个返回值（搜 `register()` / platform 注册的调用方）。

其他注册函数：
- `register_connector()` —— KV/权重传输（disaggregated serving）
- `register_model_loader()` —— 自定义模型加载（netloader/rfork）
- `register_model()` —— 额外模型注册

## 4. 学习路径建议

1. 先读 `vllm_ascend/platform.py` + 主仓 `vllm/platforms/cpu.py` 对照（我们最熟 CPU 平台）
   —— 理解"平台"抽象要提供什么（attention 后端选择、设备内存等）
2. 再读 `__init__.py` 全部 register 函数，画出"插件注入了主仓哪些扩展点"
3. 挑一个点深入：如 `attention/` 里 NPU 的 MLA 后端 vs 主仓 CPU MLA 后端（我们刚学过！）
4. 每篇笔记按 `../vllm架构笔记/模板.md` 填写

## 5. 常用命令

```bash
cd ~/code/dsh/vllm/vllm-ascend-src
git log --oneline -20          # 看最近演进
git log --oneline -- vllm_ascend/attention/   # 某个子模块的历史
git diff v0.22.0..v0.23.0 -- vllm_ascend/platform.py   # 版本间变化
```
