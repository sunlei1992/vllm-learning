# AGENTS.md — vLLM 学习/实验工作区

> 给 AI agent 的工作记忆。`wiki/` 是写给人看的学习笔记，本文件是给 agent 接上下文用的。
> 最近更新：2026-10-29

## 1. 目录与仓库边界

| 路径 | 说明 | 是否入库 |
| :--- | :--- | :--- |
| `vllm-src/` | vLLM 源码 git 仓库，`.venv` 的 editable 指向这里 | ❌ `.gitignore` |
| `vllm-ascend-src/` | vllm-ascend 源码 git 仓库 | ❌ `.gitignore` |
| `tmp/` | worktree、补丁、日志等临时物 | ❌ `.gitignore` |
| `wiki/` | 学习笔记、搭建记录、git 指南 | ✅ |
| `kvcache-research/`、`kv_research/` | KV Cache 调研 | ✅（raw/ 除外） |

两个上游源码目录各自是独立 git 仓库，**不要**把它们的内容提交到本工作区仓库。

## 2. 本地验证环境（Mac M3 / CPU，无 NPU）

| venv | vLLM 版本 | 用途 |
| :--- | :--- | :--- |
| `.venv` | 0.28.0（`vllm-src`，editable） | 原始学习环境，能跑 CPU 推理 |
| `.venv-va030` | `a98247ab4`（vllm-ascend main 的 pinned commit） | 跑 vllm-ascend main 的单测 |

- **版本配对规则**：vllm-ascend `main` 跟的是 vLLM main 的某个 commit，记在
  `vllm-ascend-src/.github/vllm-main-verified.commit`。**不能**用 `v0.30.0` 这类 release tag 配 main，
  会缺 `prepare_dcp_local_seq_lens` 等新 API，import 直接失败。
- vLLM 源码 worktree：`tmp/vllm-030`（CPU 编译约 1 分钟）。
- 跑测试：`./tmp/run-ascend-ut.sh tests/ut/distributed/ascend_store -q`
  等价于在 `vllm-ascend-src/` 下 `PYTHONPATH=. ../.venv-va030/bin/python -m pytest ...`。
- 详细环境记录见 `tmp/va030-env.md`。

## 3. 当前进行中的工作（2026-10-20）

**主题**：给 vllm-ascend 的 Mooncake（block-key）数据面开启 layerwise KV buffer 复用。

- 本地分支：`feature/mooncake-layerwise-reuse`，基于上游 `8237ee6d6`，4 个提交。
- 已推送到个人 fork：`git@github.com:sunlei1992/vllm-ascend.git`（公开 fork），
  远程分支同名。本地 `main` 已重置回 `origin/main`，保持与上游同步。
- 提交：
  1. `2148087ce` fix: reload shared buffers on the block-key plane
  2. `b56582775` fix: scope the block-key partial tail by its end token
  3. `4e2042140` feat: plan layerwise buffer reuse on the block-key plane
  4. `13d80c908` feat: enable shared KV buffers on the Mooncake backend
- 验证：`tests/ut/distributed/ascend_store` 761 passed / 12 skipped；ruff 通过。
  **Linux 容器（无 NPU）复跑一致**：761 passed / 12 skipped / 420 subtests in 13.57s（2026-10-26）。
  每个 commit 单独 checkout 也都跑过（142/143/760/761 passed）。
- **身份**：4 个 commit 的作者/提交者/签名已统一为 `sl <sunclouddev@163.com>`（2026-10-26 修复）。
- **GLM-5.3 形状已验证（本地合成，2026-10-28）**：78 层 × (主 MLA + `AscendSFAIndexerCacheSpec`)
  是**单** UniformType group → `use_hybrid=False` → 复用布局可用；`buffer_slots=3`（1 独立 + 2 共享），
  78 个物理层全部配对 indexer。新增 UT `test_glm53_sfa_indexer_layers_get_reuse`（VA `8eb74f2c7`，
  分支 `local/simulated-ascend-store`）。真机仍缺 indexer 数据面验证。
- **状态：个人验证阶段，暂不提交社区。** 未做：NPU 实机 e2e、release note fragment
  （`release_notes/fragments/<PR号>.yaml`，社区 PR 时才需要）。
