# 纯 vLLM CPU + Qwen3-0.6B KV 传输实验

## 环境

- `.venv`：vLLM 0.28.0，CPU
- 模型：`models/Qwen_Qwen3-0.6B`（只有 config/tokenizer，权重用 `load_format="dummy"` 随机生成）
- 随机权重只用于验证链路，输出 token 无语言意义

## 运行

```bash
cd /Users/sunlei/code/dsh/vllm
VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  .venv/bin/python wiki/vllm架构笔记/assets/qwen_cpu_kv/qwen_cpu_dummy.py
```

P/D 分离：

```bash
rm -rf /tmp/vllm-cpu-pd-example
VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  .venv/bin/python wiki/vllm架构笔记/assets/qwen_cpu_kv/qwen_cpu_pd_role.py kv_producer
VLLM_TARGET_DEVICE=cpu VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  .venv/bin/python wiki/vllm架构笔记/assets/qwen_cpu_kv/qwen_cpu_pd_role.py kv_consumer
```

## 结果

- 纯 CPU baseline：成功生成随机 token。
- P `kv_producer`：成功保存 KV。
- D `kv_consumer`：日志出现 `External Cache Hit!`，输出与 P 相同。
- D 的 token：

```text
[150903, 130517, 150903, 130517]
```

## 重要边界

`ExampleConnector` 的 `save_kv_layer` 是**逐层调用**的，所以它是 layerwise KV transfer；
但它把每层 KV 存到磁盘/对象里，**P 的完整 KV cache 仍然存在**，不是 `layerwise_num_shared_buffers`
的跨层 shared buffer，也不省 P 的 HBM。

真正的 shared-buffer 需要 connector/worker 参与 KV cache 分配，纯 vLLM 的默认分配器不提供
`layerwise_num_shared_buffers`；当前只能用 synthetic shared-slot 测试验证算法。
