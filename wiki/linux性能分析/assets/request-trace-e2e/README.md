# request_trace 端到端验证资产

对应笔记：[../../002-request-trace端到端与对齐.md](../../002-request-trace端到端与对齐.md)。

## 文件

| 文件 | 说明 |
| :-- | :-- |
| `run_e2e.py` | 驱动：按路径加载 `patch_request_trace.py` → `apply_all()` → `LLM(simulate_forward=True)`，并记录 `(t0_wall, t0_mono_ns)` 供对齐 |
| `trace_bpf.sh` | 侧挂容器脚本：等进程出现后用 bpftrace 记录 `sched_switch` OUT/IN + 99Hz 采样 |
| `analyze_align.py` | 把 `stage_timings` 的 StepID 窗口和 bpftrace 事件对齐，算每步 off-CPU |
| `0001-fix-customlist-self-shadow.patch` | 修复 namelist 里 `CustomList.append` 的 `self` 遮蔽（P0，不打就崩） |
| `results/time_analysis-run1.xlsx` | 第一次跑（未带 bpftrace）的报表 |
| `results/time_analysis-run2-bpf.xlsx` | 对齐实验所用的报表 |
| `results/align.csv` | 对齐结果（6 个 ok 窗口的 duration / off-CPU / on-CPU%） |

## 复现要点

1. 容器用 `sim030:int3`（vLLM pin `ced6857af`，editable `/work`），
   **先执行镜像自带的 wheel 重装**（triton / torchvision / torchaudio / torchcodec），
   否则 `RuntimeError: operator torchvision::nms does not exist`。
2. 挂载 `mxllm-trace` 到 `/mxllm`（只读），把本目录挂到 `/out`。
3. P0 补丁不能直接改 `mxllm-trace` 工作区时，可以挂一个打过补丁的
   `request_logger_namelist.yml` 覆盖进去：
   ```bash
   -v /path/to/request_logger_namelist.yml:/mxllm/tools/request_trace/request_logger_namelist.yml:ro
   ```
4. `REQUEST_PD_ROLE=prefill` + `VLLM_ENABLE_V1_MULTIPROCESSING=0`，
   单进程才能用 `prev_pid == PID` 跟主线程。

## 注意

- 这是 **overlay harness**，绕开了 `ascend_vllm.patch.platform.__init__`，
  验证的是"打点机制 + parser"，**不是 NPU 语义**。
- `printf("%d", nsecs)` 会 32 位截断，时间戳必须 `%lld`。
- `profile:hz:N` 是每 CPU 触发，事件量要按核数放大。
