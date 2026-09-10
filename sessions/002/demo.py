# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0,<7"]
# ///

"""Drive the live three-console demo for one feed mode.

    uv run demo.py binary            print the command for every console
    uv run demo.py binary deploy     deploy the pipeline to Expanso Cloud
    uv run demo.py binary feed       stream the feed into the node forever
    uv run demo.py binary raw        watch the raw bytes as they arrive
    uv run demo.py binary out        watch processed records as the node writes them
    uv run demo.py binary stop       stop the Cloud job and clear the live files

Console 1 is `expanso-edge run` itself; see CLUSTER.md. All live files sit under
this session's ignored .runtime/live/<mode>/ so every console agrees on paths.
The pipeline listens on a fixed TCP port per mode; the feed connects to it.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parent
PORTS = {"binary": 4002, "multiline": 4003}
NODE_LABELS = {"role": "office-hours"}


def credentials():
    values = {}
    for env_file in (ROOT / ".env", ROOT.parents[1] / ".env"):
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
            "Expanso Cloud credentials missing: EXPANSO_ENDPOINT and EXPANSO_API_KEY "
            "(ignored .env or environment). The demo runs through Cloud only."
        )
    return ["--endpoint", endpoint, "--api-key", api_key]


def cli(*args, check=True):
    return subprocess.run(["expanso-cli", *args, *credentials()], check=check)


def paths(mode):
    live = ROOT / ".runtime" / "live" / mode
    return live, live / "raw.bin", live / "received.jsonl", live / "job.yaml"


def job_name(mode):
    return "office-hours-002-" + mode


def cmd_print(mode):
    live, raw, out, _ = paths(mode)
    rel = live.relative_to(ROOT)
    print(f"""Live demo for the {mode} feed. One command per console, run from {ROOT}:

  Console 1  (node, start first, keep running)
    expanso-edge run --no-watch --data-dir "$(git rev-parse --show-toplevel)/.expanso-edge"

  Console 2  (raw bytes arriving)
    uv run demo.py {mode} raw

  Console 3  (records after processing)
    uv run demo.py {mode} out

  Deploy the pipeline as a Cloud job (any console, once):
    uv run demo.py {mode} deploy

  Start the feed (a fourth console, or background it):
    uv run demo.py {mode} feed

  Change {mode}.yaml, then `uv run demo.py {mode} deploy` again: Cloud rolls a new
  version onto the node while consoles 2 and 3 keep running.

  Stop the job and clear {rel}/ when done:
    uv run demo.py {mode} stop

Port {PORTS[mode]}; raw {rel}/raw.bin; output {rel}/received.jsonl.""")


def cmd_deploy(mode):
    live, _, out, job_file = paths(mode)
    live.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(
        (ROOT / f"{mode}.yaml")
        .read_text()
        .replace("${PORT}", str(PORTS[mode]))
        .replace("${OUTPUT_FILE}", str(out))
    )
    spec = {
        "name": job_name(mode),
        "type": "pipeline",
        "description": f"Office hours session 002 live {mode} feed",
        "selector": {"match_labels": NODE_LABELS},
        "config": config,
    }
    job_file.write_text(yaml.safe_dump(spec, sort_keys=False))
    cli("job", "deploy", str(job_file))
    # The scheduler reconciles about every 30 s; wait so the feed has a listener.
    for _ in range(240):
        result = subprocess.run(
            ["expanso-cli", "job", "describe", job_name(mode), "--format", "json"]
            + credentials(),
            capture_output=True,
            text=True,
        )
        state = (
            json.loads(result.stdout)["status"]["state"]
            if result.returncode == 0
            else {}
        )
        if state.get("state_type") == "running":
            break
        print(
            f"  {state.get('state_type', '?')}: {state.get('message', '')}", flush=True
        )
        time.sleep(2)
    else:
        raise SystemExit(
            f"Job never reached running; see: expanso-cli job describe {job_name(mode)}"
        )
    print(
        f"Running on 127.0.0.1:{PORTS[mode]}. In Cloud: expanso-cli job describe {job_name(mode)}"
    )


def cmd_feed(mode, interval):
    live, raw, _, _ = paths(mode)
    live.mkdir(parents=True, exist_ok=True)
    os.execvp(
        "uv",
        [
            "uv",
            "run",
            str(ROOT / "simulate.py"),
            mode,
            "--count",
            "0",
            "--interval",
            str(interval),
            "--send",
            f"127.0.0.1:{PORTS[mode]}",
            "--tee",
            str(raw),
        ],
    )


def cmd_raw(mode):
    live, raw, _, _ = paths(mode)
    live.mkdir(parents=True, exist_ok=True)
    raw.touch()
    if mode == "binary":
        # Show the compressed bytes and the decompressed JSON side by side:
        # gzip handles concatenated members as they stream in.
        script = (
            f"tail -c +1 -f '{raw}' | tee >(od -An -tx1 -v | sed 's/^/  gz  /') "
            "| gzip -dc 2>/dev/null | sed -u 's/^/  json /'"
        )
        os.execvp("bash", ["bash", "-c", script])
    os.execvp("tail", ["tail", "-n", "+1", "-f", str(raw)])


def cmd_out(mode):
    live, _, out, _ = paths(mode)
    live.mkdir(parents=True, exist_ok=True)
    out.touch()
    if shutil.which("jq"):
        filter_ = (
            "{sequence, temperature_c, status, input_format}"
            if mode == "binary"
            else '{line_count, input_format, first: (.message | split("\\n")[0])}'
        )
        os.execvp(
            "bash",
            ["bash", "-c", f"tail -n +1 -f '{out}' | jq --unbuffered -c '{filter_}'"],
        )
    os.execvp("tail", ["tail", "-n", "+1", "-f", str(out)])


def cmd_stop(mode):
    live, *_ = paths(mode)
    cli("job", "stop", job_name(mode), "--force", check=False)
    if live.exists():
        shutil.rmtree(live)
    print(f"Stopped {job_name(mode)} and cleared {live}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", choices=sorted(PORTS))
    parser.add_argument(
        "action",
        nargs="?",
        default="print",
        choices=["print", "deploy", "feed", "raw", "out", "stop"],
    )
    parser.add_argument(
        "--interval", type=float, default=0.5, help="seconds between feed records"
    )
    args = parser.parse_args()
    if args.action == "print":
        cmd_print(args.mode)
    elif args.action == "deploy":
        cmd_deploy(args.mode)
    elif args.action == "feed":
        cmd_feed(args.mode, args.interval)
    elif args.action == "raw":
        cmd_raw(args.mode)
    elif args.action == "out":
        cmd_out(args.mode)
    elif args.action == "stop":
        cmd_stop(args.mode)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
