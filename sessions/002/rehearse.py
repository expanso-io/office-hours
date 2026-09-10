# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0,<7"]
# ///

"""Deploy a feed pipeline to Expanso Cloud, stream a finite feed in, check output.

Office hours always run on the Expanso Cloud cluster, never on a standalone local
engine. The pipeline listens on TCP; this helper deploys it through the control
plane, waits for the scheduler, pushes ten records from the simulator, checks
what the node wrote, and stops the job. demo.py is the live version of the same
flow, one console per role. Credentials come
from a gitignored .env in this session directory or the repository root, or from
EXPANSO_ENDPOINT and EXPANSO_API_KEY in the environment.
"""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

import yaml

JOB_PREFIX = "office-hours-002-"
NODE_LABELS = {"role": "office-hours"}
EXPECTED = 10
PORTS = {"binary": 4002, "multiline": 4003}


def credentials(root):
    """Return (endpoint, api_key). Fail closed rather than fall back to local."""
    values = {}
    for env_file in (root / ".env", root.parents[1] / ".env"):
        if env_file.is_file():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    values.setdefault(key.strip(), value.strip())
            break
    endpoint = os.environ.get("EXPANSO_ENDPOINT") or values.get("EXPANSO_ENDPOINT")
    api_key = os.environ.get("EXPANSO_API_KEY") or values.get("EXPANSO_API_KEY")
    if not endpoint or not api_key:
        raise SystemExit(
            "Expanso Cloud credentials missing. Put EXPANSO_ENDPOINT and "
            "EXPANSO_API_KEY in an ignored .env (this folder or repository root) "
            "or export them. Local-only execution is not an option for office hours."
        )
    return endpoint, api_key


def cli(creds, *args, parse=False):
    endpoint, api_key = creds
    command = ["expanso-cli", *args, "--endpoint", endpoint, "--api-key", api_key]
    if parse:
        command += ["--format", "json"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(args)} failed ({result.returncode}):\n{result.stderr.strip()}"
        )
    return json.loads(result.stdout) if parse else result.stdout


def describe(creds, name):
    result = subprocess.run(
        [
            "expanso-cli",
            "job",
            "describe",
            name,
            "--format",
            "json",
            "--endpoint",
            creds[0],
            "--api-key",
            creds[1],
        ],
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout) if result.returncode == 0 else None


def job_version(creds, name):
    """Version already deployed under this name, or 0. Redeploys bump it."""
    job = describe(creds, name)
    return job["status"]["version"] if job else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["binary", "multiline"])
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
    pipeline = (
        root / {"binary": "binary.yaml", "multiline": "multiline.yaml"}[args.mode]
    )
    config = yaml.safe_load(
        pipeline.read_text()
        .replace("${PORT}", str(PORTS[args.mode]))
        .replace("${OUTPUT_FILE}", str(output))
    )
    creds = credentials(root)
    name = JOB_PREFIX + args.mode
    spec = {
        "name": name,
        "type": "pipeline",
        "description": f"Office hours session 002 {args.mode} feed",
        "selector": {"match_labels": NODE_LABELS},
        "config": config,
    }
    job_file = work / "job.yaml"
    job_file.write_text(yaml.safe_dump(spec, sort_keys=False))

    nodes = cli(creds, "node", "list", parse=True)
    eligible = [
        n
        for n in nodes
        if all(n["spec"].get("labels", {}).get(k) == v for k, v in NODE_LABELS.items())
        and n["status"].get("scheduling") == "eligible"
    ]
    if not eligible:
        raise SystemExit(
            f"No eligible node labelled {NODE_LABELS} on the cluster. Start the "
            "office-hours edge node first: "
            'expanso-edge run --data-dir "<repo>/.expanso-edge"'
        )
    print("Cloud node:", eligible[0]["spec"]["name"], eligible[0]["id"])

    previous = job_version(creds, name)
    print(cli(creds, "job", "deploy", str(job_file)).strip())
    job = None
    for _ in range(240):
        job = describe(creds, name)
        state = job["status"]["state"]["state_type"] if job else None
        if job and job["status"]["version"] > previous and state == "running":
            break
        if state == "failed":
            raise RuntimeError(f"Cloud job failed: {job['status']['state']}")
        time.sleep(0.5)
    else:
        raise RuntimeError(
            f"Job did not reach running; see: expanso-cli job describe {name}"
        )
    executions = cli(
        creds,
        "execution",
        "list",
        "--job-id",
        job["id"],
        "--job-version",
        str(job["status"]["version"]),
        parse=True,
    )
    for e in executions:
        print(
            "Cloud execution:",
            e["id"],
            "on node",
            e["node_id"],
            "->",
            e["status"]["observed_state"]["state_type"],
        )
    print(
        "Cloud job:",
        job["id"],
        "version",
        job["status"]["version"],
        job["status"]["state"]["state_type"],
    )

    # Push the pre-generated bytes over TCP exactly as a device would.
    for _ in range(60):
        try:
            with socket.create_connection(
                ("127.0.0.1", PORTS[args.mode]), timeout=2
            ) as sock:
                sock.sendall(feed.read_bytes())
            break
        except OSError:
            time.sleep(0.5)
    else:
        raise RuntimeError(f"Pipeline never listened on 127.0.0.1:{PORTS[args.mode]}")
    for _ in range(240):
        rows = output.read_text().splitlines() if output.exists() else []
        if len(rows) >= EXPECTED:
            break
        time.sleep(0.25)
    cli(creds, "job", "stop", name)
    assert len(rows) == EXPECTED, (
        f"Expected {EXPECTED}, received {len(rows)}; see {work}"
    )
    decoded = [json.loads(row) for row in rows]
    if args.mode == "binary":
        assert sorted(r["sequence"] for r in decoded) == list(range(10))
    else:
        assert all(
            r["line_count"] == 5 and "Caused by:" in r["message"] for r in decoded
        )
    print(
        f"PASS {args.mode}: {len(rows)} streamed over TCP and written by the Cloud-managed node; evidence: {work}"
    )
    print(
        f"Inspect in Cloud: expanso-cli job describe {name}; expanso-cli job executions {name}"
    )


if __name__ == "__main__":
    main()
