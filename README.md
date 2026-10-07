# vLLM 学习笔记 · 实验 · KV Cache 调研

个人学习仓库：在 **Mac (M3 / 24GB / CPU 后端)** 上深入 vLLM 源码，并延伸出 KV Cache 方向的技术调研。
重点是**可复现的实验记录与结论**，而非生产部署方案。

> 基线：**vLLM v0.28.0**（上游源码不入本仓库，见「如何复现」）｜ vllm-ascend v0.23.0（对照学习）

---

## 仓库内容地图

### 一、vLLM 学习笔记（`wiki/`）

| 文件 | 内容 |
|---|---|
| `环境搭建记录.md` | macOS 从零搭建：uv / cmake / Python 3.12 / 源码编译 / 全部踩坑与排查表 |
| `git使用指南.md` | git 用法 + **国内网络方案**（github.com 直连不通 → gh-proxy 代理、gitee 镜像、SSH 可用） |
| `git考古方法.md` | 用 git 历史考古代码演进的方法（blame / log -p / worktree） |
| `vscode调试指南.md` | 断点调试配置（`VLLM_ENABLE_V1_MULTIPROCESSING=0` 进程内调试）+ 断点地图 |
| `vllm架构笔记/` | 架构学习路线图、笔记模板、模块笔记（`00-模型加载与dummy机制`、`03-KV Cache 与注意力`、`实验A-截断加载GLM52`） |
| `ascend对照笔记/` | 主仓 vs **vllm-ascend** 对照：硬件插件接入机制、PCP 对照、MLA 的 NPU vs CPU 实现对照 |
| `PCP_dir/` | PCP（Prefill Context Parallel）特性相关代码文档索引 |
| `开源贡献实战记录.md` | 完整贡献历程：本地定位 CPU MLA bug → 发现社区已有 PR → 转向「验证 + 提 issue」的差异化路径 |
| `issue_draft_sparse_attn.md` / `review_draft_51471.md` | 向外提 issue / review 的草稿 |
| `资料/agent场景优化/` | 资料索引：Coding Agent 场景（超长输入短输出）的推理优化 —— 负载画像、前缀缓存与调度、稀疏注意力、PD 分离、投机解码 |

### 二、KV Cache 专题调研（`kvcache-research/` + `kv_research/`）

| 文件 | 内容 |
|---|---|
| `kvcache-research/KV_CACHE_LANDSCAPE_2026.md` | 开源 LLM KV Cache 管理与 KV Cache 中心化推理服务框架**全景**（2026-09 基准） |
| `kvcache-research/notes_standards.md` | 标准与规范（协议/接口层） |
| `kvcache-research/notes_other_oss.md` | 其他开源实现横向对比 |
| `kvcache-research/notes_china_vendors.md` | 国内厂商方案梳理 |
| `kvcache-research/notes_storage_cloud.md` | 存储与云侧方案 |
| `kv_research/README.md` | LLM KV Cache **压缩算法层**研究综述（arXiv 实时核验） |
| `kv_research/slk/KV_Cache_Systems_Report_2026-09.md` | KV Cache 管理系统论文综述（2023–2026，USENIX/ACM/MLSys 等） |
| `kv_research/q3n.md`、`*.txt` | 检索过程与原始清单 |

> 注：抓取的原始数据（`*/raw/`）不入库，笔记中的链接可重新获取。

### 三、实验代码与补丁

| 文件 | 说明 |
|---|---|
| `patches/vllm-0.28.0-cpu-mla-local.patch` | 让 **MLA 模型能在 CPU 上运行**的实验补丁（6 个文件，见下文） |
| `patches/glm52-truncated-3layer-config.json` | GLM-5.2 截断为 3 层的 config 示例 |
| `dl_model.sh` | 从 hf-mirror 下载模型 config + tokenizer（**不含权重**，用于 dummy 模式） |
| `demo_inference.py` | 最小离线推理示例（dummy 权重） |
| `debug_glm52.py` / `debug_dsv2lite_mla.py` / `trace_mla.py` | MLA 路径调试与追踪脚本 |
| `env.sh` | 环境变量（缓存目录、HF 镜像等） |
| `.vscode/` | 调试配置（进程内引擎 + 断点） |

