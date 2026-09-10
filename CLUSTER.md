# Cluster setup

Office hours run on the `expanso-demos` Expanso Cloud cluster. Nothing in this
repository starts a standalone local engine for a demo. The rehearsal and
benchmark helpers fail closed if Cloud credentials are missing.

This page is the long form of the [README setup](README.md#setup): the same
steps, with what each one should print and what to do when it does not.

## Credentials

Keep credentials in an ignored, owner-only `.env` at the repository root (or in
the session folder when a session is copied out on its own):

```sh
EXPANSO_ENDPOINT=https://<cluster>.cloud.expanso.io:9010
EXPANSO_API_KEY=exp_ak_...
EXPANSO_BOOTSTRAP_TOKEN=exp_bk_...
```

All three come from the workspace **Keys** tab in Cloud. The bootstrap token is
used once to enrol the office-hours node, and once more by the benchmark harness
to enrol its own `bench-<host>` node.

The helpers read that file, or `EXPANSO_ENDPOINT` and `EXPANSO_API_KEY` from the
environment, and pass them to `expanso-cli` explicitly. No globally selected
`expanso-cli` profile is used, so nothing here can silently talk to another
cluster. Never commit `.env`; both root and session `.gitignore` files exclude it.

## One-time node bootstrap

The presenting machine is an edge node on the cluster. Its identity lives in the
ignored `.expanso-edge/` directory at the repository root, not in `~/.expanso`.
Bootstrap once with a token from Cloud (Nodes → Add Node):

```sh
expanso-edge bootstrap --token "<bootstrap token>" --data-dir "$PWD/.expanso-edge"
printf 'labels:\n  role: office-hours\n' > .expanso-edge/config.d/20-labels.yaml
```

Every office-hours job selects nodes by the `role: office-hours` label, so the
label file is required.

## Before each session

Start the node and leave it running for the session:

```sh
expanso-edge run --no-watch --data-dir "$PWD/.expanso-edge"
```

Confirm it is connected and labelled from the Cloud side:

```sh
set -a; source .env; set +a
expanso-cli node list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

Then run a session's `uv run rehearse.py <mode>`. It prints the Cloud node,
job, version and execution it used. Inspect the same objects in Cloud with:

```sh
expanso-cli job describe office-hours-002-binary --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
expanso-cli job history  office-hours-002-binary --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
expanso-cli execution list --job-id <job id> --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

Job names are `office-hours-<session>-<mode>`. Rerunning a mode redeploys the
same job name with fresh input and output paths, so Cloud shows a new version
and a new execution each time.

## Benchmark node

Session 002's `bench.py` starts the harness from the `vendor/benchmarking`
submodule in Cloud mode. The harness enrols a second node named
`bench-<host>` (identity under `sessions/002/.runtime/bench/node/`), deploys
each benchmark to it as a Cloud job, and stops the node when the run ends. Both
nodes can be connected at the same time; jobs select by label, and the bench
node carries a `bench=<hash>` label rather than `role=office-hours`.

The harness needs Go 1.24+ to build. `bench.py` builds it on first use into the
ignored `.runtime/bin/`; you can also build it yourself:

```sh
git submodule update --init --recursive
(cd vendor/benchmarking && go build -o ../../.runtime/bin/expanso-bench ./cmd/expanso-bench)
.runtime/bin/expanso-bench doctor
```

`doctor` should print `cloud: ... ok` and `bootstrap: token present`.

## After each session

Stop the edge node with Ctrl-C (or kill its process) and confirm it has
disconnected with `expanso-cli node list`. Completed jobs stay in Cloud as the
record of what ran; delete them with `expanso-cli job delete <name>` only when
they are no longer useful.
