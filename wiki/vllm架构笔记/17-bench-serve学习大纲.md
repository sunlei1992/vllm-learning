# 17 vLLM `bench serve` 学习大纲

> 日期：2026-11-19 ｜ 版本：v0.28.0（`2cf0a6915`）｜ 状态：**大纲已定，10 讲待逐讲填充**
> 配套：[09-调度层可观测性与性能测量.md](09-调度层可观测性与性能测量.md)（服务端观测）、
> [14-vLLM统计与观测面全清单.md](14-vLLM统计与观测面全清单.md)（指标清单）、
> [实验D-bench-serve压P-D空跑.md](实验D-bench-serve压P-D空跑.md)（把 bench 用到 P/D 上的实战）

---

## 0. 元信息

| 项目 | 值 |
| :-- | :-- |
| 日期 | 2026-11-19 |
| 源码 | `vllm-src` v0.28.0（`2cf0a6915`） |
| 实现 | `vllm/benchmarks/serve.py`（2368 行） |
| CLI 注册 | `vllm/entrypoints/cli/benchmark/serve.py` |
| 核心函数 | `add_cli_args:1548`、`main_async:1966`、`benchmark:768`、`get_request:393`、`calculate_metrics:556` |
| 数据集层 | `vllm/benchmarks/datasets/datasets.py`（`SampleRequest:77`、`get_samples:2095`） |
| 协议层 | `vllm/benchmarks/lib/endpoint_request_func.py` |
| 状态 | ☐ 未开始（本文件只定大纲） |

**为什么单独学它**：它是 vLLM 唯一的"在线"压测口径（走 HTTP、有到达过程），
且它定义了后续所有讨论的指标语义（TTFT / TPOT / ITL / goodput）。口径不对，后面的 A/B 全是错的。

---

## 1. 能力全景

```
vllm bench
├── serve            在线服务压测（本大纲主角）
├── latency          单 batch 纯模型延迟（不过 HTTP）
├── throughput       离线批量吞吐（直接调 LLM(...)）
├── startup          引擎启动耗时
├── mm-processor     多模态预处理耗时
└── sweep            {serve, serve_workload, startup, plot, plot_pareto}
```

主线之外还有一批**独立脚本**（不是 CLI，但同属一套东西）：
`benchmarks/benchmark_prefix_caching.py`、`benchmark_prioritization.py`、
`benchmark_serving_structured_output.py`、`benchmark_long_document_qa_throughput.py`、
`benchmark_batch_invariance.py`、`benchmarks/multi_turn/`、`benchmarks/replayssm/`。

规模感：`vllm bench serve --help=all` 共 483 行、**104 个顶层 flag**（另有各数据集专属参数组）。
参数按 argparse group 分块，这是理解参数体系的入口。

> 官方文档：`vllm-src/docs/benchmarking/cli.md`（总览 + 例子）、
> `vllm-src/docs/benchmarking/sweeps.md`（扫参）、`vllm-src/docs/cli/README.md`（命令索引）。
> 官方也明说：只跑单点配置推荐 GuideLLM；要扫参数、画曲线用 `sweep` + `plot`。

---

## 2. 十个学习模块

### 第 1 讲｜架构与执行流程（先建立全局观）

**一条主线**：

```
CLI 解析 → main_async → 准备(base_url/header/ssl/model/tokenizer) → 数据集
        → 参数修正 → benchmark() → calculate_metrics → 打印 / 落盘 / 绘图
```

关键点：

- `add_cli_args`（`serve.py:1548`）里 104 个 flag 按组注册，先扫组名再看细节
- `main_async`（:1966）：
  - 未给 `--model` 时调 `/v1/models` 自动取第一个（`get_first_model_from_server:149`）
  - **全局 `--input-len/--output-len` 会展开到各数据集专属参数**
  - 隐式改默认值：`random`/`random-mm` + openai 系自动 `ignore_eos=True`；`timed_trace` 强制 `self_timed=True`
  - `_align_prompts_to_server_tokenizer:74`：`random`/`prefix_repetition` 按**服务端 tokenizer**校准长度
