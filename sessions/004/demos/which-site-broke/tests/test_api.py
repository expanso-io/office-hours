import os
import time

os.environ["SIMULATOR_ENABLED"] = "false"
from fastapi.testclient import TestClient
from server.main import app, state


def test_assets_mount_serves_web_bundle():
    with TestClient(app) as client:
        response = client.get("/assets/index.html")
    assert response.status_code == 200


def test_snapshot_has_ten_private_nodes():
    state.reset()
    with TestClient(app) as client:
        snapshot = client.get("/api/snapshot").json()
    assert len(snapshot["nodes"]) == 10
    assert [node["id"] for node in snapshot["nodes"]] == [
        f"source-slot-{index:02d}" for index in range(1, 11)
    ]
    assert all(node["identity_state"] == "anonymous" for node in snapshot["nodes"])
    private_keys = {"site_id", "node_id", "asset_id", "region", "app_version"}
    assert all(private_keys.isdisjoint(node) for node in snapshot["nodes"])


def test_baseline_fault_has_no_origin_fields():
    state.reset()
    state.tick = 5
    event = state.make_event(7)
    assert event["level"] == "ERROR"
    assert "source_context" not in event
    assert set(event) == {"event_id", "observed_at", "level", "code", "message"}


def test_pinned_fault_acknowledgements_survive_the_rolling_window():
    state.reset()
    baseline = {
        "event_id": "baseline-fault",
        "observed_at": "2026-08-19T19:59:55Z",
        "level": "ERROR",
        "code": "SENSOR_TIMEOUT",
        "message": "sensor response timed out",
    }
    enriched = {
        "event_id": "enriched-fault",
        "observed_at": "2026-08-19T20:00:00Z",
        "level": "ERROR",
        "code": "SENSOR_TIMEOUT",
        "message": "sensor response timed out",
        "source_context": {
            "site_id": "wind-west",
            "node_id": "edge-07",
            "asset_id": "turbine-07",
            "region": "us-west",
            "app_version": "1.8.3",
            "pipeline_version": "lineage-v2",
        },
    }
    with TestClient(app) as client:
        client.post("/api/sink/events", json=baseline)
        client.post(
            "/api/sink/events",
            json=enriched,
            headers={"X-Demo-Transport-Origin": "edge-07"},
        )
        for index in range(40):
            client.post(
                "/api/sink/events",
                json={
                    "event_id": f"heartbeat-{index}",
                    "observed_at": "2026-08-19T20:00:01Z",
                    "level": "INFO",
                    "code": "HEARTBEAT",
                    "message": "service healthy",
                },
            )
        snapshot = client.get("/api/snapshot").json()

    recent_ids = {item["event_id"] for item in snapshot["evidence"]["acknowledgements"]}
    assert "baseline-fault" not in recent_ids
    assert "enriched-fault" not in recent_ids
    assert snapshot["evidence"]["baseline_acknowledgement"]["event_id"] == "baseline-fault"
    assert snapshot["evidence"]["first_enriched_acknowledgement"]["event_id"] == "enriched-fault"


