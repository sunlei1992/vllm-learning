import os, sys, json
import torch
from vllm import LLM, SamplingParams
from vllm.config import KVTransferConfig
from vllm.v1.core import kv_cache_utils
from vllm.v1 import kv_cache_interface as kci
from vllm.v1.kv_cache_interface import KVCacheTensor, UniformTypeKVCacheSpecs

sys.path.insert(0, "/app")
ALIAS = os.getenv("ALIAS", "1") == "1"
MODEL_DIR = os.getenv("MODEL_DIR", "/models/Qwen2.5-tiny4")
print("MODEL_DIR", MODEL_DIR, "layers", json.load(open(os.path.join(MODEL_DIR, "config.json")))["num_hidden_layers"], flush=True)


def install_stride_patch():
    original = kci.compute_layout_strides

    def patched(spec, num_blocks, num_layers, layout, kernel_block_size=None, fixed_strides=(None,) * 5):
        shape = (num_layers, *kci.compute_layer_kv_cache_shape_bytes(spec, num_blocks, kernel_block_size))
        order = layout.stride_order
        padded_page_size = getattr(spec, "page_size_padded", None)
        strides = [0] * 5
        current_stride = 1
        for physical_idx, dim in reversed(tuple(enumerate(order))):
            if padded_page_size is not None and physical_idx == (max(order.index(kci._DIM_L), order.index(kci._DIM_B)) + 1) - 1:
                current_stride = max(current_stride, padded_page_size)
            strides[dim] = fixed_strides[dim] if fixed_strides[dim] is not None else current_stride
            current_stride = strides[dim] * shape[dim]
        return tuple(strides)

    kci.compute_layout_strides = patched


def install_alias_patch():
    original = kv_cache_utils.get_kv_cache_config_from_groups

    def patched(vllm_config, kv_cache_groups, available_memory):
        config = original(vllm_config, kv_cache_groups, available_memory)
        group = kv_cache_groups[0]
        spec = group.kv_cache_spec
        layer_names = list(group.layer_names)
        if isinstance(spec, UniformTypeKVCacheSpecs):
            page_size = max(spec.kv_cache_specs[name].page_size_bytes for name in layer_names)
        else:
            page_size = spec.page_size_bytes
        print("ALIAS_CONFIG layers", len(layer_names), "tensors_before", len(config.kv_cache_tensors), "page", page_size, flush=True)
        if not ALIAS:
            return config
        num_shared = int(os.getenv("NUM_SHARED", "1"))
        shared = layer_names[1:]
        slots = [[layer_names[0]]] + [shared[i::num_shared] for i in range(num_shared)]
        slots = [slot for slot in slots if slot]
        slot_size = page_size * config.num_blocks
        total = slot_size * len(slots)
        config.kv_cache_tensors = [
            KVCacheTensor(
                size=total,
                layers=names,
                layer_stride=0 if len(names) > 1 else slot_size,
                block_stride=page_size,
                offset=i * slot_size,
            )
            for i, names in enumerate(slots)
        ]
        print("ALIAS_TENSORS", len(config.kv_cache_tensors), "blocks", config.num_blocks, flush=True)
        return config

    kv_cache_utils.get_kv_cache_config_from_groups = patched


torch.manual_seed(0)
if ALIAS:
    install_stride_patch()
    install_alias_patch()

# --- instrumentation ---
import vllm.model_executor.layers.attention.attention as A
_orig_ctx = A.get_attention_context
STATS = {"none": 0, "ok": 0}
def _dbg_ctx(layer_name):
    from vllm.forward_context import get_forward_context
    raw = get_forward_context().attn_metadata
    if raw is None:
        STATS["none"] += 1
        if STATS["none"] <= 6:
            print("CTX_NONE", layer_name, flush=True)
    else:
        STATS["ok"] += 1
        if STATS["ok"] <= 3:
            print("CTX_OK", layer_name, type(raw).__name__, flush=True)
    return _orig_ctx(layer_name)
A.get_attention_context = _dbg_ctx

# Load historical KV before the layer's KV update. vLLM's decorator runs the
# hook after unified_kv_cache_update, which would clobber the new tokens.
_orig_forward = A.Attention.forward
def _wait_then_forward(self, query, key, value, *args, **kwargs):
    from vllm.distributed.kv_transfer import (
        has_kv_transfer_group, get_kv_transfer_group, is_v1_kv_transfer_group,
    )
    if has_kv_transfer_group() and is_v1_kv_transfer_group():
        conn = get_kv_transfer_group()
        if conn.has_connector_metadata():
            conn.wait_for_layer_load(self.layer_name)
    return _orig_forward(self, query, key, value, *args, **kwargs)
A.Attention.forward = _wait_then_forward

import layerwise_shared_buffer_connector as L
_orig_wait = L.LayerwiseSharedBufferConnector.wait_for_layer_load
def _dbg_wait(self, layer_name):
    print("CONN_WAIT", layer_name, "cur", self._current_key, flush=True)
    return _orig_wait(self, layer_name)
L.LayerwiseSharedBufferConnector.wait_for_layer_load = _dbg_wait
_orig_save = L.LayerwiseSharedBufferConnector.save_kv_layer
def _dbg_save(self, layer_name, *a, **k):
    print("CONN_SAVE", layer_name, "cur", self._current_key, flush=True)
    return _orig_save(self, layer_name, *a, **k)
L.LayerwiseSharedBufferConnector.save_kv_layer = _dbg_save

kv = None
if ALIAS and os.getenv("NO_CONN", "0") != "1":
    kv = KVTransferConfig(
        kv_connector="LayerwiseSharedBufferConnector",
        kv_connector_module_path="layerwise_shared_buffer_connector",
        kv_role="kv_both",
        engine_id="shared-cpu",
        kv_connector_extra_config={},
    )

llm = LLM(
    model=MODEL_DIR,
    load_format=os.getenv("LOAD_FORMAT", "dummy"),
    max_model_len=64,
    gpu_memory_utilization=0.05,
    kv_cache_memory_bytes=64 * 1024**2,
    enforce_eager=True,
    kv_transfer_config=kv,
)
out = llm.generate(["Hello, my name is"], SamplingParams(max_tokens=int(os.getenv("MAX_TOKENS", "2")), temperature=0.0, seed=0))
print("TOKENS", out[0].outputs[0].token_ids)
print("STATS", STATS)