- `benchmark()`（:768）：aiohttp 连接池（keep-alive 60s、6h 超时）→ ready check（真发一条）→ warmup
  → 派发（rate 模式 or 并发模式）→ `asyncio.gather` → 拉 spec-decode / diffusion 指标
- `get_request()`（:393）：到达时间**预先算好**并按 `num_prompts / rate` 归一化（消 seed 抖动）
- 细节：`freeze_gc_heap()` 降 GC 停顿

**实验**：最小命令跑通 + `--save-result`，逐字段读 JSON。

---

### 第 2 讲｜后端与协议层（`--backend`）

12 个 backend，本质是 `ASYNC_REQUEST_FUNCS` 一张表：

| 类别 | 取值 |
| :-- | :-- |
| vLLM 原生 | `vllm`、`vllm-pooling`、`vllm-rerank` |
| OpenAI 兼容 | `openai`、`openai-chat`、`openai-audio` |
| Embeddings | `openai-embeddings`、`openai-embeddings-chat`、`openai-embeddings-clip`、`openai-embeddings-vlm2vec`、`infinity-embeddings`、`infinity-embeddings-clip` |

关键点：

- `--backend` 与 `--endpoint` 是**两个独立参数**，默认 `openai` + `/v1/completions`；换 chat 两个都要改
- 流式响应如何解析成 **TTFT + itl 列表**，全在 `lib/endpoint_request_func.py`
- 采样参数（`temperature/top_p/top_k/min_p/...`）**只对 openai 兼容后端生效**，否则直接报错
- ⚠️ 版本变化：**不再默认 `temperature=0`**（启动会打 WARNING），跨版本对比要显式指定
- `--logprobs`、`--use-beam-search`、`--extra-body`（可塞 `chat_template_kwargs`）

**问题**：`vllm` 与 `openai` 的 token 计数路径不同（前者用服务端返回，后者可能靠 tokenizer 反数），
对 `output_throughput` 的影响有多大？→ 列入疑问清单。

---

### 第 3 讲｜数据集层（14 种 + `hf` 分派 15 个子类）

| 类 | 数据集 | 特点 |
| :-- | :-- | :-- |
| 合成 | `random`、`random-mm`、`random-rerank`、`prefix_repetition`、`sonnet` | ISL/OSL 完全可控；`--random-range-ratio` 造长度分布 |
| 语料 | `sharegpt`、`custom`、`custom_image`、`custom_audio`、`hf` | 真实分布；`custom` 只要 jsonl 有 `prompt` |
| 回放 | `timed_trace` | 带时间戳 + token hash，做真实前缀缓存回放 |
| 专用 | `spec_bench`、`speed_bench`、`burstgpt` | 投机解码 / 推理速度 / 突发流量 |

关键点（`datasets/datasets.py`）：

- `SampleRequest:77` 是统一中间表示：`prompt / prompt_len / expected_output_len / multi_modal_data /
  chat_messages / request_overrides / timestamp`
- **`hf` 是 dispatcher**：按 `dataset_path` 命中 `SUPPORTED_DATASET_PATHS` 分派到
  `VisionArena / MMVU / InstructCoder / MT-Bench / HumanEval / GSM8K / MultiModalConversation /
  Conversation / AIMO / NextEditPrediction / ASR / BlazEdit / MLPerf / MMStar / BFCL`
  （所以 BFCL、ASR 的专属参数没有独立 `--dataset-name`）
- `--no-oversample`（样本不足时是否重复采样）、`--disable-shuffle`（可复现）、`--no-stream`（HF streaming）
- `custom` 系列支持 `--skip-chat-template`、`--chat-template-kwargs`
- `--enable-multimodal-chat`、`--custom-ensure-client-side-data`（本地图转 base64）

