"""Scheduler-side prefix pin for the closed-loop 128K case.

When a request finishes, keep its first PIN_PREFIX_TOKENS tokens' blocks in
the pool (ref_cnt=1, removed from the free queue) instead of returning them.
At most PIN_MAX prefixes are retained; the oldest pin is released first.

This is a simulation-side approximation, not a production KV cache policy:
it assumes one KV group and a fixed prefix length.
"""

import math
import os
from collections import OrderedDict

from vllm.v1.core.sched.scheduler import Scheduler


class PrefixPinScheduler(Scheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pin_max = int(os.getenv("PIN_MAX", "5"))
        self._prefix_tokens = int(os.getenv("PIN_PREFIX_TOKENS", "115200"))
        self._pins: "OrderedDict[int, list]" = OrderedDict()
        self._pinned_ids: set[int] = set()
        self._keys: dict[str, int] = {}

    def _key(self, request) -> int:
        key = self._keys.get(request.request_id)
        if key is None:
            toks = request.prompt_token_ids or []
            key = hash(tuple(toks[:128]))
            self._keys[request.request_id] = key
        return key

    def _release(self, key: int) -> None:
        blocks = self._pins.pop(key, None)
        if not blocks:
            return
        for b in blocks:
            self._pinned_ids.discard(b.block_id)
        self.kv_cache_manager.block_pool.free_blocks(blocks[::-1])

    def _pin(self, key: int, blocks: list) -> None:
        pool = self.kv_cache_manager.block_pool
        for b in blocks:
            if b.block_id in self._pinned_ids:
                # The block is already pinned; drop only this request's ref.
                pool.free_blocks([b])
            else:
                pool.free_blocks([b])
                pool.touch([b])
                self._pinned_ids.add(b.block_id)
        self._pins[key] = blocks
        while len(self._pins) > self._pin_max:
            old_key = next(iter(self._pins))
            if old_key == key:
                break
            self._release(old_key)

    def _free_request_blocks(self, request):
        blocks = self.kv_cache_manager.pop_blocks_for_free(request)
        if not blocks:
            return
        n_prefix = min(
            math.ceil(self._prefix_tokens / self.block_size), len(blocks)
        )
        prefix, suffix = blocks[:n_prefix], blocks[n_prefix:]
        if suffix:
            self.kv_cache_manager.block_pool.free_blocks(suffix[::-1])
        if prefix:
            self._pin(self._key(request), prefix)
