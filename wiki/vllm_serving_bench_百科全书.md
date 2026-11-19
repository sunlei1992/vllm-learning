# vLLM Serving Bench 百科全书

> 版本基线：vLLM **v0.28.0**（commit `2cf0a6915`），源码 `vllm-src/`。
> 写作日期：2026-11-19。所有行号、默认值、枚举值均按该版本核对。
> 复核方式：`vllm bench serve --help=all`（483 行、104 个 flag）；
> 官方文档 `vllm-src/docs/benchmarking/cli.md`、`vllm-src/docs/benchmarking/sweeps.md`。
> 配套笔记：[17-bench-serve学习大纲.md](vllm架构笔记/17-bench-serve学习大纲.md)、
> [实验D-bench-serve压P-D空跑.md](vllm架构笔记/实验D-bench-serve压P-D空跑.md)。

---

## 目录

- [0. 五分钟上手](#0-五分钟上手)
- [1. 定位与测量边界](#1-定位与测量边界)
- [2. 运行方式与前置条件](#2-运行方式与前置条件)
- [3. 命令行总览与参数总表](#3-命令行总览与参数总表)
- [4. 执行流程（源码级）](#4-执行流程源码级)
- [5. 后端与协议](#5-后端与协议)
- [6. 数据集](#6-数据集)
- [7. 负载模型](#7-负载模型)
- [8. 指标定义与统计口径](#8-指标定义与统计口径)
- [9. 结果文件](#9-结果文件)
- [10. 可视化](#10-可视化)
- [11. sweep 家族](#11-sweep-家族)
- [12. 高级能力](#12-高级能力)
- [13. 场景配方（可直接抄）](#13-场景配方可直接抄)
- [14. 排错手册](#14-排错手册)
- [15. 版本差异与兼容性](#15-版本差异与兼容性)
- [16. 源码地图与扩展点](#16-源码地图与扩展点)
- [17. 附录：术语与参考](#17-附录术语与参考)

---

## 0. 五分钟上手

### 0.1 最小命令

```bash
# 终端 1：起服务
vllm serve Qwen/Qwen3-0.6B --port 8000

# 终端 2：压测（默认 random 数据集、1000 条、全速发送）
vllm bench serve --model Qwen/Qwen3-0.6B --num-prompts 1000
```

最小可复现版本（固定长度、固定 seed、落盘）：

```bash
vllm bench serve \
  --model Qwen/Qwen3-0.6B \
  --dataset-name random \
  --random-input-len 1024 --random-output-len 128 \
  --num-prompts 200 --max-concurrency 32 \
  --seed 0 --ignore-eos \
  --save-result --result-dir ./bench-results
```

### 0.2 十条"必知"事实

1. `vllm bench serve` 的延迟全部在**客户端**测量（发出 HTTP → 收到流式块），不是服务端统计。
2. `--backend vllm` 与 `--backend openai` 在这个版本是**同一个函数**（`async_request_openai_completions`），只是 label 不同；都打 `/v1/completions`。
3. `--backend` 与 `--endpoint` 必须匹配：chat 后端要求 URL 以 `chat/completions` 结尾，embeddings 要求 `embeddings`，rerank 要求 `rerank`，audio 要求 `transcriptions`/`translations`。
4. 默认 **不再把 `temperature` 设为 0**；不显式给 `--temperature 0` 时采样由服务端默认决定。
5. `--request-rate inf`（默认）表示所有请求 t=0 齐发；此时 `--burstiness` 无意义。
6. `--max-concurrency` 是**客户端**信号量：排队等待发生在发请求之前，因此**不计入 TTFT/E2EL**，但会计入 benchmark 总时长。
7. TTFT/ITL 依赖流式响应；非流式端点拿不到 TTFT（指标为 0）。chat 后端在 200 但零 chunk 时仍标 success，延迟为 0。
8. `random` / `random-mm` 在 openai 兼容后端下会**自动打开 `ignore_eos`**，保证生成到指定长度；`timed_trace` 强制打开。
9. `--goodput` 的数值单位是**毫秒**，键只允许 `ttft` / `tpot` / `e2el`；三个指标必须**同时**满足才计数。
10. 结果 JSON 只有在 `--save-detailed` 时才保留每请求明细（`ttfts`/`itls`/`generated_texts` 等），否则会被裁掉。

### 0.3 一页速查

| 需求 | 参数 |
| :-- | :-- |
| 固定 QPS | `--request-rate 8`（Poisson） |
| 更突发 / 更均匀 | `--burstiness 0.5` / `--burstiness 5` |
| 并发上限（模拟网关） | `--max-concurrency 64` |
| 逐渐加压找拐点 | `--ramp-up-strategy linear --ramp-up-start-rps 1 --ramp-up-end-rps 64` |
| SLO 达标吞吐 | `--goodput ttft:200 tpot:50` |
| 固定输出长度 | `--ignore-eos --random-output-len 256`（或 `--output-len 256`） |
| 造缓存命中流量 | `--dataset-name prefix_repetition` |
| 回放真实 trace | `--dataset-name timed_trace --dataset-path t.jsonl` |
| 扫参数画曲线 | `vllm bench sweep serve` + `vllm bench sweep plot` |
| 找 latency-throughput 拐点 | `vllm bench sweep serve_workload` |
| 抓 profiler | `--profile`（server 端要 `--profiler-config`） |
| 干扰/尾延迟归因 | `--probe-request-rate 20` |

---

## 1. 定位与测量边界

### 1.1 它是什么

`vllm bench serve` 是 vLLM 自带的**在线服务压测客户端**：

- 按指定**到达过程**（rate / burstiness / 并发上限 / trace 时间戳）向 OpenAI 兼容端点发请求；
- 逐请求测量首 token 时间、token 间隔、端到端延迟；
- 聚合吞吐、分位数、goodput、峰值并发，并输出 JSON / HTML / PNG；
- 自带多数据集、多后端、多模态、LoRA、投机解码指标采集。

### 1.2 bench 家族

| 子命令 | 测什么 | 是否走 HTTP |
| :-- | :-- | :-- |
| `vllm bench serve` | 在线吞吐 / 延迟 / goodput | ✅ |
| `vllm bench latency` | 单 batch 的纯模型延迟（引擎内） | ❌ |
| `vllm bench throughput` | 离线批量吞吐（`LLM.generate` 式） | ❌ |
| `vllm bench startup` | 引擎冷/热启动耗时 | ❌（引擎内起停） |
| `vllm bench mm-processor` | 多模态预处理各阶段耗时 | 引擎内 |
| `vllm bench sweep {serve,serve_workload,startup,plot,plot_pareto}` | 批量跑上面几个并画图 | 视子命令 |

结论：**要评估"服务"（含 HTTP、排队、调度、并发）用 serve；要评估"模型/引擎"本身用 latency / throughput。**

### 1.3 与 GuideLLM 的分工

官方明确：生产环境压测推荐 [GuideLLM](https://github.com/vllm-project/guidellm)（实时进度、自动报告、更灵活的负载）；
`vllm bench serve` 主要用于**功能验证、回归测试、参数扫描**。两者指标定义不完全一致，不要混着比。

### 1.4 测量点与"看不见的部分"

```
客户端                         网络                    vLLM
 ┌──────────────┐            ┌──────┐            ┌──────────────┐
 │ 到达调度      │            │      │            │ API → 引擎    │
 │ （sleep/信号量）│ ──POST──▶ │      │ ──▶        │ 排队/调度/推理 │
 └──────────────┘            └──────┘            └──────────────┘
        ↑ 不计入延迟              ↑ 计入 RTT          ↑ 服务端时间被包含
```

- **计入**：HTTP 建连（连接池复用）、网络 RTT、服务端排队 + 推理 + 流式回传。
- **不计入单请求延迟**：`--request-rate` 的 sleep、`--max-concurrency` 的客户端排队。
- **计入总时长**：上面两者都会拉长 `duration`，从而影响吞吐。
- 因此：`吞吐 = 完成数 / 墙钟`，`延迟 = 实际发出后的端到端`，两者口径不同，不要互相反推。

---

## 2. 运行方式与前置条件

### 2.1 三种入口

```bash
# 1) 已安装 vLLM 的 CLI
vllm bench serve --help

# 2) 不装 vLLM 也能用模块入口（官方 tip）
python -m vllm.entrypoints.cli.main bench serve --help

# 3) 老脚本入口（已废弃，只打印提示）
python benchmarks/benchmark_serving.py   # → 提示改用 vllm bench serve 并 exit(1)
```

### 2.2 Rust 前端（可选）

设置 `VLLM_USE_RUST_BENCH=1` 且 `VLLM_RUST_FRONTEND_PATH` 指向 `vllm-rs` 时，`vllm bench serve` 会 `exec` 到 Rust 实现
（`vllm/entrypoints/cli/benchmark/main.py:maybe_exec_rust_bench`）。默认关闭；行为与本实现可能有差异。

### 2.3 前置条件清单

| 项 | 要求 |
| :-- | :-- |
| 服务 | 已启动的 OpenAI 兼容 server（`vllm serve` 或任何兼容实现） |
| 模型名 | `--model`；不给则自动 `GET /v1/models` 取第一个 |
| tokenizer | 本地可用（HF tokenizer）；否则可 `--tokenizer` 指定，或 `--skip-tokenizer-init`（见坑） |
| 数据集 | `random` 类不需要文件；其余需要 `--dataset-path` |
| Python 依赖 | `aiohttp`、`numpy`、`tqdm` 必需；`pandas`（custom/burstgpt/spec/speed、sweep 汇总）、`soundfile`（audio）、`Pillow`（图像）、`opencv-python`（视频）、`plotly`（timeline）、`matplotlib`（dataset stats）、`termplotlib`+`gnuplot`（终端图）、`seaborn`（sweep 图）按需 |
| 认证 | 环境变量 `OPENAI_API_KEY` 会自动加 `Authorization: Bearer ...`；也可 `--header` |

### 2.4 服务端要开的东西

| 功能 | 服务端要求 |
| :-- | :-- |
| 自动发现模型 | `/v1/models` |
| 长度校准 | `/tokenize`、`/detokenize`（不可用时只打 WARNING 并跳过） |
| 投机解码指标 | `/metrics` 暴露 `vllm:spec_decode_*_total` |
| diffusion 指标 | `/metrics` 暴露 `vllm:diffusion*_total` |
| profiler | server 端 `--profiler-config`，并暴露 `/start_profile`、`/stop_profile` |
| sweep 缓存清理 | `VLLM_SERVER_DEV_MODE=1` + `/reset_prefix_cache`、`/reset_mm_cache`、`/reset_encoder_cache` |

---

## 3. 命令行总览与参数总表

### 3.1 结构

```
vllm bench serve [options]
  ├─ options                    （57 个通用参数）
  ├─ custom dataset options     （2）
  ├─ spec bench dataset options （2）
  ├─ sonnet dataset options     （3）
  ├─ sharegpt dataset options   （1）
  ├─ timed-trace dataset options（6）
  ├─ blazedit dataset options   （2）
  ├─ asr dataset options        （2）
  ├─ random dataset options     （6）
  ├─ random multimodal ...      （4）
  ├─ hf dataset options         （4）
  ├─ BFCL dataset options       （1）
  ├─ prefix repetition ...      （4）
  ├─ speed bench dataset ...    （3）
  └─ sampling parameters        （7）
```

总计 **104** 个 flag。参数组只是帮助阅读；同一份 Namespace 全量传入各层。

### 3.2 通用参数（57）

| 参数 | 默认 | 说明 |
| :-- | :-- | :-- |
| `--backend` | `openai` | 12 选 1，见第 5 节 |
| `--base-url` | `None` | 完整 base（含 scheme）；给了就忽略 host/port |
| `--host` | `127.0.0.1` | 与 port 拼 URL |
| `--port` | `8000` | 同上 |
| `--endpoint` | `/v1/completions` | 必须与 backend 后缀匹配 |
| `--model` | `None` | 不给则从 `/v1/models` 取第一个 |
| `--served-model-name` | `None` | 请求体里用的 name；默认等于 model |
| `--tokenizer` | `None` | 默认用 model id |
| `--tokenizer-mode` | `auto` | `auto/hf/slow/mistral/deepseek_v32` 或插件值 |
| `--trust-remote-code` | `False` | HF 可信代码 |
| `--skip-tokenizer-init` | `False` | 不加载 tokenizer（许多数据集会失败，见坑） |
| `--insecure` | `False` | 跳过 TLS 校验 |
| `--header` | `None` | `KEY=VALUE`，可多个 |
| `--extra-body` | `None` | JSON，合并进请求体 |
| `--dataset-name` | `random` | 14 选 1 |
| `--dataset-path` | `None` | 文件路径或 HF id |
| `--num-prompts` | `1000` | 请求数；部分数据集 `<=0` 表示全量 |
| `--disable-shuffle` | `False` | 关闭数据打乱，保证顺序确定 |
| `--no-oversample` | `False` | 样本不足时不重复补齐 |
| `--no-stream` | `False` | 关闭 HF 数据集 streaming 加载 |
| `--enable-multimodal-chat` | `False` | 把 prompt 包成多模态 chat 结构 |
| `--skip-chat-template` | `False` | 跳过 chat template |
| `--chat-template-kwargs` | `None` | JSON，传给 `apply_chat_template` |
| `--request-rate` | `inf` | req/s；`inf` = 全齐发 |
| `--burstiness` | `1.0` | gamma 形状参数；1=Poisson，`inf`=等间隔 |
| `--max-concurrency` | `None` | 客户端并发上限 |
| `--ramp-up-strategy` | `None` | `linear` / `exponential` |
| `--ramp-up-start-rps` | `None` | 起始 RPS |
| `--ramp-up-end-rps` | `None` | 结束 RPS |
| `--probe-request-rate` | `0.0` | >0 时发旁路探针（req/s） |
| `--num-warmups` | `0` | 预热请求数（用首条样本重复） |
| `--ready-check-timeout-sec` | `0` | 0=跳过就绪检查；>0 则每 5s 重试 |
| `--ignore-eos` | `False` | 请求体加 `ignore_eos` |
| `--seed` | `0` | 全局 random/numpy 种子 |
| `--self-timed` / `--no-self-timed` | `None` | 仅 `timed_trace` 可用，按 trace 时间戳回放 |
| `--metric-percentiles` | `99` | 逗号分隔，如 `50,90,99` |
| `--percentile-metrics` | `None` | 默认生成式 `ttft,tpot,itl`；pooling `e2el` |
| `--goodput` | `None` | `KEY:MS` 对，可多组 |
| `--label` | `None` | 结果文件前缀；默认 backend |
| `--metadata` | `None` | `KEY=VALUE`，**平铺**写进 JSON 顶层 |
| `--result-dir` | `None` | 结果目录（自动创建） |
| `--result-filename` | `None` | 覆盖完整文件名 |
| `--save-result` | `False` | 写 JSON |
| `--append-result` | `False` | 追加写（一行一个 JSON） |
| `--save-detailed` | `False` | 保留每请求明细字段 |
| `--plot-timeline` | `False` | 生成 `.timeline.html` |
| `--plot-dataset-stats` | `False` | 生成 `.dataset_stats.png`（见坑） |
| `--timeline-itl-thresholds` | `25,50` | 时间线配色阈值（ms） |
| `--profile` | `False` | 调 `/start_profile`、`/stop_profile` |
| `--logprobs` | `None` | 仅 completions 请求体 |
| `--use-beam-search` | `False` | **本版本无实际作用**（仅解析） |
| `--lora-modules` | `None` | 用 LoRA 名替换请求里的 model |
| `--lora-assignment` | `random` | `random` / `round-robin` |
| `--disable-tqdm` | `False` | 关进度条 |
| `--request-id-prefix` | `bench-<8hex>-` | 请求 id 前缀 + 序号 |
| `--input-len` | `None` | 通用入口：映射到 random/sonnet 的 input |
| `--output-len` | `None` | 通用入口：映射到 random/sonnet/sharegpt/custom/hf/spec_bench/prefix_repetition |

### 3.3 数据集专属参数

| 组 | 参数 | 默认 |
| :-- | :-- | :-- |
| custom | `--custom-output-len` | `256`（`-1` 表示用样本里的 `output_tokens`） |
| custom | `--custom-ensure-client-side-data` | `False` |
| spec bench | `--spec-bench-output-len` | `256` |
| spec bench | `--spec-bench-category` | `None`（全部类目） |
| sonnet | `--sonnet-input-len` | `550` |
| sonnet | `--sonnet-output-len` | `150` |
| sonnet | `--sonnet-prefix-len` | `200` |
| sharegpt | `--sharegpt-output-len` | `None`（用数据集里的答案长度） |
| timed-trace | `--timed-trace-chunk-hash-size` | `16`（Moonshot 512 / Qwen 16） |
| timed-trace | `--timed-trace-sec-multiplier` | `1`（ms→s 用 `0.001`） |
| timed-trace | `--timed-trace-label-timestamp` | `timestamp` |
| timed-trace | `--timed-trace-label-input-length` | `input_length` |
| timed-trace | `--timed-trace-label-output-length` | `output_length` |
| timed-trace | `--timed-trace-label-hash-ids` | `hash_ids` |
| blazedit | `--blazedit-min-distance` / `--blazedit-max-distance` | `0.0` / `1.0` |
| asr | `--asr-min-audio-len-sec` / `--asr-max-audio-len-sec` | `0.0` / `inf` |
| random | `--random-input-len` | `1024` |
| random | `--random-output-len` | `128` |
| random | `--random-prefix-len` | `0` |
| random | `--random-range-ratio` | `"0.0"`（可传 `{"input":0.3,"output":0.5}`） |
| random | `--random-batch-size` | `1`（embeddings 用） |
| random | `--no-reranker` | `False`（rerank 语义开关） |
| random-mm | `--random-mm-base-items-per-request` | `1` |
| random-mm | `--random-mm-num-mm-items-range-ratio` | `0.0` |
| random-mm | `--random-mm-limit-mm-per-prompt` | `{"image":255,"video":1}` |
| random-mm | `--random-mm-bucket-config` | `{(256,256,1):0.5,(720,1280,1):0.5,(720,1280,16):0.0}` |
| hf | `--hf-subset` / `--hf-split` / `--hf-name` / `--hf-output-len` | 全 `None` |
| BFCL | `--bfcl-categories` | `None` → `simple,live_simple,multiple` |
| prefix repetition | `--prefix-repetition-prefix-len` | `256` |
| prefix repetition | `--prefix-repetition-suffix-len` | `256` |
| prefix repetition | `--prefix-repetition-num-prefixes` | `10` |
| prefix repetition | `--prefix-repetition-output-len` | `128` |
| speed bench | `--speed-bench-dataset-subset` | `qualitative` |
| speed bench | `--speed-bench-output-len` | `4096` |
| speed bench | `--speed-bench-category` | `None` |
| sampling | `--temperature` / `--top-p` / `--top-k` / `--min-p` | 全 `None` |
| sampling | `--frequency-penalty` / `--presence-penalty` / `--repetition-penalty` | 全 `None` |

> 采样参数只对 **openai 兼容后端**（completions/chat）生效，否则启动即报错。

---

## 4. 执行流程（源码级）

### 4.1 `main_async`（`vllm/benchmarks/serve.py:1966`）

| 阶段 | 行为 |
| :-- | :-- |
| 1. 参数校验 | 时间线阈值格式、ramp-up 组合合法性 |
| 2. URL | `base_url + endpoint`；`base_url` 缺省用 `host:port`（IPv6 自动加方括号） |
| 3. headers | `--header` 解析为 dict；`--insecure` 关闭 TLS 校验 |
| 4. 模型 | 未给 `--model` → `GET /v1/models` 取第一个 |
| 5. tokenizer | 按 `--tokenizer`/`--tokenizer-mode` 加载；`--skip-tokenizer-init` 则 None |
| 6. 数据集校验 | 未给 `--dataset-name` 报错；`random` 类禁止 `--dataset-path` |
| 7. 长度映射 | `--input-len` → random/sonnet；`--output-len` → 7 个数据集 |
| 8. 隐式默认 | random/random-mm + openai 兼容 → `ignore_eos=True`；timed_trace → `self_timed=True` |
| 9. 数据集 | `get_samples(args, tokenizer)`（`datasets.py:2095`） |
| 10. 对齐 | random/prefix_repetition 调 `/tokenize` 校准长度 |
| 11. goodput | 解析 SLO，校验键与值 |
| 12. 采样参数 | 只允许 openai 兼容后端；未给 temperature 会打印 WARNING |
| 13. 压测 | `benchmark(...)`（:768） |
| 14. 结果 | 组装 JSON、打印、绘图、落盘 |

### 4.2 `benchmark()`（:768）

```
建 aiohttp 连接池（keep-alive 60s，总超时 6h）
  ↓
可选 ready check：用第一条样本真发一次，失败每 5s 重试
  ↓
可选 warmup：用同一 test_input 发 N 次并丢弃
  ↓
可选 profile 开始（POST /start_profile）
  ↓
记录 /metrics 基线（spec decode / diffusion）
  ↓
按 get_request() 的到达时间派发任务（可选信号量限流 + 可选探针任务）
  ↓
asyncio.gather 全部完成 → 停探针 → 关进度条
  ↓
记录 /metrics 终值，算 spec/diffusion 增量
  ↓
calculate_metrics（生成式）或 calculate_metrics_for_embeddings
  ↓
打印结果 → 可选 profile 结束（POST /stop_profile）→ 关 session
```

要点：

- **warmup 只重复第一条样本**，不是打乱后的数据集；用于 JIT/编译/缓存预热，不产生统计。
- **探针请求**（`--probe-request-rate`）绕过信号量，固定 `"Hi"`、输出 1 token，单独统计延迟。
- **客户端限流**：`limited_request_func` 先 `async with semaphore` 再调用请求函数；计时从请求函数内部开始，
  所以信号量等待不计入 TTFT/E2EL。
- **LoRA**：每个请求把 `model` 字段替换成所选 LoRA 模块名（`lora_modules_iter`）。
- **profile**：开始/结束都通过当前后端的请求函数发到 `/start_profile`、`/stop_profile`（URL 校验允许 `profile` 后缀）。

### 4.3 到达过程 `get_request()`（:393）

- 非 self-timed：逐条算 `current_rate`（ramp-up 会变化）→ 采样 gamma 间隔 → 累积成 `delay_ts`。
- `request_rate=inf`：所有 delay 为 0。
- `burstiness=inf`：间隔恒为 `1/rate`。
- 无 ramp-up 时把 `delay_ts` **整体缩放**到 `num_prompts / rate`，消除随机间隔带来的总时长漂移。
- self-timed：`delay_ts` 直接用 trace 的 `timestamp`（已乘 `--timed-trace-sec-multiplier`）。
- 发送循环按 `delay_ts` 与 `start_ts` 的差 `asyncio.sleep`。

---

## 5. 后端与协议

### 5.1 总表

| backend | 请求函数 | 必须的 URL 后缀 | 指标能力 |
| :-- | :-- | :-- | :-- |
| `vllm` | `async_request_openai_completions` | `completions` | TTFT/ITL/TPOT/E2EL |
| `openai` | 同上（**别名**） | `completions` | 同上 |
| `openai-chat` | `async_request_openai_chat_completions` | `chat/completions` | 同上 |
| `openai-audio` | `async_request_openai_audio` | `transcriptions`/`translations` | E2EL + RTFx |
| `openai-embeddings` | `async_request_openai_embeddings` | `embeddings` | E2EL |
| `openai-embeddings-chat` | `async_request_openai_embeddings_chat` | `embeddings` | E2EL |
| `openai-embeddings-clip` | `async_request_openai_embeddings_clip` | `embeddings` | E2EL |
| `openai-embeddings-vlm2vec` | `async_request_openai_embeddings_vlm2vec` | `embeddings` | E2EL |
| `infinity-embeddings` | `async_request_infinity_embeddings` | `embeddings` | E2EL |
| `infinity-embeddings-clip` | `async_request_infinity_embeddings_clip` | `embeddings` | E2EL |
| `vllm-pooling` | `async_request_vllm_pooling` | `pooling` | E2EL |
| `vllm-rerank` | `async_request_vllm_rerank` | `rerank` | E2EL |

`_validate_api_url` 额外允许以 `profile` 结尾，供 `/start_profile`、`/stop_profile` 复用同一函数。

### 5.2 各后端的请求与计时

**completions（`vllm`/`openai`）**

```json
{
  "model": "...",
  "prompt": "...",
  "repetition_penalty": 1.0,
  "max_tokens": N,
  "logprobs": null,
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

- 计时：第一个含 `choices` 的 chunk → TTFT；后续 chunk 间隔 → ITL；最后一个 chunk → latency。
- `usage.completion_tokens` 覆盖输出 token 数；`usage.prompt_tokens` 覆盖 prompt 长度。
- 若 200 但从未收到有效 chunk：`success=False`，错误信息 "Never received a valid chunk to calculate TTFT."

**chat（`openai-chat`）**

- 字段为 `messages` + `max_completion_tokens`（不是 `max_tokens`）。
- `prompt` 会自动包成 `{"role":"user","content":[...]}`；若数据集给了 `chat_messages`（如 BFCL）则直接使用。
- **只要 HTTP 200 就标 success**；空流会导致 ttft/latency 为 0 而不报错。
- 多模态内容放在 `content` 数组里（`image_url` / `input_audio` 等）。

**audio（`openai-audio`）**

- multipart/form-data 上传 WAV；`stream=true` + usage 字段。
- 请求体写死 `"language": "en"`（当前实现），其他语言需自行改代码。
- `input_audio_duration` 用于 `rtfx = 音频总时长 / 墙钟`。

**embeddings / pooling / rerank**

- 单次 POST，无流式；`ttft = latency = 整个响应耗时`。
- `prompt_len` 从响应 `usage.prompt_tokens` 取。
- `truncate_prompt_tokens: -1`（embedding/rerank）避免超长被截断。
- `openai-embeddings-chat` 用 `messages`；`clip` 会把 prompt 清空（纯图）；`vlm2vec` 按请求序号奇偶交替
  "纯图 / 图文"提示词（序号取自 `x-request-id` 末尾数字）。
- `vllm-rerank`：`query = prompt[0]`，`documents = prompt[1:]`，断言至少 2 段。
- `infinity-embeddings`：`input` 取文本或多模态 URL，`modality` 由 `type` 前缀推出。

### 5.3 认证、HTTPS、header 优先级

```
默认 headers（_get_headers）
  └─ Content-Type（按后端）
  └─ Authorization: Bearer $OPENAI_API_KEY（若设置）
--header 覆盖默认
x-request-id 最后写入（来自 --request-id-prefix + 序号）
```

- `--base-url https://...` 自动启用默认 SSL；`--insecure` 传 `False` 关闭校验。
- header 值里 `=` 只按第一个切分，`KEY=VALUE` 格式错误会直接报错。

### 5.4 后端选择的坑

| 现象 | 原因 |
| :-- | :-- |
| `URL must end with one of: {'completions','profile'}` | 用 chat 后端却给了 `/v1/completions`（或反之） |
| 采样参数报错 | 非 openai 兼容后端（如 embeddings/audio） |
| chat 请求全部 0 延迟 | 服务端返回 200 但没有流式 chunk（例如仿真器缺 trace） |
| audio 全部失败 | 缺 `soundfile`，或端点后缀不对 |
| rerank 断言失败 | prompt 不是 `[query, doc...]`（需用 `random-rerank`） |

---

## 6. 数据集

### 6.1 总表（14 种）

| `--dataset-name` | 类别 | 数据来源 | 需要 tokenizer | 关键参数 |
| :-- | :-- | :-- | :-- | :-- |
| `random` | 合成 | 无 | 是 | `--random-*` |
| `random-mm` | 合成 | 无（cv2/Pillow） | 是 | `--random-mm-*` |
| `random-rerank` | 合成 | 无 | 是 | `--random-batch-size`、`--no-reranker` |
| `prefix_repetition` | 合成 | 无 | 是 | `--prefix-repetition-*` |
| `sonnet` | 合成/语料 | 本地 txt（poem） | 是 | `--sonnet-*`（**已 deprecated**） |
| `sharegpt` | 语料 | 本地 JSON | 是 | `--sharegpt-output-len` |
| `custom` | 语料 | 本地 JSONL | 可空 | `--custom-output-len`、`--skip-chat-template` |
| `custom_image` | 多模态 | 本地 JSONL | 可空 | `--custom-ensure-client-side-data` |
| `custom_audio` | 多模态 | 本地 JSONL | 可空 | 与 `--enable-multimodal-chat` 配合 |
| `hf` | 语料 | HuggingFace | 是 | `--hf-*`、`--bfcl-*`、`--asr-*` 等 |
| `timed_trace` | 回放 | 本地 JSONL | 是 | `--timed-trace-*` |
| `spec_bench` | 专用 | 本地 JSONL | 是 | `--spec-bench-*` |
| `speed_bench` | 专用 | 本地目录 | 是 | `--speed-bench-*` |
| `burstgpt` | 专用 | 本地 CSV | 是 | — |

### 6.2 合成类

**`random`**（`datasets.py:559`）

- 长度：`input_len`、`output_len` 均值；`range_ratio` 控制均匀分布范围
  `[len*(1-r), len*(1+r)]`；可分别给 input/output（JSON dict）。
- `--random-prefix-len`：固定前缀（同一 seed 下所有请求共享），模拟系统提示词缓存命中。
- 生成方式：`(offset + index + arange(input_len)) % vocab_size`，再 decode→encode 校准到精确长度；
  因此**可复现**且**不依赖语料**。
- `--random-batch-size > 1`：把多条 prompt 合成一个 `list[str]` 请求（embeddings 批测）。
- 默认 `range_ratio=0`（定长），`prefix_len=0`。

**`random-mm`**（:908）

- 生成**纯随机 RGB 噪声**图片（Pillow）或视频（cv2，`num_frames>1`）；这是"最坏压缩"压力测试，不代表真实图片分布。
- `--random-mm-bucket-config`：`(H,W,T) → 概率`，T=1 为图、T>1 为视频；概率自动归一化。
- `--random-mm-limit-mm-per-prompt`：按模态硬上限；达到上限后该模态 bucket 被剔除并重新归一化。
- `--random-mm-base-items-per-request` + `--random-mm-num-mm-items-range-ratio`：每请求条数。
- 官方标注**当前只支持图片采样**；视频分支在代码里存在但默认概率 0，慎用。
- 必须配 `openai-chat`（或 `openai-audio`）后端。

**`random-rerank`**（:780）

- 生成 `[query, doc1, doc2, ...]` 的批请求；`--random-batch-size` = 每请求文档数。
- `is_reranker=True` 时 query 与文档都按 `input_len` 切分；`--no-reranker` 表示模型用 embedding 跑 `/v1/rerank`，
  此时补一个 query 语义、文档数 `batchsize-1`，token 记账方式不同（官方文档有说明）。

**`prefix_repetition`**（:4380）

- 生成 `num_prefixes` 个固定前缀，每个前缀下 `num_prompts // num_prefixes` 条不同后缀。
- 实际请求数 = `num_prefixes * floor(num_prompts / num_prefixes)`，**可能少于 `--num-prompts`**；不做 oversample。
- 默认会 shuffle（除非 `--disable-shuffle`）。
- 用途：制造"高前缀缓存命中"，观察 APC 对 TTFT/吞吐的影响。

**`sonnet`**（:3102，**deprecated**）

- 从 txt 读诗行，拼成约 `input_len` 的 prompt；`prefix_len` 为共享前缀；强制走 chat template。
- 限制：`input_len` 必须大于模板 base 长度；生成循环可能因行长不足而迭代。
- 新项目建议改用 `random` + `prefix_len` 或 `prefix_repetition`。

### 6.3 语料类

**`sharegpt`**（:1348）

- 读 JSON 数组，条目需 `conversations` 且至少 2 轮；取第 1 轮 Q/A。
- 过滤规则（`is_valid_sequence`）：prompt ≥ 4 token、答案 ≥ 4 token、prompt ≤ 1024、总长 ≤ 2048。
  **长样本会被静默丢弃**，样本不足时自动 oversample。
- 支持条目里的 `image` / `video` 字段（多模态），配合 `--enable-multimodal-chat`。

**`custom`**（:2505）

- 仅支持 `.jsonl`（pandas 读）；必须有 `prompt` 列；`output_tokens` 可选。
- `--custom-output-len` 默认 256；设为 `-1` 时用样本 `output_tokens`（缺失则报错）。
- 默认会套 chat template（`add_generation_prompt=True`）；数据自带模板时用 `--skip-chat-template`。
- `--num-prompts <= 0` 表示用全部样本。

**`custom_image`**（:2634）

- 两种格式：`{"prompt", "image_files": [...]}` 或 `{"content": [text/image/image_url...]}`。
- 本地路径会转成 `file://`；`--custom-ensure-client-side-data` 会在客户端下载/编码成 base64。
- 必须 `openai-chat` 后端。

**`custom_audio`**（:2919）

- `{"prompt", "audio": "/path.wav"}`。
- Whisper 类：`openai-audio` + `/v1/audio/transcriptions`（不需要 chat）。
- Qwen2-Audio 类：`openai-chat` + `--enable-multimodal-chat`（音频转 base64）。

**`hf`**（:3280）

- `--dataset-path` 既可以是 HF id，也可以是本地目录 + `--hf-name` 指定 repo id。
- 默认 **streaming 加载**；`--no-stream` 关闭。
- 按 `dataset_path`/`hf_name` 分派到 15 个子类（见表 6.6）。

### 6.4 回放类：`timed_trace`（:1439）

输入 JSONL，每行至少包含（字段名可配）：

```json
{"timestamp": 0.123, "input_length": 2048, "output_length": 128, "hash_ids": [111, 222, 333]}
```

- `hash_ids` 中的每个 hash 展开成 `chunk_hash_size` 个 token（**同一个 hash 总是展开成同一段 token**，
  因此跨请求前缀可命中）；最后一个 chunk 可能不足额。
- 时间戳 × `--timed-trace-sec-multiplier` 作为到达时间；默认 `self_timed=True`。
- 强制 `ignore_eos=True`；后端必须是 `vllm` 或 `openai`（因为 prompt 是预 tokenize 的 `list[int]`）。
- 用途：真实 trace 回放、前缀缓存效果评估。

### 6.5 专用数据集

**`spec_bench`**：Spec-Bench `question.jsonl`，取 `turns[0]`；`--spec-bench-category` 过滤。
**`speed_bench`**：SPEED-Bench 目录（内含 `<subset>.jsonl`），取 `messages[0].content`；有 6 个 subset。
**`burstgpt`**：CSV，只保留 `Model == "GPT-4"` 且 response tokens > 0 的行；按行里的 input/output 长度
生成合成 token 序列；样本不足时有放回抽样。
**`BFCL`**：`gorilla-llm/Berkeley-Function-Calling-Leaderboard`，按类目下载 `BFCL_v3_<cat>.json`；
只取第一轮；把 BFCL 方言 schema 转成 JSON Schema；每请求带 `tools` + `tool_choice=auto`；
必须 `openai-chat`；默认输出 512。
**`ASR`**：`openslr/librispeech_asr` 等；按音频时长过滤；支持 array / bytes / path 三种音频形态。
**`BlazEdit`**：`vdaita/edit_5k_char` / `edit_10k_char`，按编辑距离过滤。
**`MLPerf`**：`mgoin/mlperf-inference-llama2-data`、`llama3.1-data`。
**`MMStar`**：`Lin-Chen/MMStar`。

### 6.6 `hf` 分派表

| 子类 | 支持的 dataset path | 默认 split | 多模态 |
| :-- | :-- | :-- | :-- |
| `VisionArenaDataset` | `lmarena-ai/VisionArena-Chat`、`lmarena-ai/vision-arena-bench-v0.1` | train | ✅ |
| `MMVUDataset` | `yale-nlp/MMVU` | validation | ✅ |
| `InstructCoderDataset` | `likaixin/InstructCoder` | train | ❌ |
| `MTBenchDataset` | `philschmid/mt-bench` | train | ❌ |
| `HumanEvalDataset` | `openai/openai_humaneval` | test | ❌ |
| `GSM8KDataset` | `openai/gsm8k`（默认 subset `main`） | test | ❌ |
| `MultiModalConversationDataset` | `lmms-lab/LLaVA-OneVision-Data` | 默认 | ✅ |
| `ConversationDataset` | `Aeala/ShareGPT_Vicuna_unfiltered` | 默认 | ❌ |
| `AIMODataset` | `AI-MO/aimo-validation-aime`、`NuminaMath-1.5`、`-CoT` | train | ❌ |
| `NextEditPredictionDataset` | `zed-industries/zeta` | train | ❌ |
| `ASRDataset` | librispeech、voxpopuli、tedlium、ami、gigaspeech、spgispeech 等 | train | ✅ |
| `BlazeditDataset` | `vdaita/edit_5k_char`、`edit_10k_char` | train | ❌ |
| `MLPerfDataset` | `mgoin/mlperf-inference-llama2-data`、`llama3.1-data` | train | ❌ |
| `MMStarDataset` | `Lin-Chen/MMStar` | val | ✅ |
| `BFCLDataset` | `gorilla-llm/Berkeley-Function-Calling-Leaderboard` | train（占位） | ❌ |

多模态子类要求后端是 `openai-chat`/`openai-audio` 或 `*embeddings*`，否则报错。

### 6.7 长度与采样控制

- **通用映射**：`--input-len` → `random_input_len`、`sonnet_input_len`；
  `--output-len` → `random/sonnet/sharegpt/custom/hf/spec_bench/prefix_repetition`。
- 数据集专属参数优先：两者同时给时，专属参数在 **映射之后** 生效吗？
  实际顺序是：先映射（覆盖专属参数），再加载数据集。因此 **`--output-len` 会覆盖你写的专属参数**。
- `--no-oversample`：样本不足时不重复；否则随机复制并重新编号（会检查 request_id 唯一）。
- `--disable-shuffle`：保持数据集顺序（`hf` 不 shuffle stream）。
- **服务端 tokenizer 校准**（`serve.py:74`）：`random`/`prefix_repetition` 会调 `/tokenize` 验证首条长度；
  不一致时把每条 prompt 重新 tokenize 并截断到目标长度。`/tokenize` 不可用则跳过（WARNING）。

### 6.8 数据格式速查

```jsonl
// custom
{"prompt": "What is the capital of India?", "output_tokens": 10}

// custom_image（二选一）
{"prompt": "How many animals?", "image_files": ["/img/a.jpg"]}
{"content": [{"type": "text", "text": "Compare "}, {"type": "image", "image": "/img/a.png"}]}

// custom_audio
{"prompt": "Transcribe the audio.", "audio": "/audio/a.wav"}

// timed_trace
{"timestamp": 0.0, "input_length": 2048, "output_length": 128, "hash_ids": [1,2,3]}
```

---

## 7. 负载模型

### 7.1 三种基本形态

| 形态 | 参数 | 语义 |
| :-- | :-- | :-- |
| 全速（默认） | `--request-rate inf` | t=0 创建所有任务；吞吐上限测试 |
| 固定 QPS | `--request-rate 8` | Poisson/ gamma 到达 |
| 固定并发 | `--max-concurrency 64`（常配 `inf`） | 模拟网关限流；请求按完成速度补位 |

### 7.2 rate 与 burstiness 的数学

间隔 `Δt ~ Gamma(shape=burstiness, scale=1/(rate*burstiness))`：

- 均值 `1/rate`，方差 `1/(rate² * burstiness)`，CV = `1/sqrt(burstiness)`。
- `burstiness=1` → 指数分布 = Poisson；`0.1` → CV≈3.16（很突发）；`5` → CV≈0.45（均匀）；
  `inf` → 恒定间隔。
- 非 ramp-up 时会把所有间隔整体缩放，使**最后一条**的发送时间恰为 `num_prompts / rate`。

推荐（官方文档给的用法）：

| 场景 | rate | burstiness | max-concurrency |
| :-- | :-- | :-- | :-- |
| 最大吞吐 | inf | 无影响 | 有（网关上限） |
| 真实基线 | 5–20 | 1.0 | 不限 |
| 压力/韧性 | 20–100 | 0.1–0.5 | 不限 |
| 延迟分析 | 1–10 | 2–5 | 不限 |
| 容量规划 | 变量 | 1.0 | 有 |
| SLA 验证 | 目标 QPS | 1.0 | SLA 上限 |

### 7.3 ramp-up

```bash
--ramp-up-strategy linear --ramp-up-start-rps 1 --ramp-up-end-rps 64
```

- 第 i 条请求的速率按进度线性/指数插值；不允许同时给 `--request-rate`（给了会报错）。
- 结果 JSON 里产生 `rps_change_events`（每个整数 RPS 首次出现的时间）。
- 用途：一次跑完"从轻载到过载"，观察延迟拐点。

### 7.4 `--max-concurrency` 的真实作用

- 客户端 `asyncio.Semaphore`；并发满后任务挂起。
- **挂起期间不计入单请求延迟**（计时在请求函数内），但会拉长总时长。
- 也会设置 aiohttp 连接池的 `limit`，因此同时限制 TCP 连接数。
- 与 `--request-rate` 同给时，实际速率可能低于设定值（服务端跟不上）。

### 7.5 探针请求

```bash
--probe-request-rate 20
```

- 固定文本 `"Hi"`、输出 1 token、绕过并发限制。
- 单独统计 `probe_completed/failed/median_e2el/p99/max`。
- 用途：量化主负载对"无关小请求"的干扰（如多模态预处理阻塞前端）。

### 7.6 预热与就绪检查

- `--ready-check-timeout-sec 0`（默认）→ 完全跳过首条探测；>0 时真发首条样本，
  失败每 5s 重试，直到超时（超时后仍返回最后一次失败，由调用方决定）。
- `--num-warmups N`：用**同一条** test_input 发 N 次，完成后再开始计时。
- 冷启动会显著抬高 TTFT（首请求编译/分配）；正式实验建议先跑一轮完整负载并丢弃。

### 7.7 self-timed（trace 回放）

- 只允许 `timed_trace`；默认开启，`--no-self-timed` 可关闭并改用 rate 控制。
- 关闭后 trace 的时间戳被忽略，用 `--request-rate` 重新定速。

### 7.8 可复现性清单

固定：`--seed`、`--disable-shuffle`、`--random-range-ratio`、`--num-warmups`、`--temperature 0`、
`--ignore-eos`、同一 server 配置、同一 `--request-rate`/`--max-concurrency`。
注意：`--request-rate` 有限值时，到达时间仍受 gamma 随机影响（由 seed 固定）。

---

## 8. 指标定义与统计口径

### 8.1 指标总表

| 指标 | 含义 | 统计方式 |
| :-- | :-- | :-- |
| TTFT | 发出请求 → 第一个流式块 | 每请求，再 mean/median/std/分位 |
| ITL | 相邻流式块间隔 | **所有请求汇总**后算分位 |
| TPOT | `(e2el − ttft) / (输出 token 数 − 1)` | 每请求先算，再在请求间平均 |
| E2EL | 发出 → 收到最后一块 | 每请求 |
| request_throughput | 完成请求 / duration | — |
| output_throughput | 生成 token / duration | — |
| total_token_throughput | (输入+输出) / duration | — |
| request_goodput | 满足全部 SLO 的请求 / duration | 无 SLO 时 JSON 为 `null` |
| max_output_tokens_per_s | 1s 桶内的 token 峰值 | 成功请求 |
| max_concurrent_requests | 1s 桶内同时活跃请求峰值 | 成功请求 |
| rtfx | 音频总时长 / duration | ASR |

### 8.2 公式与聚合细节

- **TTFT**：completions 在第一个含 `choices` 的 chunk 记时；chat 在第一个含 `choices` 的 chunk 记时
  （即使 `delta.content` 为 None）。
- **ITL**：`itl.append(now - last_chunk_ts)`；报告时把所有请求的 itl 拼起来算 mean/std/median/分位，
  **不是**"每请求分位再平均"。
- **TPOT**：若输出 ≤ 1 token，TPOT 记 0（仍参与 goodput）。
- **E2EL**：`latency`。
- **duration**：从开始派发到 `gather` 结束的墙钟，包含到达间隔与客户端排队。
- **分母**：吞吐类指标都用 `duration`；失败请求不计入完成数，但会出现在 `failed` 和明细数组里。

### 8.3 goodput

```bash
--goodput ttft:200 tpot:50 e2el:5000
```

- 值单位毫秒；键只能是 `ttft`/`tpot`/`e2el`。
- 判定：**所有**给定 SLO 都满足（`measured <= slo`）才算 good；`goodput = good / duration`。
- 单 token 响应的 TPOT=0，因此 TPOT SLO 对它恒成立。

### 8.4 峰值指标

- 以每个成功请求的 token 时间戳（`start + ttft + 累计 itl`）落入 1s 桶，统计每桶 token 数，取最大值。
- 并发峰值：把每个请求的活跃区间映射到秒桶，统计每桶活跃数，取最大值。
- 这两个值反映"瞬时压力"，与平均吞吐互补。

### 8.5 投机解码 / diffusion / RTFx

- **spec decode**：压测前后各拉一次 `/metrics`，对 `vllm:spec_decode_*_total` 求增量；
  计算接受率 `accepted/draft_tokens`、接受长度 `1 + accepted/drafts`、逐位置接受率。
  没有该类指标时返回 None（JSON 里不出现）。
- **diffusion**：同理，对 `vllm:diffusion*_total` 求增量，计算 committed throughput、
  每 canvas 去噪步数、每步 committed token。
- **RTFx**（ASR）：`sum(input_audio_duration) / duration`，>1 表示比实时快。

### 8.6 纯 pooling / embedding 的指标

- 只有 `e2el`（`ttft` 等于它）、`request_throughput`、`total_token_throughput`（输入 token/s）、
  `input_lens`、`errors`；**没有** `failed` 字段（代码里未写入）。
- `--percentile-metrics` 默认 `e2el`。

### 8.7 输出样例解读

```text
============ Serving Benchmark Result ============
Successful requests:                     10
Benchmark duration (s):                  5.78
Total input tokens:                      1369
Total generated tokens:                  2212
Request throughput (req/s):              1.73
Output token throughput (tok/s):         382.89
Total token throughput (tok/s):          619.85
---------------Time to First Token----------------
Mean TTFT (ms):                          71.54
Median TTFT (ms):                        73.88
P99 TTFT (ms):                           79.49
-----Time per Output Token (excl. 1st token)------
Mean TPOT (ms):                          7.91
...
```

- 吞吐 = 完成数或 token 数 / 5.78s。
- TTFT 的 P99 高于均值说明长尾；结合 `--plot-timeline` 看是否集中在开头（冷启动）或某段（突发）。
- `Total token throughput` = (输入 + 输出) / duration，常用于"系统总处理能力"。

### 8.8 常见误解

| 误解 | 事实 |
| :-- | :-- |
| "ITL 就是 TPOT" | 标准解码近似相等；投机解码下块内多 token，ITL 只记块间、TPOT 摊到每个 token |
| "max-concurrency 会抬高延迟" | 它只影响排队位置；排队不计入单请求延迟，但会压低吞吐/拉长总时长 |
| "失败请求不影响结果" | 吞吐分母是总时长，失败会浪费时间；明细里会出现 0 值 |
| "TTFT 一定 > 0" | 非流式或空流时为 0 |
| "吞吐和延迟可以互相反推" | 口径不同（是否含排队、是否只算成功），不能反推 |

---

## 9. 结果文件

### 9.1 文件命名

默认（`compute_result_filename`）：

```
{label}-{request_rate}qps[-concurrency{N}]-{model_basename}-{YYYYmmdd-HHMMSS}.json
# ramp-up 时：
{label}-ramp-up-{strategy}-{start}qps-{end}qps[-concurrency{N}]-...json
```

- `label` 默认 `--backend`。
- `--result-filename` 覆盖整个文件名；`--result-dir` 前置目录（自动 mkdir）。
- `.pytorch.json` 文件由环境变量 `SAVE_TO_PYTORCH_BENCHMARK_FORMAT=1` 控制。
- timeline：同 stem `.timeline.html`；dataset stats：同 stem `.dataset_stats.png`。

### 9.2 JSON 字段全表

基础字段（`main_async` 组装）：

| 字段 | 说明 |
| :-- | :-- |
| `date` | `YYYYmmdd-HHMMSS` |
| `endpoint_type` / `backend` | 向后兼容 / 当前 backend |
| `label` | 标签 |
| `model_id` / `tokenizer_id` | 模型与 tokenizer |
| `num_prompts` | 计划请求数 |
| `request_rate` | 数字或字符串 `"inf"` |
| `burstiness` / `max_concurrency` | 负载参数 |
| `ramp_up_strategy/start_rps/end_rps` | 仅 ramp-up 时出现 |
| `--metadata` 的 KEY | **平铺**到顶层（可能覆盖内置字段） |

压测结果（生成式）：

| 字段 | 说明 |
| :-- | :-- |
| `duration` | 墙钟秒 |
| `completed` / `failed` | 成功/失败数 |
| `total_input_tokens` / `total_output_tokens` | 总量 |
| `request_throughput` / `output_throughput` / `total_token_throughput` | 吞吐 |
| `request_goodput` | 无 SLO 时为 `null` |
| `input_lens` | 每请求输入长度（来自响应 usage，失败为计划值/0） |
| `output_lens` | 每请求输出长度（失败为 0） |
| `ttfts` / `itls` / `start_times` | 每请求明细 |
| `generated_texts` / `errors` | 文本与错误 |
| `max_output_tokens_per_s` / `max_concurrent_requests` | 峰值 |
| `rtfx` | ASR |
| `mean/median/std_{ttft,tpot,itl,e2el}_ms` | 仅所选指标 |
| `p{P}_{metric}_ms` | 仅所选分位 |

条件字段：

| 来源 | 字段 |
| :-- | :-- |
| probe | `probe_completed`、`probe_failed`、`probe_median_e2el_ms`、`probe_p99_e2el_ms`、`probe_max_e2el_ms` |
| ramp-up | `rps_change_events: [{rps, timestamp}]` |
| spec decode | `spec_decode_acceptance_rate`、`spec_decode_acceptance_length`、`spec_decode_num_drafts`、`spec_decode_draft_tokens`、`spec_decode_accepted_tokens`、`spec_decode_per_position_acceptance_rates` |
| diffusion | `diffusion_committed_throughput`、`diffusion_steps_per_canvas`、`diffusion_committed_per_step`、`diffusion_committed_tokens`、`diffusion_denoising_steps`、`diffusion_canvas_positions` |

embedding/pooling 结果：`duration`、`completed`、`total_input_tokens`、`request_throughput`、
`total_token_throughput`、`input_lens`、`errors`、`mean/median/std_e2el_ms`、`p{P}_e2el_ms`。

### 9.3 `--save-detailed` 与 `--append-result`

- 不加 `--save-detailed`：删除 `input_lens`、`output_lens`、`start_times`、`ttfts`、`itls`、`generated_texts`、`errors`。
- `--append-result`：以追加模式写，多条记录之间换行（JSON Lines），适合 pandas/`jq` 逐行读；
  与 `--save-result` 同时给时以 append 为准（代码用 `"a+" if append else "w"`）。

### 9.4 pytorch benchmark 格式

```bash
SAVE_TO_PYTORCH_BENCHMARK_FORMAT=1 vllm bench serve ... --save-result
```

额外写 `{stem}.pytorch.json`：每条指标一个 record，含 `benchmark.extra_info.args`（完整 Namespace）、
`model.name`、`metric.name` 与 `benchmark_values`。仅记录
`median/mean/std/p99` 的 ttft/tpot/itl（注意：固定 p99，不随 `--metric-percentiles` 变）。

### 9.5 结果留痕建议

- `--metadata tp=8 dp=2 version=... max_num_seqs=...`：把**服务端**配置写进结果，否则无法溯源。
- `--label` 区分实验组；配合 sweep 的 `--serve-params` 自动记录。
- 每次实验保留原始 JSON（不要只存 p99 截图）。

---

## 10. 可视化

| 开关 | 产物 | 依赖 | 说明 |
| :-- | :-- | :-- | :-- |
| `--plot-timeline` | `<stem>.timeline.html` | plotly | 每请求甘特图，ITL 三色（`--timeline-itl-thresholds`） |
| `--plot-dataset-stats` | `<stem>.dataset_stats.png` | matplotlib | 输入/输出/总 token 分布 |
| 自动（若安装） | 终端图 | termplotlib + gnuplot | token/s 与并发随时间 |
| `vllm bench sweep plot` | PNG | seaborn/pandas | 扫参曲线 |
| `vllm bench sweep plot_pareto` | PNG | — | tokens/s/user vs tokens/s/GPU 帕累托 |

timeline 的延迟口径：`ttft + sum(itl)`；必须存在 `start_times/ttfts/itls`，否则只警告不生成。
**坑**：`--plot-dataset-stats` 单独使用会触发 `assert file_name is not None`（`file_name` 仅在
`--save-result`/`--append-result`/`--plot-timeline` 时才计算）。至少搭配 `--save-result`。

---

## 11. sweep 家族

### 11.1 `vllm bench sweep serve`

自动完成"起 server → 跑 bench → 关 server → 清缓存 → 下一组"。

| 参数 | 默认 | 说明 |
| :-- | :-- | :-- |
| `--serve-cmd` | `None` | 基础 `vllm serve ...` 命令 |
| `--bench-cmd` | `None` | 基础 `vllm bench serve ...` 命令 |
| `--serve-params` | `None` | JSON：list[dict] 或 {name: dict} |
| `--bench-params` | `None` | 同上；两组取笛卡尔积 |
| `--link-vars` | 空 | `serve_key=bench_key,...`，只跑取值相等的组合 |
| `--num-runs` | `3` | 每组重复次数 |
| `--output-dir` | `results` | 根目录 |
| `--experiment-name` / `-e` | 时间戳 | 子目录 |
| `--resume` | `False` | 跳过已有结果 |
| `--dry-run` | `False` | 只打印命令 |
| `--show-stdout` | `False` | 透传子进程输出 |
| `--server-ready-timeout` | `300` | 等 `/health` |
| `--after-bench-cmd` | `None` | 每轮结束后执行；默认调 `/reset_*_cache` |

参数文件示例：

```json
[
  {"max_num_seqs": 32, "max_num_batched_tokens": 1024},
  {"max_num_seqs": 64, "max_num_batched_tokens": 2048}
]
```

或：

```json
{
  "baseline": {"max_num_seqs": 32},
  "tuned":    {"max_num_seqs": 64}
}
```

`_benchmark_name` 可给组合命名；键名中的 `-`/`_` 会自动适配 CLI 写法；bool 会转成
`--flag` / `--no-flag`；dict 值会序列化成 JSON。

输出结构：

```
results/<experiment-name>/
├── SERVE-<组合名>-BENCH-<组合名>/
│   ├── run=0.json          # 单次 bench 结果 + serve/bench 覆盖 + run_number
│   ├── run=1.json
│   └── summary.json        # 该组合所有 run 的 list
└── summary.csv             # 所有组合的所有 run 平铺
```

### 11.2 缓存清理

- 默认在每组 bench 后清 `prefix cache`、`mm cache`、`encoder cache`（需要 `VLLM_SERVER_DEV_MODE=1`，
  sweep 已替你设置）。
- 服务端不是 `vllm`（或 `infinity_emb`）时必须给 `--after-bench-cmd`，否则直接 `NotImplementedError`。
- 这会显著影响前缀缓存类实验：每轮都从冷缓存开始。

### 11.3 `serve_workload`：找拐点

```bash
vllm bench sweep serve_workload \
  --serve-cmd 'vllm serve meta-llama/Llama-2-7b-chat-hf' \
  --bench-cmd 'vllm bench serve --model meta-llama/Llama-2-7b-chat-hf --dataset-name sharegpt --dataset-path s.json --num-prompts 100' \
  --workload-var max_concurrency \
  --workload-iters 10 \
  --num-runs 1 --output-dir results -e demo
```

算法：先跑 1 并发（最低负载）→ 再跑全并发（最高）→ 估算上限 → 中间均匀取点。
`--workload-var` 默认 `request_rate`，官方建议 `max_concurrency`（更贴近引擎压力）。

### 11.4 `plot` / `plot_pareto`

```bash
vllm bench sweep plot results/demo \
  --var-x total_token_throughput --var-y median_ttft_ms \
  --curve-by max_num_seqs --fig-by tp \
  --filter-by 'max_concurrency<=256' --bin-by request_throughput%10 \
  --fig-dir figs --fig-dpi 300
```

- `--fig-by/--row-by/--col-by/--curve-by` 多维分面；`--filter-by`/`--bin-by` 过滤与分箱。
- `--dry-run` 只打印图信息；`--no-error-bars` 关误差棒。

```bash
vllm bench sweep plot_pareto results/demo \
  --user-count-var max_concurrency \
  --label-by max_concurrency,gpu_count
```

帕累托：横轴 tokens/s/user，纵轴 tokens/s/GPU；GPU 数回退顺序
`num_gpus/gpu_count` → `tensor_parallel_size * pipeline_parallel_size`。

### 11.5 `sweep startup`

复用 `--serve-params` 对比不同引擎设置的冷/热启动时间；参数见 `sweeps.md`。

---

## 12. 高级能力

### 12.1 Profiler

```bash
# server
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --profiler-config '{"profiler":"torch","torch_profiler_dir":"./profile"}'
# client
vllm bench serve --model ... --profile --num-prompts 2
```

- 客户端在压测前后调 `/start_profile`、`/stop_profile`；trace 在 stop 时落盘（大模型可能很慢）。
- 只发少量请求，trace 会很大；用 Perfetto 打开。

### 12.2 LoRA

- `--lora-modules a b c`：每请求的 `model` 字段被替换成模块名（服务端按 name 路由）。
- `--lora-assignment round-robin` 可复现；`random` 用全局随机。

### 12.3 多模态

- 文本 + 图/视频/音频统一走 `multi_modal_data`；chat 后端自动拼进 `content`。
- `--enable-multimodal-chat`：把文本包成 chat 结构（部分数据集需要）。
- `--custom-ensure-client-side-data`：客户端预取并 base64 化（避免服务端拉取）。

### 12.4 Embedding / Rerank / Pooling

- embedding：`--backend openai-embeddings`（或 `-chat`/`-clip`/`-vlm2vec`、`infinity-*`）+ `/v1/embeddings`。
- pooling：`--backend vllm-pooling` + `/v1/pooling`。
- rerank：`--backend vllm-rerank` + `/v1/rerank`，且 `--dataset-name random-rerank`；
  embedding 模型跑 rerank 时加 `--no-reranker`。
- `random-batch-size` 只对 embedding/rerank 有意义。

### 12.5 ASR

- Whisper：`openai-audio` + `/v1/audio/transcriptions`；Qwen2-Audio：`openai-chat`。
- `--asr-min/max-audio-len-sec` 过滤；结果含 `rtfx`。

### 12.6 工具调用（BFCL）

- 必须 `--backend openai-chat`；服务端需 `--enable-auto-tool-choice --tool-call-parser <parser>`。
- `--bfcl-categories` 支持非多轮类目；多轮类目暂不支持。

### 12.7 独立脚本（不属于 serve CLI）

| 脚本 | 用途 |
| :-- | :-- |
| `benchmarks/benchmark_prefix_caching.py` | 固定 prompt/ShareGPT 的前缀缓存收益 |
| `benchmarks/benchmark_long_document_qa_throughput.py` | 长文档 QA + APC，支持 random/tile/interleave 重复模式 |
| `benchmarks/benchmark_serving_structured_output.py` | JSON/grammar/regex/choice 结构化输出 |
| `benchmarks/benchmark_prioritization.py` | 优先级调度（`--scheduling-policy priority`） |
| `benchmarks/benchmark_batch_invariance.py` | 批不变性 |
| `benchmarks/multi_turn/` | 多轮对话客户端（独立实现） |
| `benchmarks/benchmark_hash.py`、`benchmark_prefix_block_hash.py` | 哈希算法微基准（无需 server） |
| `benchmarks/replayssm/` | SSM 解码速度 |

---

## 13. 场景配方（可直接抄）

### 配方 1｜基线：固定 QPS + SLO

```bash
vllm bench serve \
  --model Qwen/Qwen3-8B --backend openai-chat --endpoint /v1/chat/completions \
  --dataset-name random --random-input-len 2048 --random-output-len 256 \
  --num-prompts 1000 --request-rate 8 --burstiness 1.0 --max-concurrency 64 \
  --goodput ttft:500 tpot:50 \
  --metric-percentiles 50,90,99 --percentile-metrics ttft,tpot,itl,e2el \
  --seed 0 --temperature 0 --ignore-eos \
  --save-result --save-detailed --plot-timeline --plot-dataset-stats \
  --result-dir results --metadata tp=1 conc=64
```

### 配方 2｜找最大吞吐（无限速率 + 网关并发）

```bash
vllm bench serve --model ... --dataset-name random \
  --request-rate inf --max-concurrency 256 --num-prompts 4096 --ignore-eos
```

### 配方 3｜ramp-up 找拐点

```bash
vllm bench serve --model ... --dataset-name random \
  --ramp-up-strategy linear --ramp-up-start-rps 1 --ramp-up-end-rps 128 \
  --num-prompts 2000 --save-result
```

### 配方 4｜前缀缓存收益

```bash
vllm bench serve --model ... --dataset-name prefix_repetition \
  --prefix-repetition-num-prefixes 8 \
  --prefix-repetition-prefix-len 2048 \
  --prefix-repetition-suffix-len 128 \
  --prefix-repetition-output-len 64 \
  --num-prompts 256 --request-rate 4 --save-result
```

### 配方 5｜真实 trace 回放

```bash
vllm bench serve --model ... --backend vllm --endpoint /v1/completions \
  --dataset-name timed_trace --dataset-path trace.jsonl \
  --timed-trace-chunk-hash-size 512 --timed-trace-sec-multiplier 0.001 \
  --num-prompts 1000 --ignore-eos --save-result
```

### 配方 6｜多模态图像压力

```bash
vllm bench serve --model Qwen/Qwen2.5-VL-7B-Instruct \
  --backend openai-chat --endpoint /v1/chat/completions \
  --dataset-name random-mm --num-prompts 200 \
  --random-input-len 300 --random-output-len 40 \
  --random-mm-base-items-per-request 2 \
  --random-mm-limit-mm-per-prompt '{"image":3,"video":0}' \
  --random-mm-bucket-config '{(256,256,1):0.7,(720,1280,1):0.3}' \
  --request-rate 4 --ignore-eos
```

### 配方 7｜干扰测量

```bash
vllm bench serve --model ... --dataset-name random \
  --request-rate 4 --probe-request-rate 20 --num-prompts 200
```

### 配方 8｜embedding 吞吐

```bash
vllm bench serve --model BAAI/bge-m3 --backend openai-embeddings \
  --endpoint /v1/embeddings --dataset-name sharegpt --dataset-path s.json \
  --num-prompts 500 --random-batch-size 8
```

### 配方 9｜rerank

```bash
vllm bench serve --model BAAI/bge-reranker-v2-m3 --backend vllm-rerank \
  --endpoint /v1/rerank --dataset-name random-rerank \
  --random-input-len 512 --num-prompts 10 --random-batch-size 5
```

### 配方 10｜ASR

```bash
vllm bench serve --model openai/whisper-large-v3-turbo \
  --backend openai-audio --endpoint /v1/audio/transcriptions \
  --dataset-name custom_audio --dataset-path audio.jsonl \
  --custom-output-len 256 --max-concurrency 16 --save-result
```

### 配方 11｜扫 server 参数

```bash
vllm bench sweep serve \
  --serve-cmd 'vllm serve Qwen/Qwen3-8B --port 8000' \
  --bench-cmd 'vllm bench serve --model Qwen/Qwen3-8B --dataset-name random --num-prompts 500 --max-concurrency 64' \
  --serve-params serve.json --bench-params bench.json \
  --num-runs 3 --output-dir results -e qwen3-tune
vllm bench sweep plot results/qwen3-tune --fig-by max_num_seqs
```

### 配方 12｜P/D 分离

`bench serve` 本身只说单请求协议，P/D 需要两步（P 返回 `kv_transfer_params` 再打 D）。
在本工作区用薄代理实现，见 [实验D](vllm架构笔记/实验D-bench-serve压P-D空跑.md)：
`pd_proxy.py` 把两段式协议包成 OpenAI 兼容端点。

---

## 14. 排错手册

| 报错/现象 | 原因 | 处理 |
| :-- | :-- | :-- |
| `Initial test run failed` | server 未就绪 / 模型名不匹配 / 端点错 | 先 `--ready-check-timeout-sec 60`；核对 `/v1/models` |
| `URL must end with ...` | backend 与 endpoint 不匹配 | completions↔chat↔embeddings↔rerank↔pooling 对齐 |
| 全部请求 200 但 0 token | 仿真器缺 `trace_decode_token_ids`；或非流式端点 | 加 trace / `return_token_ids` |
| TTFT 全 0 | 空流；或 pooling 后端（正常，ttft=e2el 但被计入 e2el） | 查服务端是否真流式 |
| `Please specify '--dataset-name'` | 显式传了 None | 给 `--dataset-name` |
| `Cannot use 'random' dataset with --dataset-path` | random 类不接受路径 | 去掉 path 或换 dataset |
| `--self-timed ... only supported with timed_trace` | 用错数据集 | 只在 timed_trace 用 |
| `When using ramp-up, do not specify --request-rate` | 两者冲突 | 删掉 request-rate |
| `tokenizer mismatch ... re-aligning` | 本地/服务端 tokenizer 不同 | 同版本 tokenizer；或忽略（已自动截断） |
| `AssertionError: file_name must be set when plot_dataset_stats` | 只开了 dataset stats | 加 `--save-result` 或 `--plot-timeline` |
| `Duplicate request_id found` | 数据集 id 冲突 | 用 `--no-oversample` 或换 seed |
| `num_requests must be greater than or equal to num_prefixes` | prefix_repetition 参数不合理 | 提高 num-prompts 或降前缀数 |
| `If no output length is provided ... 'output_tokens'` | custom 输出长度未给且样本无字段 | 给 `--custom-output-len` 或补字段 |
| `Multi-modal content ... not supported on backend` | 后端不支持多模态 | 改 `openai-chat`/`openai-audio` |
| `BFCL dataset requires 'openai-chat'` | 后端错 | 改后端 |
| `NotImplementedError: No implementation of reset_caches` | sweep 遇到非 vllm server | 给 `--after-bench-cmd` |
| 服务端 500 / 超时 | 请求体字段不被支持（如 `max_completion_tokens`） | 换 backend/endpoint 或降级字段 |

---

## 15. 版本差异与兼容性

| 项 | 本版本（v0.28.0） | 旧版本 |
| :-- | :-- | :-- |
| 入口 | `vllm bench serve` | `benchmarks/benchmark_serving.py`（现仅提示废弃） |
| temperature | 默认不设（服务端决定） | 旧版默认 greedy（0） |
| `--input-len/--output-len` | 新增通用映射 | 只能用数据集专属参数 |
| `--random-range-ratio` | 支持 JSON（input/output 分开） | 只支持 float |
| `--self-timed` | 新增，仅 timed_trace | 无 |
| `--probe-request-rate` | 新增 | 无 |
| `--plot-timeline` / `--plot-dataset-stats` | 新增 | 无 |
| spec decode / diffusion 指标 | 新增（拉 `/metrics`） | 无 |
| Rust 前端 | `VLLM_USE_RUST_BENCH` 可切换 | 无 |
| 文档漂移 | 文档里的 `--custom-skip-chat-template` **不存在**，实际是 `--skip-chat-template` | — |

---

## 16. 源码地图与扩展点

### 16.1 关键文件

| 文件 | 作用 |
| :-- | :-- |
| `vllm/benchmarks/serve.py` | CLI 参数、主流程、指标、结果组装（2368 行） |
| `vllm/benchmarks/datasets/datasets.py` | 数据集实现与参数（4814 行） |
| `vllm/benchmarks/lib/endpoint_request_func.py` | 12 个后端的请求函数与 SSE 解析（905 行） |
| `vllm/benchmarks/lib/ready_checker.py` | 就绪检查（每 5s 重试） |
| `vllm/benchmarks/lib/utils.py` | pytorch benchmark 格式、JSON 序列化 |
| `vllm/benchmarks/plot.py` | timeline / dataset stats |
| `vllm/benchmarks/sweep/` | sweep 全家桶 |
| `vllm/entrypoints/cli/benchmark/` | CLI 注册（serve/latency/throughput/startup/mm_processor/sweep） |

### 16.2 关键函数行号（v0.28.0）

| 函数 | 位置 |
| :-- | :-- |
| `add_cli_args` | `serve.py:1548` |
| `main_async` | `serve.py:1966` |
| `benchmark` | `serve.py:768` |
| `get_request` | `serve.py:393` |
| `calculate_metrics` | `serve.py:556` |
| `calculate_metrics_for_embeddings` | `serve.py:507` |
| `fetch_spec_decode_metrics` | `serve.py:189` |
| `fetch_diffusion_metrics` | `serve.py:262` |
| `compute_result_filename` | `serve.py:1505` |
| `_align_prompts_to_server_tokenizer` | `serve.py:74` |
| `SampleRequest` | `datasets.py:77` |
| `get_samples` | `datasets.py:2095` |
| `add_dataset_parser` | `datasets.py:1602` |
| `ASYNC_REQUEST_FUNCS` | `endpoint_request_func.py:873` |

### 16.3 扩展点

| 想加什么 | 改哪里 |
| :-- | :-- |
| 新后端 | 写 `async_request_*`；注册到 `ASYNC_REQUEST_FUNCS`；必要时加入 `POOLING_BACKENDS`；`--backend` choices 在 `serve.py` |
| 新数据集 | 继承 `BenchmarkDataset` 实现 `sample()`；在 `add_dataset_parser` 加参数；在 `get_samples` 加分支；更新 `--dataset-name` 的 choices |
| 新指标 | `BenchmarkMetrics` + `calculate_metrics` + 打印/JSON 组装 |
| 新可视化 | `plot.py` 或 `sweep/plot*.py` |
| 新负载形态 | `get_request` / `benchmark` 的派发循环 |

---

## 17. 附录：术语与参考

### 17.1 术语

| 术语 | 含义 |
| :-- | :-- |
| ISL / OSL | 输入序列长度 / 输出序列长度 |
| TTFT / TPOT / ITL / E2EL | 首 token 时间 / 每输出 token 时间 / token 间隔 / 端到端 |
| goodput | 满足 SLO 的有效吞吐 |
| APC | Automatic Prefix Caching |
| RPS | requests per second |
| P/D | Prefill/Decode 分离 |
| SLO | Service Level Objective |

### 17.2 参考

- 源码：`vllm-src/vllm/benchmarks/`（serve.py、datasets/、lib/、sweep/）
- 文档：`vllm-src/docs/benchmarking/cli.md`、`vllm-src/docs/benchmarking/sweeps.md`、`vllm-src/docs/cli/README.md`、`vllm-src/docs/contributing/profiling.md`
- 上游：<https://docs.vllm.ai>、GuideLLM <https://github.com/vllm-project/guidellm>
- 本工作区：[17-bench-serve学习大纲.md](vllm架构笔记/17-bench-serve学习大纲.md)、[实验D-bench-serve压P-D空跑.md](vllm架构笔记/实验D-bench-serve压P-D空跑.md)

### 17.3 维护说明

- 本文所有默认值来自 `vllm bench serve --help=all`；升级 vLLM 后先重跑该命令并 diff。
- 行号会随版本漂移；以函数名为准，行号仅供参考。
- 新发现的口径/坑请直接补进第 8、14 节，并在笔记里留实验证据。
