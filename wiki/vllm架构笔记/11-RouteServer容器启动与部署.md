# 11 RouteServer 容器启动与部署

> 日期：2026-10-31 ｜ 上游：`/Users/sunlei/code/gitcode/RouteServer` `dev@54d7d80`
> 本地封装：`/Users/sunlei/code/dsh/vllm/tmp/routeserver/`（`Dockerfile.build` / `Dockerfile.run` / `rs_demo.sh`）
> 配套：[实验E-RouteServer对接P-D空跑.md](实验E-RouteServer对接P-D空跑.md)（RS 接空跑引擎）

---

## 0. 元信息

| 项目 | 值 |
|---|---|
| 仓库 | `gitcode.com/InferTurbo/RouteServer`，模块名 `infer-dp-scheduler` |
| 构建入口（官方） | `Makefile`：`make package` |
| 构建入口（流水线） | `.codearts/build.sh` |
| 容器入口（官方产物） | `deploy.sh` |
| 容器入口（本地封装） | `rs_demo.sh`（薄壳，最后仍调 `deploy.sh`） |
| 二进制 | `cmd/route_server` → `route-server`，以及 `cmd/config-tool` → `config_generator` |
| 状态 | ☑ 已梳理（未做打镜像全流程复现） |

---

## 1. 核心问题

1. RS 的**发布包**里有什么？仓库为什么不带 Dockerfile？
2. 容器里靠什么把它**拉起来**？`deploy.sh` 到底做了几件事？
3. 为什么容器经常"**起来就退出**"？
4. P/D 实例是**怎么注册**进来的？运行期能不能加？
5. 多个 RS 容器怎么组成**集群**？

---

## 2. 一句话总结

> RS 的容器启动是**两段式**：先把 Go 静态二进制 + `deploy.sh` + YAML 打成一个"发布包"（走 `make package`），
> 容器启动时由 `deploy.sh` **现场生成配置**（`config_generator` 填模板）再拉起 `route-server`。
> **镜像怎么打不在仓库里**——仓库只交付"包 + 启动脚本"，Dockerfile 是外部（流水线/本地 `tmp/routeserver/`）补的。

---

## 3. 全局图

```
┌─ 构建期（仓库内）─────────────────────────────────────────┐
│  cmd/route_server  ──go build (CGO_ENABLED=0)──>  route-server   │
│  cmd/config-tool   ──go build──────────────────>  config_generator│
│  deploy/{*.yaml, deploy.sh, pipelines/, scale/}                  │
│                       └── make package ──> DistributedScheduler-*.zip│
└──────────────────────────────────────────────────────────────┘
                              │  （zip 被 COPY 进运行镜像）
┌─ 容器启动期 ─────────────────────────────────────────────────┐
│  ENTRYPOINT tini ──> rs_demo.sh                              │
│     1. unzip package.zip -> /opt/rs_pkg                      │
│     2. 起后端（mock_server ×2 或 external P/D）并等 /health    │
│     3. bash deploy.sh（官方入口）                              │
│     4. tail -F 保活                                           │
│                                                              │
│  deploy.sh 内部：                                             │
│     kill 旧进程 -> 铺/改 YAML -> config_generator 生成配置     │
│     -> export ENV_ROUTE_SERVER_CONFIG_PATH -> 后台起二进制      │
│                    -> sleep 5 验活 -> （无 --daemon）exit 0     │
└──────────────────────────────────────────────────────────────┘
                              │
                        route-server  :9800（业务） / :9810（运维）
```

---

## 4. 发布包：仓库到底产出什么

### 4.1 仓库里**没有** Dockerfile

| 证据 | 位置 |
| :-- | :-- |
| git 跟踪文件与磁盘（含未跟踪）均无 `Dockerfile` | `ls` / `git ls-files` |
| 打包步骤是"有就拷、没有就静默跳过" | `Makefile` 的 `copy-deploy`：`cp Dockerfile $(OUTPUT_DIR)/ 2>/dev/null \|\| true` |
| 但文档把 Dockerfile 列进了包结构 | `docs/build.md:142` |
| 流水线脚本只编译 + 打 tar.gz，**没有 docker build** | `.codearts/build.sh` |

