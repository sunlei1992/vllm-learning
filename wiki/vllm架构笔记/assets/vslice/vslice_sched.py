"""Scheduling-policy switch for the vertical slice.

Both baseline and candidate run this same class; only VSLICE_POLICY differs.
`fcfs` is a no-op, `srs` reorders the waiting queue by prompt length before
each schedule call. This mirrors sim_policy.py, but as a real --scheduler-cls
so it works under `vllm serve`.
"""

import os

from vllm.v1.core.sched.scheduler import Scheduler


class PolicyScheduler(Scheduler):
    def schedule(self, throttle_prefills: bool = False):
        policy = os.getenv("VSLICE_POLICY", "fcfs")
        if policy == "srs" and len(self.waiting) > 1:
            items = sorted(self.waiting, key=lambda r: r.num_prompt_tokens)
            self.waiting.clear()
            self.waiting.extend(items)
        return super().schedule(throttle_prefills)
