# 14 vLLM 统计与观测面全清单

## 0. 元信息

- 日期：2026-11-05，核对基座 `vllm-src`（0.28.0）
- 用途：**参考表**。想知道「某个现象该开什么开关、看哪个指标、抓哪个端点」时查这里。
- 前置：`09-调度层可观测性与性能测量.md`（调度层读法）、`13-性能调试方法论-系统级瓶颈归因.md`（归因流程与判定树）。
- 源码索引：`vllm/config/observability.py`、`vllm/config/profiler.py`、`vllm/v1/metrics/{loggers,stats,perf,prometheus}.py`、`vllm/v1/spec_decode/metrics.py`、`vllm/distributed/kv_transfer/kv_connector/v1/{metrics.py,nixl/stats.py,mooncake/store/metrics.py,hf3fs/hf3fs_connector.py}`、`vllm/compilation/cuda_graph.py`、`vllm/entrypoints/serve/`。

## 1. 五条输出通道

| # | 通道 | 默认 | 粒度 | 去向 |
| :-- | :-- | :-- | :-- | :-- |
| 1 | 周期统计日志 | **开**（10s，`VLLM_LOG_STATS_INTERVAL`） | 聚合 | stdout |
| 2 | 每步 iteration details | 关 | 每 engine step 一行 | stdout |
| 3 | Prometheus `/metrics` | 开（随 api_server） | 直方图/counter/gauge | 拉取 |
| 4 | 每请求 metrics | 关 | 单请求 | 随响应回传客户端 |
| 5 | OpenTelemetry traces | 关 | 单请求 span | OTLP endpoint |

另有两类**不叫 metrics 但等效**的通道：profiler trace（`/start_profile`）、KV 事件（`--kv-events-config`，给外部缓存/调度器用）。

## 2. 开关总表

### 2.1 `ObservabilityConfig`（`--<field>` 形式暴露）

| 字段 | 默认 | 作用 | 开销 |
| :-- | :-- | :-- | :-- |
| `show_hidden_metrics_for_version` | None | 放出已隐藏的旧指标（迁移逃生门） | 无 |
| `otlp_traces_endpoint` | None | OTel 上报地址，需装 otel 包 | 低-中 |
| `collect_detailed_traces` | None | `model`/`worker`/`all`；**每请求**采 forward/execute 时间 | **高**（逐请求计时） |
| `kv_cache_metrics` | False | KV 块级驻留三指标 | 低（采样） |
| `kv_cache_metrics_sample` | 0.01 | 块采样率 (0,1] | 与采样率成正比 |
| `cudagraph_metrics` | False | padding/分发模式表 | 低 |
| `enable_layerwise_nvtx_tracing` | False | 逐层 NVTX（带 shape）；**与 CUDA graph 不兼容** | 中-高 |
| `enable_mfu_metrics` | False | MFU：算力/带宽利用率 | 中（解析式估算） |
| `enable_mm_processor_stats` | False | 多模态 processor 计时；**内部用，无 CLI** | 低 |
| `enable_logging_iteration_details` | False | 每步明细日志 | 中（firehose） |
| `jit_monitor_mode` | `warn` | post-warmup JIT 编译事件：warn/error | 低 |
| `jit_monitor_verbose` | False | 逐次打印 JIT 细节 | 高（日志量） |

### 2.2 `ProfilerConfig`（`--profiler-config '<json>'`）

`profiler`: `torch` | `cuda` | `proton`；`torch_profiler_dir`（**绝对路径**）、`torch_profiler_with_stack`（默认 True，NPU 上务必关）、`torch_profiler_record_shapes`、`torch_profiler_with_memory`、`torch_profiler_with_flops`、`torch_profiler_use_gzip`、`torch_profiler_dump_cuda_time_total`、**`detailed_trace_annotation`**（roofline 注解 `sq/sqsq/sqsk`）、`capture_torch_profiler`（采 graph capture 本身）、`ignore_frontend`、`delay_iterations`、`max_iterations`。

### 2.3 其他相关 CLI / ENV

