# Session 001 — August 28, 2026

[Edited replay](https://www.youtube.com/watch?v=Utvn1Mddyfo)

The session covered CSV sensor logs, filtering OK readings, source context,
Parquet fan-out, malformed/schema-invalid records, and identifier hashing.

## Provenance

This folder is a runnable reconstruction prepared September 7, 2026 from the
post-event runbook and transcript. It is **not an exact export of the live job**.
The pre-event Apache access-log plan was not what ran on air. The recorded session
included Cloud-connected execution, and so does this reproduction: the helper
deploys the job to the Expanso Cloud cluster and checks what the node wrote.
The original simulator and successive live YAML revisions have not been recovered.

## Reproduce

This folder stands alone: copy or download it with its scripts, `tests/`, YAML,
and `.gitignore`. Nothing imports or executes a helper from the repository root
or another session. Requirements: `uv`, Python 3.11+ (managed by `uv`), `expanso-cli` on PATH,
Cloud credentials in an ignored `.env` (see [CLUSTER.md](../../CLUSTER.md)), and
the office-hours edge node running. The rehearsal declares its PyYAML dependency inline.

From this directory (`sessions/001` in the full repository):

```sh
uv run rehearse.py csv
```

Generate the feed separately with `uv run simulate.py csv --count 20`.
The helper generates the feed, deploys `office-hours-001-csv` to Cloud with a
`role: office-hours` node selector, waits for the job to complete there, and
prints the Cloud job, version, execution and node. Input, rendered job spec and
output live under this folder's ignored `.runtime/`. It also works when invoked by its full path from another directory;
its files remain associated with this session, not the caller's working directory.

The simulator emits ten CSV rows: `sequence,sensor_id,temperature_c,status`.
The rehearsal appends one malformed row. Expected output:

- Two WARN events in `received.jsonl`.
- Eight OK events retained as eight small Parquet files.
- One malformed row in `received.jsonl.dead-letter.jsonl`.
- Valid output contains a SHA-256 identifier instead of the raw sensor ID.

For a live correction, inspect an OK sample, predict the warning output, then
explain why it goes to the archive. Change the routing condition and rerun with
fresh input/output files. The final YAML retains normal data instead of deleting it.

`source` is an explicit synthetic label, not proof of node provenance. SHA-256 is
a deterministic hashing example, not anonymization; predictable identifiers can
still be guessed. The original session used a different hashing demonstration.
The dead-letter output intentionally retains raw synthetic input for debugging.

The one-record Parquet files make routing easy to count. Production pipelines
should batch writes; this example makes no throughput claim.

## Checks

From this directory:

```sh
uv run check.py
uvx ruff check simulate.py rehearse.py check.py tests
uvx ruff format --check simulate.py rehearse.py check.py tests
FEED_FILE=input OUTPUT_FILE=output expanso-edge validate sensor.yaml
```

`check.py` tests the simulator and session-relative rehearsal paths without
contacting Cloud. `rehearse.py csv` is the real Cloud execution; inspect the job
afterwards with `expanso-cli job describe office-hours-001-csv`. See this folder's [verification record](VERIFICATION.md)
for the distinction between historical execution and current packaging checks.
