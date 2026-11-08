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
| T-013 | ShardQ 迁移到 vllm-ascend | Step 0-3 本机已通（`tmp/va-shardq` @ `8edb38678`）；下一步把 attention 切到 token-shard + 真 Scheduler 联调 | 本机 UT 全绿 + 950DT 上 go/no-go（算子吃全 head） |
| T-030 | request_trace：waiting 采样节流 | 加 `REQUEST_TRACE_WAIT_SAMPLE=N`（每 N 个 step 采一次），默认 1 保持现状 | 100 并发下 Sm 行数随 N 线性下降，waiting_breakdown 结论不变 |
| T-031 | request_trace：CI 回归看板 | 把 CDF 的 p50/p99 抽成 JSON，按 commit 存时间序列 | 能指出"哪个 commit 让 p99 涨了" |

---

## 待办

| ID | 事项 | 领域 | 优先级 | 下一步 | 完成标准 | 参考 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| T-005 | 时间模型加二次项（prefill ≈ tokens²） | simulator | P2 | 在 `sim_timing.py` 加 `c_quad` 项，重跑扫描 | 长 prompt 的 TTFT 不再线性外推 | 实验B 第 12 节 |
| T-008 | 前缀缓存 × 时间模型组合实验 | simulator | P2 | 命中率 0/25/50/75% 各跑一次，比较 TTFT | 得到"命中率→TTFT"曲线 | 实验B 第 11/12 节 |
| T-010 | 用 `sim_policy.py` 评估自己的调度策略 | simulator | P1 | 在 `_schedule` 里实现候选策略，跑对比表 | 得到 mean/p95 TTFT + TPOT 的对比结论 | 实验B 第 13 节 |
| T-032 | request_trace：serving target 惰性包装 | trace | P2 | 用 import hook 延迟包装 serving 层 target | 离线跑 trace 的固定开销从 +0.42s 降到 ~0 | 006 §8 |
| T-033 | request_trace：写盘 ring buffer | trace | P2 | 后台线程 + 队列批量落盘（004 方案 B） | 每事件写盘从 7µs 降到 ≤2µs | 004、006 |
| T-034 | request_trace：span 模型（trace_id/parent） | trace | P2 | 设计 span schema，替换 `_STAGE_PAIRS` 配对表 | 阶段关系由父子表达，不再维护配对元组 | 003 §3.3 |
| T-035 | request_trace：parser 拆分 | trace | P2 | 拆成 parse / normalize / export 三段 | 加字段不再改 900 行单文件 | 005 |
| T-036 | request_trace：P/D 跨节点时钟 offset | trace | P2 | 在 trace 里记录 boot_id + offset 估计 | P/D 合并报表能标出时钟不确定性 | 003 §3.3 |
| T-043 | store 断言 guard 根因化 | trace | P2 | connector 侧跟踪 preemption，或在 get_finished 里按生命周期过滤 | 去掉整体替换 `_update_from_kv_xfer_finished` 的 shim | 实验C §17.5 |
| T-044 | store connector 移植到 v0.30 线 | trace | P2 | 把 `local_store_connector.py` 需要的钩子搬进 sim030 | v0.30 镜像能跑 store 多轮实验 | 实验C §17 |

---

## 阻塞

| ID | 事项 | 阻塞原因 | 解除条件 |
| :-- | :-- | :-- | :-- |
| T-003 | NPU 实机 e2e 验证 layerwise 复用 | 本地无 NPU | 拿到 NPU 机器 |
| T-004 | 时间模型系数标定 | 需要真机 TTFT/TPOT 数据 | 有 GPU/NPU 可跑基准 |
| T-006 | 接入 #61305 的 `TimingProvider`（空跑线） | 上游 RFC 未落地 | #61305 合并 |
| T-007 | 去掉 #47922 的本地 patch（空跑线） | PR 未合并 | #47922 合并后换正式分支 |
| T-009 | layerwise 提社区 PR | 依赖 T-002、T-003 | 邮箱修好 + NPU e2e 通过 |
| T-037 | request_trace：内网 8.1–8.8 + KV 字节对账 | 本地无 NPU | 按 003 §9.12 清单跑一次，回传 coverage + stage_timings 样本 |
| T-038 | request_trace：V2 打点真机验证 | CPU 上被 `worker.v2.model_runner` 判断挡住 | 内网 V2 冒烟，确认 V2 outer/inner/forward 三段都出 |

---

## 想法池（还没想清楚 / 写不出下一步）

| ID | 想法 | 备注 |
| :-- | :-- | :-- |
| I-001 | PD 分离场景的调度仿真 | 当前模拟器不覆盖 PD，需要另一个数据面 |
| I-002 | 用模拟器评估 layerwise 复用的调度收益 | 把"复用 vs 不复用"作为策略变量，配合时间模型 |
| I-003 | 多租户 / 优先级调度实验 | 需要先给模拟器加优先级 workload |
| I-004 | 在空跑里初始化 `AscendConfig`，让 MLA 模型也能加载 VA 补丁 | 需要构造 VllmConfig 并挂到 CPU 平台的 config 钩子上 |
| I-005 | 长请求错峰到达，验证 `long_max_wait_ms` 的渐进效果 | 同批到达时老化是二值开关；错峰才能看出"只提权最老的那个" |
| I-006 | 用 DeepSeek-V4 config 验证空跑的 MLA 限制 | 需要 V4 的 config（本地没有），确认是否卡在 `compress_ratios` 路径 |
| I-007 | 保留 DSA indexer 的 GLM-5.3 空跑 | 需要给 CPU 加稀疏注意力的 KV spec/记账支持，否则只能用 dense MLA 变体近似 |
| I-008 | 从真实日志提取 KV 容量的小工具 | 解析 `Available KV cache memory` / `GPU blocks` 直接输出 `--kv-cache-memory-bytes`，避免手算 |

