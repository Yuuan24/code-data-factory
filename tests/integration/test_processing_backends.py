from __future__ import annotations

from code_data_factory.processing.backends import process_events


def test_local_and_ray_backends_restore_event_order_and_externalize_large_observations() -> None:
    events = [
        {"attempt_id": "a", "seq": 2, "event_type": "OBSERVATION", "payload": "x" * 128},
        {"attempt_id": "a", "seq": 1, "event_type": "TOOL_CALL", "payload": "small"},
        {"attempt_id": "b", "seq": 1, "event_type": "OBSERVATION", "payload": "small"},
    ]

    local = process_events(events, backend="local", observation_inline_limit=32)
    ray = process_events(events, backend="ray", observation_inline_limit=32)

    assert local.rows == ray.rows
    assert [item["seq"] for item in local.rows if item["attempt_id"] == "a"] == [1, 2]
    assert local.rows[1]["payload"] is None
    assert local.rows[1]["payload_ref"] is not None
