# AGENTS.md — vLLM 学习/实验工作区

> 给 AI agent 的工作记忆。`wiki/` 是写给人看的学习笔记，本文件是给 agent 接上下文用的。
> 最近更新：2026-10-20

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
  1. `9a3821e6b` fix: reload shared buffers on the block-key plane
  2. `6c0e4b2a2` fix: scope the block-key partial tail by its end token
  3. `604bc19bd` feat: plan layerwise buffer reuse on the block-key plane
  4. `fe6de285b` feat: enable shared KV buffers on the Mooncake backend
- 验证：`tests/ut/distributed/ascend_store` 761 passed / 12 skipped；ruff 通过。
  **Linux 容器（无 NPU）复跑一致**：761 passed / 12 skipped / 420 subtests in 13.57s（2026-10-26）。
  每个 commit 单独 checkout 也都跑过（142/143/760/761 passed）。
- **状态：个人验证阶段，暂不提交社区。** 未做：NPU 实机 e2e、release note fragment
  （`release_notes/fragments/<PR号>.yaml`，社区 PR 时才需要）。
- 远程：`origin` = gh-proxy 镜像的上游（只读），`fork` = `sunlei1992/vllm-ascend`（SSH 可写）。
- 详细笔记：`wiki/ascend对照笔记/003-layerwise-KV-buffer复用.md`

### 空跑模式（dry run，PR #47922 simulate-forward）

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

## 4. 已知环境问题（不是代码 bug）

- `tests/ut/kv_offload` 全目录跑时 `test_sfa_pd_rd2h_lifecycle.py` 有 20 个失败（跨文件 mock 泄漏）；
  单独跑该文件 21 个全过。
- `tests/ut/worker/test_worker_v1.py` 3 个失败：`PermissionError: '/Users/sunlei/ascend'`，沙箱挡住 CANN 路径。
- `test_encoder_acl_graph.py` 2 个失败：CPU 平台下 mock 为 None，既有问题。
- `gh` CLI 的 token 已失效；push 一律走 SSH（`git@github.com:...`），不要用 `origin` 的 gh-proxy 地址。

## 5. 约定

- **待办与想法统一记在根目录 [`todo.md`](todo.md)**：每条有 ID（`T-###`/`I-###`），
  写不出"下一步"的放「想法池」；完成时移到「归档」并留证据。
  本文件（`AGENTS.md`）只记状态与结论，不记 TODO。
- 提交信息用 Conventional Commits（`feat(kv-pool): ...`），带 `-s` 签名。
- 改 vllm-ascend 前先跑一遍相关 UT 基线，改完保持全绿。
- 新的调研结论写进 `wiki/` 或 `kvcache-research/`，不要只留在对话里。
