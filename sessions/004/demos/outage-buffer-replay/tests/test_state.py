import time

from server.main import DemoState


def test_audit_is_receiver_derived():
    state = DemoState()
    state.accepted_sequences.update({1, 2, 3})
    state.delivered_sequences.update({1, 3})
    state.delivery_counts.update({1: 1, 3: 2})
    assert state.audit() == ([2], [3])


def test_event_sequence_is_monotonic_and_deterministic_shape():
    state = DemoState()
    first = state.make_event()
    second = state.make_event()
    assert (first["sequence"], second["sequence"]) == (1, 2)
    assert first["stream_id"] == "remote-substation-a"


def test_restore_freezes_audit_high_water_and_exact_replay_backlog():
    state = DemoState()
    state.accepted_sequences.update({1, 2, 3, 4, 5})
    state.delivered_sequences.update({1, 2})
    state.restore_uplink()
    assert state.audit_high_water == 5
    assert state.backlog_at_restore == {3, 4, 5}

    state.accepted_sequences.update({6, 7})
    state.delivered_sequences.update({3, 4, 5, 6, 7})
    state.delivery_counts.update({6: 2})
    snapshot = state.snapshot()

    assert snapshot["metrics"]["replayed_total"] == 3
    assert snapshot["metrics"]["audit_high_water"] == 5
    assert snapshot["metrics"]["missing_accepted_sequences"] == 0
    assert snapshot["metrics"]["duplicate_successful_deliveries"] == 0
    assert snapshot["evidence"]["backlog_at_restore_sequence_ids"] == [3, 4, 5]


def test_local_pipeline_health_expires_without_recent_admission(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    state = DemoState()
    stale_at = time.monotonic() - 4
    state.last_input_at = "2026-08-19T20:00:00Z"
    state.last_input_monotonic = stale_at
    state.last_output_at = "2026-08-19T20:00:00Z"
    state.last_output_monotonic = stale_at

    snapshot = state.snapshot()

    assert snapshot["pipeline"]["status"] == "stale"
    assert snapshot["control_plane"]["nodes_running"] == 0
    edge = next(node for node in snapshot["nodes"] if node["id"] == "expanso-edge-buffer")
    assert edge["state"] == "stale"
