# Git 使用指南（vLLM 学习工作区）

> 本文件记录这套 vLLM 学习环境的 git 相关设置与用法。
> 创建于 2026-08-27，vLLM v0.28.0 环境搭建完成后。
> **核心提醒：源码目录 `vllm-src/` 是 git 仓库；工作区根目录（含 wiki/）不是。**

---

## 1. 当前状态速览

| 项目 | 值 |
|---|---|
| git 仓库位置 | `~/code/dsh/vllm/vllm-src/` |
| 当前版本 | v0.28.0（commit `2cf0a6915c`，HEAD 在 `main` 分支） |
| 历史 | 全量 20051 个提交（`.git` 约 543MB，正常，勿删） |
| 远程 origin | `https://gh-proxy.com/https://github.com/vllm-project/vllm.git`（GitHub 代理） |
| 远程 gitee | `https://gitee.com/mirrors/vllm.git`（备用镜像，滞后几天） |
| 提交身份 | user.name=sl，user.email=sl@sunclouddev@163.com |

**目录结构**：

```
~/code/dsh/vllm/            ← 工作区根（无 git）
├── vllm-src/               ← vLLM 源码（git 仓库，editable 安装指向这里）
├── wiki/                   ← 学习笔记（本文件所在）
├── env.sh                  ← 环境变量（source 它）
├── demo_inference.py       ← 离线推理示例脚本
└── .venv/  .uv-cache/  .hf-cache/  .vllm-cache/
```

---

## 2. 为什么 git 仓库长这样（背景，别忘）

1. **源码最初来自 GitHub tarball**（不是 clone），所以没有 `.git`。当时 github.com 直连不通。
2. 后来用 **gh-proxy.com 代理**重新拉取了全量 git 历史（`git fetch origin tag v0.28.0`），并验证 tarball 内容与官方 tag **逐字节一致**（`git reset --hard v0.28.0` 对齐）。
3. **网络现状**（2026-08 实测）：
   - `github.com` 直连：❌ 超时（git 协议不通）
   - `gh-proxy.com` 前缀代理：✅ 可用（约 3 秒响应）—— origin 用的就是它
   - `ghfast.top` 前缀代理：✅ 可用（稍慢）
   - `gitee.com/mirrors/vllm`：✅ 可用但只同步到 v0.27.1
   - `api.github.com` / `codeload.github.com`：✅ 可用（下载 tarball 用）

---

## 3. 日常命令速查

```bash
cd ~/code/dsh/vllm/vllm-src

git status                  # 当前工作区状态
git log --oneline -20       # 最近 20 条提交
git log --oneline --graph   # 带分支图的提交历史
git diff                    # 工作区未暂存改动
git diff v0.27.1..v0.28.0   # 两个版本之间所有差异
git show v0.28.0            # 查看某个提交/标签的改动内容
```

---

## 4. 学习场景用法（重点）

### 4.1 追一个文件的演进史
```bash
# 看文件所有历史提交（--follow 跟踪文件改名/移动）
git log --follow --oneline -- vllm/v1/core/sched/scheduler.py

# 看某个文件完整的历史改动内容
git log --follow -p -- vllm/v1/core/sched/scheduler.py

# 逐行追责：谁、什么时候、为什么改了这一行
git blame vllm/v1/core/sched/scheduler.py
```

> 实例：`scheduler.py` 在 2025-06-03 从 `vllm/v1/core/scheduler.py` 移入 `vllm/v1/core/sched/` 子目录（Simon Mo 的提交），blame 能直接看到这种结构演进。

### 4.2 看任意历史版本的任意文件
```bash
# 语法：git show <版本>:<文件路径>
git show v0.9.0:vllm/v1/engine/llm_engine.py        # 老版本引擎
git show v0.13.0:vllm/v1/core/sched/scheduler.py     # 中间版本调度器
```

### 4.3 对比两个版本的某个模块
```bash
git diff v0.27.1..v0.28.0 -- vllm/v1/core/sched/     # 只看调度器
git diff v0.9.0..v0.28.0 --stat                      # 版本间文件变更统计
```

### 4.4 ⚠️ 想看其他版本的完整代码：用 worktree，别直接 checkout！

**原因**：`.venv` 是 editable 安装，直接 `git checkout` 切换版本会改变 `vllm-src/` 里的代码，导致 import 的代码跟着变，破坏你的调试环境。

```bash
# 在仓库外建独立目录看旧版本（互不干扰）
git worktree add ../vllm-v0.9.0 v0.9.0
cd ../vllm-v0.9.0    # 这里可以随便改、随便看
# 用完删除：
git worktree remove ../vllm-v0.9.0
```

---

## 5. 升级 vLLM 到新版本

