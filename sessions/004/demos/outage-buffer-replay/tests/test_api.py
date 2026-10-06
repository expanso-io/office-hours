import os
import time

os.environ["SIMULATOR_ENABLED"] = "false"
from fastapi.testclient import TestClient
from server.main import app, state


def test_assets_mount_serves_web_bundle():
    with TestClient(app) as client:
        response = client.get("/assets/index.html")
    assert response.status_code == 200


def test_offline_sink_returns_real_503_without_success():
    state.reset()
    state.uplink_online = False
    with TestClient(app) as client:
        response = client.post("/api/sink/events", json=state.make_event())
    assert response.status_code == 503
    assert not state.delivered_sequences


def test_snapshot_contract_has_buffer_denominator():
    with TestClient(app) as client:
        snapshot = client.get("/api/snapshot").json()
    assert snapshot["metrics"]["buffer_capacity"] == 10000
    assert snapshot["truth"]["synthetic_source"] is True
    assert snapshot["metrics"]["dropped_total"] is None
    assert snapshot["metrics"]["dropped_state"] == "not_measured_from_edge"


def test_rejected_source_attempts_are_not_claimed_as_dropped_edge_records():
    state.reset()
    state.make_event()
    state.pipeline_rejected = 1
    snapshot = state.snapshot()
    assert snapshot["metrics"]["generated_total"] == 1
    assert snapshot["metrics"]["sent_total"] == 0
    assert snapshot["metrics"]["source_generated_not_accepted_total"] == 1
    assert snapshot["verification"]["state"] == "pending"


def test_cloud_snapshot_does_not_invent_edge_runtime_state(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state.reset()
    snapshot = state.snapshot()
    edge = next(node for node in snapshot["nodes"] if node["id"] == "expanso-edge-buffer")
    assert snapshot["pipeline"]["variant"] == "unverified"
    assert snapshot["pipeline"]["expected_variant"] == "durable-sqlite"
    assert snapshot["pipeline"]["status"] == "unverified"
    assert snapshot["control_plane"]["nodes_running"] is None
    assert edge["state"] == "unverified"
    assert snapshot["edges"][0]["state"] == "unverified"
    assert snapshot["edges"][1]["state"] == "unverified"


def test_cloud_snapshot_labels_receiver_evidence_without_claiming_cloud_health(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state.reset()
    state.last_input_at = "2026-08-19T20:00:00Z"
    state.last_output_at = "2026-08-19T20:00:01Z"
    state.last_output_monotonic = time.monotonic()
    snapshot = state.snapshot()
    edge = next(node for node in snapshot["nodes"] if node["id"] == "expanso-edge-buffer")
    assert snapshot["pipeline"]["status"] == "receiver-observed"
    assert snapshot["pipeline"]["receiver_fresh"] is True
    assert edge["state"] == "receiver-observed"
    assert snapshot["control_plane"]["state"] == "unverified"


def test_cloud_health_never_promotes_edge_to_healthy(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state.reset()
    state.accepted_sequences.add(1)
    with TestClient(app) as client:
        health = client.get("/healthz").json()
    assert health["edge"]["state"] == "unverified"
