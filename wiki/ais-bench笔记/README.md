# AISBench（原 ais-bench）知识库

> 定位：把 AISBench 当**会用的工具**记清楚 —— 能测什么、怎么装、数据怎么造、结果怎么读、哪里会错。
> 版本基线：`v3.1-20261013-master`（2026-10-16 发布）；仓库最新提交 `7bcb6440`（2026-10-26，`[perf][prefix cache] optimize prefix cache planning for large scenarios (#596)`）。
> 资料截至 **2026-10-28**。上游：[GitHub AISBench/benchmark](https://github.com/AISBench/benchmark) · [中文文档](https://ais-bench-benchmark.readthedocs.io/zh-cn/latest/) · [官网](https://www.aisbench.com)
> ⚠️ 本目录目前**全部来自官方文档与仓库源码阅读，没有跑过真机**。标注约定：
> `【文档】`= 官方文档/代码原文；`【推算】`= 按文档规则自己算出来的，需要用 `inspect` 或实测验证。

## 笔记索引

| # | 笔记 | 解决的问题 |
|---|---|---|
| 001 | [定位与版本脉络](001-定位与版本脉络.md) ✅ | 它到底是谁家的？和 OpenCompass / vLLM benchmark / EvalScope 什么关系？版本怎么发？ |
| 002 | [安装与最小跑通](002-安装与最小跑通.md) ✅ | 装哪套、怎么验证、跑通一条精度/性能命令、结果落哪 |
| 003 | [评测场景与产物](003-评测场景与产物.md) ✅ | 精度/性能/Agent 三大场景、`--mode` 八种取值、目录结构和指标口径 |
| 004 | [CLI 与配置体系](004-CLI与配置体系.md) ✅ | 三种驱动方式、参数优先级、API 覆盖参数、`global_consts`、`abbr` 陷阱 |
| 005 | [测试数据构造](005-测试数据构造.md) ✅ | 四条造数路径怎么选：开源 / 合成 / 自定义 / PrefixCache |
| 006 | [PrefixCache 插件详解](006-PrefixCache插件详解.md) ✅ | 指定命中率数据怎么造、五子命令、scenario 全字段、可达性算法 |
| 007 | [128K / 90% APC / 24 组的方案](007-128K-90%-24组方案.md) ✅ | 本工作区的具体需求：参数映射、可达性算术、可直接用的 scenario |
| 008 | [坑与 FAQ](008-坑与FAQ.md) ✅ | 版本差异、易错点、常见误解、限制清单 |

配套资产：`assets/scenario-128k-apc90-g24.json`（可直接改的 scenario）、`assets/gsm8k_to_jsonl.py`（语料转换脚本）。

## 30 秒速查

```bash
# 精度（默认场景，不用带 --mode）
ais_bench --models vllm_api_general_chat --datasets demo_gsm8k_gen_4_shot_cot_chat_prompt

# 性能（必须 -m perf，且只能用流式接口；测长输出要 ignore_eos=True）
ais_bench --models vllm_api_stream_chat --datasets demo_gsm8k_gen_4_shot_cot_chat_prompt -m perf

# 造压测数据（纯离线，不需要推理服务）
ais-bench-prefix-cache inspect --scenario ./scenario.json
ais-bench-prefix-cache prepare --mode text --scenario ./scenario.json
```

| 项目 | 值 |
|---|---|
| 结果根目录 | `outputs/default/<时间戳>/` |
| 开源数据集放哪 | `ais_bench/datasets/` |
| 模型任务配置 | `ais_bench/benchmark/configs/models/` |
| 数据集任务配置 | `ais_bench/benchmark/configs/datasets/` |
| PrefixCache 插件 | `plugins/prefix_cache/`（独立包，命令行是连字符版 `ais-bench-prefix-cache`） |
| Python | 3.10 / 3.11 / 3.12（`v3.1-20260415` 那份文档还只写 3.10/3.11） |

**三个最容易踩的**：① Python 3.9 及以下/3.13 装不上；② 性能测长输出不设 `ignore_eos=True`，token 数一定对不上；③ PrefixCache 的 `tokenizer.path` / `block_size` 必须与服务端**完全一致**，否则理论命中率是从错的边界算的。

## 知识地图

```
                    ┌── 开源数据集（gsm8k/mmlu/…）──┐
数据从哪来 ──────────┼── 随机合成（synthetic_*）    ──┼──> AISBench 任务 ──> outputs/<时间戳>/
                    ├── 自定义（jsonl/csv）        ──┤        │
                    └── PrefixCache 插件（指定命中率）┘        │
                                                              ├─ predictions/  results/  summary/
                                                              └─ performances/  *_plot.html
```

三条主线，对应第 005/006/007 篇：
- **要精度** → 开源数据集或自定义数据集，`--mode all/infer/eval`，看 `summary/*.csv`。
- **要性能** → 开源/合成/自定义/PrefixCache，`-m perf`，看 `performances/<abbr>/*.json` 和 TTFT/TPOT/ITL。
- **要"可复现的缓存命中率"** → 只有 PrefixCache 插件能给你理论值 + 实际值对账。

## 与本工作区其它笔记的关系

| 关联 | 说明 |
|---|---|
| `../vllm架构笔记/实验B-simulate-forward仿真环境.md` §11 | 在**仿真器**里观察 APC 行为（共享 371-token 前缀，prefill 2968→1176，-60.4%）。AISBench 是"打真服务"，两者互补：仿真器看调度，AISBench 看端到端指标。 |
| `../ascend对照笔记/` | 昇腾侧。MindIE 文档的精度测试直接以 AISBench 为例；跑 NPU 时后端换 `mindie_*` 或 vllm-ascend 起的 OpenAI 服务。 |

## 来源与维护

所有结论的出处：

| 类型 | 地址 |
|---|---|
| 文档站（版本化） | `https://ais-bench-benchmark.readthedocs.io/zh-cn/latest/` |
| 插件源码与 README | `https://github.com/AISBench/benchmark/tree/master/plugins/prefix_cache` |
| 发布记录 | `https://api.github.com/repos/AISBench/benchmark/releases` |
| 昇腾侧引用 | [MindIE 使用导读](https://www.hiascend.com/document/detail/zh/mindie/300/index/index.html) |

复核版本的两个命令：

```bash
curl -s https://api.github.com/repos/AISBench/benchmark/releases?per_page=3 | jq -r '.[].tag_name'
curl -s https://api.github.com/repos/AISBench/benchmark/commits?per_page=1 | jq -r '.[0].sha[0:10], .[0].commit.committer.date'
```