**实验**：写 20 行 jsonl 跑 `custom`；再用 `prefix_repetition` 造高缓存命中流量。

---

### 第 4 讲｜负载模型（到达过程）

这是 `serve` 与 `throughput` 的本质区别：**模拟流量，而不是批量**。

- `--request-rate`：`inf` = 全部 t=0 齐发；否则间隔按 **gamma 分布**采样
- `--burstiness`：`1.0` ≈ Poisson；`<1` 更突发；`>1` 更均匀；`inf` 退化为严格等间隔
- 尾部归一化：总时长缩放到 `num_prompts / rate`（ramp-up 模式下不做归一化）
- `--ramp-up-strategy {linear,exponential}` + `--ramp-up-start-rps/--ramp-up-end-rps`：
  **开 ramp-up 就不能给 `--request-rate`**（会报错）
- `--max-concurrency`：客户端并发上限，同时传给 TCPConnector 的 `limit`；实际 rate 可能被它压低
- `--probe-request-rate`：旁路发单 token 探针，**测主负载对无关请求的干扰**（尾延迟归因）
- `--num-warmups`、`--ready-check-timeout-sec`（0 = 跳过）
- `--self-timed`：只允许配 `timed_trace`，完全按 trace 时间戳回放
- `--lora-modules` + `--lora-assignment {random,round-robin}`

**实验**：同一 server 跑 `rate=inf` / `rate=8` / `max-concurrency=8`，看三种"看起来一样"的负载的差异。

---

### 第 5 讲｜指标定义与统计口径（最容易踩坑）

代码：`calculate_metrics`（`serve.py:556`）。

| 指标 | 定义 | 聚合方式 |
| :-- | :-- | :-- |
| **TTFT** | 发出请求 → 收到第一个流式块 | 每请求一个值，再 mean/median/std/分位 |
| **ITL** | 相邻两个流式块的间隔 | **所有请求的间隙汇总**后算分位 |
| **TPOT** | `(e2el − ttft) / (output_len − 1)` | 每请求先算，再在请求间平均 |
| **E2EL** | 客户端发出 → 收完 | 每请求 |
| `request_throughput` | `completed / duration` | — |
| `output_throughput` | `total_output_tokens / duration` | — |
| `total_token_throughput` | `(input+output) / duration` | — |
| **goodput** | 所有 SLO 都满足的请求 / duration | `--goodput ttft:200 tpot:50 e2el:5000`（毫秒） |
| `max_output_tokens_per_s` | 按 1s 分桶统计的 token 峰值 | 附带 `max_concurrent_requests` |
| `rtfx` | ASR：音频总时长 / 墙钟 | 越大越快 |

必记的坑：

- **投机解码下 ITL ≠ TPOT**：一个流式块可含多个 token，ITL 不会为块内 token 补零
- `output_len <= 1` 时 TPOT 记 0 参与 goodput
- 非流式后端拿不到 TTFT（`ttfts` 为空 → 指标为 0）
- 失败请求不计入延迟指标，但计入 `failed`；前 10 条错误打印
- 装了 `termplotlib` 会画 token/s 曲线（:718）

**实验**：`--save-detailed` 拿每请求 ttft/itl，自己用 numpy 重算 mean/p99 对账。

---

### 第 6 讲｜结果落盘与可视化

- 文件名模板 `{label}-{request_rate}qps-{model_id}-{时间戳}.json`（`compute_result_filename:1505`）
- `--label`、`--metadata key=value`（写进 JSON 留痕）、`--append-result`（一行一个 JSON，方便 pandas）
- `--save-detailed`：保留 `input_lens/output_lens/start_times/ttfts/itls/generated_texts/errors`；不加会被裁掉
- 额外产出一份 pytorch benchmark 格式（`save_to_pytorch_benchmark_format:1470`）
- `--plot-timeline` → `.timeline.html` 交互甘特图，`--timeline-itl-thresholds 25,50` 三色
- `--plot-dataset-stats` → `.dataset_stats.png`，**建议每次都开**，先确认 workload 形状
- `vllm bench sweep plot` / `plot_pareto` 读 JSON 出曲线与帕累托图