| 开关 | 默认 | 作用 |
| :-- | :-- | :-- |
| `--enable-per-request-metrics` | False | 每请求 `queue_time_ms/ttft/mean_itl_ms/tokens_per_second` 回传；要求 stats 未禁用 |
| `--disable-log-stats` | 未设 | 关掉 1/2/4 通道的依赖；与 per-request metrics 互斥 |
| `VLLM_LOG_STATS_INTERVAL` | 10.0 | 周期日志间隔（秒）；1.0 用于压测 |
| `VLLM_DEBUG_MFU_METRICS` | 0 | MFU 分解明细（per-component） |
| `VLLM_COMPUTE_NANS_IN_LOGITS` | 0 | 检测 NaN logits → `Corrupted: N reqs` + `vllm:corrupted_requests` |
| `VLLM_NVTX_SCOPES_FOR_PROFILING` | 0 | 给关键路径加 NVTX scope |
| `VLLM_GC_DEBUG` | "" | `1` 或 `{"top_objects":5}`：gc.collect 耗时与热点对象 |
| `VLLM_DEBUG_LOG_API_SERVER_RESPONSE` | False | 打印 API 响应体（排协议问题） |
| `VLLM_TRACE_FUNCTION` | 0 | 全函数调用记录，**调试卡死/崩溃用，非性能** |

## 3. Prometheus 指标全表（69 个）

公共 label：`model_name` + `engine`（DP 下每 rank 一个 engine）。counter 暴露时自动加 `_total`。

### 3.1 队列与状态（4）
`vllm:num_requests_running`、`vllm:num_requests_waiting`、
`vllm:num_requests_waiting_by_reason{reason=capacity|deferred}`、`vllm:engine_sleep_state`

### 3.2 KV 容量与驻留（5）
`vllm:kv_cache_usage_perc`、`vllm:num_preemptions`、
`vllm:kv_block_lifetime_seconds`、`vllm:kv_block_idle_before_evict_seconds`、`vllm:kv_block_reuse_gap_seconds`（后三需 `--kv-cache-metrics`，采样）

### 3.3 缓存命中（8）
`vllm:prefix_cache_queries`、`vllm:prefix_cache_hits`、
`vllm:external_prefix_cache_queries`、`vllm:external_prefix_cache_hits`、
`vllm:mm_cache_queries`、`vllm:mm_cache_hits`、
`vllm:prompt_tokens_cached`、
`vllm:prompt_tokens_by_source{source=local_compute|local_cache_hit|external_kv_transfer}`

### 3.4 token 与吞吐（4）
`vllm:prompt_tokens`、`vllm:generation_tokens`、
`vllm:iteration_tokens_total`（每 step token 数直方图）、
`vllm:request_success{finished_reason=...}`

### 3.5 请求规模分布（5）
`vllm:request_prompt_tokens`、`vllm:request_generation_tokens`、
`vllm:request_max_num_generation_tokens`、`vllm:request_params_n`、`vllm:request_params_max_tokens`

### 3.6 延迟分解（8，核心）
| 指标 | 区间定义 |
| :-- | :-- |
| `vllm:time_to_first_token_seconds` | 到达 → 首 token |
| `vllm:inter_token_latency_seconds` | 相邻流式包间隔 |
| `vllm:request_time_per_output_token_seconds` | (E2E−TTFT)/(n−1) |
| `vllm:e2e_request_latency_seconds` | 到达 → 末 token |
| `vllm:request_queue_time_seconds` | 到达 → 被调度（**排队**） |
| `vllm:request_prefill_time_seconds` | 调度 → 首 token（**prefill**） |
| `vllm:request_decode_time_seconds` | 首 token → 末 token（**decode**） |
| `vllm:request_inference_time_seconds` | 调度 → 末 token |

### 3.7 prefill 真实工作量（1）
`vllm:request_prefill_kv_computed_tokens` —— 排除 cached 后**实际新算**的 KV token 直方图。APC 有效性的分布视角。

### 3.8 正确性 / 多租户（2）
`vllm:corrupted_requests`（需 `VLLM_COMPUTE_NANS_IN_LOGITS`）、`vllm:lora_requests_info`（带 adapter label）

### 3.9 roofline / MFU（3，需 `--enable-mfu-metrics`）
`vllm:estimated_flops_per_gpu_total`、
`vllm:estimated_read_bytes_per_gpu_total`、
`vllm:estimated_write_bytes_per_gpu_total`
（解析式 FLOPs/字节估算，`vllm/v1/metrics/perf.py`）

