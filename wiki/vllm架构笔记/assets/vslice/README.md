# vSlice：调度优化 A/B 的最小闭环

配套笔记：[10-调度优化测试工作流](../../10-调度优化测试工作流.md) ｜ 结果：[RESULTS.md](RESULTS.md)

目标：**同一个镜像**，只切 `VSLICE_POLICY=fcfs|srs`，跑「造 case → 空跑 server → bench/collector → step 轨迹 → compare」。

## 文件

| 文件 | 作用 |
|---|---|
| `gen_case.py` | 生成 `case_mixed.jsonl`（8 长 725 token + 8 短 65 token，长在前） |
| `case_mixed.jsonl` | 已生成好的 case（`prompt` + `output_tokens`） |
| `vslice_sched.py` | `PolicyScheduler`：`fcfs` no-op，`srs` 按 prompt 长度重排 `Scheduler.waiting` |
| `start_server.sh` | 容器内启动单实例空跑（linear timing、real clock、KV 4GiB、budget 512） |
| `run_vslice.sh` | 起容器 → warmup → N 次 bench → collector → metrics/steps 快照 → 清理 |
| `collect.py` | 并发发 16 个请求，按 SHORT/LONG 汇总每请求 `queue_time_ms` / TTFT / ITL |
| `compare.py` | 读 `results/*.json` 与 `logs/*/collect.json`，输出 Δ 表 |
| `test_vslice_trace.py` | golden trace UT：离线 Scheduler，断言 FCFS/SRS 的前 3 步轨迹 |
| `run_trace_test.sh` | 在 `sim-int:dry-run` 里跑上面的 UT（`unittest`，约 4s） |
| `logs/<mode>/` | 每次运行的 `steps.jsonl`、`metrics_before/after.txt`、`collect.json`、bench 日志 |
| `results/` | bench JSON（每组 2 次） |

## 跑法

```bash
cd /Users/sunlei/code/dsh/vllm

MODE=baseline  RUNS=2 bash tmp/vslice/run_vslice.sh
MODE=candidate RUNS=2 bash tmp/vslice/run_vslice.sh
.venv/bin/python tmp/vslice/compare.py
```

或者直接在本目录跑（脚本会向上找 `AGENTS.md` 定位工作区根）：

```bash
MODE=baseline RUNS=2 bash run_vslice.sh
MODE=candidate RUNS=2 bash run_vslice.sh
../../../../.venv/bin/python compare.py
```

`KEEP=1` 保留容器；`PORT` / `RUNS` / `IMAGE` 可覆盖。

轨迹 UT（不需要起 server、不需要 bench，约 4s）：

```bash
bash run_trace_test.sh
# 或容器内：cd /tools && PYTHONPATH=/work:/tools python -m unittest -v test_vslice_trace
```

它断言：FCFS 前 3 步 0 个 short、first short 在第 16 步；SRS 第 0 步就调度 8 个 short、
first long 在第 16 步；两者总 token 数/步数一致且 0 抢占。golden 值钉在 `sim-int:dry-run`
（vLLM 0.31.1rc1），换镜像/改调度语义时需要显式更新。

## 设计要点

- **同镜像 + 开关**：baseline/candidate 都加载 `vslice_sched.PolicyScheduler`，只差 `VSLICE_POLICY`，避免两个镜像的构建差异。
- **完整负载 warmup 丢弃**：空跑冷启动（Triton JIT / 新 batch 形状）会把 TTFT 抬高约 2 倍，`--num-warmups 2` 压不住。
- **step 轨迹**：`--simulation-config` 的 `log_path` 每步写 `StepDescriptor`；`compare.py` 用前 3 步的 short/long 数量判断策略是否真的生效。
- **per-class 指标**：bench 只给聚合分位数；`collect.py` 额外按 SHORT/LONG 给 queue/TTFT 分布，避免「均值掩盖重分配」。
- **`--disable-shuffle`**：`CustomDataset` 默认 shuffle，会打乱「长请求在前」的队列顺序。

## 已知限制

- 仿真 `block_size=32`（GPU 常见 16）；token 容量可对齐，但 APC 命中粒度不同。
- `timing=linear` 是标定模型，不是真实硬件；结论应看相对趋势。
- `srs` 是玩具策略（每步全量排序），用于验证流水线，不是生产优化。
- 当前只有 2 次重复，没有置信区间；扩到 5 次再报告 p99。