> ⚠️ **文档比仓库多一个文件**。不要按 `docs/build.md` 的包结构去找 Dockerfile。
> 镜像实际由外部补：官方大概是流水线，本地是 `tmp/routeserver/Dockerfile.run`（见 §5）。

### 4.2 包内容（`make package` 口径）

```
<zip-root>/
├── deploy.sh                   # 容器内真正的入口
├── config_generator            # 配置生成器（按模板 + 参数写出 route-server.yaml）
├── route-server-template.yaml  # 配置模板（占位符由 env 填）
├── metrics_config*.yaml        # vLLM 版本相关的指标采集模板
├── prometheus-template.yaml
├── anthropic_error_type_config.yaml
├── pipelines/                  # PD / Hybrid / EPD / Layerwise 的 DAG 定义
├── scale/                      # 扩缩容脚本（join/leave + k8s 助手）
└── DistributedScheduler/
    ├── bin/route-server        # 静态二进制
    └── version.info            # 构建元信息
```

`version.info` 由 ldflags 注入的版本信息另存一份，内容形如：

```
Build Tag/Branch: dev
Build Commit ID: 54d7d80...
Build Time: 2026xxxx_xxxxxx
```

### 4.3 ⚠️ 两条构建路径的目录名**对不上**

| 路径 | 产物内层目录 | 与 `deploy.sh` 是否匹配 |
| :-- | :-- | :-- |
| `make package` | `DistributedScheduler/` | ✅ 匹配 |
| `.codearts/build.sh` | `route-server/route-server/bin/route-server` | ❌ 不匹配 |

`deploy.sh` 里 `PACKAGE_DIR=DistributedScheduler` 是**硬编码**，且一开始就检查
`${DEPLOY_ROOT_PATH}/DistributedScheduler` 是否存在，不存在直接 `Failed` 退出（`deploy.sh:615`）。

所以 CodeArts 打出来的包，**直接跑 deploy.sh 会在目录检查那步失败**，除非镜像构建阶段做了
`mv route-server DistributedScheduler`。仓库里看不到那一步 → 见 §11 疑问清单。

---

## 5. 容器内启动：`rs_demo.sh` 六步（本地封装，实际在用）

`tmp/routeserver/` 是本地为了"让 RS 跑起来压测"补的一层封装，**不是上游代码**，但清楚地展示了容器里该怎么用 RS。

### 5.1 镜像分两层

```dockerfile
# Dockerfile.build —— 只用来编译，产物不带走
FROM golang:1.25-bookworm
RUN apt-get install -y make zip unzip git     # Makefile 打包依赖 zip
WORKDIR /src

# Dockerfile.run —— 运行镜像，不装 Go
FROM debian:bookworm-slim
RUN apt-get install -y unzip curl jq procps tini
COPY pkg/package.zip /pkg/package.zip          # make package 的产物
COPY bin/mock_server /opt/bin/mock_server      # 不在包里，单独编（模拟 vLLM）
COPY rs_demo.sh      /opt/rs_demo.sh
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/rs_demo.sh"]
EXPOSE 9800 9810 8001 8002
```

构建流程 `build.sh`：`rsync 源码 → docker build 构建镜像 → 容器内 make clean && make package → 拷出 zip → 另编 mock_server`。

### 5.2 容器内 `rs_demo.sh` 做的事

| # | 动作 | 关键点 |
| :-- | :-- | :-- |
| 1 | `unzip package.zip -> /opt/rs_pkg` | 等价于用户拿到 zip 后解包 |
| 2 | 可选打 pipeline 补丁 | **必须在 deploy.sh 之前**，因为配置启动时一次性读入 |
| 3 | 起后端：`BACKENDS=mock` 起 2 个 `mock_server`；`external` 则轮询外部 P/D 的 `/health` | mock 端口 8001/8002 |
| 4 | **调快探活节奏**（仅演示） | `sed` 改模板：`interval-ms: 10000→2000`、`consecutive-time: 3→1` |
| 5 | 调 `deploy.sh`（官方路径） | 见下方命令；失败则打印 `deploy.log` 尾部并退出 |
| 6 | 轮询 `/status` 直到 `"status":"running"`，然后 `tail -F` 保活 | **靠 tail 撑住 PID 1** |

第 5 步的实际命令（这就是"容器里怎么用 RS"的标准姿势）：

