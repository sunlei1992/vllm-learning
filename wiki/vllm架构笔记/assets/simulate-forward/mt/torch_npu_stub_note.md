# torch_npu stub 的 Event 语义（P1）

`assets/simulate-forward/va/torch_npu_stub/torch_npu/__init__.py` 里：

- `npu.Event` 用 `threading.Event` 实现：`record()` 置位，`wait()` 阻塞，`query()/is_set()` 查询
- `npu.Stream` 的 `wait_event` 直接等对应事件
- `npu.current_stream()` 返回空 Stream

这样 CPU 上跑 layerwise save/load 的 fence 逻辑不会卡死，也不需要 NPU。
