"""Cockpit for the tiny-models demo.

Reads the records the Expanso Edge pipeline writes to .runtime/enriched.jsonl
and serves them, with per-model timings and model sizes, to one page on
127.0.0.1. Standard library only; started and stopped by scripts/democtl.sh.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
MODEL_KEYS = ("python", "ollama", "direct")
SEVERITIES = ("low", "medium", "high")
RECENT = 30
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".woff2": "font/woff2",
}


def read_records(path: Path) -> list[dict]:
    """Every complete JSON line in the output file, oldest first."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a line still being written
    return records


def current_run(records: list[dict]) -> list[dict]:
    """Records since the last deploy. Each deploy restarts the counter at r-0001."""
    start = 0
    for index, record in enumerate(records):
        if record.get("id") == "r-0001":
            start = index
    return records[start:]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(pct / 100 * len(ordered)) - 1)
    return round(ordered[rank], 1)


def answer_label(key: str, answer: dict) -> str | None:
    if "error" in answer or "unparsed" in answer:
        return None
    if key == "python":
        return "anomaly" if answer.get("anomaly") else "normal"
    if key == "ollama":
        severity = answer.get("severity")
        return severity if severity in SEVERITIES else None
    part = answer.get("part")
    return part if isinstance(part, str) and part else None


def model_stats(run: list[dict]) -> dict:
    stats = {}
    for key in MODEL_KEYS:
        answers = [r[key] for r in run if isinstance(r.get(key), dict)]
        timings = [a["call_ms"] for a in answers if isinstance(a.get("call_ms"), (int, float))]
        counts: dict[str, int] = {}
        failed = 0
        for answer in answers:
            label = answer_label(key, answer)
            if label is None:
                failed += 1
            else:
                counts[label] = counts.get(label, 0) + 1
        stats[key] = {
            "calls": len(answers),
            "failed": failed,
            "first_ms": round(timings[0], 1) if timings else None,
            "p50_ms": percentile(timings, 50),
            "p95_ms": percentile(timings, 95),
            "max_ms": round(max(timings), 1) if timings else None,
            "total_ms": round(sum(timings), 1) if timings else None,
            "answers": dict(sorted(counts.items(), key=lambda item: -item[1])),
        }
    return stats


def http_json(url: str, body: dict | None = None, timeout: float = 2.0):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class ModelInfo:
    """Size and shape of each model, read from the model itself, cached briefly."""

    def __init__(self, env: dict[str, str]):
        self.env = env
        self.cached: dict = {}
        self.fetched = 0.0

    def get(self) -> dict:
        if time.monotonic() - self.fetched > 15:
            self.cached = {
                "python": self.python(),
                "ollama": self.ollama(),
                "direct": self.direct(),
            }
            self.fetched = time.monotonic()
        # Whether the Ollama model is in memory changes second to second.
        self.cached["ollama"]["in_memory_until"] = self.ollama_loaded_until()
        return self.cached

    def python(self) -> dict:
        info = {"name": "IsolationForest", "runtime": "scikit-learn, in a uv Python process"}
        meta_path = Path(self.env.get("OH5_MODELS", "")) / "scorer.json"
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            return info
        info.update(
            bytes=meta.get("bytes"),
            shape=f"{meta.get('trees')} trees, {meta.get('nodes'):,} nodes",
        )
        return info

    def ollama(self) -> dict:
        url = self.env.get("OLLAMA_URL", "")
        name = self.env.get("OLLAMA_MODEL", "")
        info = {"name": name, "runtime": f"Ollama at {url}"}
        try:
            tags = http_json(f"{url}/api/tags")
            for model in tags.get("models", []):
                if name in (model.get("name"), model.get("model")):
                    info["bytes"] = model.get("size")
                    details = model.get("details", {})
                    info["shape"] = (
                        f"{details.get('parameter_size', '?')} parameters, "
                        f"{details.get('quantization_level', '?')}"
                    )
        except (OSError, urllib.error.URLError, ValueError):
            info["unreachable"] = True
        return info

    def ollama_loaded_until(self) -> str | None:
        url = self.env.get("OLLAMA_URL", "")
        name = self.env.get("OLLAMA_MODEL", "")
        try:
            loaded = http_json(f"{url}/api/ps")
        except (OSError, urllib.error.URLError, ValueError):
            return None
        for model in loaded.get("models", []):
            if name in (model.get("name"), model.get("model")):
                return model.get("expires_at")
        return None

    def direct(self) -> dict:
        url = self.env.get("DIRECT_MODEL_URL", "")
        name = self.env.get("DIRECT_MODEL_NAME", "")
        base = url.removesuffix("/chat/completions")
        info = {"name": name, "runtime": f"OpenAI-compatible endpoint {url}"}
        gguf = Path(self.env.get("DIRECT_GGUF", ""))
        if gguf.is_file() and url.startswith("http://127.0.0.1"):
            info["bytes"] = gguf.stat().st_size
            info["file"] = gguf.name
        try:
            models = http_json(f"{base}/models")
            for model in models.get("data", []):
                meta = model.get("meta") or {}
                if model.get("id") == name and meta:
                    info["shape"] = (
                        f"{meta['n_params'] / 1e6:.1f}M parameters, {meta.get('ftype', '')}".strip(
                            ", "
                        )
                    )
        except (OSError, urllib.error.URLError, ValueError, KeyError):
            info["unreachable"] = True
        return info


def build_state(runtime: Path, models: ModelInfo) -> dict:
    records = read_records(runtime / "enriched.jsonl")
    run = current_run(records)

    def read(name: str) -> str | None:
        path = runtime / name
        return path.read_text().strip() if path.exists() else None

    stats = model_stats(run)
    info = models.get()
    merged = {key: {**info.get(key, {}), **stats[key]} for key in MODEL_KEYS}
    return {
        "lane": read("lane"),
        "stage": read("stage"),
        "records_total": len(run),
        "records": list(reversed(run[-RECENT:])),
        "models": merged,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def make_handler(runtime: Path, models: ModelInfo):
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

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/health":
                return self.send(200, b'{"ok": true}', "application/json")
            if path == "/api/state":
                body = json.dumps(build_state(runtime, models)).encode()
                return self.send(200, body, "application/json")
            name = "index.html" if path == "/" else path.lstrip("/")
            target = (WEB / name).resolve()
            if WEB not in target.parents or not target.is_file():
                return self.send(404, b"not found", "text/plain")
            content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            return self.send(200, target.read_bytes(), content_type)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19500)
    args = parser.parse_args()
    runtime = Path(
        os.environ.get("OH5_RUNTIME", Path(__file__).resolve().parent.parent / ".runtime")
    )
    models = ModelInfo(dict(os.environ))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(runtime, models))
    print(f"cockpit on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
