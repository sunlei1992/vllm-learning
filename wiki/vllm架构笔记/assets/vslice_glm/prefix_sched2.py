"""Prefix-grouped scheduler v2: consider the running prefixes.

Policy:
  - never open more than PREFIX_ACTIVE prefix groups at once;
  - while a running prefix still has waiting requests, feed those first;
  - if the active set is below the cap, open the oldest waiting prefix;
  - otherwise leave the new prefixes waiting (drain the active ones first).
"""

import os
from collections import OrderedDict

from vllm.v1.core.sched.scheduler import Scheduler


class PrefixGroupedScheduler(Scheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._prefix_keys: dict[str, int] = {}
        self._max_active = int(os.getenv("PREFIX_ACTIVE", "2"))
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
        first_seen: dict[int, int] = {}
        for idx, req in enumerate(self.waiting):
            key = self._key(req)
            buckets.setdefault(key, []).append(req)
            first_seen.setdefault(key, idx)

        running_keys = list(dict.fromkeys(self._key(r) for r in self.running))
        active = [k for k in running_keys if k in buckets]
        active.sort(key=lambda k: first_seen[k])
        active = active[: self._max_active]

        # If the running set is below the cap, open the oldest waiting prefix.
        new_keys: list[int] = []
        if len(running_keys) < self._max_active:
            for key in buckets:
                if key in running_keys:
                    continue
                new_keys.append(key)
                if len(running_keys) + len(new_keys) >= self._max_active:
                    break

        ordered = []
        for key in active:
            ordered.extend(buckets.pop(key))
        for key in new_keys:
            ordered.extend(buckets.pop(key))
        for reqs in buckets.values():
            ordered.extend(reqs)

        self.waiting.clear()
        self.waiting.extend(ordered)

    def schedule(self, *args, **kwargs):
        if len(self.waiting) > 1:
            self._reorder()
        return super().schedule(*args, **kwargs)