---

## 归档（已完成）

| ID | 事项 | 完成日期 | 证据 |
| :-- | :-- | :-- | :-- |
| — | 模拟器跑通 + 60s 排查 + 6 组实验 | 2026-10-26 | `wiki/vllm架构笔记/实验B-...md`，commit `57519f9`…`a65aa03` |
| — | layerwise block-key 复用实现（4 commit） | 2026-10-26 | `wiki/ascend对照笔记/003-...md`，分支 `feature/mooncake-layerwise-reuse` |
| — | 策略对比框架（FCFS/短优先/长优先） | 2026-10-26 | `sim_policy.py`，实验B 第 13 节 |
| — | 空跑环境加载 vllm-ascend main（无 NPU） | 2026-10-26 | `va/run_va_dry_run.sh`，004 笔记 |
| T-011 | VA 补丁 on/off 对比（dense no-op、MLA 需 AscendConfig） | 2026-10-26 | `sim_va_compare.py`，004 第 7 节 |
| T-012 | 复刻 VA 短请求优先 + 老化（短请求 -50%~-69%，老化是悬崖） | 2026-10-26 | `sim_srs.py` / `sim_srs_arrivals.py`，实验B 第 14 节 |
| T-014 | request_trace 端到端跑通 + P0/P1 修复（CustomList 遮蔽、chunk 步 start、RequestID 归一） | 2026-11-07 | mxllm `77e7c54`、`92daf47`；002 |
| T-015 | trace 事件附加线程 CPU 时钟，输出 on/off CPU 列 | 2026-11-07 | mxllm `204557c`；与 bpftrace 交叉验证 90.3% 一致 |
| T-016 | trace 自身 dropped 统计 + stage coverage + per-request coverage | 2026-11-07 | `204557c`、`249dd30`；003 §9.11 |
| T-017 | metrics 轻量计数模式（L0，实测 +1.0%） | 2026-11-07 | `8e87cfb`；006 |
| T-018 | 请求状态机（reason code + state_timeline + waiting_breakdown） | 2026-11-07 | `3aa09c4`；003 §9.5 |
| T-019 | KV 视角（驱逐/峰值/每步序列） | 2026-11-07 | `fd86246`；003 §9.6 |
| T-020 | 算子级打点降级为 deep 模式 | 2026-11-07 | `05b2474`；003 §9.8 |
| T-021 | KV 换入换出本机验证（Mooncake put/get，payload 级字节） | 2026-11-07 | `35dd081`、`4aba04d`；003 §9.9 |
| T-022 | 观测模块单测（18→48 条，含 namelist 片段 compile 防护） | 2026-11-07 | `d821074`、`431b996` |
| T-023 | trace 开销实测 + 三项优化（去块级 target、预编译 snippet、缓存 handler） | 2026-11-07 | `573f73a`、`1f264cb`、`a77f4f1`、`ec8e478`；006 |
| T-024 | 新增 KV_PRESSURE 原因、删除误导性 `P4_save_kv_bytes` | 2026-11-07 | `d6a258c` |
| T-025 | per-request coverage 报表（complete/partial/no-finish/no-events） | 2026-11-07 | `249dd30` |
| T-026 | 单请求瀑布图（状态时间轴 + on-CPU 轨道） | 2026-11-07 | `a493603`；005 §6 |
| T-027 | KV 利用率×饱和、等待原因堆叠、多请求泳道三张图 | 2026-11-07 | `81adcc1`；005 §7 |
| T-028 | 延迟 CDF 图（多分组 + 前后对比 + p50/p99） | 2026-11-07 | `8644b10`；005 §8 |
| T-029 | 换入换出接真机（store/P2P 的 bytes+blocks，`kv_bytes.py`） | 2026-11-07 | `431b996`；003 §9.12（真机验证待 T-037） |
| T-039 | 真 Mooncake 后端（4KB 占位）接入 fake connector | 2026-11-08 | `0351db4`、`14dee1f`；实验C §17.3/17.4（0.5G 49%、2G/4G 81.1%，avg_put 0.21ms） |
| T-040 | KV 传输完成断言修复（容错替换，2G 连跑 3/3） | 2026-11-08 | 实验C §17.5（`14dee1f`） |
| T-041 | 1P1D + MultiConnector(store) 跑通 | 2026-11-08 | 实验C §17.6/17.7（HBM 192MB：mean -10.1%、p99 -11.5%；`MC_SYNC` 绕过异步 deadlock） |
| T-042 | P/D 下 store 异步 load 跑通 | 2026-11-08 | 实验C §17.6（`_loading` 去重 + 复合 `next_transfer_completion`；8 前缀 280.08→276.85ms，TTFT 含 load 延迟） |
| T-045 | store 双模式（memory / mooncake）+ 统一接口 | 2026-11-08 | 实验C §17.8（`store_backends.py`：StoreBackend/StoreStats/LRU/Mooncake；4 条单测；P/D 下两模式 255.79ms 逐位一致） |
