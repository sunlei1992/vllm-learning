import os
import random

import torch

from vllm import LLM, SamplingParams
from vllm.v1.core import kv_cache_utils
from vllm.v1.kv_cache_interface import KVCacheTensor, UniformTypeKVCacheSpecs

ALIAS = os.getenv("ALIAS", "0") == "1"
NUM_SHARED = 3


def _install_alias_patch() -> None:
    original = kv_cache_utils.get_kv_cache_config_from_groups

    def patched(vllm_config, kv_cache_groups, available_memory):
        config = original(vllm_config, kv_cache_groups, available_memory)
        group = kv_cache_groups[0]
        spec = group.kv_cache_spec
        print("CONFIG", len(config.kv_cache_tensors), type(spec).__name__, len(group.layer_names))
        if not ALIAS:
            return config
        layer_names = list(group.layer_names)
        if isinstance(spec, UniformTypeKVCacheSpecs):
            page_size = max(
                spec.kv_cache_specs[name].page_size_bytes for name in layer_names
            )
        else:
            page_size = spec.page_size_bytes
        slots = [[layer_names[0]]]
        rest = layer_names[1:]
        for shard in range(NUM_SHARED):
            slots.append(rest[shard::NUM_SHARED])
        config.kv_cache_tensors = [
            KVCacheTensor(
                size=page_size * config.num_blocks,
                shared_by=names,
            )
            for names in slots
        ]
        print(
            "ALIAS_PATCH layers=", len(layer_names),
            "tensors=", len(config.kv_cache_tensors),
            "blocks=", config.num_blocks,
            "page_size=", page_size,
        )
        return config

    kv_cache_utils.get_kv_cache_config_from_groups = patched


if ALIAS:
    _install_alias_patch()
    from vllm.v1.worker.cpu_model_runner import CPUModelRunner

    _orig_alloc = CPUModelRunner._allocate_kv_cache_tensors

    def _alloc_with_ptrs(self, kv_cache_config):
        tensors = _orig_alloc(self, kv_cache_config)
        print("PTRS", {name: tensor.data_ptr() for name, tensor in list(tensors.items())[:4]})
        print("UNIQUE_PTRS", len({tensor.data_ptr() for tensor in tensors.values()}))
        return tensors

    CPUModelRunner._allocate_kv_cache_tensors = _alloc_with_ptrs

torch.manual_seed(0)
random.seed(0)
llm = LLM(
    model="models/Qwen_Qwen3-0.6B",
    load_format="dummy",
    max_model_len=256,
    gpu_memory_utilization=0.3,
    enforce_eager=True,
)
out = llm.generate(
    ["Hello, my name is"],
    SamplingParams(max_tokens=int(os.getenv("MAX_TOKENS", "1")), temperature=0.0),
)
print("ALIAS", ALIAS)
print("TOKENS", out[0].outputs[0].token_ids)
