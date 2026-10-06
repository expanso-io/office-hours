import time

from server.main import DemoState, VERIFICATION_INCIDENT_CODE, VERIFICATION_INCIDENT_MESSAGE


def test_distribution_is_exact_over_one_hundred_events():
    state = DemoState()
    levels = [state.make_event()[0]["level"] for _ in range(100)]
    assert levels.count("DEBUG") == 70
    assert levels.count("INFO") == 24
    assert levels.count("WARN") == 5
    assert levels.count("ERROR") == 1


def test_event_ids_are_opaque_and_unique():
    state = DemoState()
    ids = [state.make_event()[0]["event_id"] for _ in range(100)]
    assert len(set(ids)) == 100
    assert all(len(event_id) == 16 for event_id in ids)


def test_forced_incident_has_exact_code_and_message():
    state = DemoState()
    event, _ = state.make_event("incident-proof")
    assert event["level"] == "ERROR"
    assert event["code"] == VERIFICATION_INCIDENT_CODE
    assert event["message"] == VERIFICATION_INCIDENT_MESSAGE
    assert state.incident_status["incident-proof"]["emitted_code"] == VERIFICATION_INCIDENT_CODE


def test_filter_observation_requires_full_accepted_window_and_receiver_reduction():
    state = DemoState()
    now = time.monotonic()
    state.pipeline_accepted = 300
    state.pipeline_accepted_bytes = 30000
    state.accepted_window.extend([(now - 4.7, 15000), (now, 15000)])
    state.delivered_window.extend([(now - 4.7, 1000), (now, 1000)])
    state.incident_status["incident-proof"] = {
        "accepted": True,
        "accepted_code": VERIFICATION_INCIDENT_CODE,
        "delivered": True,
        "delivered_code": VERIFICATION_INCIDENT_CODE,
    }
    state.verification_incident = "incident-proof"
    snapshot = state.snapshot()
    assert snapshot["filter_observation"]["observed"] is True
    assert snapshot["verification"]["state"] == "verified"
    assert snapshot["metrics"]["byte_reduction_denominator"] == 30000


def test_verified_incident_must_match_selected_verification_event():
    state = DemoState()
    now = time.monotonic()
    state.pipeline_accepted = 300
    state.pipeline_accepted_bytes = 30000
    state.accepted_window.extend([(now - 4.7, 15000), (now, 15000)])
    state.delivered_window.extend([(now - 4.7, 1000), (now, 1000)])
    state.incident_status["old-incident"] = {
        "accepted": True,
        "accepted_code": VERIFICATION_INCIDENT_CODE,
        "delivered": True,
        "delivered_code": VERIFICATION_INCIDENT_CODE,
    }
    state.incident_status["selected-incident"] = {
        "accepted": True,
        "accepted_code": VERIFICATION_INCIDENT_CODE,
        "delivered": False,
        "delivered_code": None,
    }
    state.verification_incident = "selected-incident"
    snapshot = state.snapshot()
    assert snapshot["verification"]["state"] == "pending"
    exact_assertion = next(
        assertion
        for assertion in snapshot["verification"]["assertions"]
        if assertion["name"] == "exact_accepted_incident_delivered"
    )
    assert exact_assertion["passed"] is False


def test_verified_incident_requires_exact_code_at_admission_and_receiver():
    state = DemoState()
    now = time.monotonic()
    state.pipeline_accepted = 300
    state.pipeline_accepted_bytes = 30000
    state.accepted_window.extend([(now - 4.7, 15000), (now, 15000)])
    state.delivered_window.extend([(now - 4.7, 1000), (now, 1000)])
    state.incident_status["incident-wrong-code"] = {
        "accepted": True,
        "accepted_code": VERIFICATION_INCIDENT_CODE,
        "delivered": True,
        "delivered_code": "DATABASE_POOL_EXHAUSTED",
    }
    state.verification_incident = "incident-wrong-code"
    snapshot = state.snapshot()
    assert snapshot["verification"]["state"] == "pending"
    assertions = {
        assertion["name"]: assertion["passed"]
        for assertion in snapshot["verification"]["assertions"]
    }
    assert assertions["selected_incident_exact_code"] is False
    assert assertions["exact_accepted_incident_delivered"] is False


def test_cloud_observation_queues_post_observation_incident(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state = DemoState()
    now = time.monotonic()
    state.pipeline_accepted = 300
    state.pipeline_accepted_bytes = 30000
    state.accepted_window.extend([(now - 4.7, 15000), (now, 15000)])
    state.delivered_window.extend([(now - 4.7, 1000), (now, 1000)])
    snapshot = state.snapshot()
    assert snapshot["filter_observation"]["observed"] is True
    assert snapshot["verification"]["state"] == "pending"
    assert state.verification_incident in state.pending_incidents
    assert snapshot["action"]["enabled"] is False


def test_local_filtered_incident_waits_for_observed_filter_window(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    monkeypatch.setenv("DEMO_VARIANT", "filtered")
    state = DemoState()

    state.snapshot()
    assert state.verification_incident is None
    assert not state.pending_incidents

    now = time.monotonic()
    state.pipeline_accepted = 300
    state.pipeline_accepted_bytes = 30000
    state.accepted_window.extend([(now - 4.7, 15000), (now, 15000)])
    state.delivered_window.extend([(now - 4.7, 1000), (now, 1000)])
    snapshot = state.snapshot()

    assert snapshot["filter_observation"]["observed"] is True
    assert state.verification_incident in state.pending_incidents
    assert snapshot["verification"]["state"] == "pending"


def test_local_runtime_health_becomes_stale_without_recent_activity(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    state = DemoState()
    stale_at = time.monotonic() - 4
    state.generated_window.append((stale_at, 100))
    state.accepted_window.append((stale_at, 100))
    state.delivered_window.append((stale_at, 100))
    state.last_generated_at = "2026-08-19T20:00:00Z"
    state.last_input_at = "2026-08-19T20:00:00Z"
    state.last_output_at = "2026-08-19T20:00:00Z"

    snapshot = state.snapshot()

    assert snapshot["pipeline"]["status"] == "stale"
    assert snapshot["control_plane"]["nodes_running"] == 0
    assert snapshot["nodes"][0]["state"] == "stale"
    assert snapshot["nodes"][1]["state"] == "stale"
    assert all(edge["state"] == "stale" for edge in snapshot["edges"])


def test_local_edge_is_not_healthy_without_recent_receiver_activity(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    state = DemoState()
    now = time.monotonic()
    state.generated_window.append((now, 100))
    state.accepted_window.append((now, 100))
    state.last_generated_at = "2026-08-19T20:00:00Z"
    state.last_input_at = "2026-08-19T20:00:00Z"

    snapshot = state.snapshot()

    assert snapshot["pipeline"]["status"] == "running"
    assert snapshot["control_plane"]["nodes_running"] == 0
    assert snapshot["nodes"][1]["state"] == "stale"
    assert snapshot["edges"][1]["state"] == "stale"
