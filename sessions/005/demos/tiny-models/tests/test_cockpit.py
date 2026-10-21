import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from cockpit import server


def test_percentile_uses_nearest_rank():
    assert server.percentile([], 50) is None
    assert server.percentile([5.0, 1.0, 3.0], 50) == 3.0
    assert server.percentile([float(v) for v in range(1, 101)], 95) == 95.0


def test_is_degraded_detects_direct_and_joined_note_errors():
    assert (
        server.is_degraded({"kind": "reading", "python": {"anomaly": True, "score": 0.7}}) is False
    )
    assert server.is_degraded({"kind": "note", "direct": {"error": "connection refused"}}) is True
    assert (
        server.is_degraded(
            {
                "kind": "reading",
                "python": {"anomaly": True, "score": 0.7},
                "last_note": {"direct": {"error": "connection refused"}},
            }
        )
        is True
    )


def test_ledger_tracks_sink_records_rates_and_60s_timing_window(tmp_path):
    now = [100.0]
    ledger = server.Ledger(tmp_path, clock=lambda: now[0])
    (tmp_path / "feed.json").write_text(
        json.dumps(
            {
                "admitted": 0,
                "admitted_readings": 0,
                "admitted_notes": 0,
                "bytes": 0,
                "refused": 0,
                "rate": 20.0,
            }
        )
    )
    ledger.tick()

    now[0] = 110.0
    (tmp_path / "feed.json").write_text(
        json.dumps(
            {
                "admitted": 200,
                "admitted_readings": 198,
                "admitted_notes": 2,
                "bytes": 20_000,
                "refused": 0,
                "rate": 20.0,
            }
        )
    )
    note = {
        "kind": "note",
        "asset": "pump-03",
        "text": "Drive end bearing running hot and getting noisier.",
        "ollama": {"part": "bearing", "symptom": "hot and noisy", "call_ms": 62.4},
        "direct": {"part": "bearing", "call_ms": 94.2},
    }
    alert = {
        "kind": "reading",
        "asset": "pump-03",
        "temp_c": 80.5,
        "vibration_mm_s": 6.1,
        "current_a": 18.2,
        "python": {"anomaly": True, "score": 0.68, "call_ms": 1.4},
        "last_note": {
            "text": note["text"],
            "ollama": note["ollama"],
            "direct": note["direct"],
        },
    }
    ledger.sink(json.dumps(note).encode())
    ledger.sink(json.dumps(alert).encode())
    ledger.tick()

    snap = ledger.snapshot()
    assert snap["records_in"] == 200
    assert snap["records_out"] == 2
    assert snap["degraded"] == 0
    assert snap["latest_note"]["asset"] == "pump-03"
    assert snap["latest_alert"]["python"]["anomaly"] is True
    # The alert's copy of last_note does not double-count the LLM calls.
    assert snap["timings"]["python"]["calls"] == 1
    assert snap["timings"]["ollama"]["calls"] == 1
    assert snap["timings"]["direct"]["calls"] == 1
    assert snap["rates"]["in_per_s"] == 20.0
    assert snap["rates"]["out_per_s"] == 0.2
    assert snap["rates"]["kept_pct"] == 99.0


@pytest.fixture
def cockpit_url(tmp_path):
    runtime = tmp_path / "runtime"
    models = tmp_path / "models"
    runtime.mkdir()
    models.mkdir()
    (runtime / "job.json").write_text(
        json.dumps(
            {"name": "office-hours-005-models", "lane": "local", "version": 3, "state": "running"}
        )
    )
    (models / "manifest.json").write_text(
        json.dumps(
            {
                "python": {"name": "IsolationForest", "wiring": "subprocess", "bytes": 63430},
                "ollama": {"name": "qwen2.5:0.5b", "wiring": "ollama_chat", "bytes": 397821319},
                "direct": {"name": "smollm2-360m", "wiring": "http", "bytes": 386404992},
            }
        )
    )
    ledger = server.Ledger(runtime)
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        server.make_handler(
            ledger, models, {"OLLAMA_URL": "http://127.0.0.1:9", "OLLAMA_MODEL": "qwen2.5:0.5b"}
        ),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_http_sink_and_state_endpoints(cockpit_url):
    record = {
        "kind": "reading",
        "asset": "pump-03",
        "temp_c": 81.0,
        "vibration_mm_s": 6.2,
        "current_a": 18.0,
        "python": {"anomaly": True, "score": 0.71, "call_ms": 1.5},
    }
    req = urllib.request.Request(
        f"{cockpit_url}/api/sink",
        data=json.dumps(record).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        assert response.status == 200

    with urllib.request.urlopen(f"{cockpit_url}/api/state") as response:
        state = json.load(response)
    assert state["job"]["version"] == 3
    assert state["records_out"] == 1
    assert state["tail"][0]["asset"] == "pump-03"
    assert state["models"]["python"]["calls"] == 1
    assert state["models"]["python"]["bytes"] == 63430
    assert state["models"]["direct"]["bytes"] == 386404992


def test_static_files_are_served_and_nothing_outside_web(cockpit_url):
    with urllib.request.urlopen(f"{cockpit_url}/") as response:
        assert b"Three tiny models, one stream" in response.read()
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f"{cockpit_url}/../server.py")
    assert excinfo.value.code == 404
