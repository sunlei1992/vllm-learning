# 实验E：RouteServer 对接 vLLM 空跑（P/D）

> 日期：2026-10-30 ｜ 上游：`/Users/sunlei/code/gitcode/RouteServer` `dev@54d7d80` ｜ 镜像 `rs-demo:dev` + `sim-int:dry-run`
> 结论：**RouteServer 可以直接当空跑 P/D 的 proxy**，实例注册制、trace 透传、两跳 KV 都通；
> 但**必须打 `pd_separate_with_remote_decode` 这个 pipeline 补丁**，否则它会**静默降级**成"P 只出 1 token、D 重新 prefill"，
> 请求照样 200、指标看着还更快——这是本节最值得记住的坑。

---

## 1. 为什么它天生适合接空跑

| 机制 | 证据 | 含义 |
| :-- | :-- | :-- |
| 实例是**注册制** | `deploy.sh` 从 `PREFILL_SERVERS` / `DECODE_SERVERS=name#ip:port` 读地址 | RS 不拉起 vLLM，空跑可以自己带 `--simulate-forward` |
| 请求体走通用 JSON | `utils.JSONModifier`（`map[string]interface{}`） | `trace_decode_token_ids` / `return_token_ids` 不会丢 |
| P 段强制 `max_tokens=1` + 非流式 | `PreparePrefillRequestBody`（`mono_phases.go:363`） | 与手写两步客户端语义一致 |
| 有现成外部后端入口 | `rs_demo.sh` 的 `BACKENDS=external` | 少写启动脚本 |

## 2. 关键：同一个 network namespace

RS 的 external 地址是 `127.0.0.1:8001/8002`，而 NIXL 的 side-channel 也要求同容器（`remote_host=localhost`）。
两个镜像各缺一半（`rs-demo:dev` 没有 python/vllm，`sim-int:dry-run` 没有 curl/unzip），所以**不合并镜像**，改成共享 netns：

```bash
# 1) 路由容器：持有 netns，对外发布 9800/9810（以及 8001/8002 便于调试）
docker run -d --name rs-pd -p 9800:9800 -p 9810:9810 -p 8001:8001 -p 8002:8002 \
  -v "$PWD/tmp/rs_sim:/patches:ro" --entrypoint sleep rs-demo:dev infinity

# 2) 引擎容器：--network container:rs-pd ⇒ localhost 互通
docker run -d --name sim-pd --network container:rs-pd --shm-size=16g \
  -e SIM_TIMING -e LOAD_GBPS -e KV_MB -e MAX_MODEL_LEN \
  -v "$PWD/models:/models:ro" -v "$PWD/tmp/simlogs:/logs" -v "$PWD/tmp/rs_sim:/tools:ro" \
  sim-int:dry-run bash /tools/start_sim_pd.sh

# 3) 在路由容器里用外部后端模式起 RS
docker exec -d rs-pd bash -lc '
  BACKENDS=external PREFILL_ADDR=127.0.0.1:8001 DECODE_ADDR=127.0.0.1:8002 \
  PIPELINE_PATCH=/patches/pd_separate_with_remote_decode.yaml \
  nohup /opt/rs_demo.sh > /tmp/rs_demo.out 2>&1'
```

一键脚本：`assets/routeserver-sim/run.sh`（含就绪等待与补丁校验），引擎启动：`start_sim_pd.sh`。

## 3. 坑：不打补丁会**静默**降级

默认 `pipelines/pd_separate.yaml` 的 P 段只有 `prefill_prepare_request`，它会
**删掉** `kv_transfer_params`（`PreparePrefillRequestBody` 里 `copiedBody.Remove(KvTransferParamsKey)`），
于是 vanilla vLLM 的 P 不知道"远程 decode"，响应里 `kv_transfer_params` 是 `null`。

更麻烦的是 `CheckKVTransferParams` 对 `/v1/completions` **只打警告、不报错**（只有流式 chat 才硬失败）：

```
WARN prefill res for request [cmpl-...] don't contains [kv_transfer_params]
```

于是 D 收到 null，就自己把 prompt 又 prefill 一遍——**请求全部 200，token 也全对，但根本没做 P/D**。
第一次跑我们就是踩了这个：日志里 32 条警告，TTFT 还比真 P/D 更低（因为 D 并行做完了自己的 prefill）。

补丁 `pd_separate_with_remote_decode.yaml` 在 P 段加上 `vllm_ascend_prepare_request`，
它会显式写 `kv_transfer_params={do_remote_decode: true, ...}` 并设 `min_tokens=1`。