---

## 核心实验：大模型「截断加载」

**问题**：GLM-5.2 是 504B 参数（78 层、1M 上下文）旗舰 MoE，24GB 内存本地无法运行。

**方法**：只下载 config（几十 KB～几十 MB，不含权重），把 `num_hidden_layers` 从 78 截到 3，
配合 `load_format=dummy`（随机权重）→ 内存降到 ~5.4GB，**架构维度（hidden size / 注意力结构 / 词表）保持真实**，可用于调试引擎全链路。

**结果**：
- GLM-5.2（3/78 层）在 M3 CPU 上完整跑通，`vllm bench latency` **2.52s/批**（batch=4, 16+16 tokens）
- DeepSeek-V2-Lite（27 → 3 层，含 2 层 MoE）跑通，**0.415s/批** —— 覆盖 MoE 路径

**过程中定位并修复了 vLLM 0.28.0 的 CPU 侧缺口**（`patches/`）：

| # | 问题 | 修复 |
|---|---|---|
| 1 | 稀疏注意力（DSA）在 CPU 硬性不支持，且 `index_topk` 由 config 类默认注入、**无法用 config 关闭** | 模型层强制关闭 v32 稀疏分支 |
| 2 | `fa_utils.py` 缺 CPU 平台分支 → `ImportError` | 补 CPU 分支 |
| 3 | **CPU 缺少 MLA prefill 实现**（参考后端只有 decode kernel） | 新增 `CPUSDPAMLAPrefillBackend`（PyTorch SDPA）并注册到 prefill 后端选择器 |
| 4 | MLA chunked-context 在 CPU 无 gather 实现 | 补 CPU gather 算子 |

## 如何复现

```bash
# 1. 拉源码（国内：代理通道；SSH 亦可用）
git clone https://gh-proxy.com/https://github.com/vllm-project/vllm.git vllm-src
cd vllm-src && git checkout v0.28.0

# 2. 应用实验补丁
git apply ../patches/vllm-0.28.0-cpu-mla-local.patch

# 3. 环境（详见 wiki/环境搭建记录.md）
cd .. && source env.sh
uv venv --python 3.12
uv pip install -r vllm-src/requirements/cpu.txt --index-strategy unsafe-best-match
uv pip install -e ./vllm-src

# 4. 取 config（不含权重）+ 截断层数（或用 patches/ 里的示例 config）
./dl_model.sh zai-org/GLM-5.2

# 5. 跑基准
.venv/bin/vllm bench latency --model models/zai-org_GLM-5.2 --load-format dummy \
  --dtype float16 --gpu-memory-utilization 0.3 --enforce-eager \
  --max-model-len 4096 --input-len 16 --output-len 16 --batch-size 4
```

## Mac 环境要点速记

| 事项 | 结论 |
|---|---|
| 安装 | macOS **无预编译 wheel**，必须源码编译（CPU 后端，仅支持 FP32/FP16） |
| 网络 | github.com 直连不通：拉取走 `gh-proxy.com` 代理、**SSH 推送可用**、HF 走 `hf-mirror.com` |
| 内存 | CPU 后端 `--gpu-memory-utilization` 控制 **CPU 内存**预留比例（默认 0.92 必挂，实测 0.2~0.3） |
| 长上下文 | 1M context 模型必须显式 `--max-model-len`，否则 KV cache 校验失败 |
| 调试 | `VLLM_ENABLE_V1_MULTIPROCESSING=0` → 引擎进程内运行，单调试器可跟到底 |

## 说明

- **补丁为实验性质**：目标是让学习者在 CPU 上跑通 MLA 模型，**参考质量、未做性能优化**；基于 v0.28.0，仅供学习参考。若向上游贡献需按其规范重写与测试。
- **不入库内容**：上游源码（`vllm-src/`、`vllm-ascend-src/`）、虚拟环境与缓存、模型文件、调研原始抓取数据。
- **许可**：笔记为个人学习记录；涉及的 vLLM 代码片段遵循 Apache-2.0（Copyright contributors to the vLLM project）。
