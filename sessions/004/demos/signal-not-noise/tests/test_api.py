import os

os.environ["SIMULATOR_ENABLED"] = "false"

from fastapi.testclient import TestClient

from server.main import app, state


def test_health_and_snapshot_contract():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["ok"] is True
        snap = client.get("/api/snapshot").json()
        assert snap["schema_version"] == "1.0"
        assert snap["truth"]["synthetic_source"] is True


def test_assets_mount_serves_web_bundle():
    with TestClient(app) as client:
        response = client.get("/assets/index.html")
    assert response.status_code == 200


def test_sink_ack_is_measured():
    state.reset()
    with TestClient(app) as client:
        event, _ = state.make_event("incident-test")
        response = client.post("/api/sink/logs", json=event)
        assert response.status_code == 200
        assert state.downstream_acked == 1
        assert state.incident_status["incident-test"]["delivered"] is True


def test_selected_incident_evidence_stays_pinned_after_routine_traffic():
    state.reset()
    state.verification_incident = "incident-selected"
    incident, _ = state.make_event("incident-selected")
    routine, _ = state.make_event()
    with TestClient(app) as client:
        assert client.post("/api/sink/logs", json=incident).status_code == 200
        assert client.post("/api/sink/logs", json=routine).status_code == 200
        snapshot = client.get("/api/snapshot").json()
    assert snapshot["evidence"]["verification_event"]["event_id"] == "incident-selected"
    assert snapshot["evidence"]["verification_event"]["code"] == "COMPRESSOR_OVERHEAT"
    assert snapshot["evidence"]["verification_acknowledgement"]["event_id"] == "incident-selected"
    assert snapshot["evidence"]["payloads"][0]["event_id"] == "incident-selected"
    assert snapshot["evidence"]["acknowledgements"][0]["event_id"] == "incident-selected"


def test_ingress_rates_exclude_generated_but_rejected_bytes(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    state.reset()
    _, body = state.make_event()
    snapshot = state.snapshot()
    assert snapshot["metrics"]["generated_bytes_total"] == len(body)
    assert snapshot["metrics"]["raw_bytes_total"] == 0
    assert snapshot["pipeline"]["last_input_at"] is None


def test_cloud_snapshot_never_invents_runtime_or_revision(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state.reset()
    snapshot = state.snapshot()
    assert snapshot["control_plane"]["state"] == "unverified"
    assert snapshot["control_plane"]["nodes_running"] is None
    assert snapshot["control_plane"]["nodes_scheduled"] is None
    assert snapshot["pipeline_revision"] is None
    assert snapshot["pipeline"]["status"] == "unverified"
    assert snapshot["pipeline"]["receiver_fresh"] is False
    assert [node["id"] for node in snapshot["nodes"]] == [
        "compressor-service",
        "expanso-edge",
    ]
    assert all(node["state"] == "unverified" for node in snapshot["nodes"])
    assert all(edge["state"] == "unverified" for edge in snapshot["edges"])


def test_filtered_incident_endpoint_selects_exact_verification_event(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    monkeypatch.setenv("DEMO_VARIANT", "filtered")
    state.reset()
    with TestClient(app) as client:
        event_id = client.post("/api/control/incident").json()["event_id"]
    assert state.verification_incident == event_id