```bash
cd /opt/rs_pkg
RS_INSTALL_DIR=/opt/route_server \
PREFILL_SERVERS="prefill1#127.0.0.1:8001" \
DECODE_SERVERS="decode1#127.0.0.1:8002" \
bash deploy.sh \
    --rs_name rs-demo \
    --host 0.0.0.0 \
    --port 9800 \
    --ops-port 9810 \
    --mode singleton \
    --infer-mode PD \
    --infer-module-version pipeline \
    --enable-https false \
    --ops-enable-https false \
    --client-https-enable false \
    --etcd-tls-enable false
```

注意三个细节：

- 实例地址格式是 **`名字#ip:port`**（`prefill1#127.0.0.1:8001`），多个用逗号分隔
- 容器里 `--host 0.0.0.0`（监听所有网卡），不是宿主 IP
- **四个 TLS 开关全部显式关掉**——模板默认全开，不关会因缺证书直接起不来（见 §7）

---

## 6. `deploy.sh` 做了什么（官方路径，8 步）

| # | 动作 | 细节 / 证据 |
| :-- | :-- | :-- |
| 1 | 解析参数 | 实例地址来自 `PREFILL_SERVERS`/`DECODE_SERVERS`/`ENCODE_SERVERS`/`MOE_SERVERS`，集群来自 `ETCD_ENDPOINTS` |
| 2 | 补默认值 | `RS_NAME`（缺省用本机 IP 生成）、`PORT=9800`、`RS_INSTALL_DIR=/opt/route_server` |
| 3 | 前置校验 | 检查 `DistributedScheduler/`、`route-server-template.yaml`、`prometheus-template.yaml`、`config_generator` 是否都在 |
| 4 | 安装 | 拷到 `${RS_INSTALL_DIR}/<rs_name>/DistributedScheduler/` |
| 5 | **幂等重启** | `ps -ef \| grep <路径> \| kill`，先杀旧进程 |
| 6 | 铺 + 改配置 | 拷 `pipelines/`、`metrics_config*`；按 infer-mode / `REUSE_PREFILLED_TOKENS` 用 `sed` 改 YAML |
| 7 | **生成配置** | `config_generator --template route-server-template.yaml ...` → 写 `config/route-server.yaml`（0600）；再拷 prometheus 模板 |
| 8 | 起进程 | `export ENV_ROUTE_SERVER_CONFIG_PATH`、设 `GOMAXPROCS`、`chmod 500`，后台拉起并 `sleep 5` 验活 |

### 6.1 配置不是挂进去的，是**生成**出来的

这是 RS 和常见"配置挂载"型服务最大的不同：

```
route-server-template.yaml（占位符 <ip> <port> <name> ...）
        +  环境变量（PREFILL_SERVERS 等）
        +  命令行（--infer-mode / --mode / TLS 开关）
        ──config_generator──>  <target>/config/route-server.yaml
```

二进制只认一个环境变量找配置：`ENV_ROUTE_SERVER_CONFIG_PATH`
（`pkg/common/constant/const.go:143`），而这个变量由 `deploy.sh` 导出。
**手工起二进制时必须自己 export，否则读不到配置。**

已有的 `route-server.yaml` 会被备份成 `.bak` 再重新生成（"exists in config dir, backup and regenerate"）。

---

## 7. 坑清单（按踩到概率排序）

### 7.1 ⚠️ 容器"起来就退出"

`deploy.sh` 末尾：

```bash
nohup .../bin/route-server > /dev/null 2>&1 &
PID=$!
sleep 5
if ! ps -p "$PID"; then exit 1; fi
if [ -z "$DAEMON" ]; then
  echo "... --daemon is not set, exit with 0"
  exit 0          # ← 脚本退出，进程被 nohup 甩在后台
else
  wait "$PID"
fi
```

如果容器把 `deploy.sh` 直接当 entrypoint（PID 1），**PID 1 一退容器就结束**。
两种解法：

- `--daemon true` → 脚本 `wait` 住进程（注意要带参数，只写 `--daemon` 会报 `requires a arg`）
- `--show-std-output true` → 前台输出，日志进 `docker logs`
- 或者像 `rs_demo.sh` 那样，自己 `tail -F` 挂住 PID 1