- 远程：`origin` = gh-proxy 镜像的上游（只读），`fork` = `sunlei1992/vllm-ascend`（SSH 可写）。
- 详细笔记：`wiki/ascend对照笔记/003-layerwise-KV-buffer复用.md`

### 空跑模式（dry run，PR #47922 simulate-forward）

**仿真器移植矩阵（2026-10-29 快照）**

| 版本线 | 分支 / 提交 | 镜像 | 能力 |
| :-- | :-- | :-- | :-- |
| **main**（`a98247ab`） | `sim-integrated` / `d96a6f5b82`（fork 已推） | `sim-int:store3` | 冒烟、时间模型、离线/在线 P/D、VA 共存、fake AscendStore（含计时）、多轮 APC |
| **v0.30.0**（`ced6857af`） | `sim-0.30-integrated` / `a5d8ccc654`（fork 已推） | `sim030:int3` | 冒烟、离线/在线 P/D、VA 0.30 + 离线 P/D；`vllm bench sweep simulate` 不可用（未移植 serve 重构） |

两条线的调度指标**逐位一致**：1P1D 90.89 / 2P1D 87.51 / 1P2D 92.81 / 2P2D 68.95 ms。

- 分支 `sim` 在 `tmp/vllm-030`（基于 `a98247ab`），提交 `16ab166382`，已应用 #47922 并跑通。
- **macOS 原生不可用**：MRV2 依赖 triton，而 triton-cpu 只有 Linux wheel。
- 可用方式：Docker Desktop + `linux/arm64` 容器，镜像 `sim-built`（已编译好 vLLM + ACL + oneDNN）。
- 一键复现：`./tmp/sim_forward_run.sh`（内部挂载 `tmp/` 下的 triton/torchvision/torchaudio/torchcodec CPU wheel）。
- 实测结果：虚拟 KV 146 blocks、模型加载 0.01 GiB（meta device、不读权重）、
  输出 token 与注入的 trace 完全一致（`[100..107]`）。
- **60s 停顿已定位并解决**：不是死锁，是 Triton CPU 后端在运行时 JIT 编译 kernel
  （`buffer_utils.apply_write` → `triton/backends/cpu/compiler.py:make_asm`），每个约 60s。
  把 `TRITON_CACHE_DIR` 指向持久目录（`tmp/triton-cache`）后：冷缓存 146s → 热缓存 **0.26s**。
  `tmp/sim_forward_run.sh` 已默认挂载该缓存。
- **step 级观测**：`VLLM_ENABLE_V1_MULTIPROCESSING=0` 让 Scheduler 跑在主进程，
  可以 monkey-patch `Scheduler.schedule` 记录每步（脚本 `tmp/sim_steps.py`）。
  通用跑法：`./tmp/run_in_container.sh <tmp 下的脚本>`。
- 实测（`max_num_batched_tokens=64`，4 请求）：7 个 step、0.23s，chunked prefill 清晰可见
  （step 0–3 长请求吃满 64 token，`running=1 waiting=2`；step 4 预算释放后进来 2 个新请求）。
- 注意：**换 workload 形状可能触发新的 Triton JIT**（首次 48s，同形状再跑 0.23s），
  实验脚本要么固定 workload，要么先预热。
- **多轮实验 + KV block 观测**：`tmp/sim_rounds.py`（同一引擎实例连续 generate，
  记录每步 prefill/chunk/decode 组成、running/waiting、`kv_cache_manager.block_pool` 占用）。
  实测 3 轮：短请求 2 步、长请求 6 步（4×64+45 分块）、4 并发 2 步；
  KV block 随 prefill 推进 1→2→3，结束即释放（下一轮从自己的请求数重新开始）。
- **KV 压力 / 抢占**：`tmp/sim_kv_stress.py`（env: `KV_MB/N_REQS/PROMPT_REP/MAX_TOKENS/MAX_MODEL_LEN`）。
  两个关键结论：① 准入控制是"没 block 就排队"，只压长 prompt 只会 `waiting`，不会抢占；
  ② 抢占要"运行中的请求自己长大"——短 prompt + 长输出 + 小 KV。实测 128MB/8 blocks/8 请求×300 token：
  564 步、7 次抢占、max_waiting=6；第一次抢占在 step 127（第 128 个 token 后需要第 2 个 block）。
  冷 47.9s → 热 0.353s。
