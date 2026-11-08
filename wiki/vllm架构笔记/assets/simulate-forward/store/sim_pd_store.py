"""1P1D with a real-Mooncake store connector on the prefill side."""

import dataclasses
import os
import uuid

os.environ.setdefault("VLLM_TARGET_DEVICE", "cpu")

from vllm import SamplingParams
from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
from vllm.engine.arg_utils import EngineArgs
from vllm.v1.worker.simulated.offline import TimedRequest

KVConnectorFactory.register_connector(
    "SimulatedAscendStoreConnector",
    "local_store_connector",
    "SimulatedAscendStoreConnector",
)

def install_kv_xfer_guard() -> None:
    """Tolerant replacement for Scheduler._update_from_kv_xfer_finished.

    MultiConnector may report completions for requests it no longer owns (or
    that were preempted between submit and completion). Stock vLLM asserts on
    those; drop them instead.
    """
    from vllm.v1.core.sched.scheduler import Scheduler
    from vllm.v1.metrics.stats import KV_FETCH_COMPLETED_WAITING
    from vllm.v1.request import RequestStatus

    if getattr(Scheduler, "_mc_guarded", False):
        return

    def guarded(self, kv_connector_output):
        if self.connector is not None:
            self.connector.update_connector_output(kv_connector_output)
        for req_id in list(kv_connector_output.finished_recving or ()):
            req = self.requests.get(req_id)
            if req is None:
                continue
            if req.status == RequestStatus.WAITING_FOR_REMOTE_KVS:
                self.finished_recving_kv_req_ids.add(req_id)
                self._set_kv_fetch_stage(req, KV_FETCH_COMPLETED_WAITING)
            elif RequestStatus.is_finished(req.status):
                self._free_blocks(req)
        for req_id in list(kv_connector_output.finished_sending or ()):
            req = self.requests.get(req_id)
            if req is None:
                continue
            self._free_blocks(req)

    Scheduler._update_from_kv_xfer_finished = guarded
    Scheduler._mc_guarded = True


install_kv_xfer_guard()

from vllm.config.simulation import SimulationConfig

_orig_verify = SimulationConfig._verify_kv_transfer


def _verify_kv_transfer(self, vllm_config):
    kv = vllm_config.kv_transfer_config
    if kv is not None and kv.kv_connector == "MultiConnector":
        # Local experiment: children are validated by their own connectors.
        return
    return _orig_verify(self, vllm_config)


SimulationConfig._verify_kv_transfer = _verify_kv_transfer

from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory as _Factory
from vllm.v1.worker.simulated.kv_nixl import NixlConnector as SimNixlConnector
from vllm.v1.worker.simulated.kv_nixl import NixlPushConnector as SimNixlPushConnector

# MultiConnector resolves children through the real factory; point the Nixl
# names at the simulated subclasses so no NIXL runtime is needed.
_Factory._registry["NixlConnector"] = lambda: SimNixlConnector
_Factory._registry["NixlPushConnector"] = lambda: SimNixlPushConnector

import vllm.v1.worker.simulated.disaggregated as dis
import vllm.v1.worker.simulated.kv_transfer as kt
import vllm.v1.worker.simulated.model_runner as mr

MODEL = os.environ.get("SIM_MODEL", "/models/Qwen_Qwen3-0.6B")
N = int(os.environ.get("PD_N", "16"))
PROMPT = int(os.environ.get("PD_PROMPT", "1024"))
GAP = float(os.environ.get("PD_GAP", "0.002"))
PREFIXES = int(os.environ.get("PD_PREFIXES", "1"))

_orig_make_instance = dis.make_instance


def make_instance(engine_args, kv_role, name, usage_context=None):
    base = engine_args.kv_transfer_config
    if isinstance(base, dict):
        from vllm.config import KVTransferConfig

        base = KVTransferConfig(**base)
    if base is not None and base.kv_connector not in (None, "NixlConnector"):
        from vllm.config import KVTransferConfig

        sim = dataclasses.replace(engine_args.simulation_config, clock="virtual")
        args = dataclasses.replace(
            engine_args,
            kv_transfer_config=KVTransferConfig(
                kv_connector=base.kv_connector,
                kv_role=kv_role,
                engine_id=f"{name}-{uuid.uuid4().hex[:8]}",
                kv_connector_extra_config=dict(base.kv_connector_extra_config or {}),
            ),
            simulation_config=sim,
        )
        return dis.make_engine(args, dis.VirtualClock(), usage_context)
    return _orig_make_instance(engine_args, kv_role, name, usage_context)