### 3.10 投机解码 / 扩散（7）
`vllm:spec_decode_num_drafts`、`vllm:spec_decode_num_draft_tokens`、
`vllm:spec_decode_num_accepted_tokens`、`vllm:spec_decode_num_accepted_tokens_per_pos{position}`
扩散模型同位置换成：`vllm:diffusion_num_denoising_steps`、`vllm:diffusion_num_canvas_positions`、`vllm:diffusion_num_committed_tokens`

### 3.11 KV 传输连接器（插件注册，16）
- NIXL：`nixl_xfer_time_seconds`、`nixl_post_time_seconds`、`nixl_bytes_transferred`、`nixl_num_descriptors`、`nixl_num_failed_transfers`、`nixl_num_failed_notifications`、`nixl_num_kv_expired_reqs`
- Mooncake store：`mooncake_store_operation_time_seconds`、`mooncake_store_operation_total`、`..._keys_total`、`..._bytes_total`、`..._failed_keys_total`
- HF3FS：`hf3fs_save_duration_seconds`、`hf3fs_load_duration_seconds`、`hf3fs_num_failed_save`、`hf3fs_num_failed_load`

### 3.12 语音 WebSocket（3）
`vllm:websocket_connections_active`、`..._total`、`websocket_connection_duration_seconds`

## 4. 日志行清单

### 4.1 基础周期行（`LoggingStatLogger.log`）
```text
Engine 000: Avg prompt throughput: X tokens/s, Avg generation throughput: Y tokens/s,
Running: n reqs, Waiting: m reqs[, Deferred: k reqs][, Preemptions: j],
GPU KV cache usage: Z%, Prefix cache hit rate: W%
[, Corrupted: c reqs][, External prefix cache hit rate: e%][, MM cache hit rate: q%]
```
注意：**prompt throughput 用 `computed` token 算**（排除 cached/transferred），所以 APC 命中率高时 prompt throughput 会变低——这是"真的没算"，不是"变慢"。

### 4.2 每步行（`--enable-logging-iteration-details`）
```text
Iteration(N): a context requests, b context tokens, c generation requests,
d generation tokens, iteration elapsed time: T ms, GPU KV cache usage: Z%
```

### 4.3 功能追加行

| 功能 | 日志行 |
| :-- | :-- |
| MFU | `MFU: X TF/s/GPU Y GB/s/GPU`（+`VLLM_DEBUG_MFU_METRICS` 出分解） |
| 投机解码 | `SpecDecoding metrics: Mean acceptance length: .., Accepted throughput: .., Drafted throughput: .., Accepted: .. tokens, Drafted: .. tokens, Per-position acceptance rate: p0, p1, .., Avg Draft acceptance rate: ..%` |
| CUDA graph | markdown 表：`Unpadded Tokens / Padded Tokens / Num Paddings / Runtime Mode / Count` |
| KV 传输 | `KV Transfer metrics: k=v, ...`（由 connector 的 `reduce()` 决定字段） |
| JIT | post-warmup 编译事件（`jit_monitor_mode=warn/error`） |

## 5. HTTP 端点（33）

| 类别 | 端点 |
| :-- | :-- |
| 指标/健康 | `/metrics`、`/load`（在飞请求数，给外部 LB）、`/health`、`/version`、`/server_info`、`/ping`(sagemaker) |
| Profile | `/start_profile`、`/stop_profile`（**未配 `--profiler-config` 则 404**） |
| 缓存重置 | `/reset_prefix_cache`、`/reset_mm_cache`、`/reset_encoder_cache` |
| 睡眠/暂停 | `/sleep`、`/wake_up`、`/is_sleeping`、`/pause`、`/resume`、`/is_paused` |
| 权重热更 | `/update_weights`、`/weight_info`、`/init_weight_transfer_engine`、`/start_weight_update`、`/finish_weight_update`、`/update_weight_version`、`/start_draft_weight_update` |
| 故障/弹性 | `/fault_tolerance/status`、`/is_scaling_elastic_ep`、`/abort_requests`、`/collective_rpc`、`/get_world_size` |
| 其他 | `/tokenizer_info`、`/classify`、`/v1/models`、`/v1/load_lora_adapter`、`/v1/responses/{id}[/cancel]` |

