# RouteServer × 空跑 P/D

配套笔记：[实验E-RouteServer对接P-D空跑.md](../../../../实验E-RouteServer对接P-D空跑.md)

把 `/Users/sunlei/code/gitcode/RouteServer`（`dev@54d7d80`）当成 P/D proxy，后端接
`simulate-forward` 的空跑引擎。

## 前置条件

1. 已构建 `rs-demo:dev`（见 `tmp/routeserver/`：`build.sh` → `run.sh`，产物是 `pkg/package.zip`）
2. 已构建 `sim-int:dry-run`（见 `../DOCKER.md`）
3. 仓库根下有 `models/Qwen_Qwen3-0.6B`

## 用法

```bash
# 起两个容器（共享 netns）+ RouteServer + 等就绪
SIM_TIMING='"timing":"linear","timing_args":{"fixed_us":6200,"prefill_us_per_token":15,"decode_us_per_req":2400,"decode_us_per_kv_token":0.14}' \
LOAD_GBPS=25 ./wiki/vllm架构笔记/assets/routeserver-sim/run.sh

# 停止
./wiki/vllm架构笔记/assets/routeserver-sim/run.sh stop
```

起来之后：

```bash
curl -s localhost:9800/status | python3 -m json.tool   # prefill/decode 都 running
vllm bench serve --base-url http://127.0.0.1:9800 ...  # 和打薄代理一样用
```

环境变量：`SIM_TIMING`、`LOAD_GBPS`、`KV_MB`、`MAX_MODEL_LEN`、`RS_IMG`、`SIM_IMG`、`RS_PORT`。
额外挂载：`/patches`（本目录）给路由容器，`/logs`（=`tmp/simlogs`）给引擎容器。

## 两个必读的坑

1. **必须打 pipeline 补丁**：默认 `pd_separate.yaml` 的 P 段不会注入 `do_remote_decode`，
   于是 P 返回 `kv_transfer_params: null`，D 自己重新 prefill —— 请求仍 200，
   `/v1/completions` 下只有一条 WARN，看起来"更快"。`run.sh` 会校验补丁是否落地。
2. **`PIPELINE_PATCH` 必须是容器内路径**（`/patches/xxx.yaml`）。传宿主路径会被 `[ -f ]` 静默跳过。

## 文件

| 文件 | 作用 |
| :-- | :-- |
| `run.sh` | 宿主侧：起 `rs-pd`（持有 netns）+ `sim-pd`（`--network container:rs-pd`）、起 RS、校验补丁、等就绪 |
| `start_sim_pd.sh` | 容器内：起空跑 P(:8001, `kv_producer`) / D(:8002, `kv_consumer`) |
| `pd_separate_with_remote_decode.yaml` | 在 P 段加 `vllm_ascend_prepare_request`，显式写 `do_remote_decode` |

## 已知限制

- 目前只跑通 1P1D；多实例路由 A/B（`round-robin` vs `least-total-load`）需要把
  `start_sim_pd.sh` 扩成 N 个实例，并给 `PREFILL_SERVERS` / `DECODE_SERVERS` 传多个地址。
- 首次压测会被冷启动抬高约 2 倍（Triton JIT / NIXL 注册），务必先跑一轮丢弃。