def test_cloud_enrichment_becomes_active_only_from_receiver_payload(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state.reset()
    baseline = state.snapshot()
    assert baseline["pipeline"]["variant"] == "unverified"
    assert baseline["pipeline"]["status"] == "unverified"
    assert baseline["control_plane"]["nodes_running"] is None
    assert baseline["control_plane"]["nodes_scheduled"] is None
    assert baseline["metrics"]["sites_online"] is None
    assert all(node["health"] == "unverified" for node in baseline["nodes"])
    assert baseline["edges"][0]["state"] == "unverified"
    assert baseline["action"]["enabled"] is False
    event = {
        "event_id": "observed-enrichment",
        "observed_at": "2026-08-19T20:00:00Z",
        "level": "ERROR",
        "code": "SENSOR_TIMEOUT",
        "message": "sensor response timed out",
        "source_context": {
            "site_id": "wind-west",
            "node_id": "edge-07",
            "asset_id": "turbine-07",
            "region": "us-west",
            "app_version": "1.8.3",
            "pipeline_version": "lineage-v2",
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/sink/events",
            json=event,
            headers={"X-Demo-Transport-Origin": "edge-07"},
        )
        snapshot = client.get("/api/snapshot").json()
    assert response.status_code == 200
    assert snapshot["pipeline"]["variant"] == "enriched"
    assert snapshot["control_plane"]["pipeline_revision"] == "lineage-v2"
    observed = next(node for node in snapshot["nodes"] if node["id"] == "source-slot-07")
    assert observed["node_id"] == "edge-07"
    assert observed["app_version"] == "1.8.3"
    assert observed["health"] == "receiver-observed"
    assert snapshot["pipeline"]["status"] == "receiver-observed"
    assert snapshot["pipeline"]["receiver_fresh_nodes"] == 1
    assert snapshot["edges"][0]["state"] == "receiver-observed"
    assert all(
        node["health"] == "unverified"
        for node in snapshot["nodes"]
        if node["id"] != "source-slot-07"
    )
    assert snapshot["verification"]["state"] == "verified"
    assert (
        snapshot["evidence"]["first_enriched_acknowledgement"]["event_id"]
        == snapshot["evidence"]["first_enriched_fault"]["event_id"]
    )


def test_cloud_action_requires_cloud_side_revision(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "cloud")
    state.reset()
    with TestClient(app) as client:
        response = client.post(
            "/api/actions/add-context", headers={"Idempotency-Key": "cloud-action"}
        )
    assert response.status_code == 200
    assert response.json()["accepted"] is False
    assert "Expanso Cloud" in response.json()["reason"]
    assert state.action_phase == "ready"


def test_mismatched_transport_origin_cannot_create_attribution():
    state.reset()
    event = {
        "event_id": "forged-lineage",
        "observed_at": "2026-08-19T20:00:00Z",
        "level": "ERROR",
        "code": "SENSOR_TIMEOUT",
        "message": "sensor response timed out",
        "source_context": {
            "site_id": "wind-west",
            "node_id": "edge-07",
            "asset_id": "turbine-07",
            "region": "us-west",
            "app_version": "1.8.3",
            "pipeline_version": "lineage-v2",
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/sink/events",
            json=event,
            headers={"X-Demo-Transport-Origin": "edge-08"},
        )
        snapshot = client.get("/api/snapshot").json()

    assert response.status_code == 200
    assert snapshot["metrics"]["faults_attributable_total"] == 0
    assert snapshot["evidence"]["first_enriched_fault"] is None
    assert snapshot["evidence"]["context_by_node"] == {}
    assert snapshot["evidence"]["acknowledgements"][0]["origin_check"] is False


def test_local_health_uses_recent_per_node_admission_and_receiver_activity(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    state.reset()
    now = time.monotonic()
    state.last_admitted_monotonic["edge-01"] = now
    state.last_received_monotonic["edge-01"] = now

    snapshot = state.snapshot()

    assert snapshot["pipeline"]["status"] == "degraded"
    assert snapshot["control_plane"]["nodes_running"] == 1
    assert snapshot["metrics"]["sites_online"] == 1
    assert snapshot["nodes"][0]["health"] == "healthy"
    assert all(node["health"] == "starting" for node in snapshot["nodes"][1:])


def test_local_health_becomes_stale_when_all_node_activity_expires(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "local")
    state.reset()
    stale_at = time.monotonic() - 4
    state.last_input_at = "2026-08-19T20:00:00Z"
    state.last_output_at = "2026-08-19T20:00:00Z"
    for node_id in state.expected:
        state.last_admitted_monotonic[node_id] = stale_at
        state.last_received_monotonic[node_id] = stale_at

    snapshot = state.snapshot()

    assert snapshot["pipeline"]["status"] == "stale"
    assert snapshot["pipeline"]["receiver_fresh_nodes"] == 0
    assert snapshot["control_plane"]["nodes_running"] == 0
    assert snapshot["metrics"]["sites_online"] == 0
    assert all(node["health"] == "stale" for node in snapshot["nodes"])
    with TestClient(app) as client:
        health = client.get("/healthz").json()
    assert health["receiver"]["state"] == "stale"