## 6. 「想看 X → 开 Y」速查

| 想看 | 开关 | 看什么 |
| :-- | :-- | :-- |
| 慢在排队还是算 | 默认 | `request_queue_time` vs `prefill`/`decode` 直方图 |
| 并发/队列卡在哪 | 默认 | `num_requests_waiting_by_reason{capacity,deferred}` |
| KV 够不够 | `--kv-cache-metrics` | `idle_before_evict` ≈ 0 + `lifetime` 短 = 真不够 |
| APC 有没有真命中 | 默认 | `prompt_tokens_by_source` + `request_prefill_kv_computed_tokens` |
| 每步 batch 形状 | `--enable-logging-iteration-details` | ctx/gen 请求数与 token 数 |
| padding 浪费 | `--cudagraph-metrics` | Padded vs Unpadded 表 |
| 算力/带宽利用率 | `--enable-mfu-metrics` | `MFU: TF/s/GPU, GB/s/GPU` + 3 个 estimated_* |
| 投机解码赚不赚 | 默认（开了投机就有） | acceptance length / per-position rate |
| KV 传输瓶颈 | 默认（有 connector 就有） | `nixl_*` / `mooncake_store_*` / `KV Transfer metrics` |
| 单请求归因 | `--enable-per-request-metrics` | 响应里的 `queue_time_ms`/`ttft`/`mean_itl_ms` |
| 跨请求链路 | `--otlp-traces-endpoint` + `--collect-detailed-traces` | OTel span（queue/prefill/decode/forward） |
| 逐层/通信占比 | `--enable-layerwise-nvtx-tracing` + nsys | 层级 NVTX range |
| 负载均衡 | 默认 | `engine` label 横向比；`/load` |
| 首次请求慢 | `--jit-monitor-mode error` | post-warmup 编译告警 |
| 数值错误混入性能 | `VLLM_COMPUTE_NANS_IN_LOGITS=1` | `Corrupted: N reqs` |

## 7. 采样与开销约束（选型时先看这张）

| 手段 | 数量级开销 | 能不能报性能数字 |
| :-- | :-- | :-- |
| 周期日志（10s） | 可忽略 | ✅ |
| Prometheus 直方图 | 低 | ✅ |
| `--kv-cache-metrics`（1% 采样） | 低 | ✅ |
| 每步 iteration details | 中（每步一条 INFO） | ⚠️ 短窗口 |
| `--enable-mfu-metrics` | 中（解析式估算，有计算） | ⚠️ 同版本内相对比较 |
| OTel `--collect-detailed-traces` | 高（逐请求） | ❌ |
| torch profiler（无 stack） | 中 | ❌ |
| torch profiler + stack（NPU 默认！） | 很高 | ❌ |
| nsys | 低-中 | 仅看结构，不看绝对秒数 |
| `VLLM_TRACE_FUNCTION` | 极高 | ❌ 仅调 hang |

## 8. 已知盲区

1. `vllm:iteration_tokens_total` 在多 api_server + prometheus multiprocess 下可能不准（源码 TODO 指向 PR #18053）。
2. DP 下 `EngineLoggers` 会打 `N Engines Aggregated` 聚合行——**聚合值不能当单卡值**；要看分布必须用 `engine` label。
3. 每请求 cached token 数**没有**回传通道（`PerRequestTimingMetrics` 只有时间字段），只能靠 `prompt_tokens_by_source` 聚合或 `request_prefill_kv_computed_tokens` 分布间接看。
4. `Prefix cache hit rate` 是最近窗口（`CachingMetrics` 环形缓冲）的块命中率，不是全生命周期。
5. tokenizer/前端排队时间不在 `request_queue_time` 里（后者是 engine core 的 queued→scheduled）。

## 9. 落地：实验级指标隔离与归档

### 9.1 为什么必须隔离（不只是为了好看）

- vLLM 的 counter/histogram **随进程重启归零**。同一 Prometheus 连续抓多个实验时，`rate()` 会把 counter reset 当成"从 0 重来"，`histogram_quantile` 跨 reset 窗口会**失真**——跨实验的 p99 是不可信的。
- 实验之间往往改了不同变量（并发、scheduler、KV 容量），混在一条 time series 上无法用 `sum by (engine)` 区分。
- 归档需求：实验结束后要能"回到当时那个图"，而不是靠回忆时间段去 Grafana 里拖时间轴。

