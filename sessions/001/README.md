# Session 001 — August 28, 2026

[Edited replay](https://www.youtube.com/watch?v=Utvn1Mddyfo)

The session covered CSV sensor logs, filtering OK readings, source context,
Parquet fan-out, malformed/schema-invalid records, and identifier hashing.

## Provenance

This folder is a runnable reconstruction prepared September 7, 2026 from the
post-event runbook and transcript. It is **not an exact export of the live job**.
The pre-event Apache access-log plan was not what ran on air. The recorded session
included Cloud-connected execution; the reproduction here is tested locally.
The original simulator and successive live YAML revisions have not been recovered.

## Reproduce

From the repository root:

```sh
uv run rehearse.py csv
```

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
