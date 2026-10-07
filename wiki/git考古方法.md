# Git 考古方法：实战案例（MLA SDPA 之谜）

> 场景：发现代码行为与文档矛盾（docstring 说"prefill 用 SDPA"但代码里没有），
> 用 git 历史追查"是不是以前有、后来删了"。
> 配套：`git使用指南.md`（基础命令）、`vllm架构笔记/实验A-截断加载GLM52.md`（本案例的工程背景）。

---

## 1. 什么情况适合 git 考古

- **文档/注释与代码矛盾**：注释说某功能存在，代码里找不到
- **"这个功能以前有吗？"**：想确认某实现是被删除、改名还是从未存在
- **理解架构演进**：一个模块为什么长成现在这样（哪些重构塑造了它）

## 2. 核心命令清单（考古工具箱）

| 命令 | 用途 | 本次案例中的用法 |
|---|---|---|
| `git log --follow -- <文件>` | 文件完整历史（**含改名**跟踪） | 找到 `cpu_mla.py` 的引入提交 #49453 |
| `git log -S "字符串" -- <路径>` | **pickaxe**：找出"字符串出现/消失"的提交 | 追 `scaled_dot_product` 的增删 |
| `git log --diff-filter=D --name-only` | 列出被删除的文件 | 确认没有删除过 SDPA 文件 |
| `git show <commit>:<文件>` | 看历史版本的文件内容 | 看 #13789 原始 common.py、#49453 原始 cpu_mla.py |
| `git show --stat <commit>` | 看提交改了哪些文件、多少行 | 判断重构规模、是否纯改名 |
| `git log --all` | 全分支搜索 | 防止漏掉其他分支的提交 |

> **pickaxe 技巧**：`-S` 找"字符串数量变化"的提交，是"这行代码什么时候没的"的最快答案。
> 配合 `git show <commit> | grep -c 字符串` 验证"某版本里还有几个"。

## 3. 实战案例：MLA SDPA 到底是不是被删的？

### 问题起点
```
AssertionError: FlashAttnPrefillBackend requires flash_attn_varlen_func
```
而 `cpu_mla.py` 的 docstring 写着 *"The prefill path is a plain PyTorch SDPA"*——
代码说没有，文档说有，矛盾 → 启动考古。

### 步骤 1：定位现状
- `fa_utils.py`：`flash_attn_varlen_func` 只在 CUDA/XPU/ROCm 分支定义，**CPU 分支缺失**
- `selector.py get_mla_prefill_backend`：CPU 上 `device_capability is None` → 早退选 FLASH_ATTN，**不检查可用性**
- 结论（现状）：CPU 没有任何可用的 MLA prefill 后端

### 步骤 2：找 CPU MLA 后端的出生证明
```bash
git log --follow --oneline -- vllm/v1/attention/backends/mla/cpu_mla.py
# → 13726c80fe [CPU] Add MLA backend so DeepSeek-V2/V3 can run on CPU (#49453)
```

### 步骤 3：看它的"原始面貌"
```bash
git show 13726c80fe:vllm/v1/attention/backends/mla/cpu_mla.py | grep -n "def \|SDPA"
```
发现：**原始版本就和现在一样**——只有 decode kernel（`forward_mqa`），docstring 里已有 SDPA 承诺。
说明"悬空承诺"从出生就有。

### 步骤 4：pickaxe 追 SDPA 的增删
```bash
git log -S "scaled_dot_product" --oneline -- vllm/v1/attention/backends/mla/
# → 2263d44b68 [4/N][Attention] Move MLA common to model_executor (#32060)
# → 58d1b2aa77 [Attention] MLA support for V1 (#13789)
```
两个提交：`#13789` 引入（有 SDPA），`#32060` 移除（没了）。

### 步骤 5：验证移除
```bash
# 移除前：common.py 里还有 4 处 SDPA
git show 2263d44b68^:vllm/v1/attention/backends/mla/common.py | grep -c scaled_dot_product   # 4
# 移除后：新位置 mla_attention.py 是 0 处
git show 2263d44b68:model_executor/layers/attention/mla_attention.py | grep -c scaled_dot_product   # 0
# 且 #32060 的 --stat 显示该文件是"纯改名"（0 行变化）→ SDPA 是被丢弃而非搬走
```

### 步骤 6：官方测试佐证
`tests/v1/attention/test_cpu_mla_backend.py::test_cpu_mla_backend_smoke`：
- 官方测试**思路与我们完全一致**：`hf_overrides` 缩小模型（2 层、4 专家）+ dummy 权重
- 本地实测：**无补丁必挂**（同样的断言），**有补丁通过**

### 结论
| 结论 | 证据 |
|---|---|
| 以前确实有 SDPA | #13789 的 common.py 有 4 处实现（含 chunked+LSE） |
| 是重构时删的 | #32060 移动文件时丢弃，新文件 0 处 |
| 现在的代码有缺口 | CPU 上 MLA prefill 无可用后端，官方测试必挂 |
| docstring 是历史遗留 | #49453 从旧版继承承诺，但代码已不存在 |

---

## 4. 考古注意事项

1. **改名要加 `--follow`**，否则改名后文件历史会断
2. **pickaxe 的 `-S` vs `-G`**：`-S` 数出现次数变化；`-G` 按正则匹配 diff 行。找"某段逻辑没了"用 `-S`
3. **区分"删除"与"搬走"**：看 `--stat` 是否是 rename（`{old → new}` 语法）；搬走的话新位置还能找到
4. **结合测试文件看意图**：官方测试往往暴露"这个功能本来该怎么用"
5. **不要过度断言**：本地必挂 ≠ CI 必挂（CI 环境未知）；下结论前先区分"代码事实"与"环境推断"