```bash
cd ~/code/dsh/vllm/vllm-src

# 1) 拉取新 tag（走代理）
git fetch origin tag v0.29.0        # 示例，改成实际版本号

# 2) 切过去（工作区有未提交改动时先 stash 或确认干净）
git checkout v0.29.0                # 或 git reset --hard v0.29.0

# 3) 重新编译安装（C++ 代码变了才需要；纯 Python 改动不用）
cd ~/code/dsh/vllm && source env.sh
uv pip install --python .venv/bin/python -e ./vllm-src

# 4) 验证
.venv/bin/python -c "import vllm; print(vllm.__version__)"
```

**版本号检测说明**：vLLM 用 setuptools-scm 从 git tag 自动推断版本。以前 tarball 没有 `.git` 时编译会报错，需要 `VLLM_VERSION_OVERRIDE=0.28.0` 兜底；**现在有 git 了，正常编译不再需要这个变量**（`vllm/_version.py` 会自动生成）。

---

## 6. 远程仓库操作

```bash
# 查看远程
git remote -v

# 添加/更换远程（代理通道）
git remote set-url origin https://gh-proxy.com/https://github.com/vllm-project/vllm.git
# 其他可用代理前缀：https://ghfast.top/https://github.com/...

# 从 gitee 备用镜像拉（可能滞后，用于代理失效时）
git fetch gitee

# 拉取 main 分支最新（日常更新源码）
git fetch origin main
```

---

## 7. 踩过的坑（备忘）

| 坑 | 现象 | 解决 |
|---|---|---|
| 源码没有 `.git` | 编译报 `setuptools-scm was unable to detect version` | 补 git 历史（见 §2）或临时 `VLLM_VERSION_OVERRIDE=0.28.0` |
| 自定义 `VLLM_` 前缀环境变量 | 启动警告 `Unknown vLLM environment variable detected` | 别定义 `VLLM_*` 变量（env.sh 里已删） |
| `git checkout` 报 untracked 文件阻挡 | tarball 文件全是 untracked | 内容一致时用 `git reset --hard <tag>` |
| `.git` 有 543MB | 看着吓人 | 全量历史就是这么大，正常，别删 |
| 忘记加载环境 | 缓存写到 `~/.cache` 报权限错 | 每次新终端先 `source env.sh` |
| 内存不足 | `Available memory ... less than desired` | 调低 `--mem`（demo 脚本参数，0.2~0.3） |

---

## 8. 万一要重新搭建（速查）

```bash
# 拉源码（用代理，别直连 github）
git clone https://gh-proxy.com/https://github.com/vllm-project/vllm.git vllm-src
cd vllm-src && git checkout v0.28.0

# 环境（uv + Python 3.12 + 编译工具）
brew install uv cmake ninja
uv venv --python 3.12
uv pip install -r requirements/cpu.txt --index-strategy unsafe-best-match
uv pip install -e .          # macOS 自动走 CPU 后端，编译约 10-30 分钟

# 跑测试
source ../env.sh && .venv/bin/python ../demo_inference.py
```

---

## 9. 常用 git 配置检查

```bash
git config --list | grep user   # 提交身份
git config user.name "你的名字"     # 修改身份
git config user.email "you@example.com"
```

---

## 10. 推送到自己的 GitHub 仓库（本工作区）

**远程地址**：`git@github.com:sunlei1992/vllm-learning.git`（本工作区根目录就是这个仓库）

> 关键：**github.com 的 HTTPS / git 协议在本机不通，但 SSH 可用**（密钥已配好，认证 `sunlei1992`）。
> 因此 remote 必须用 SSH 形式（`git@github.com:...`），**不能**用 `https://github.com/...`。

### 日常推送三步

```bash
cd ~/code/dsh/vllm

# 若 ssh 报 known_hosts 无法写入（沙箱/权限限制），先设这一行：
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

git add -A
git commit -m "这次改了什么"
git push
```

### 首次配置（已完成，备忘）

```bash
git init -b main
git config user.name "sunlei1992"
git config user.email "sunlei1992@users.noreply.github.com"   # noreply 邮箱才会关联 GitHub 账号
git remote add origin git@github.com:sunlei1992/vllm-learning.git
git push -u origin main
```

### 哪些内容不入库（根目录 `.gitignore`）

| 排除项 | 原因 |
|---|---|
| `vllm-src/`、`vllm-ascend-src/` | 上游源码（765M / 259M），随时可重新拉取 |
| `.venv/`、`.uv-cache/`、`.hf-cache/`、`.vllm-cache/`、`.torchinductor-cache/` | 环境与缓存，可重新生成 |
| `models/` | 模型 config/tokenizer，可用 `dl_model.sh` 重新下载 |
| `kvcache-research/raw/`、`kv_research/raw/`、`kv_research/cache/` | 抓取的原始数据（约 450M），笔记中留有来源链接 |
| `anki/`、`tmp/` | 无关应用 / 临时目录 |

> 入库规模约 **116 文件 / 3.2 MB**（笔记 + 补丁 + 脚本）。

### 状态检查

```bash
git status -sb                 # 本地 vs 远程
git log --oneline -5           # 最近提交
git ls-remote --heads origin   # 远程分支指向的 commit（验证推送成功）
```
