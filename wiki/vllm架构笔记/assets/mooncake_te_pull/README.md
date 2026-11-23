# Mooncake TE TCP PullTransport prototype

本地验证 **“D 单边读 P 的 host 内存”**（DRAM2DRAM），为昇腾 `ascend` transport 做接口预演。
2026-11-23 跑通。

## 结果

```text
D got peer pull-p buffers [4194304, 4194304, 4194304]
range buf=0 off=0 len=1048576 match=True
range buf=1 off=2097152 len=1048576 match=True
range buf=2 off=0 len=4194304 match=True
RESULT PASS bytes=6291456 time=8.38ms
```

- 3 个 4 MiB buffer，按 offset/长度读 3 段，共 6 MiB
- P 收到 `READ_DONE`
- 时间只是 Docker 内 TCP 参考，**不代表昇腾性能**

## 组件

| 文件 | 作用 |
| :-- | :-- |
| `pull_transport.py` | `PullTransport` 接口 + `MooncakeTransport`（register/read/close） |
| `p_side.py` | P：建 buffer、`batch_register_memory`、控制面发布地址、等 `READ_DONE` |
| `d_side.py` | D：取地址、注册本地 buffer、`batch_transfer_sync_read`、校验、回 `READ_DONE` |
| `run_demo.sh` | 起 metadata server + P + D 的一键脚本 |

## 运行

```bash
./run_demo.sh
```

依赖镜像 `mooncake-tcp-p2p:latest`（Mooncake 0.3.14，non-cuda）。

### 两个坑（已踩）

1. metadata URL 必须带 **`/metadata`**：
   `http://pull-meta:8080/metadata`
2. 0.3.14 的 HTTP metadata server 默认拒绝无 token 绑定 0.0.0.0：
   需要 `MC_METADATA_HTTP_ALLOW_INSECURE=1`（meta/P/D 三边都要）

## 接口

```python
class PullTransport:
    def register(self, ptrs: list[int], sizes: list[int]) -> None
    def read(self, peer: str, local_ptrs: list[int],
             peer_ptrs: list[int], lengths: list[int]) -> None
    def close(self) -> None
```

`MooncakeTransport(hostname, protocol="tcp", device="", metadata=...)`：

- `register` → `batch_register_memory`
- `read` → `batch_transfer_sync_read(peer, local, peer_ptrs, lengths)`

## 换到昇腾时要改什么

| 项 | 本地 | 昇腾 |
| :-- | :-- | :-- |
| protocol | `"tcp"` | `"ascend"` |
| wheel | `mooncake-transfer-engine-non-cuda` | `mooncake-transfer-engine-npu >= 0.3.13` |
| 注册内存 | host buffer | HBM（`batch_register_memory` + device） |
| read 首参 | `target_hostname` | NPU wheel 为 **`session_id`**（签名不同，需版本探测） |
| metadata | HTTP server（`/metadata`） | 同上，或 connector 侧交换 session |

## read_thread 类级注入（2026-11-23）

用真实的 `MembPullReadThread._do_read_batch` 跑通 MooncakeTransport：

```text
block=0 k_match=True v_match=True
block=1 k_match=True v_match=True
RESULT PASS
```

| 文件 | 作用 |
| :-- | :-- |
| `p_kv_side.py` | P：K/V 各 2 个 block 注册 + 发布 base 地址 |
| `d_read_thread_test.py` | 构造 `ConsumerReadState`，调用 `_do_read_batch` |
| `run_read_thread_demo.sh` | 一键：拷 VA 源码 + `_build_info` stub + 起 meta/P + 跑 D |

```bash
./run_read_thread_demo.sh
```

要求：

- VA 源码（默认 `tmp/vllm-ascend-layerwise-v030`），拷到 `/tmp/va_rt` 并补
  `vllm_ascend/_build_info.py`（`__soc_version__ = "ASCEND910B1"`）
- `torch_npu` stub（`assets/simulate-forward/va/torch_npu_stub`）
- D 容器 `sim030:mooncake`（`/opt/v030`，vLLM 0.30.0）

这证明：`_do_read_batch` 的 K/V 指针计算 + `engine.batch_transfer_sync_read` 契约
可以直接换成 MooncakeTransport，不需要改 read_thread。

## worker 接入（2026-11-23）

vllm-ascend 分支 `layerwise/v030-mooncake-pull` @ `25f87d8d0`：

| 改动 | 内容 |
| :-- | :-- |
| `utils/pull_engine.py` | `MemfabricPullEngine` / `MooncakePullEngine` / `make_pull_engine` |
| `sfa_pd_rd2h/worker.py` | `transfer_backend=memfabric|mooncake`；`mooncake_metadata` / `mooncake_transfer_protocol` / `mooncake_device_name` |
| 测试 | 新增 6 passed；SFA P/D 回归 113 passed |

配置示例：

```json
{"kv_connector": "SfaRemoteD2HConnector",
 "kv_connector_extra_config": {
   "transfer_backend": "mooncake",
   "mooncake_metadata": "http://pull-meta:8080/metadata",
   "mooncake_transfer_protocol": "tcp"}}
```

昇腾上把 `mooncake_transfer_protocol` 改成 `ascend`、`mooncake_device_name`
填 NIC/设备名，并换 NPU wheel。

注意：P 的 `p_session` 现在取 `engine.unique_id`——TCP 下是 hostname，
NPU wheel 下应是 session id，需要按 wheel 的 `batch_transfer_sync_read`
签名确认。

## 下一步

1. 把 `MooncakeTransport` 注入 `sfa_pd_rd2h/read_thread.py` 的 `engine`（它已是 duck-typed）
2. P 侧地址/会话字段接进现有 ZMQ `LayerMetadata`
3. 与 layerwise 组合时加 **双 fence**：`store commit + READ_DONE` 才能覆盖共享 slot
4. 失败注入：短读、peer 断连、revoke、重试
5. 昇腾：`register_memory(HBM)` + `protocol=ascend` + NPU wheel 验证

## 边界

- 只验证 **传输原语 + 控制面 + 完成语义**，不验证 vLLM connector 集成
- TCP 带宽/延迟无参考价值
- 未验证 `batch_transfer_async_read` / 多线程并发
