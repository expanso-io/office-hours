# Expanso Pipeline Office Hours

A hands-on tutorial series. Each session is a folder you can run end to end:
synthetic feeds, real Expanso pipelines deployed through Expanso Cloud, checks
that tell you whether what came out is what should have come out, and a
benchmark harness for measuring the same machine under load.

**Everything runs on the Expanso Cloud cluster.** Feeds are generated on the
edge node, every pipeline is deployed with `expanso-cli job deploy`, and the
job, its execution, and the node are the things you inspect. Nothing here
starts a standalone local engine for a demo; the helpers refuse to run without
Cloud credentials.

## What you will be able to do

By the end of the two sessions you can take a feed you have never seen, work
out where one record ends and the next begins, write a pipeline that reshapes
and routes it, prove the output is correct, and put a number on how fast the
machine can do it.

| Session | You will learn | Time |
| --- | --- | --- |
| [Setup](#setup) | Connect this machine to the cluster as a node | 10 min, once |
| [001 — CSV to Parquet, dead letters, hashing](sessions/001/README.md) | Filter, route, reject bad rows, hash identifiers | 20 min |
| [002 — Binary feeds, multiline events, benchmarking](sessions/002/README.md) | Stream bytes into a node, frame stack traces, change a running pipeline, measure throughput | 20 min |

## Setup

You need `uv`, `expanso-cli`, `expanso-edge`, and Go 1.24+ (for the benchmark
harness) on your PATH, plus an Expanso Cloud workspace. Full detail, including
what each command should print, is in [CLUSTER.md](CLUSTER.md). The short form:

**1. Clone with the benchmark submodule.**

```sh
git clone --recurse-submodules https://github.com/expanso-io/office-hours.git
cd office-hours
```

If you already cloned without it: `git submodule update --init --recursive`.

**2. Put your Cloud credentials in an ignored `.env` at the repository root.**

```sh
EXPANSO_ENDPOINT=https://<workspace>.cloud.expanso.io:9010
EXPANSO_API_KEY=exp_ak_...
EXPANSO_BOOTSTRAP_TOKEN=exp_bk_...
```

**3. Enrol this machine as the office-hours node (once).**

```sh
set -a; source .env; set +a
expanso-edge bootstrap --token "$EXPANSO_BOOTSTRAP_TOKEN" --data-dir "$PWD/.expanso-edge"
printf 'labels:\n  role: office-hours\n' > .expanso-edge/config.d/20-labels.yaml
```

**4. Start the node before every session, in its own terminal.**

```sh
expanso-edge run --no-watch --data-dir "$PWD/.expanso-edge"
```

**5. Confirm Cloud sees it.**

```sh
expanso-cli node list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

You should see one node with `role=office-hours` in its labels and
`connected` as its state. If you do, you are ready for
[Session 001](sessions/001/README.md).

## How a session is laid out

Every session folder is self-contained and has the same shape:

| File | What it is for |
| --- | --- |
| `README.md` | The tutorial: steps, what to run, what you should see, what to try |
| `simulate.py` | Generates the synthetic feed for that session |
| `*.yaml` | The pipeline(s) as taught; `${FEED_FILE}` and `${OUTPUT_FILE}` are filled in at deploy time |
| `rehearse.py` | Generates a feed, deploys the pipeline to Cloud, waits, checks the output |
| `check.py` + `tests/` | Offline checks that never contact Cloud |
| `VERIFICATION.md` | What was actually run, where, and what came out |
| `.runtime/` | Ignored. Inputs, rendered job specs, outputs, logs from your runs |

Session 002 also has `demo.py`, which runs the live three-console demo (raw
bytes in, node in the middle, processed records out), and `bench.py`, which
drives the benchmark harness in [`vendor/benchmarking`](vendor/benchmarking)
through Cloud.

Helpers work from any working directory and always keep their files inside
their own session folder. Copy a session folder somewhere else and it still
runs, as long as a `.env` sits beside it or at the repository root.

## Conventions

- Cloud job names are `office-hours-<session>-<mode>`. Rerunning a mode
  redeploys the same name with fresh paths, so Cloud shows a new version and a
  new execution each time. Completed jobs stay as the record of what ran.
- A `PASS` line from a helper is a check, not the demonstration. Open the
  output file and the job in Cloud; that is what the audience should see.
- Presenter web UIs (the benchmark UI included) bind to `127.0.0.1` only.
  Publishing this code does not authorize hosting them.
- After a session, stop the node (Ctrl-C in its terminal) and confirm with
  `expanso-cli node list` that it has disconnected.

Session 001 is reconstructed teaching code, not the original live export.
Session 002 is prepared material, not yet a published recording. The
[historical cross-session verification](VERIFICATION.md) is kept for context;
each session's own `VERIFICATION.md` is the current record.