- 跑任意脚本：`KV_MB=... ./tmp/run_in_container.sh <script.py>`（runner 会透传这些 env）。
- **参数扫描**：`tmp/sim_sweep.py`（固定 8 请求 workload、KV 2GiB、`max_tokens=8`；
  扫 `max_num_batched_tokens` {64,128,256,512} × `max_num_seqs` {2,4,8}，每组重建引擎）。
  结论：预算/并发 ↑ → 步数 50→10（5×）、avg_reqs 1.7→6.6（3.9×）、chunk 步 21→2、max_waiting 6→3、
  KV 峰值 8→18；无抢占（KV 给足）。**模拟器没有时间模型，只能证明"调度行为变了"，不能说"更快"。**
- **前缀缓存**：`tmp/sim_prefix.py`（8 个依次发送的请求共享 371-token prompt，`MAX_BATCHED` 可调）。
  off/on 对比：prefill token 2968 → 1176（-60.4%）；命中按 block 对齐（共享前缀 ~308 token，
  只复用 2×128=256）；步数只在窄预算下下降（128 预算：每请求 4→2，总 32→18）；
  `kv_peak` 不变，因为缓存块可驱逐、仍计入 free。
- **时间模型（初版）**：`tmp/sim_timing.py`。给每步定价
  `cost = c_prefill*prefill_tokens + c_decode*decode_tokens + c_overhead`，
  逐请求推 TTFT（prefill 完成那步结束）与 TPOT。系数未标定，所以扫 `c_prefill/c_decode`：
  比例 0.01 时 TTFT 最优是 512/8；0.1 时变成 64/4；1.0 时 64/2。
  makespan 最优恒为 512/8，但 ratio=1.0 下 makespan 只比 64/2 好 0.13%，
  而 mean TTFT 差 33%（945 vs 710）——**吞吐最优 ≠ 延迟最优**。
- **脚本归档**：以上实验脚本已复制到 `wiki/vllm架构笔记/assets/simulate-forward/` 并入库
  （`tmp/` 被 gitignore，只有本机副本）。归档版 `run_in_container.sh` 用
  `VLLM_LAB_ROOT` 或脚本位置推导仓库根。
- **镜像构建**：逐层命令见 `wiki/vllm架构笔记/assets/simulate-forward/DOCKER.md`
  （apt 换源、torch `+cpu`、ACL/oneDNN 预取、`libnuma-dev`、`MAX_JOBS=2`、shm 等）。
- **策略对比**：`sim_policy.py` 通过重排 `Scheduler.waiting`（deque）实现 FCFS / 短优先 / 长优先，
  不改 vLLM。实测三者 **makespan 完全相同（205.45）**，但 mean TTFT 56.5 / 90.9 / 143.0，
  max TTFT 181 / 171 / 152——**策略只重新分配延迟，不改变总吞吐**。
- **空跑 + vllm-ascend main**：`assets/simulate-forward/va/run_va_dry_run.sh`。VA main 的
  vLLM pin 就是 `a98247ab`（与空跑容器一致），因此**可直接加载**。需要 6 个 stub
  （torch_npu、torch.npu、`_build_info`、triton cann 算子、HCCL、`torch_npu._C`）+ 改
  `register()`（无 NPU 返回 None）+ 伪造 entry points。实测 4 个 general plugin 全 OK，
  `patch_engine_core` / `patch_kv_cache_utils` 已生效，空跑输出正确。
  详见 `wiki/ascend对照笔记/004-在空跑环境加载vllm-ascend.md`。
- **VA 补丁 on/off 实测（T-011）**：dense 模型（Qwen3）下补丁**逐位 no-op**（13 步、145 blocks、
  TTFT 90.94、makespan 205.45 完全相同）；MLA 模型（DeepSeek-V2-Lite）下补丁 ON 崩溃
  （`Ascend config is not initialized`），因为 CPU 平台没人调 `init_ascend_config`。
  VA 自带的 `ShortRequestFirstAsyncScheduler` 还要求 `async_scheduling=True`，而空跑强制 False。
  **结论：空跑=兼容性脚手架，不是 VA 策略评估器；评估策略请用 `sim_policy.py`。**
