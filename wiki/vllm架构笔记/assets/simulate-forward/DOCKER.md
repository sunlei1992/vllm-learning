# Docker 镜像分层构建（simulate-forward 环境）

配套笔记：[实验B-simulate-forward仿真环境.md](../../实验B-simulate-forward仿真环境.md)

目标：造一个能跑 vLLM `--simulate-forward` 的 Linux 镜像。
适用：macOS（Apple Silicon）或任意 Linux 主机。

> 为什么需要容器：MRV2 依赖 Triton，而 `triton-cpu` 只发布 Linux wheel。
> 详见笔记第 2 节。

---

## 0. 宿主机准备

```bash
# 目录约定（按需修改）
ROOT=/path/to/workspace
mkdir -p "$ROOT/tmp" "$ROOT/tmp/triton-cache" "$ROOT/models"
```

### 0.1 下载运行时 wheel（宿主机）

容器内直连 GitHub/PyPI 往往很慢，先在宿主机下好再挂载。

```bash
cd "$ROOT/tmp"

# triton-cpu：按平台/架构选一个（下面以 linux/arm64 + cp312 为例）
curl -L -o triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl \
  "https://ghfast.top/https://github.com/triton-lang/triton-cpu/releases/download/v3.8.0/triton-3.8.0%2Bcpu-cp312-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl"

# torch / torchvision / torchaudio / torchcodec 的 CPU 版本（用国内镜像）
BASE=https://mirrors.aliyun.com/pytorch-wheels/cpu
curl -L -O "$BASE/torch-2.13.0%2Bcpu-cp312-cp312-manylinux_2_28_aarch64.whl"
curl -L -O "$BASE/torchvision-0.28.0%2Bcpu-cp312-cp312-manylinux_2_28_aarch64.whl"
curl -L -O "$BASE/torchaudio-2.11.0%2Bcpu-cp312-cp312-manylinux_2_28_aarch64.whl"
curl -L -O "$BASE/torchcodec-0.17.0%2Bcpu-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl"
```

### 0.2 预取 vLLM CPU 构建的两个外部依赖

vLLM 的 CPU CMake 会从 GitHub clone **ARM ComputeLibrary** 和 **oneDNN**，
容器内经常卡死，所以宿主机先准备好。

```bash
cd "$ROOT/tmp"

# ACL v52.6.0（注意：构建时会往这个目录里写 build/，所以进容器后要复制一份可写副本）
git clone --depth 1 --branch v52.6.0 \
  git@github.com:ARM-software/ComputeLibrary.git acl

# oneDNN：vLLM 在 aarch64 上 pin 了这个 commit
mkdir -p onednn && cd onednn
git init -q
git remote add origin git@github.com:oneapi-src/oneDNN.git
git fetch --depth 1 -q origin 9c5be1cc59e368aebf0909e6cf20f981ea61462a
git checkout -q FETCH_HEAD
```

---

## 1. 基础镜像

```bash
docker pull --platform linux/arm64 python:3.12-slim
```

> x86_64 主机把 `linux/arm64` 换成 `linux/amd64`，wheel 也换成对应架构。

---

## 2. 层 1：工具链（apt 换源 + 编译依赖）

```bash
docker run --name sim-base --platform linux/arm64 python:3.12-slim bash -c "
  set -e
  sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends \
      git build-essential libnuma-dev
  pip install -q uv
"
docker commit sim-base sim-deps
```

对应踩过的坑：

| 问题 | 解法 |
| :-- | :-- |
| `deb.debian.org` 502 | 换 `mirrors.aliyun.com` |
| `numa.h: No such file` | `libnuma-dev` |
| 没有 uv | `pip install uv` |

---

## 3. 层 2：Python 依赖（torch + vLLM requirements）

```bash
docker run --name sim-env --platform linux/arm64 \
  -v "$ROOT/tmp:/wheels:ro" -v "$ROOT/tmp/vllm-030:/src:ro" \
  sim-deps bash -c "
    set -e
    # 3.1 先装宿主准备好的 torch CPU wheel
    uv pip install --system -q \
      /wheels/torch-2.13.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl

    # 3.2 复制 requirements，并删掉 torch 的 +cpu pin
    #     （PyPI 上 aarch64 的 torch 会拖一堆 nvidia-* CUDA 依赖，几个 GB）
    cp -r /src/requirements /tmp/reqs
    sed -i '/^torch==/d' /tmp/reqs/cpu.txt
    uv pip install --system -q -r /tmp/reqs/cpu.txt --index-strategy unsafe-best-match

    # 3.3 构建工具 + setuptools 生态（--no-build-isolation 需要）
    uv pip install --system -q \
      cmake ninja packaging 'setuptools>=77,<81' 'setuptools-scm>=8' \
      'setuptools-rust>=1.9' wheel jinja2
"
docker commit sim-env sim-env:torch
```

