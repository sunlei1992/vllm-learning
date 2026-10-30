# pd/bench —— 用 `vllm bench serve` 压 P/D 空跑

配套笔记：[实验D-bench-serve压P-D空跑.md](../../../../实验D-bench-serve压P-D空跑.md)

## 为什么需要这层

`vllm bench serve` 只会发**一条** OpenAI 请求，而 P/D 分离需要两段式协议：

1. P 段：`max_tokens=1` + `kv_transfer_params={"do_remote_decode": true}`，拿回
   `remote_block_ids / remote_engine_id / remote_host / remote_port`；
2. D 段：带这些参数 + `do_remote_prefill`，才真正生成。

`pd_proxy.py` 把这两步包成一个 OpenAI 端点，bench 只要 `--base-url` 指过来就行。

## 前置条件

1. Docker Desktop（`linux/arm64`）+ 已移植 #61506 的镜像（默认 `sim-int:dry-run`）
2. 仓库根下的 `models/Qwen_Qwen3-0.6B`
3. `.venv`（跑 bench 客户端和画图，需要 `aiohttp`、`Pillow`）

## 用法

```bash
# 1P1D，16 请求
PRE=1 DEC=1 ./pd/bench/pd_bench.sh

# 2P1D，8 请求 × 1024 in / 64 out
PRE=2 DEC=1 NPROMPTS=8 INLEN=1024 OUTLEN=64 ./pd/bench/pd_bench.sh

# 注入时间模型（否则 timing=zero，算力免费）
SIM_TIMING='"timing":"linear","timing_args":{"fixed_us":6200,"prefill_us_per_token":15,"decode_us_per_req":2400,"decode_us_per_kv_token":0.14}' \
  LOAD_GBPS=25 PRE=2 DEC=1 NPROMPTS=8 INLEN=1024 OUTLEN=64 ./pd/bench/pd_bench.sh

# 保留环境，手动压测/看日志
KEEP=1 PRE=2 DEC=2 ./pd/bench/pd_bench.sh
curl -s localhost:18000/health
```

环境变量：

| 变量 | 默认 | 说明 |
| :-- | :-- | :-- |
| `PRE` / `DEC` | 1 / 1 | prefill / decode 实例数（XpYd） |
| `NPROMPTS` `INLEN` `OUTLEN` | 16 / 256 / 8 | 负载形状 |
| `TRACE_LEN` | 16 | 注入的 `trace_decode_token_ids` 长度（必须 ≥ `OUTLEN`） |
| `LOAD_GBPS` | 10 | 模拟 KV 传输带宽 |
| `SIM_TIMING` | 空 | 拼进 `--simulation-config` 的时间模型片段 |
| `KV_MB` | 2048 | 每个引擎的 KV 预算（**小到装不下工作集会退化成排队**） |
| `MAX_MODEL_LEN` | 4096 | `--max-model-len` |
| `IMG` | `sim-int:dry-run` | 镜像 |
| `KEEP` | 0 | 1 = 不删容器、不杀代理 |
| `LABEL` | `pd{X}p{Y}d` | 结果文件名前缀 |

额外参数会原样追加给 `vllm bench serve`。

## 文件

| 文件 | 作用 |
| :-- | :-- |
| `pd_bench.sh` | 宿主侧驱动：起容器 → 等代理健康 → bench → 存 JSON → 清理 |
| `pd_sim_launch.sh` | 容器内：起 X 个 `kv_producer` + Y 个 `kv_consumer` + 代理，等全部 health |
| `pd_proxy.py` | 两段式 P/D 协议代理（OpenAI completions/chat，SSE 透传） |
| `make_pd_chart.py` | 读 `tmp/simlogs/pd_bench/*.json` 画趋势图（Pillow，无 matplotlib） |
| `pd_trend.png` | 上面脚本产出的图（示例数据见笔记） |

结果 JSON 落在 `tmp/simlogs/pd_bench/`，引擎日志在 `tmp/simlogs/pd_{prefill,decode}_*.log`。

## 注意

- 请求必须带 `trace_decode_token_ids`（`--simulate-forward` 隐含 `enable_trace_replay`），
  不带时会静默输出全 0 token；脚本用 `--extra-body` **全局**注入，所以所有请求共用一条 trace。
- 两个实例必须同容器（`remote_host=localhost`），side-channel 端口用
  `VLLM_NIXL_SIDE_CHANNEL_PORT` 区分；代理和引擎同容器跑，只对外暴露代理端口。
- 代理会把 P 段消费掉的 1 个 token 从 D 段 `max_tokens` 里扣掉，所以 bench 看到的总输出会
  少 1 个 token（例：16 请求 × 8 → 112 = 16×7）。
