"""Unit tests for the layerwise shared-buffer hook ordering.

These do not start an engine: they pin the connector contract that the full
CPU run depends on.  The key invariant is that historical KV is loaded BEFORE
the layer's KV update writes the new tokens.
"""

import torch

from layerwise_shared_buffer_connector import (
    LayerwiseSharedBufferConnector,
    Metadata,
    RequestMeta,
)


def make_connector():
    conn = LayerwiseSharedBufferConnector.__new__(LayerwiseSharedBufferConnector)
    conn._pending = {}
    conn._store = {}
    conn._kv_caches = {}
    conn._current_key = None
    conn._loaded = set()
    conn._mooncake = None
    conn._versions = {}
    conn._latest = {}
    conn._checksums = {}
    conn._saved_ptrs = {}
    conn._saved_shapes = {}
    conn._connector_metadata = None
    return conn


def make_tensor(blocks=4, heads=2, block_size=8, dim=4):
    return torch.zeros(blocks, heads, block_size, dim)


def write_tokens(tensor, slots, value):
    for slot in slots:
        block, offset = divmod(slot, tensor.shape[2])
        tensor[block, :, offset, :] = value


def bind(conn, request_id="req-0"):
    conn.bind_connector_metadata(Metadata((RequestMeta(request_id),)))


def test_bind_sets_key_before_forward():
    conn = make_connector()
    assert conn._current_key is None
    bind(conn, "req-42")
    assert conn._current_key == "req-42"


def test_prefill_zero_then_update_then_save():
    conn = make_connector()
    tensor = make_tensor()
    conn._kv_caches["layer.0"] = tensor
    bind(conn)

    # New order: load (zero, no history) happens before the KV update.
    conn.wait_for_layer_load("layer.0")
    assert torch.count_nonzero(tensor) == 0
    write_tokens(tensor, [9, 10], 1.5)

    conn.save_kv_layer("layer.0", tensor, None)
    key = next(iter(conn._store))
    assert torch.equal(conn._store[key], tensor)


def test_decode_old_order_loses_new_token():
    """Documents the original bug: update before load clobbers the new KV."""
    conn = make_connector()
    history = make_tensor()
    write_tokens(history, [1, 2], 7.0)
    conn._kv_caches["layer.0"] = history
    bind(conn)
    conn.save_kv_layer("layer.0", history, None)  # prefill saved

    tensor = make_tensor()
    conn._kv_caches["layer.0"] = tensor
    bind(conn)  # decode step
    write_tokens(tensor, [3], 9.0)  # KV update first
    conn.wait_for_layer_load("layer.0")  # then history load

    # New token row is gone: the load overwrote it.
    assert tensor[0, :, 3, :].abs().sum() == 0


def test_decode_new_order_keeps_new_token():
    conn = make_connector()
    history = make_tensor()
    write_tokens(history, [1, 2], 7.0)
    conn._kv_caches["layer.0"] = history
    bind(conn)
    conn.save_kv_layer("layer.0", history, None)

    tensor = make_tensor()
    conn._kv_caches["layer.0"] = tensor
    bind(conn)
    conn.wait_for_layer_load("layer.0")  # history first
    write_tokens(tensor, [3], 9.0)  # then the KV update

    assert torch.equal(tensor[0, :, 1, :], torch.full_like(tensor[0, :, 1, :], 7.0))
    assert torch.equal(tensor[0, :, 3, :], torch.full_like(tensor[0, :, 3, :], 9.0))


def test_wait_is_deduplicated_per_step():
    conn = make_connector()
    tensor = make_tensor()
    conn._kv_caches["layer.0"] = tensor
    history = make_tensor()
    write_tokens(history, [1], 3.0)
    conn._kv_caches["layer.1"] = history
    bind(conn)
    conn.save_kv_layer("layer.1", history, None)

    conn.wait_for_layer_load("layer.1")
    first = tensor.clone()
    tensor.zero_()  # simulate an update between the two hook calls
    conn.wait_for_layer_load("layer.1")
    # Deduplicated: the second call must not reload (and thus not re-zero).
    assert torch.count_nonzero(tensor) == 0, (first, tensor)


def test_save_without_bind_is_skipped():
    conn = make_connector()
    tensor = make_tensor()
    conn._kv_caches["layer.0"] = tensor
    conn.save_kv_layer("layer.0", tensor, None)
    assert not conn._store


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print("FAIL", name, type(exc).__name__, exc)
    print("RESULT", "ALL PASS" if failures == 0 else f"{failures} FAILED")
    raise SystemExit(1 if failures else 0)