### 9.2 三种方案

| 方案 | 隔离粒度 | 切换成本 | 适合 |
| :-- | :-- | :-- | :-- |
| **A. 每个实验一个 Prometheus 实例**（独立 `-p` 项目 / 独立端口 / 独立 data 目录） | 物理隔离，最彻底 | 起停容器 | **一次跑一个实验（推荐）** |
| **B. 单实例 + scrape 静态 label + reload** | 逻辑隔离（`experiment` label） | `POST /-/reload` | 想只维护一个 Prometheus |
| **C. 不用 Prometheus**：轮询存 TSV/Parquet | 文件即隔离 | 无 | 单次实验、要 pandas 出图 |

### 9.3 方案 A：一实验一实例（推荐）

目录即实验包，与仓库 `wiki/**/assets/<实验名>/` 的组织方式一致：

```text
experiments/2026-11-05_srs-cap5/
├── prometheus.yaml      # 抓 host.docker.internal:8000
├── compose.yaml         # 独立 -p 项目 + 独立端口 + data 卷
├── data/                # TSDB，实验结束整目录归档
├── bench.json           # vllm bench serve --save-result
└── RESULTS.md           # 结论 + 关键 PromQL
```

`compose.yaml` 模板（关键：端口与 `-p` 项目名都要独立，并挂 data 卷）：

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    extra_hosts: ["host.docker.internal:host-gateway"]
    ports: ["19091:9090"]                    # 每个实验换端口
    volumes:
      - ./prometheus.yaml:/etc/prometheus/prometheus.yml:ro
      - ./data:/prometheus                   # 必加，否则 down 即丢
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=90d'
```

```bash
cd experiments/2026-11-05_srs-cap5
docker compose -p srs_cap5 up -d      # -p 保证容器/网络不与别的实验冲突
docker compose -p srs_cap5 stop       # 停但保留 data/
```

Grafana 侧：给每个实验加一个 Prometheus 数据源（`http://localhost:19091` …），dashboard 里用 **Data source 类型变量**切换，或在每个面板的 datasource 选不同实验——一张 dashboard 看一个实验，天然分开。

### 9.4 方案 B：单实例 + `experiment` label

vLLM 的指标 label 固定为 `model_name` + `engine`，**不能自定义**；只能在 Prometheus 抓取侧加静态 label：

```yaml
scrape_configs:
  - job_name: vllm
    static_configs:
      - targets: ['host.docker.internal:8000']
        labels:
          experiment: srs_cap5
```

改完热加载（需启动时带 `--web.enable-lifecycle`）：

```bash
curl -X POST localhost:9090/-/reload
```

之后所有查询带 `experiment` 维度：

```promql
histogram_quantile(0.99, sum by (le, experiment) (rate(vllm:time_to_first_token_seconds_bucket[5m])))
```

Grafana 加一个 `label_values(vllm:num_requests_running, experiment)` 的变量，就能一键切实验。

⚠️ 不要用多个 job 指同一个地址来模拟多实验——只跑一个服务时，其余 job 会重复抓同一份数据，产生带错 label 的重复序列。

### 9.5 方案 C：轮询落盘（零依赖）

```bash
PID=$(pgrep -f "vllm serve" | head -1)
while kill -0 "$PID" 2>/dev/null; do
  ts=$(date +%s)
  curl -s localhost:8000/metrics | awk -v t="$ts" '/^vllm:/{print t"\t"$0}'
  sleep 1
done > "metrics_$(date +%F_%H%M).tsv"
# 事后：pandas.read_csv(sep="\t")，自己算 p99/占比
```

牺牲的是 PromQL 的便利（p99 要自己从桶算），换来的是"一个文件 = 一个实验"。

### 9.6 与既有实验规范的衔接

沿用 `10-调度优化测试工作流.md` 的产物要求：每个实验目录里除图之外，**必须留 `RESULTS.md` 记录三个东西**——① 本轮的关键 PromQL；② 区分 baseline/candidate 的那个 label 或端口；③ TSDB 是保留还是已删（`data/` 体积可达数百 MB，不适合入库，建议 `.gitignore` + 只保留导出的 png/csv）。