---

## 4. 层 3：编译 vLLM（带 PR #47922 补丁）

前提：`/src` 是已经打好补丁的源码树（见实验B 第 3.1 节）。

```bash
docker run --name sim-build --platform linux/arm64 \
  -v "$ROOT/tmp/vllm-030:/src:ro" \
  -v "$ROOT/tmp/acl:/acl:ro" \
  -v "$ROOT/tmp/onednn:/onednn:ro" \
  sim-env:torch bash -c "
    set -e
    cp -a /src /work
    cp -a /acl /work-acl        # ACL 构建会写入 build/，必须可写
    cp -a /onednn /work-onednn
    cd /work

    export VLLM_TARGET_DEVICE=cpu
    export ACL_ROOT_DIR=/work-acl
    export FETCHCONTENT_SOURCE_DIR_ONEDNN=/work-onednn
    export SETUPTOOLS_SCM_PRETEND_VERSION=0.31.1rc1   # worktree 的 .git 是文件，scm 拿不到版本
    export MAX_JOBS=2                                  # Docker 内存有限，-j8 会 OOM 杀 cc1plus

    uv pip install --system --no-deps --no-build-isolation -e .
  "
docker commit sim-build sim-built
```

对应踩过的坑：

| 问题 | 解法 |
| :-- | :-- |
| CMake clone ACL 卡死 | `ACL_ROOT_DIR` 指向本地副本 |
| CMake clone oneDNN 失败 | `FETCHCONTENT_SOURCE_DIR_ONEDNN` |
| `cc1plus: Killed signal`（OOM） | `MAX_JOBS=2` |
| setuptools-scm 找不到版本 | `SETUPTOOLS_SCM_PRETEND_VERSION` |

---

## 5. 层 4：运行时 wheel（triton + 视觉/音频解码）

```bash
docker run --name sim-runtime --platform linux/arm64 \
  -v "$ROOT/tmp:/wheels:ro" sim-built bash -c "
    set -e
    uv pip install --system -q --force-reinstall --no-deps \
      /wheels/triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl \
      /wheels/torchvision-0.28.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchaudio-2.11.0+cpu-cp312-cp312-manylinux_2_28_aarch64.whl \
      /wheels/torchcodec-0.17.0+cpu-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
"
docker commit sim-runtime sim-built:latest
```

对应踩过的坑：

| 报错 | 原因 | 解法 |
| :-- | :-- | :-- |
| `operator torchvision::nms does not exist` | torchvision 与 torch 不匹配 | 换 `+cpu` 对应版本 |
| `Could not load lib/_torchaudio.abi3.so` | torchaudio 不匹配 | 换 `+cpu` 对应版本 |
| `libnvrtc.so.13: not found` | torchcodec 是 CUDA 版 | 换 `torchcodec +cpu` |
| `TypeError: 'function' object is not subscriptable` | 没有 triton，`kernel[grid]` 失败 | 装 `triton-cpu` |

---

## 6. 运行

```bash
docker run --rm --platform linux/arm64 --shm-size=16g \
  -v "$ROOT/tmp:/wheels:ro" \
  -v "$ROOT/models:/models:ro" \
  -v "$ROOT/tmp/triton-cache:/triton-cache" \
  -e TRITON_CACHE_DIR=/triton-cache \
  sim-built bash -c "cd /work && VLLM_TARGET_DEVICE=cpu python /out/sim_smoke.py"
```

要点：

- `--shm-size=16g`：默认 64MB 不够，引擎启动会报
  `Insufficient space in /dev/shm`
- `TRITON_CACHE_DIR` 指向持久目录：否则每次都要重编 kernel（每个约 60s）
- 镜像里 `/work` 是可编辑安装的源码树，脚本从 `/out` 挂载

---

## 7. 镜像一览

| 镜像 | 内容 | 大小量级 |
| :-- | :-- | :-- |
| `python:3.12-slim` | 基础 | ~200MB |
| `sim-deps` | + apt 工具链 + uv | ~1GB |
| `sim-env:torch` | + torch / vLLM 依赖 | ~6GB（含 uv 缓存） |
| `sim-built` | + 编译好的 vLLM（ACL/oneDNN 静态链接） | ~7GB |

> 如果在意体积，可以在每层 `docker commit` 前清掉 `/root/.cache/uv`。

---

## 8. 一键脚本

日常跑实验不需要重复这些步骤，直接用：

```bash
./run_in_container.sh sim_timing.py
```

它会挂载 wheel、模型、Triton 缓存，并在 `sim-built` 里执行脚本。
