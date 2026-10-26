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
  每个 commit 单独 checkout 也都跑过（142/143/760/761 passed）。
- **状态：个人验证阶段，暂不提交社区。** 未做：NPU 实机 e2e、release note fragment
  （`release_notes/fragments/<PR号>.yaml`，社区 PR 时才需要）。
- 远程：`origin` = gh-proxy 镜像的上游（只读），`fork` = `sunlei1992/vllm-ascend`（SSH 可写）。

### vLLM 原生 simulator 实验环境（PR #47922）

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

## 4. 已知环境问题（不是代码 bug）

- `tests/ut/kv_offload` 全目录跑时 `test_sfa_pd_rd2h_lifecycle.py` 有 20 个失败（跨文件 mock 泄漏）；
  单独跑该文件 21 个全过。
- `tests/ut/worker/test_worker_v1.py` 3 个失败：`PermissionError: '/Users/sunlei/ascend'`，沙箱挡住 CANN 路径。
- `test_encoder_acl_graph.py` 2 个失败：CPU 平台下 mock 为 None，既有问题。
- `gh` CLI 的 token 已失效；push 一律走 SSH（`git@github.com:...`），不要用 `origin` 的 gh-proxy 地址。

## 5. 约定

- 提交信息用 Conventional Commits（`feat(kv-pool): ...`），带 `-s` 签名。
- 改 vllm-ascend 前先跑一遍相关 UT 基线，改完保持全绿。
- 新的调研结论写进 `wiki/` 或 `kvcache-research/`，不要只留在对话里。