- **复刻 VA 短请求优先（T-012）**：`sim_srs.py`（同时到达）/ `sim_srs_arrivals.py`（错峰到达）。
  同时到达（budget=256）：短请求均值 83.83→25.65（-69%），长请求 +5%，老化**完全不触发**
  （短请求早已做完，提权时 `short=0`）。错峰 + 竞争：mean TTFT 209.95→147.68（-30%），
  短请求 -50%，长请求 +4%，makespan 不变。老化阈值是**悬崖**：≤100 全退化为 FCFS，≥120 等价纯 SRS，
  没有中间态（同批长请求等待时间相同）。
- **v0.30 迁移（已完成）**：`tmp/vllm-030-030`（分支 `sim-0.30`，基于 v0.30.0）+
  `tmp/va030`（VA `releases/v0.30.0`）。镜像 `sim030:build` → `sim030:dry-run`。
  补丁冲突 5 hunk + 1 处 API（`prepare_inputs` 无 `num_active_loras`）。
  VA 0.30 还需 `VLLM_USE_V2_MODEL_RUNNER=1`（它的 patch 覆盖了上游 MRV2 判定）。
  复现：`assets/simulate-forward/run_smoke_030.sh` / `va/run_va_dry_run_030.sh`。
  详见 `wiki/ascend对照笔记/005-空跑迁移到v0.30.md`。
- **main vs 0.30 行为对照（实测）**：策略对比、12 组参数扫描、KV 抢占（564 步/7 次）、
  前缀缓存（2968→1176）四条路径上，两者**调度指标逐位一致**，只有墙钟时间不同。
  → 0.30 移植保真；这 1428 个 commit 没改这些调度路径。
- **在线模式（HTTP server）**：`python -m vllm.entrypoints.openai.api_server --simulate-forward ...`
  可用；启动约 24s。请求必须带 `trace_decode_token_ids`（completion/chat 都有），
  **不带 trace 会静默返回全 0 token**（200，不报错）。要看 token 需 `return_token_ids: true`。
  并发 4 个不同 trace 互不串扰。
  脚本：`assets/simulate-forward/server/{run_server,smoke_client}.sh`，实验B 第 15 节。
- **⚠️ KV 容量必须对齐真实硬件（实验B §18）**：空跑的容量不是测出来的——
  给 `--kv-cache-memory-bytes` 就用它，不给就用 **主机内存 × gpu_memory_utilization**（Mac 上约 21GB，毫无意义）。
  容量 → 块数 → 准入/抢占，给错则结论无意义。取数方法：抄真实日志的
  `Available KV cache memory: X GiB` / `GPU KV cache size` / `GPU blocks`，或按
  `HBM×util − 权重 − 激活` 估算。另外注意 block_size（CPU 32/128 vs GPU 16）和 MLA 在 CPU 上的降级。
- **MLA 支持**：PR Notes 写"Doesn't support MLA yet (deepseekv4)"，但代码里**没有强制检查**。
  实测 DeepSeek-V2-Lite（V2 风格 MLA，config 为实验A 截断的 **3 层**版）在 0.30 空跑下正常：
  38,836 blocks / 621,376 tokens，
  trace token 正确。限制更可能只针对 **V4 风格**（`compress_ratios` / unified head_dim）。
  用 MLA 前先跑 `assets/simulate-forward/sim_mla.py` 冒烟。
- **GLM-5.3 空跑**：`glm53/run_glm53.sh`（镜像 `sim030:glm53`）。config 只下 5 个文件（29KB + 20MB tokenizer），
  78 层完整、无权重。CPU 会拦稀疏注意力（`cpu.py` 的 `use_sparse`），需把 `deepseek_v2.py` 两处
  `is_v32 = False`（同实验A）。结果：23,888 tokens / 1,493 blocks（16/block，约 88KB/token），
  init 13.5s、generate 0.37s、trace 正确。**caveat：`is_v32=False` 同时关掉了 DSA indexer，
  所以模拟的是 dense MLA 变体，GLM-5.3 真正省 KV 的那部分未建模。**
  **main 镜像同样验证**（`sim-main:glm53`，vllm 0.31.1rc1）：23,888 tokens / 1,493 blocks / 11.66x，
  与 0.30 **逐位一致**。
