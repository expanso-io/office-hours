import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from cockpit import server


def record(n, **models):
    return {"id": f"r-{n:04d}", "asset": "pump-01", "note": "x", **models}


def test_current_run_starts_at_the_last_counter_reset():
    records = [record(1), record(2), record(1), record(2), record(3)]
    run = server.current_run(records)
    assert [r["id"] for r in run] == ["r-0001", "r-0002", "r-0003"]


def test_percentile_uses_nearest_rank():
    assert server.percentile([], 50) is None
    assert server.percentile([5.0, 1.0, 3.0], 50) == 3.0
    assert server.percentile([float(v) for v in range(1, 101)], 95) == 95.0


def test_stats_count_answers_failures_and_off_format_replies():
    run = [
        record(
            1,
            python={"anomaly": True, "score": 0.7, "call_ms": 200.0},
            ollama={"severity": "high", "call_ms": 5000.0},
            direct={"part": "motor", "call_ms": 90.0},
        ),
        record(
            2,
            python={"anomaly": False, "score": 0.4, "call_ms": 2.0},
            ollama={"high}": "medium", "call_ms": 40.0},
            direct={"error": "connection refused"},
        ),
        record(3, python={"anomaly": False, "score": 0.4, "call_ms": 2.0}),
    ]
    stats = server.model_stats(run)
    assert stats["python"]["calls"] == 3
    assert stats["python"]["answers"] == {"normal": 2, "anomaly": 1}
    assert stats["python"]["first_ms"] == 200.0
    assert stats["python"]["p50_ms"] == 2.0
    assert stats["ollama"]["calls"] == 2
    assert stats["ollama"]["failed"] == 1
    assert stats["ollama"]["answers"] == {"high": 1}
    assert stats["direct"]["failed"] == 1
    assert stats["direct"]["max_ms"] == 90.0


class StubModels:
    def get(self):
        return {"python": {"bytes": 1}, "ollama": {"bytes": 2}, "direct": {"bytes": 3}}


@pytest.fixture
def cockpit(tmp_path):
    lines = [
        json.dumps(record(n, python={"anomaly": False, "score": 0.4, "call_ms": 1.0}))
        for n in (1, 2)
    ]
    (tmp_path / "enriched.jsonl").write_text("\n".join(lines) + '\n{"partial')
    (tmp_path / "lane").write_text("local\n")
    (tmp_path / "stage").write_text("1\n")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(tmp_path, StubModels()))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_state_endpoint_serves_newest_first_and_skips_partial_lines(cockpit):
    with urllib.request.urlopen(f"{cockpit}/api/state") as response:
        state = json.load(response)
    assert state["lane"] == "local"
    assert state["stage"] == "1"
    assert state["records_total"] == 2
    assert [r["id"] for r in state["records"]] == ["r-0002", "r-0001"]
    assert state["models"]["python"]["calls"] == 2
    assert state["models"]["direct"]["bytes"] == 3


def test_static_files_are_served_and_nothing_outside_web(cockpit):
    with urllib.request.urlopen(f"{cockpit}/") as response:
        assert b"Three tiny models, one stream" in response.read()
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f"{cockpit}/../server.py")
    assert excinfo.value.code == 404
