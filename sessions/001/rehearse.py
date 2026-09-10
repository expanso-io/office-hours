# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0,<7"]
# ///

"""Deploy a finite feed pipeline to Expanso Cloud and check what the node wrote.

Office hours always run on the Expanso Cloud cluster, never on a standalone local
engine. The feed is generated on the edge node (this machine), the job is deployed
through the control plane, and the execution is observed there. Credentials come
from a gitignored .env in this session directory or the repository root, or from
EXPANSO_ENDPOINT and EXPANSO_API_KEY in the environment.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import yaml

JOB_PREFIX = "office-hours-001-"
NODE_LABELS = {"role": "office-hours"}
EXPECTED = 2


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
    creds = credentials(root)
    name = JOB_PREFIX + args.mode
    spec = {
        "name": name,
        "type": "pipeline",
        "description": f"Office hours session 001 {args.mode} feed",
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
        if (
            job
            and job["status"]["version"] > previous
            and state in ("running", "completed")
        ):
            break
        if state == "failed":
            raise RuntimeError(f"Cloud job failed: {job['status']['state']}")
        time.sleep(0.5)
    else:
        raise RuntimeError(
            f"Job did not reach running/completed; see: expanso-cli job describe {name}"
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

    for _ in range(240):
        rows = output.read_text().splitlines() if output.exists() else []
        if len(rows) >= EXPECTED:
            break
        time.sleep(0.25)
    assert len(rows) == EXPECTED, (
        f"Expected {EXPECTED}, received {len(rows)}; see {work}"
    )
    decoded = [json.loads(row) for row in rows]
    dead_letter = Path(str(output) + ".dead-letter.jsonl")
    for _ in range(40):
        if len(list(work.glob("*.parquet"))) == 8 and dead_letter.exists():
            break
        time.sleep(0.25)
    parquet = list(work.glob("*.parquet"))
    assert len(parquet) == 8, (
        f"Expected 8 Parquet files, found {len(parquet)}; see {work}"
    )
    assert all(
        p.read_bytes()[:4] == b"PAR1" and p.read_bytes()[-4:] == b"PAR1"
        for p in parquet
    )
    assert all("sensor_id" not in r and len(r["sensor_hash"]) == 64 for r in decoded)
    assert len(dead_letter.read_text().splitlines()) == 1
    print(
        f"PASS {args.mode}: {len(rows)} records written by the Cloud-managed node; evidence: {work}"
    )
    print(
        f"Inspect in Cloud: expanso-cli job describe {name}; expanso-cli job executions {name}"
    )


if __name__ == "__main__":
    main()