- **#61506 仿真器（实验C）**：分支 `sim-integrated`（worktree `tmp/vllm-sim-int`，基于 `a98247ab`），
  提交 `1cd22c891b`，镜像 `sim-int:dry-run`。移植时 43 文件里 4 个冲突（gpu_worker `_bind_device`、
  cpu.py 仿真 block_size、config 钩子、base_loader meta 跳过 repack），**无 csrc 改动**→复用已编译扩展。
  能力：可插拔时间模型（zero/linear/table/replay）、录制、**P/D 分离**、配置搜索、TP/PP/DP、投机解码。
  冒烟：block_size 32、18,720 tokens / 585 blocks、`timing=zero` 时 generate 0.00s。
  P/D 用 `simulate_disaggregated(prefill_args, decode_args, requests, num_prefill, num_decode)`
  （内部自动配 NixlConnector + 模拟 NIXL 传输）；16 请求下 2P2D 最优（mean TTFT 68.95ms vs 1P1D 90.89ms）。
  脚本 `pd/run_pd.sh` + `pd/sim_pd_ratio.py`，详见 `wiki/vllm架构笔记/实验C-移植PR61506仿真器.md`。
  **VA + P/D 也通**（`pd/run_pd_va.sh`）：4 个 plugin OK，1P1D/2P1D/1P2D/2P2D 的 TTFT 与纯 vLLM 逐位一致。
  **在线 P/D 也通**（`pd/online_pd.sh` / `online_pd_va.sh`）：两个 server 必须同容器（`remote_host=localhost`），
  side-channel 端口用 `VLLM_NIXL_SIDE_CHANNEL_PORT` 区分；`vllm serve` 必须给
  `--simulation-config '{"kv_transfer_timing":{"load_gbps":10}}'`，否则报 "Simulated KV transfer needs
  simulation_config.kv_transfer_timing"。流程：prefill（max_tokens=1 + do_remote_decode）→ 拿
  `kv_transfer_params` → decode 带参数生成。
- **多轮 APC + 二级缓存代理实验（实验C §12）**：用 `OffloadingConnector`(+`CPUOffloadingSpec`) 代替
  Mooncake 做分层缓存仿真，脚本 `mt/run_multiturn.sh`。实测（Qwen3-0.6B、HBM 1GiB、8 会话×6 轮）：
  容量 4GiB 后命中率饱和在 81.1%（= 1 − 新增 token 占比），TTFT 19.4→11.1ms；
  带宽 10GB/s 以下收益消失（B*=k×R≈11.2GB/s），5GB/s 反而更差。
  **AscendStoreConnector 当前不能空跑**（§13）：`ValueError: Simulated forward does not support the
  AscendStoreConnector connector`；要支持需假 store + simulated worker（1–2 天）。
- **fake AscendStoreConnector 已实现（实验C §14）**：VA 分支 `local/simulated-ascend-store` 新增
  `SimulatedAscendStoreConnector`（scheduler 真实查找 + 内存 LRU；worker no-op），
  vLLM 侧放行 + `simulated_kv_connector` 挂 `_NoTransfers`；镜像 `sim-int:store2`。
  容量扫描：1G 以下无效、2G 66.3%、4G 饱和 81.1%，阈值≈工作集 2.8GiB。
  **传输计时已补齐**（`SimulatedStoreWorker` + 异步加载）：10/25/50 GB/s 下 TTFT 为
  21.0/13.4/10.9ms，与 offloading 的 21.7/13.7/11.1ms 基本重合。
- **#61506 移植到 v0.30.0（实验C §16）**：分支 `sim-0.30-integrated`（基于 `ced6857af`，
  提交 `a5d8ccc654`，已推 fork），镜像 `sim030:int3`。9 文件 / 20 hunk（main 是 4/6）；
  冲突集中在 config、arg_utils、cpu.py、gpu_worker、gpu/model_runner、kv_connector；
  运行期还要补两处（没有 `_init_workspace_and_model_runner`、`prepare_inputs` 无 `num_active_loras`）。
  未移植 `benchmarks/serve.py` 重构（`vllm bench sweep simulate` 不可用）。
  验证：冒烟（585 blocks / 18,720 tokens）、离线 P/D、在线 P/D、VA 0.30 + P/D，
  TTFT 90.89/87.51/92.81/68.95 与 main 移植**逐位一致**。