---

### 第 7 讲｜sweep 家族（真正的"做实验"工具）

`vllm bench sweep serve`（`vllm/benchmarks/sweep/serve.py`）：

- `--serve-cmd` / `--bench-cmd`：两条基础命令
- `--serve-params` / `--bench-params`：JSON 数组，每个对象一组覆盖值；`_benchmark_name` 可命名
- `--link-vars`：同一变量绑定 serve 与 bench 两侧
- `--num-runs`、`--output-dir`、`--experiment-name`、`--resume`、`--dry-run`（只打印命令，调试很好用）、
  `--show-stdout`、`--server-ready-timeout`、`--after-bench-cmd`

`vllm bench sweep serve_workload`：找 latency-throughput 拐点。
先跑 1 并发、再跑全并发、估上限、再均匀取点；`--workload-var {request_rate,max_concurrency}`
（官方建议用 `max_concurrency`，更贴近引擎真实压力）。

`vllm bench sweep startup`：冷/热启动对比。

---

### 第 8 讲｜高级与专用能力

- `--profile`：server 端要配 `--profiler-config`（见 `docs/contributing/profiling.md`）
- **投机解码**：自动从 server `/metrics` 拉 `spec_decode_*`，算接受率、每步接受 token 数
  （`SpecDecodeMetrics:180`、`fetch_spec_decode_metrics:189`）
- **diffusion 模型**：`DiffusionMetrics:254` 统计 step 数与 committed tokens
- **多模态**：`random-mm` bucket 采样、`--enable-multimodal-chat`、`--custom-ensure-client-side-data`
- **pooling/embedding/rerank**：`TaskType.POOLING:315` 分支，指标退化为只有 E2EL
- **ASR**：`rtfx` + `--asr-min/max-audio-len-sec`
- **前缀缓存专项**：不在 serve 里，用 `benchmarks/benchmark_prefix_caching.py` + `--dataset-name timed_trace`
- **多轮对话**：`benchmarks/multi_turn/`
- `--skip-tokenizer-init` / `--tokenizer-mode deepseek_v32`

---

### 第 9 讲｜和本工作区的仿真/昇腾环境结合

- 对 `--simulate-forward` 起的 server 可以跑 `bench serve`，但**请求必须带 `trace_decode_token_ids`**，
  否则 200 但生成 0 token（静默失败）；要看 token 需 `return_token_ids: true`
- 仿真器 KV 容量必须按真实硬件给 `--kv-cache-memory-bytes`，否则准入/抢占结论无意义
- `bench serve` 延迟是**客户端侧**的；仿真 `timing=zero` 时看的是调度行为，两者不要混比
  （实验D 已踩：默认 `timing=zero` 让 P/D 配比实验失效）
- 昇腾侧：bench 只是 HTTP client，可直接打 Ascend 上的 `vllm serve`；但要结合 vllm-ascend 的调度改动解读
- `sim-0.30` 分支未移植 `benchmarks/serve.py` 重构，`vllm bench sweep simulate` 不可用

---

### 第 10 讲｜实验设计方法学

八条"不踩坑"清单：

1. 先 `--plot-dataset-stats` 确认 workload 形状，再谈指标
2. `rate` 与 `concurrency` 二选一作自变量，别同时扫（互相耦合）
3. 每个配置至少 3 次（`--num-runs` 或 sweep 重复）
4. 报告永远带 p50/p90/p99，均值会被长尾骗
5. 记录 server 侧配置（`--metadata` 或 sweep 的 `--serve-params`），否则 JSON 无法溯源
6. 跨版本比较固定 `--seed`、`--temperature=0`、`--ignore-eos`、`--num-warmups`
7. 客户端别成瓶颈：并发大时注意进程/网卡/GC（代码已 `freeze_gc_heap`）
8. 要"服务能力"而不只是"峰值吞吐"时，用 `--goodput` 把 SLO 写进结果

