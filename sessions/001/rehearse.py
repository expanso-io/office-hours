# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0,<7"]
# ///

"""Run a finite feed through an isolated local Expanso Edge, then stop it."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["csv"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    runtime = root / ".runtime"
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=args.mode + "-", dir=runtime))
    feed = work / "input"
    output = work / "received.jsonl"
    with feed.open("wb") as target:
        subprocess.run(
            ["uv", "run", str(root / "simulate.py"), args.mode],
            cwd=root,
            stdout=target,
            check=True,
        )
    with feed.open("ab") as target:
        target.write(b"malformed,record\n")
    pipeline = root / "sensor.yaml"
    config = yaml.safe_load(
        pipeline.read_text()
        .replace("${FEED_FILE}", str(feed))
        .replace("${OUTPUT_FILE}", str(output))
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}/api/v1"
    # Keep all configuration and credentials isolated from the user's Cloud agent.
    env = {k: v for k, v in os.environ.items() if not k.startswith("EXPANSO_")}
    with (work / "edge.log").open("w") as log:
        proc = subprocess.Popen(
            [
                "expanso-edge",
                "run",
                "--local",
                "--no-watch",
                "--data-dir",
                str(work / "edge"),
                "--api-listen",
                f"127.0.0.1:{port}",
            ],
            stdout=log,
            stderr=log,
            env=env,
        )
        try:
            for _ in range(120):
                if proc.poll() is not None:
                    raise RuntimeError(f"Edge exited; inspect {work / 'edge.log'}")
                try:
                    with urllib.request.urlopen(base + "/health", timeout=1):
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.25)
            else:
                raise RuntimeError("Local Edge health timeout")
            body = json.dumps(
                {
                    "spec": {
                        "name": "office-hours-" + args.mode,
                        "type": "pipeline",
                        "config": config,
                    }
                }
            ).encode()
            request = urllib.request.Request(
                base + "/jobs",
                data=body,
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                print("Local job:", json.load(response)["job"]["id"])
            expected = 2
            for _ in range(120):
                rows = output.read_text().splitlines() if output.exists() else []
                if len(rows) >= expected:
                    break
                time.sleep(0.25)
            assert len(rows) == expected, (
                f"Expected {expected}, received {len(rows)}; see {work}"
            )
            decoded = [json.loads(row) for row in rows]
            for _ in range(40):
                if (
                    len(list(work.glob("*.parquet"))) == 8
                    and Path(str(output) + ".dead-letter.jsonl").exists()
                ):
                    break
                time.sleep(0.25)
            assert len(list(work.glob("*.parquet"))) == 8
            assert all(
                p.read_bytes()[:4] == b"PAR1" and p.read_bytes()[-4:] == b"PAR1"
                for p in work.glob("*.parquet")
            )
            assert all(
                "sensor_id" not in r and len(r["sensor_hash"]) == 64 for r in decoded
            )
            assert (
                len(Path(str(output) + ".dead-letter.jsonl").read_text().splitlines())
                == 1
            )
            print(f"PASS {args.mode}: {len(rows)} received records; evidence: {work}")
        finally:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            print("Local Edge stopped:", proc.returncode)


if __name__ == "__main__":
    main()
