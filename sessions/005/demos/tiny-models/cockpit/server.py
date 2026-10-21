"""Cockpit for the tiny-models demo, on 127.0.0.1 only.

The pipeline's output POSTs every record that leaves the node to /api/sink.
The feed writes what it put in to .runtime/feed.json. This server keeps both
sides' counters, the model timings carried inside the records, and a short
tail, and serves them to one page. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
MODEL_KEYS = ("python", "ollama", "direct")
WINDOW_S = 60
RATE_S = 10
TAIL = 10
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".woff2": "font/woff2",
}


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile, rounded to 0.1."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return round(ordered[rank], 1)


def is_degraded(record: dict) -> bool:
    for key in MODEL_KEYS:
        answer = record.get(key)
        if isinstance(answer, dict) and "error" in answer:
            return True
    return False


class Ledger:
    """Everything the cockpit knows, updated by the sink and a 1 s sampler."""

    def __init__(self, runtime: Path, clock=time.time):
        self.runtime = runtime
        self.clock = clock
        self.lock = threading.Lock()
        self.out_records = 0
        self.out_bytes = 0
        self.degraded = 0
        self.tail: deque[dict] = deque(maxlen=TAIL)
        self.latest_note: dict | None = None
        self.latest_alert: dict | None = None
        self.timings: dict[str, deque] = {key: deque() for key in MODEL_KEYS}
        self.samples: deque[dict] = deque(maxlen=WINDOW_S + 5)

    def sink(self, body: bytes) -> None:
        record = json.loads(body)
        now = self.clock()
        with self.lock:
            self.out_records += 1
            self.out_bytes += len(body)
            self.tail.appendleft(record)
            if is_degraded(record):
                self.degraded += 1
            if record.get("kind") == "note":
                self.latest_note = record
            elif "python" in record:
                self.latest_alert = record
            for key in MODEL_KEYS:
                # Only the record that carried the call counts it. An alert's
                # copy of its last note's answers is not a second call.
                answer = record.get(key)
                if isinstance(answer, dict) and isinstance(answer.get("call_ms"), (int, float)):
                    self.timings[key].append((now, answer["call_ms"]))
            self.trim(now)
        with (self.runtime / "out.jsonl").open("ab") as out:
            out.write(body.rstrip(b"\n") + b"\n")

    def trim(self, now: float) -> None:
        for series in self.timings.values():
            while series and series[0][0] < now - WINDOW_S:
                series.popleft()

    def feed(self) -> dict:
        try:
            return json.loads((self.runtime / "feed.json").read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    def sample(self) -> None:
        feed = self.feed()
        with self.lock:
            self.samples.append(
                {
                    "at": self.clock(),
                    "in": feed.get("admitted", 0),
                    "in_readings": feed.get("admitted_readings", 0),
                    "in_notes": feed.get("admitted_notes", 0),
                    "in_bytes": feed.get("bytes", 0),
                    "out": self.out_records,
                    "out_bytes": self.out_bytes,
                }
            )
            self.trim(self.clock())

    def rates(self) -> dict:
        samples = list(self.samples)
        if len(samples) < 2:
            return {}
        last = samples[-1]
        first = samples[max(0, len(samples) - 1 - RATE_S)]
        span = last["at"] - first["at"] or 1
        window = samples[max(0, len(samples) - 1 - 30)]
        records_in = last["in"] - window["in"]
        records_out = last["out"] - window["out"]
        kept = None
        if records_in > 0:
            kept = round(100 * max(0, records_in - records_out) / records_in, 1)
        return {
            "in_per_s": round((last["in"] - first["in"]) / span, 1),
            "out_per_s": round((last["out"] - first["out"]) / span, 1),
            "in_bytes_per_s": round((last["in_bytes"] - first["in_bytes"]) / span),
            "out_bytes_per_s": round((last["out_bytes"] - first["out_bytes"]) / span),
            "kept_pct": kept,
            "notes_share_pct": round(100 * (last["in_notes"] - window["in_notes"]) / records_in, 1)
            if records_in
            else None,
            "readings_share_pct": round(
                100 * (last["in_readings"] - window["in_readings"]) / records_in, 1
            )
            if records_in
            else None,
        }

    def dead_letters(self) -> int:
        path = self.runtime / "dead-letter.jsonl"
        try:
            with path.open("rb") as handle:
                return sum(1 for _ in handle)
        except OSError:
            return 0

    def snapshot(self) -> dict:
        feed = self.feed()
        with self.lock:
            timings = {key: [ms for _, ms in series] for key, series in self.timings.items()}
            state = {
                "records_in": feed.get("admitted", 0),
                "bytes_in": feed.get("bytes", 0),
                "refused_in": feed.get("refused", 0),
                "feed_rate": feed.get("rate"),
                "records_out": self.out_records,
                "bytes_out": self.out_bytes,
                "degraded": self.degraded,
                "tail": list(self.tail),
                "latest_note": self.latest_note,
                "latest_alert": self.latest_alert,
            }
        state["rates"] = self.rates()
        state["dead_letters"] = self.dead_letters()
        state["timings"] = {
            key: {
                "calls": len(values),
                "p50_ms": percentile(values, 50),
                "p95_ms": percentile(values, 95),
            }
            for key, values in timings.items()
        }
        return state


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def ollama_in_memory(url: str, name: str) -> bool | None:
    try:
        with urllib.request.urlopen(f"{url}/api/ps", timeout=1) as response:
            loaded = json.load(response)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    return any(name in (m.get("name"), m.get("model")) for m in loaded.get("models", []))


def build_state(ledger: Ledger, models_dir: Path, env: dict[str, str]) -> dict:
    state = ledger.snapshot()
    state["job"] = read_json(ledger.runtime / "job.json")
    manifest = read_json(models_dir / "manifest.json")
    rates = state["rates"]
    share = {
        "python": rates.get("readings_share_pct"),
        "ollama": rates.get("notes_share_pct"),
        "direct": rates.get("notes_share_pct"),
    }
    models = {}
    for key in MODEL_KEYS:
        timing = state["timings"][key]
        models[key] = {
            **manifest.get(key, {}),
            **timing,
            "share_pct": share[key] if timing["calls"] else None,
        }
    models["ollama"]["in_memory"] = ollama_in_memory(
        env.get("OLLAMA_URL", "http://127.0.0.1:11434"), env.get("OLLAMA_MODEL", "")
    )
    state["models"] = models
    del state["timings"]
    return state


def make_handler(ledger: Ledger, models_dir: Path, env: dict[str, str]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/sink":
                return self.send(404, b"not found", "text/plain")
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                ledger.sink(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self.send(400, b"not json", "text/plain")
            return self.send(200, b"ok", "text/plain")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/health":
                return self.send(200, b'{"ok": true}', "application/json")
            if path == "/api/state":
                body = json.dumps(build_state(ledger, models_dir, env)).encode()
                return self.send(200, body, "application/json")
            name = "index.html" if path == "/" else path.lstrip("/")
            target = (WEB / name).resolve()
            if WEB not in target.parents or not target.is_file():
                return self.send(404, b"not found", "text/plain")
            content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            return self.send(200, target.read_bytes(), content_type)

    return Handler


def sampler(ledger: Ledger, stop: threading.Event) -> None:
    while not stop.wait(1.0):
        ledger.sample()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19500)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent.parent
    runtime = Path(os.environ.get("OH5_RUNTIME", here / ".runtime"))
    models_dir = Path(os.environ.get("OH5_MODELS", here / ".models"))
    runtime.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(runtime)
    stop = threading.Event()
    threading.Thread(target=sampler, args=(ledger, stop), daemon=True).start()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), make_handler(ledger, models_dir, dict(os.environ))
    )
    print(f"cockpit on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
