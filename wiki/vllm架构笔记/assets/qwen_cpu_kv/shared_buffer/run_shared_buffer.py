import os
import sys

import torch
from vllm import LLM, SamplingParams
from vllm.config import KVTransferConfig
from vllm.v1.core import kv_cache_utils
from vllm.v1 import kv_cache_interface as kci
from vllm.v1.kv_cache_interface import KVCacheTensor, UniformTypeKVCacheSpecs

sys.path.insert(0, "/app")
ALIAS = os.getenv("ALIAS", "0") == "1"


def install_stride_patch() -> None:
    """Allow layer_stride=0 so multiple layers can alias one backing tensor."""
    original = kci.compute_layout_strides

    def patched(spec, num_blocks, num_layers, layout, kernel_block_size=None, fixed_strides=(None,) * 5):
        assert len(fixed_strides) == 5
        assert all(stride is None or stride >= 0 for stride in fixed_strides)
        shape = (num_layers, *kci.compute_layer_kv_cache_shape_bytes(spec, num_blocks, kernel_block_size))
        order = layout.stride_order
        padded_page_size = getattr(spec, "page_size_padded", None)
        strides = [0] * 5
        current_stride = 1
        for physical_idx, dim in reversed(tuple(enumerate(order))):
            if padded_page_size is not None and physical_idx == (max(order.index(kci._DIM_L), order.index(kci._DIM_B)) + 1) - 1:
                current_stride = max(current_stride, padded_page_size)
                assert current_stride % padded_page_size == 0
            strides[dim] = fixed_strides[dim] if fixed_strides[dim] is not None else current_stride
            current_stride = strides[dim] * shape[dim]
        return tuple(strides)

    kci.compute_layout_strides = patched


def install_alias_patch() -> None:
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
        print("ALIAS_CONFIG layers", len(layer_names), "tensors_before", len(config.kv_cache_tensors), "page", page_size)
        if not ALIAS:
            return config
        # 4 layers -> independent layer0 + one shared slot for 1,2,3.
        slots = [[layer_names[0]], layer_names[1:]]
        config.kv_cache_tensors = [
            KVCacheTensor(
                size=page_size * config.num_blocks,
                layers=names,
                layer_stride=0 if len(names) > 1 else page_size * config.num_blocks,
                block_stride=page_size,
                offset=0,
            )
            for names in slots
        ]
        print("ALIAS_TENSORS", len(config.kv_cache_tensors), "blocks", config.num_blocks)
        return config

    kv_cache_utils.get_kv_cache_config_from_groups = patched


torch.manual_seed(0)
if ALIAS:
    install_stride_patch()
    install_alias_patch()

kv = None
if ALIAS:
    kv = KVTransferConfig(
        kv_connector="LayerwiseSharedBufferConnector",
        kv_connector_module_path="layerwise_shared_buffer_connector",
        kv_role="kv_both",
        engine_id="shared-cpu",
        kv_connector_extra_config=({"mooncake_master": "mooncake-master:50051",
                                    "mooncake_key_prefix": "shared",
                                    "mooncake_segment_size": 4 * 1024**3,
                                    "mooncake_local_buffer": 256 * 1024**2}
                                   if os.getenv("MOONCAKE") == "1" else {}),
    )

llm = LLM(
    model="/models/Qwen2.5-tiny4",
    load_format="dummy",
    max_model_len=64,
    gpu_memory_utilization=0.05,
    kv_cache_memory_bytes=64 * 1024**2,
    enforce_eager=True,
    kv_transfer_config=kv,
)
out = llm.generate(
    ["Hello, my name is"],
    SamplingParams(max_tokens=4, temperature=0.0, seed=0),
)
print("ALIAS", ALIAS)
print("TOKENS", out[0].outputs[0].token_ids)