`run.sh` 现在会在起 RS 后校验：

```bash
docker exec rs-pd grep -q vllm_ascend_prepare_request /opt/rs_pkg/pipelines/pd_separate.yaml
```

不通过直接退出，避免又跑出一组"假 P/D"数据。

> ⚠️ `PIPELINE_PATCH` 必须是**容器内路径**。第一次把宿主路径传进去，`rs_demo.sh` 的
> `[ -f ]` 判断失败、静默跳过——这就是上面那 32 条警告的来源。

## 4. 实测

环境：Qwen3-0.6B 空跑，`linear` 时间模型（`fixed_us=6200`、`prefill_us_per_token=15`、
`decode_us_per_req=2400`、`decode_us_per_kv_token=0.14`），`load_gbps=25`、KV 2 GiB、
8 请求 × 1024 in / 64 out、`request-rate=inf`。

| 路径 | TTFT mean（热，3 次） | TPOT | duration | 是否真 P/D |
| :-- | :-- | -: | -: | :-- |
| RouteServer（**打补丁**） | 96.7 / 96.3 / 97.9 → **97.0 ms** | 26.3 | 1.76 s | ✅ 0 条警告 |
| 薄代理 `pd_proxy.py` | 96.6 / 93.3 / 87.8 → **92.6 ms** | 24.8 | 1.73 s | ✅ |
| RouteServer（未打补丁） | 81.7 / 78.7 / 73.5 → **78.0 ms** | 26.3 | 1.75 s | ❌ 32 条警告 |

结论：

- RS 多一跳 Go 进程 + JSON 改写，TTFT 比 180 行的薄代理高 **~4–5 ms（约 5%）**，可以接受；
- 未打补丁那组看着快 20ms，是因为它干的活更少（没有 KV 传输），**不能当性能数据用**；
- 两条路径的 TPOT / duration 基本一致，说明 decode 侧行为没有被 proxy 改变。

### P 段的一个细节（用裸 curl 测得）

| P 请求形状 | 结果 |
| :-- | :-- |
| `max_tokens=1`, `stream=false`, `do_remote_decode=true` | 18–20 ms 返回，**带 `remote_block_ids`** |
| `max_tokens=64`, `stream=true`, `do_remote_decode=true` | 首块 19–27 ms，但**完整响应要 576 ms**（P 真的生成了 64 个 token） |

所以 P 段必须显式 `max_tokens=1`，这正是 RS `prefill_prepare_request` 做的事；
`do_remote_decode` 本身**不会**把 P 的生成长度截断。

## 5. 附带发现：冷启动会把 TTFT 抬高约 2 倍

同一套引擎，第一次压测 vs 之后：

| 时机 | TTFT mean |
| :-- | -: |
| 新栈第一次压测（即使 `--num-warmups 2`） | **190.7 / 196.8 / 215.9 ms** |
| 同一栈第二次及以后 | **93–97 ms** |

2 个 warmup 请求**压不住**：真正要预热的是"8 并发 prefill / decode"这个 batch 形状
（Triton JIT、NIXL 首次注册、首次大块分配都在这条路径上）。

**影响**：实验D 里 `k8_*` 矩阵每格都是全新容器 + 单次压测，绝对值被冷启动抬高了约 2 倍
（1P1D 记为 194.7 ms，热态实为 ~93–97 ms）。相对趋势仍可用，但绝对值要打这个折扣。

**正确协议**：起引擎后先用**完整负载跑一遍丢弃**（不是 1–2 个 warmup 请求），再测。

## 6. 下一步

- RS 的实例级路由算法（`round-robin` / `least-total-load` / `apc` / `abc6`）可以做 A/B：
  起 2P2D，在同一 workload 下比较派发策略——这才是 RS 相对薄代理的真正价值；
- 与实验D 的 `ab_policy.py` 分工：**RS 管"发给哪个实例"，Scheduler 管"批内怎么排"**，两者别混。

## 7. 文件

| 路径 | 说明 |
| :-- | :-- |
| `assets/routeserver-sim/run.sh` | 起两个容器（共享 netns）+ 起 RS + 校验补丁 + 等就绪 |
| `assets/routeserver-sim/start_sim_pd.sh` | 容器内起空跑 P(:8001) / D(:8002) |
| `assets/routeserver-sim/pd_separate_with_remote_decode.yaml` | 注入 `do_remote_decode` 的 pipeline 补丁 |

相关：实验D（薄代理 + bench serve）、`pd/online_pd.sh`（手写两步冒烟）。
