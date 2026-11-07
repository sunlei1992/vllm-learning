# Linux 性能分析笔记

对照《性能之巅》《BPF 之巅》整理，落到本工作区（vLLM / vllm-ascend / 容器空跑）的场景。

| 编号 | 主题 | 说明 |
| :-- | :-- | :-- |
| 001 | [bpftrace 单行命令速查](001-bpftrace单行命令速查.md) | 按子系统整理的 bpftrace 命令 + vLLM 专用配方，命令在本机 Docker 环境逐条验证 |
| 002 | [request_trace 端到端验证与对齐](002-request-trace端到端与对齐.md) | mxllm 的请求级打点在 CPU 空跑上跑通，产出第一份 Excel，并和 bpftrace 做 StepID 级联合归因 |

实测存档：

| 目录 | 内容 |
| :-- | :-- |
| [assets/bpf-vllm-trace](assets/bpf-vllm-trace/RESULTS.md) | 在 `sim-int:dry-run` 空跑容器里采样 vLLM 进程（`run.sh` 可复现，含原始采样） |

约定：

- 每条命令都标「怎么读」，不只给命令。
- 实测过的结论标日期和环境；没实测的明确写「待验证」。
- 与 vLLM 相关的配方，链接到 `../vllm架构笔记/` 对应实验。