dis.make_instance = make_instance

_orig_sim_connector = kt.simulated_kv_connector


_STORE_WORKERS = {}


def simulated_kv_connector(vllm_config, kv_cache_config, clock, device_free_at):
    from vllm.distributed.kv_transfer.kv_transfer_state import get_kv_transfer_group
    from vllm.v1.worker.simulated.kv_nixl import SimulatedNixlWorker

    connector = get_kv_transfer_group()
    if type(connector).__name__ == "MultiConnector":
        timing = vllm_config.simulation_config.kv_transfer_timing
        load, store = kt.kv_transfer_rates(timing)
        nixl_worker = None
        for child in connector._connectors:
            if type(child).__name__ == "SimulatedAscendStoreConnector":
                store_worker = kt.SimulatedStoreWorker(clock, load, store)
                child.simulated_transfers = store_worker
                engine_id = vllm_config.kv_transfer_config.engine_id
                _STORE_WORKERS[engine_id] = store_worker
            elif isinstance(getattr(child, "connector_worker", None), SimulatedNixlWorker):
                nixl_worker = child.connector_worker
                nixl_worker.configure(clock, load, kt.kv_post_cost(timing))
        print(f"[PD] multi: nixl={nixl_worker is not None}", flush=True)
        return kt.SimulatedKVConnector(vllm_config, nixl_worker)
    return _orig_sim_connector(vllm_config, kv_cache_config, clock, device_free_at)


kt.simulated_kv_connector = simulated_kv_connector
mr.simulated_kv_connector = simulated_kv_connector

_orig_next_completion = dis.next_transfer_completion


def next_transfer_completion(engine):
    """Composite: the store worker's loads also wake the virtual clock."""
    t = _orig_next_completion(engine)
    engine_id = engine.vllm_config.kv_transfer_config.engine_id
    worker = _STORE_WORKERS.get(engine_id)
    if worker is not None:
        store_t = worker.next_completion()
        if store_t is not None:
            t = min(t, store_t)
    return t


dis.next_transfer_completion = next_transfer_completion


def make_args(connector: str) -> EngineArgs:
    if connector == "multi":
        kv = {
            "kv_connector": "MultiConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "connectors": [
                    {
                        "kv_connector": "NixlConnector",
                        "kv_connector_module_path": "vllm.v1.worker.simulated.kv_nixl",
                        "kv_role": "kv_both",
                    },
                    {
                        "kv_connector": "SimulatedAscendStoreConnector",
                        "kv_role": "kv_both",
                        "kv_connector_extra_config": {
                            "store_backend": "mooncake",
                            "mooncake_master": os.environ.get("MC_MASTER", "mc-master:50051"),
                            "payload_bytes": int(os.environ.get("MC_PAYLOAD", "4096")),
                            "store_gb": float(os.environ.get("STORE_GB", "2")),
                        },
                    },
                ]
            },
        }
    else:
        kv = {"kv_connector": "NixlConnector", "kv_role": "kv_both"}
    return EngineArgs(
        model=MODEL,
        max_model_len=int(os.environ.get("PD_MAXLEN", "4096")),
        kv_cache_memory_bytes=int(os.environ.get("HBM_MB", "2048")) * 1024**2,
        kv_transfer_config=kv,
        simulation_config={
            "simulate_forward": True,
            "timing": "linear",
            "timing_args": {"fixed_us": 1000, "prefill_us_per_token": 10},
            "kv_transfer_timing": {"load_gbps": 10, "store_gbps": 10},
        },
    )


def run(mode: str) -> None:
    params = SamplingParams(max_tokens=8, ignore_eos=True)
    requests = [
        TimedRequest(
            list(range(1000 + (i % PREFIXES) * 4096, 1000 + (i % PREFIXES) * 4096 + PROMPT)),
            params,
            i * GAP,
        )
        for i in range(N)
    ]
    result = dis.simulate_disaggregated(
        make_args(mode), make_args("nixl"), requests, num_prefill=1, num_decode=1
    )
    s = result.summary()
    keys = [k for k in s if "ttft" in k]
    print(mode, " ".join(f"{k}={s[k]:.2f}" for k in keys), flush=True)


if __name__ == "__main__":
    run(os.environ.get("PD_MODE", "multi"))
