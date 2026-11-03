# mxllm 贡献规范与 CI 注意事项

> 记录 mxllm（本地目录 `mxvllm`，旧名 `vllm-cloud`）的提交规范、patch 规范、CI 现象和当前 PR 状态。
> 最近更新：2026-11-03

## 1. 仓库与分支模型

| 项 | 值 |
| :-- | :-- |
| 正式项目 | **mxllm** |
| 本地路径 | `/Users/sunlei/code/gitcode/mxvllm` |
| remote | `https://gitcode.com/InferTurbo/mxllm.git` |
| `main` | 开源演进分支；对外合入从 `main` 走 |
| `glm_v0.26.0_poc` | 公司内部推送分支；公司环境到个人电脑的**唯一桥接通道** |

环境约束：

```text
公司 NPU 环境（无互联网）
  → git push glm_v0.26.0_poc
  → 个人电脑 fetch/清洗/移植
  → main
```

- 个人电脑有互联网、无 NPU；公司环境有 NPU、无互联网。
- 不把 `glm_v0.26.0_poc` 的内部历史直接 merge 进 `main`；按主题 cherry-pick/重提。
- `transit/` 是公司内网暂存目录，**不要出现在 main**；开源文件放 `docs/`、`scripts/models/...` 等最终路径。

## 2. 提交/PR 规范

- 从最新 `origin/main` 新建分支，不在 `main` 上直接开发。
- 提交信息必须匹配 GitCode pre-receive hook：

```text
^(feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert): .{15,100}$
```

注意：`docs(deploy): ...` 这种带 scope 的写法会被拒绝；用 `docs: ...`。

- PR 模板要求：
  - `## Summary`
  - `## Validation`，勾选 `bash scripts/lint.sh`、`python -m pytest`
  - `## Upstream Impact`，无上游变更时选 `No upstream sync impact`
- 提交前跑：

```bash
bash scripts/lint.sh
python -m pytest
```

- 项目要求 Python 3.11；本地可用：

```bash
uv run --python 3.11 --with pytest --with anyio python -m pytest ...
```

- 当前 main 自身存在一些历史 repo hygiene 问题（如 `docs/source/...` 缺末尾换行），全量 `scripts/lint.sh` 可能不是全绿；先确认失败文件是否与本次改动相关。

## 3. 下游 patch 规范（来自 PR #132 review）

每个 downstream patch 必须在 `ascend_vllm/patch/__init__.py` 注册：

```text
ID
Name
Target
Why
How
Validation
Future Plan
```

ID 示例：

```text
MXLLM-TRACE_LOG-001
MXLLM-KVCB-001
MXLLM-KVFAIL-001
MXLLM-KVCTOK-001
MXLLM-W4A4-001
```

patch 代码用边界注释：

```python
# adapt begin: MXLLM-XXX-001
...
# adapt end: MXLLM-XXX-001
```

review 会检查 `patch/__init__.py` 中能否找到对应 ID/Target/Why/How，而不是只写在 patch 文件里。

## 4. CI：`ascend-vllm-smoke-demo` 已知 flaky

PR #132 的同一 PR、不同 commit：

- 通过：Jenkins `1155` / `1158` / `1162` / `1163` / `1165`
- 失败：Jenkins `1160` / `1174` / `1176`

失败项全部是：

```text
ascend-vllm-smoke-demo
[smoke-demo阶段]
```

PR #139 也出现同一阶段失败（Jenkins `1169` / `1170` / `1172`），没有 traceback。说明这是流水线/环境 flaky，不应只凭一次 smoke 失败判定代码回归。

处理顺序：

1. 先看 build / lint / UT；
2. 如果只有 `smoke-demo` 失败，先重跑；
3. 连续同一阶段失败，找 CI 负责人拿 Jenkins 日志；
4. GitCode 的 `mergeable_state.ci_state_passed=true` 可能与评论里的 CI 失败不一致，不能只看该字段。

## 5. 当前 PR 状态

### PR #137：GLM-5.3 A5 2P2D 部署文档 + 脚本

- 分支：`docs/glm53-a5-deployment`
- 内容：`docs/glm5.3/GLM-5.3.md`、`scripts/models/glm5.3/a5/*`
- 已从 `transit/` 移到最终路径；不含 `patch_validator.py`
- 已 rebase 到最新 main

### PR #139：GLM-5.3 validator 配置

- 分支：`fix/use-beam-search-validator`
- 新增：`ascend_vllm/middleware/validator_config_glm53.json`
- 基于 `validator_config.json`，保留 `reasoning_effort`，增加 `use_beam_search=false-only` 校验
- 不修改原 `validator_config.json` / `validator_config_glm.json`
- 测试：`tests/middleware/test_param_check.py` 19 passed
- 还需要另一个 PR 把 GLM-5.3 的 `VALIDATORS_CONFIG_PATH` 指到新配置

## 6. 经验

- PR 前先确认 base 是否落后：`git fetch origin main` + `git rev-list --count HEAD..origin/main`。
- rebase 后用 `git push --force-with-lease`，不要普通 force push。
- 文档中的链接要和文件最终路径一起检查；`transit/` 下的相对路径不能直接带进 main。
- 新增模型配置时，先看 `validator_config*.json` 的模型差异，不要默认所有模型共用一份。
