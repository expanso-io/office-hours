# /// script
# requires-python = ">=3.11"
# ///

"""Run one Expanso Bench scenario through Expanso Cloud and print the ladder.

The harness lives in the pinned submodule at vendor/benchmarking. Its `run`
subcommand only knows local mode, so this helper drives `expanso-bench serve`
instead: serve enrols this machine as a `bench-*` node in the workspace, deploys
every benchmark as a Cloud job, and exposes a JSON API on localhost. The presenter
UI stays on 127.0.0.1 and is stopped when the run finishes. Credentials are read
from the same ignored .env the rehearsal helper uses; EXPANSO_BOOTSTRAP_TOKEN is
needed the first time so the bench node can enrol.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SUBMODULE = REPO / "vendor" / "benchmarking"
BINARY = REPO / ".runtime" / "bin" / "expanso-bench"


def load_env():
    values = {}
    for env_file in (ROOT / ".env", REPO / ".env"):
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    values.setdefault(key.strip(), value.strip())
            break
    env = dict(os.environ)
    for key in ("EXPANSO_ENDPOINT", "EXPANSO_API_KEY", "EXPANSO_BOOTSTRAP_TOKEN"):
        env.setdefault(key, values.get(key, ""))
    if not env["EXPANSO_ENDPOINT"] or not env["EXPANSO_API_KEY"]:
        raise SystemExit(
            "Expanso Cloud credentials missing: EXPANSO_ENDPOINT and EXPANSO_API_KEY "
            "(ignored .env or environment). Benchmarks run through Cloud only."
        )
    return env


def binary():
    if BINARY.is_file():
        return BINARY
    if not (SUBMODULE / "go.mod").is_file():
        raise SystemExit(
            "vendor/benchmarking is empty. Run: git submodule update --init --recursive"
        )
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    print("Building expanso-bench from the pinned submodule...")
    subprocess.run(
        ["go", "build", "-o", str(BINARY), "./cmd/expanso-bench"],
        cwd=SUBMODULE,
        check=True,
    )
    return BINARY


def api(base, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method="POST" if data else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", nargs="?", default="passthrough")
    parser.add_argument("--ladder", default="1000,5000")
    parser.add_argument("--step-seconds", type=int, default=3)
    parser.add_argument("--batch", type=int, default=None)
    parser.add_argument("--label", default="office hours session 002")
    args = parser.parse_args()

    env = load_env()
    bench = binary()
    data_dir = ROOT / ".runtime" / "bench"
    data_dir.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    log_path = data_dir / "serve.log"
    with log_path.open("a") as log:
        proc = subprocess.Popen(
            [
                str(bench),
                "serve",
                "--addr",
                f"127.0.0.1:{port}",
                "--data-dir",
                str(data_dir),
            ],
            stdout=log,
            stderr=log,
            env=env,
        )
        try:
            status = None
            for _ in range(720):
                if proc.poll() is not None:
                    raise SystemExit(f"expanso-bench serve exited; see {log_path}")
                try:
                    status = api(base, "/api/status")
                    if status.get("mode") == "cloud" and status.get("node"):
                        break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    pass
                time.sleep(0.5)
            else:
                raise SystemExit(f"Bench node never reached Cloud mode; see {log_path}")
            if status.get("mode") != "cloud":
                raise SystemExit(
                    f"Refusing to benchmark in {status.get('mode')} mode: {status.get('mode_note')}"
                )
            node = status["node"]
            print(
                f"Cloud bench node: {node['name']} {node['id']} (edge {node['version']})"
            )
            print(status["mode_note"])

            request = {
                "scenario": args.scenario,
                "ladder": [int(x) for x in args.ladder.split(",")],
                "step_seconds": args.step_seconds,
                "label": args.label,
            }
            if args.batch is not None:
                request["batch"] = args.batch
            submitted = api(base, "/api/runs", request)
            run_id = submitted["id"]
            print(f"Submitted run {run_id}; estimated {submitted['estimate_seconds']}s")

            result = None
            deadline = time.time() + 60 + submitted["estimate_seconds"] * 3
            while time.time() < deadline:
                answer = api(base, f"/api/runs/{run_id}")
                if answer.get("result"):
                    result = answer["result"]
                    break
                time.sleep(1)
            if result is None:
                raise SystemExit(f"Run {run_id} did not finish in time; see {log_path}")

            saved = data_dir / "results" / f"{run_id}.json"
            print()
            print(
                f"Scenario : {result['scenario']['name']} ({result['scenario']['id']})"
            )
            print(f"Mode     : {result['mode']} on node {result.get('node_id', '')}")
            print(f"Edge     : {result['edge'].get('version', '')}")
            print("TARGET/s  PROCESSED/s  RATIO  EDGE CPU  RSS MB  DROPPED  RESULT")
            for step in result["steps"]:
                print(
                    f"{step['target_rate']:<9} {step['process_rate']:<12.0f} "
                    f"{step['ratio'] * 100:>4.0f}%  {step['edge_cpu_avg']:>7.0f}%  "
                    f"{step['edge_rss_max'] / 1e6:>6.0f}  {step['dropped']:>7}  "
                    f"{'pass' if step['passed'] else 'FAIL'}"
                )
            print()
            print(result["summary"])
            print(f"saved {saved}")
            if result["status"] != "completed":
                print(f"Run status: {result['status']} {result.get('error', '')}")
                sys.exit(1)
            if result["mode"] != "cloud":
                sys.exit(
                    "Result was not produced through Cloud; refusing to call it a pass."
                )
            print(
                f"PASS {args.scenario}: every rung ran as a Cloud job on the bench node"
            )
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            print("Bench server and node stopped:", proc.returncode)


if __name__ == "__main__":
    main()
