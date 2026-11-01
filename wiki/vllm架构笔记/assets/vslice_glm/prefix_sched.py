"""Minimal prefix-grouped scheduler for the 128K / 24-prefix case.

Reorders `Scheduler.waiting` so requests of the same prefix are scheduled
together, with a cap on how many prefix groups are active at once.
"""

import os
from collections import OrderedDict

from vllm.v1.core.sched.scheduler import Scheduler


class PrefixGroupedScheduler(Scheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefix_keys: dict[str, int] = {}
        self._max_active = int(os.getenv("PREFIX_ACTIVE", "1"))
        self._key_len = int(os.getenv("PREFIX_KEY_LEN", "128"))

    def _key(self, req) -> int:
        key = self._prefix_keys.get(req.request_id)
        if key is None:
            toks = req.prompt_token_ids or []
            key = hash(tuple(toks[: self._key_len]))
            self._prefix_keys[req.request_id] = key
        return key

    def _reorder(self) -> None:
        buckets: "OrderedDict[int, list]" = OrderedDict()
        for req in list(self.waiting):
            buckets.setdefault(self._key(req), []).append(req)

        active: list[int] = []
        if self.running:
            running_key = self._key(self.running[0])
            if running_key in buckets:
                active.append(running_key)

        for key in buckets:
            if len(active) >= self._max_active:
                break
            if key not in active:
                active.append(key)

        ordered = []
        for key in active:
            ordered.extend(buckets.pop(key))
        for reqs in buckets.values():
            ordered.extend(reqs)

        self.waiting.clear()
        self.waiting.extend(ordered)

    def schedule(self, *args, **kwargs):
        if len(self.waiting) > 1:
            self._reorder()
        return super().schedule(*args, **kwargs)