- **layerwise HBM 节省（003 §11）**：槽位 `S = num_shared_buffers + len(independent)`，
  节省 `1 − S/L`，容量倍数 `L/S`。GLM-5.3（L=78）：N=3 → 4 槽，省 94.9%、容量 19.5×；
  140K 单请求 KV 从 12.0 GiB → 615 MiB。`apply_layerwise_kv_cache_plan` 只改 descriptor
  不改 `num_blocks`，默认是"占用变少"，要"容量变大"需同步调大 KV 预算。
  **Mooncake 存储池不省**；不设 `layerwise_num_shared_buffers`（默认=层数）则完全不复用。
- **P0/P1/P2 本机验证 layerwise（实验C §15）**：
  P1 把 `torch_npu` stub 的 `Event` 换成 threading 语义；
  P0 新增 `tests/ut/distributed/ascend_store/test_layerwise_fake_store.py`（CPU 张量 + fake address store +
  真实 `LayerBatchBuilder`），覆盖 main+indexer round-trip、复用 slot 覆盖后重载、非均匀层；全量 **766 passed**；
  P2 用 fake AscendStore 跑 24 公共前缀（24 会话×6 轮）：store 16 GiB 命中 80.0%/TTFT 18.6ms，
  store 8 GiB 掉到 54.2%/p90 215ms → **24 个 140K 前缀约需 295 GiB store**。
  剩余只有 P3 真机（RDMA、NPU kernel、带宽）。
- **GLM-5.3 + VA 0.30 共存**：`va/run_va_glm53.sh`。在纯 vLLM 的 `is_v32=False` 之外还要
  ① 跳过 `register_model`（VA 的 deepseek_mtp 要 AscendConfig）② 在 `Worker.load_model` 里
  `init_ascend_config`（patch_fused_moe 要 eplb_config）③ 给 `RoutedExperts.__init__` 丢掉
  `n_shared_experts`（VA 多传的 kwarg）。跑通后 KV 指标与纯 vLLM 完全一致（23,888/1,493/11.66x）。
  **注意 `VA_SKIP_MODEL=1` 意味着 VA 模型侧补丁未生效，只验证了 platform 层共存。**
  判断 VA 是否真生效：必须看到 `[va-plugin] ... OK` + `patch_engine_core` / `patch_kv_cache_utils`；
  只看 `[sim]` 输出可能只是纯 vLLM（归档脚本曾因 ROOT 深度和模板语法 bug 出现假阳性）。

## 4. 已知环境问题（不是代码 bug）

- `tests/ut/kv_offload` 全目录跑时 `test_sfa_pd_rd2h_lifecycle.py` 有 20 个失败（跨文件 mock 泄漏）；
  单独跑该文件 21 个全过。
- `tests/ut/worker/test_worker_v1.py` 3 个失败：`PermissionError: '/Users/sunlei/ascend'`，沙箱挡住 CANN 路径。
- `test_encoder_acl_graph.py` 2 个失败：CPU 平台下 mock 为 None，既有问题。
- `gh` CLI 的 token 已失效；push 一律走 SSH（`git@github.com:...`），不要用 `origin` 的 gh-proxy 地址。

## 5. 约定

- **本仓库是个人仓：直接 commit + push 到 `main`，不开分支、不走 PR。**
- **待办与想法统一记在根目录 [`todo.md`](todo.md)**：每条有 ID（`T-###`/`I-###`），
  写不出"下一步"的放「想法池」；完成时移到「归档」并留证据。
  本文件（`AGENTS.md`）只记状态与结论，不记 TODO。
- 提交信息用 Conventional Commits（`feat(kv-pool): ...`），带 `-s` 签名。
- 改 vllm-ascend 前先跑一遍相关 UT 基线，改完保持全绿。
- 新的调研结论写进 `wiki/` 或 `kvcache-research/`，不要只留在对话里。