### 7.2 ⚠️ TLS 默认全开，容器里没证书就起不来

`deploy.sh` 默认 `ENABLE_HTTPS=true` / `OPS_ENABLE_HTTPS=true` / `CLIENT_HTTPS_ENABLE=true` / `ETCD_TLS_ENABLE=true`，
而 `server.go:301` 在 HTTPS 开但没配 `cert-file`/`key-file` 时直接返回错误：

```
HTTPS is enabled but TLS certificate is not configured: cert-file and key-file are required
```

本地/容器里跑必须显式关（见 §5.2 的四个 `--*-https false`）。生产该开，但要先把证书挂进去。

### 7.3 ⚠️ 配置和 pipeline 是**启动时一次性读入**的

`rs_demo.sh` 里那句注释很关键：

> 必须在 deploy.sh 之前改，因为配置是 route-server 启动时一次性读入的。

所以**热改 YAML 无效**，改 pipeline / 模板 → 必须重新 `deploy.sh`（或重启进程）。
`deploy.sh` 每次都会重铺 `pipelines/` 并重跑 `config_generator`，这既是"幂等重启"也是"配置漂移"的来源：
手工改过 `config/` 下的文件，下次重启会被覆盖。

### 7.4 ⚠️ 默认探活节奏很慢，看着像"起不来"

模板默认 `interval-ms: 10000` + `consecutive-time: 3`，实例要连续 3 次成功才 available，
`/status` 变 `running` 可能要**半分钟以上**。`rs_demo.sh` 为此把模板改成 `2000ms` / `consecutive-time: 1`（**仅演示**）。
编排里给 RS 的 startupProbe 留足时间，别用默认 10s 判死。

### 7.5 包目录名不一致（见 §4.3）

`DistributedScheduler` vs `route-server`，CodeArts 产物直接跑 `deploy.sh` 会 `Failed`。

### 7.6 `--readiness-cfg` 不满足就一直不 ready

默认 `prefill:1#decode:1`。实例没注册够，`/internal/worker/readiness` 返回 500，
K8s 会一直判未就绪——**这不是服务坏了，是没实例**。

### 7.7 二进制和目录被 `chmod 500`

`deploy.sh` 结束前 `chmod 500 bin bin/route-server`。容器里非 root 用户跑会**没权限执行**，
要么以 root 起，要么改权限。

---

## 8. 怎么用（命令速查）

### 8.1 起容器（本地封装）

```bash
# 构建：源码 rsync -> 容器内 make package -> 出 pkg/package.zip
tmp/routeserver/build.sh

# 起容器（自带 2 个 mock vLLM）
tmp/routeserver/run.sh

# 起容器（后端接外部真 P/D）
tmp/routeserver/run_ext.sh
```

### 8.2 验证

```bash
curl -s localhost:9800/status | python3 -m json.tool      # 期望 "status": "running"
curl -s -o /dev/null -w '%{http_code}\n' localhost:9800/internal/liveness
curl -s localhost:9800/ | python3 -m json.tool             # 版本信息
docker logs -f rs-demo
```

### 8.3 压测

```bash
vllm bench serve --base-url http://127.0.0.1:9800 --model <name> --dataset-name random ...
```

对客户端来说就是普通 OpenAI 端点，**不需要知道后端是 P/D 两个实例**。

### 8.4 实例注册（运行期）

```bash
python3 scale/rs_instance_join.py \
    --rs-addr=<RS_IP>:<PORT> --role=decode \
    --instance-ips=<IP1>,<IP2> --api-server-ports=9000,9000 \
    --static-infos=max_num_seqs#32 --ascend-rt-visible-devices-num=16
```

摘除走 `rs_instance_leave.py`，它**不是直接摘**：等 running/waiting 队列清空，
P 侧再多等 `--waiting-kvcache-pulled-completed-time`（默认 120s）让 KV 拉完，是给弹性伸缩用的优雅摘流。

---

## 9. 端口与探针

| 用途 | 端口 | 说明 |
| :-- | :-- | :-- |
| 业务推理 | `--port`，默认 `9800` | OpenAI / Anthropic 兼容接口 |
| 运维 | 默认 `业务端口 + 10` | 可 `--ops-port` 覆盖；**独立 TLS 配置** |
| pprof | `20000` | 仅 `-debug` 时开 |
| meta server | 同业务端口 | `/v1/metaserver`，Layerwise 模式下 vLLM 反向回调用 |

