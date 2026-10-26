# TODO

> 用途：持久化**对话中产生的想法与待办**，避免"聊过就忘"。
> 与其它文档的分工：
> - `AGENTS.md`：**现在是什么状态**（环境、当前工作、已知问题）
> - `wiki/`：**已经想清楚的东西**（结论、实验、设计）
> - `todo.md`（本文）：**接下来要做什么**
>
> 约定：
> 1. 每条有唯一 ID（`T-###` / `I-###`），对话和 commit 里可以直接引用
> 2. **写不出"下一步"的，放「想法池」，不放「待办」**
> 3. 每条 ≤ 2 行；细节写进 wiki，不在这里展开
> 4. 完成时填完成日期 + 证据（commit / 测试结果），移到「归档」
> 5. 状态变更随手提交，git 历史就是变更记录
> 6. 每周过一遍：「现在做」超过 5 条就砍，「阻塞」看看解除条件

---

## 现在做（最多 5 条）

| ID | 事项 | 下一步 | 完成标准 |
| :-- | :-- | :-- | :-- |
| T-001 | Linux 容器跑完整 `ascend_store` UT | 起 `sim-built` 容器装 pytest 后跑 `tests/ut/distributed/ascend_store` | 与 macOS 一致：761 passed / 12 skipped |
| T-002 | 修 `Signed-off-by` 邮箱（当前有两个 `@`） | 改 git 配置后 rebase 4 个 commit | `git log --format=%B` 里没有双 `@` |

---

## 待办

| ID | 事项 | 领域 | 优先级 | 下一步 | 完成标准 | 参考 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| T-005 | 时间模型加二次项（prefill ≈ tokens²） | simulator | P2 | 在 `sim_timing.py` 加 `c_quad` 项，重跑扫描 | 长 prompt 的 TTFT 不再线性外推 | 实验B 第 12 节 |
| T-008 | 前缀缓存 × 时间模型组合实验 | simulator | P2 | 命中率 0/25/50/75% 各跑一次，比较 TTFT | 得到"命中率→TTFT"曲线 | 实验B 第 11/12 节 |
| T-010 | 用 `sim_policy.py` 评估自己的调度策略 | simulator | P1 | 在 `_schedule` 里实现候选策略，跑对比表 | 得到 mean/p95 TTFT + TPOT 的对比结论 | 实验B 第 13 节 |
| T-012 | 在 `sim_policy.py` 复刻 VA 的 short-request-first（含 `long_max_wait_ms` 老化） | simulator | P1 | 按 threshold 分流 + 老化提权，与 FCFS 对比 | 得到 VA 策略在 CPU 调度下的近似收益 | 004 第 7 节 |

---

## 阻塞

| ID | 事项 | 阻塞原因 | 解除条件 |
| :-- | :-- | :-- | :-- |
| T-003 | NPU 实机 e2e 验证 layerwise 复用 | 本地无 NPU | 拿到 NPU 机器 |
| T-004 | 时间模型系数标定 | 需要真机 TTFT/TPOT 数据 | 有 GPU/NPU 可跑基准 |
| T-006 | 接入 #61305 的 `TimingProvider`（空跑线） | 上游 RFC 未落地 | #61305 合并 |
| T-007 | 去掉 #47922 的本地 patch（空跑线） | PR 未合并 | #47922 合并后换正式分支 |
| T-009 | layerwise 提社区 PR | 依赖 T-002、T-003 | 邮箱修好 + NPU e2e 通过 |

---

## 想法池（还没想清楚 / 写不出下一步）

| ID | 想法 | 备注 |
| :-- | :-- | :-- |
| I-001 | PD 分离场景的调度仿真 | 当前模拟器不覆盖 PD，需要另一个数据面 |
| I-002 | 用模拟器评估 layerwise 复用的调度收益 | 把"复用 vs 不复用"作为策略变量，配合时间模型 |
| I-003 | 多租户 / 优先级调度实验 | 需要先给模拟器加优先级 workload |
| I-004 | 在空跑里初始化 `AscendConfig`，让 MLA 模型也能加载 VA 补丁 | 需要构造 VllmConfig 并挂到 CPU 平台的 config 钩子上 |

---

## 归档（已完成）

| ID | 事项 | 完成日期 | 证据 |
| :-- | :-- | :-- | :-- |
| — | 模拟器跑通 + 60s 排查 + 6 组实验 | 2026-10-26 | `wiki/vllm架构笔记/实验B-...md`，commit `57519f9`…`a65aa03` |
| — | layerwise block-key 复用实现（4 commit） | 2026-10-26 | `wiki/ascend对照笔记/003-...md`，分支 `feature/mooncake-layerwise-reuse` |
| — | 策略对比框架（FCFS/短优先/长优先） | 2026-10-26 | `sim_policy.py`，实验B 第 13 节 |
| — | 空跑环境加载 vllm-ascend main（无 NPU） | 2026-10-26 | `va/run_va_dry_run.sh`，004 笔记 |
| T-011 | VA 补丁 on/off 对比（dense no-op、MLA 需 AscendConfig） | 2026-10-26 | `sim_va_compare.py`，004 第 7 节 |
