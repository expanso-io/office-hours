# Session 001 verification

## Cloud execution — 9 September 2026

`uv run rehearse.py csv` deployed `office-hours-001-csv` to the `expanso-demos`
Expanso Cloud cluster (control plane v2.1.20) with a `role: office-hours` node
selector. The control plane scheduled it on node `M5-Max.local`
(`d6a9eba7-c98f-4302-be57-284b473b2b4c`, Expanso Edge v2.1.21, macOS arm64),
reported the execution completed, and the node wrote:

- Two WARN records in `received.jsonl`.
- Eight one-record Parquet files with valid `PAR1` envelope markers.
- One malformed row in `received.jsonl.dead-letter.jsonl`.
- SHA-256 `sensor_hash` in place of `sensor_id` in every valid record.

The Cloud validator rejected the previous `sensor.yaml`, which put `processors`
directly under a switch case; offline `expanso-edge validate` had accepted it.
The OK branch now uses a `broker` with batch processors, which both validators
accept. No standalone local engine was started.

Offline `uv run check.py` passed three tests, and Ruff lint/format passed.

## Historical local execution — 7 September 2026

Before the Cloud conversion, an isolated local Edge rehearsal on macOS with
Expanso Edge v2.1.21 produced the same record counts. Retained for context only;
local execution is no longer a supported path for office hours.

This folder is reconstructed teaching code, not the original live export.
