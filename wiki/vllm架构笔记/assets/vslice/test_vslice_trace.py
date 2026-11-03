"""Golden scheduling-trace unit test for the vslice policy.

Runs the real vLLM Scheduler offline (no model forward) with a fake KV cache,
so the trace is deterministic and fast. The assertions pin the first three
steps of FCFS and SRS, which is what the vertical slice observed over HTTP.

Run in the simulator image:
    bash run_trace_test.sh
or inside the container:
    cd /tools && PYTHONPATH=/work:/tools python -m unittest -v test_vslice_trace
"""

import os
import unittest

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

from tests.v1.core.utils import create_requests, create_scheduler  # noqa: E402
from vllm.v1.outputs import ModelRunnerOutput  # noqa: E402
from vslice_sched import PolicyScheduler  # noqa: E402

MODEL = "/models/Qwen_Qwen3-0.6B"
N_PER_CLASS = 8
LONG_TOKENS = 725
SHORT_TOKENS = 65
MAX_TOKENS = 16


def run_trace(policy: str) -> dict:
    os.environ["VSLICE_POLICY"] = policy
    scheduler = create_scheduler(
        model=MODEL,
        max_num_seqs=8,
        max_num_batched_tokens=512,
        max_model_len=2048,
        num_blocks=10000,
        block_size=16,
        enable_prefix_caching=False,
        enable_chunked_prefill=True,
    )
    # create_scheduler() hardcodes Scheduler; rebind to the policy subclass so
    # the test exercises vslice_sched.PolicyScheduler itself.
    scheduler.__class__ = PolicyScheduler

    requests = create_requests(
        N_PER_CLASS,
        num_tokens=LONG_TOKENS,
        max_tokens=MAX_TOKENS,
        ignore_eos=True,
        req_ids=[f"long-{i}" for i in range(N_PER_CLASS)],
    ) + create_requests(
        N_PER_CLASS,
        num_tokens=SHORT_TOKENS,
        max_tokens=MAX_TOKENS,
        ignore_eos=True,
        req_ids=[f"short-{i}" for i in range(N_PER_CLASS)],
    )
    for req in requests:
        scheduler.add_request(req)

    steps = []
    preemptions = 0
    for _ in range(200):
        if not scheduler.has_requests():
            break
        out = scheduler.schedule()
        preemptions += len(out.preempted_req_ids or ())
        ids = [rid for rid, n in out.num_scheduled_tokens.items() if n > 0]
        labels = [
            "SHORT" if scheduler.requests[rid].num_prompt_tokens < 200 else "LONG"
            for rid in ids
        ]
        steps.append(
            {
                "labels": labels,
                "tokens": dict(out.num_scheduled_tokens),
                "waiting": len(scheduler.waiting),
            }
        )
        if out.total_num_scheduled_tokens == 0:
            break
        model_output = ModelRunnerOutput(
            req_ids=ids,
            req_id_to_index={rid: i for i, rid in enumerate(ids)},
            sampled_token_ids=[[0] for _ in ids],
        )
        scheduler.update_from_output(out, model_output)

    first = {"SHORT": None, "LONG": None}
    early = {"SHORT": 0, "LONG": 0}
    for i, step in enumerate(steps):
        for label in step["labels"]:
            if first[label] is None:
                first[label] = i
            if i < 3:
                early[label] += 1

    return {
        "policy": policy,
        "steps": len(steps),
        "total_tokens": sum(sum(s["tokens"].values()) for s in steps),
        "preemptions": preemptions,
        "first_short_step": first["SHORT"],
        "first_long_step": first["LONG"],
        "first3_short": early["SHORT"],
        "first3_long": early["LONG"],
        "head": steps[:5],
    }


class TestVSliceTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fcfs = run_trace("fcfs")
        cls.srs = run_trace("srs")

    def test_fcfs_golden_trace(self):
        t = self.fcfs
        self.assertEqual(t["steps"], 42)
        # 15 decode tokens are scheduled per request; the 16th is the
        # finishing sample, so 8*(725+15) + 8*(65+15) = 6560.
        self.assertEqual(t["total_tokens"], 6560)
        self.assertEqual(t["preemptions"], 0)
        self.assertEqual(t["first_long_step"], 0)
        self.assertEqual(t["first_short_step"], 16)
        self.assertEqual(t["first3_short"], 0)
        self.assertEqual(t["first3_long"], 6)
        self.assertEqual(t["head"][0]["labels"], ["LONG"])
        self.assertEqual(t["head"][0]["tokens"], {"long-0": 512})

    def test_srs_golden_trace(self):
        t = self.srs
        self.assertEqual(t["steps"], 42)
        self.assertEqual(t["total_tokens"], 6560)
        self.assertEqual(t["preemptions"], 0)
        self.assertEqual(t["first_short_step"], 0)
        self.assertEqual(t["first_long_step"], 16)
        self.assertEqual(t["first3_short"], 24)
        self.assertEqual(t["first3_long"], 0)
        self.assertEqual(t["head"][0]["labels"], ["SHORT"] * 8)
        self.assertEqual(t["head"][0]["tokens"]["short-7"], 57)
        self.assertEqual(sum(t["head"][0]["tokens"].values()), 512)

    def test_srs_moves_short_requests_forward(self):
        self.assertLess(self.srs["first_short_step"], self.fcfs["first_short_step"])
        self.assertGreater(self.srs["first3_short"], self.fcfs["first3_short"])
        self.assertGreater(self.srs["first_long_step"], self.fcfs["first_long_step"])
        # Policy must not change the total work or cause preemptions.
        self.assertEqual(self.srs["total_tokens"], self.fcfs["total_tokens"])
        self.assertEqual(self.srs["steps"], self.fcfs["steps"])
        self.assertEqual(self.srs["preemptions"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