探针（都在业务端口）：

| 路径 | 含义 |
| :-- | :-- |
| `/internal/liveness` | 进程活着就 200 |
| `/internal/worker/readiness` | 按 required-roles 检查可用实例数 |
| `/internal/leader/readiness` | 仅看自己是不是 Leader |

> 别把 liveness 和 readiness 混用：worker 的 readiness 依赖**实例注册**，
> 实例没起来时 liveness 是 200、readiness 是 500，属于预期行为。

---

## 10. 多 RS 集群模式

每个容器跑同一套 `deploy.sh`，只是参数不同：

```bash
bash deploy.sh \
    --mode etcd \
    --etcd-endpoints "<ip1>:2379,<ip2>:2379,<ip3>:2379" \
    --candidate true \
    ...
```

- 容器内**不区分角色**，靠 etcd 选主（`/rs/leader`，租约默认 3s、1s 续约）
- Leader 做调度决策，非 Leader 只做请求转发 + 流式回写（`adminLeaderProxyMiddleware`）
- ⚠️ 官方文档明确：**ETCD 集群不能在多个 MO 集群间共享**，否则两个集群会合并，造成 P/D 跨集群访问

---

## 11. 疑问清单（待解决）

- [ ] `docs/build.md` 里写的 `Dockerfile` 到底谁提供？CodeArts 流水线里有没有 `mv route-server DistributedScheduler`？
- [ ] 官方生产镜像的基础镜像和时区/证书挂载约定是什么？
- [ ] `scale/` 下的 `k8s/*.py`（`check_instance_status.py` / `health.py`）在编排里是怎么被调用的？
- [ ] `--max-procs`（GOMAXPROCS）在容器 CPU limit 下有没有推荐值？
- [ ] 非 root 运行时 `chmod 500` 的处理方式（是否需要 `--user` + 预改权限）？

---

## 附录 A：源码出处对照

| 结论 | 出处 |
| :-- | :-- |
| 配置目录环境变量 | `pkg/common/constant/const.go:143` `ENV_ROUTE_SERVER_CONFIG_PATH` |
| 配置生成器输出 | `cmd/config-tool/config_generator.go:482` 写 `route-server.yaml`（0600） |
| 日志默认路径 | `cmd/config-tool/config_generator.go:458` `<target>/log/route-server.log` |
| 包目录硬编码 | `deploy/deploy.sh:27` `PACKAGE_DIR=DistributedScheduler`；`:615` 目录检查 |
| 安装目录默认 | `deploy/deploy.sh` `RS_INSTALL_DIR=/opt/route_server` |
| 幂等重启 | `deploy/deploy.sh` `ps -ef \| grep <路径> \| kill` |
| 后台起进程 + 验活 | `deploy/deploy.sh:848-871` |
| `--daemon` 语义 | `docs/deploy.md:105`；`deploy/deploy.sh:213` 参数解析 |
| TLS 缺失即失败 | `cmd/route_server/server/server.go:301` |
| 运维端口默认 +10 | `cmd/route_server/server/app.go:420-429` |
| 探针实现 | `cmd/route_server/server/probe.go` |
| 打包内容 | `Makefile` `copy-deploy` / `package` |
| 流水线构建 | `.codearts/build.sh` |
| 本地镜像封装 | `tmp/routeserver/Dockerfile.build`、`Dockerfile.run`、`rs_demo.sh`、`build.sh`、`run.sh` |

## 附录 B：和实验E 的关系

| 文档 | 关注点 |
| :-- | :-- |
| **本篇（11）** | RS **怎么被装进容器、怎么起、怎么配、坑在哪** |
| [实验E](实验E-RouteServer对接P-D空跑.md) | RS **接什么后端**：空跑引擎（`--simulate-forward`）+ pipeline 补丁，避免"静默降级成假 P/D" |

实验E 里的 `rs-demo:dev` 镜像就是按 `tmp/routeserver/` 这套封装的；`run.sh` 复用本篇 §5.2 的 `rs_demo.sh`，
只是用 `BACKENDS=external` + `PIPELINE_PATCH` 换掉了 mock 后端。