---

## 3. 学习路线（6 次）

| 次序 | 内容 | 产出 |
| :-- | :-- | :-- |
| 1 | 第 1 讲 + 跑通一条 random | 一份 JSON，每个字段都能解释 |
| 2 | 第 3 讲 数据集 | `custom` / `sonnet` / `prefix_repetition` 三条流量 |
| 3 | 第 4 讲 负载模型 | rate vs concurrency vs ramp-up 对比 |
| 4 | 第 5 讲 指标 | 手算对账 + goodput 实验 |
| 5 | 第 6–7 讲 落盘与 sweep | 一套 sweep + pareto 图 |
| 6 | 第 9 讲 结合仿真器 | 对 `--simulate-forward` server 出第一份压测 |

第 2 讲（后端）与第 8 讲（高级特性）按需插入。

---

## 4. 版本敏感项（跨版本对比前先核对）

| 项 | 本版本行为 | 影响 |
| :-- | :-- | :-- |
| 默认 temperature | **不再强制 0**，由 server 决定 | 与旧版本数据不可直接比 |
| 旧脚本入口 | `benchmarks/benchmark_serving.py` 只打印 DEPRECATED 并 `exit(1)` | 老教程命令跑不通 |
| 指标名 | `--percentile-metrics` 支持 `ttft,tpot,itl,e2el`；pooling 默认 `e2el` | 少配会缺分位 |
| `--input-len`/`--output-len` | 新增的"通用映射"入口 | 与专属参数同时给时的优先级要确认 |
| `--self-timed` | 仅 `timed_trace` 可用 | 其他数据集给会报错 |

---

## 5. 与其他笔记的关系

| 笔记 | 关系 |
| :-- | :-- |
| [09-调度层可观测性与性能测量.md](09-调度层可观测性与性能测量.md) | 服务端视角（日志/`/metrics`/每请求 metrics），与 bench 的客户端指标互补 |
| [14-vLLM统计与观测面全清单.md](14-vLLM统计与观测面全清单.md) | 指标语义与坑的全景表 |
| [实验D-bench-serve压P-D空跑.md](实验D-bench-serve压P-D空跑.md) | 把 bench 用到 P/D 分离上的实战：缺两段式协议 → 薄代理 |
| [10-调度优化测试工作流.md](10-调度优化测试工作流.md) | 用 bench + 每请求 metrics + step 轨迹做 A/B 归因 |

---

## 6. 疑问清单（学习过程中逐条填）

- [ ] `--backend vllm` 与 `openai` 的 output token 计数差异有多大？影响 `output_throughput` 吗？
- [ ] `--max-concurrency` 同时控制客户端并发与 TCP 连接数，二者耦合会不会扭曲结果？
- [ ] ITL 是"池化所有间隙"算分位，与"每请求分位再平均"在长尾下差多少？
- [ ] ramp-up 模式下为什么不做尾部归一化？实际到达率是否偏离设定？
- [ ] `--probe-request-rate` 的探针请求会不会被 server 的调度策略特殊对待？
- [ ] spec-decode / diffusion 指标抓取失败时是静默跳过还是报错？
- [ ] `--append-result` 与 `--save-detailed` 组合、以及 `--resume` 在 sweep 里的语义？
- [ ] `timed_trace` 的 `chunk_hash_size`（16 vs 512）如何影响前缀命中判定？

---

## 7. 参考

- 源码：`vllm-src/vllm/benchmarks/serve.py`、`vllm/benchmarks/datasets/datasets.py`、`vllm/benchmarks/lib/`
- 文档：`vllm-src/docs/benchmarking/cli.md`、`vllm-src/docs/benchmarking/sweeps.md`、`vllm-src/docs/cli/README.md`
- 自检命令：`vllm bench serve --help=all`（483 行，最终事实来源）
