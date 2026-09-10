# Session 001 — CSV sensor logs: filter, route to Parquet, reject bad rows, hash IDs

[Edited replay of the live session (August 28, 2026)](https://www.youtube.com/watch?v=Utvn1Mddyfo)

This is the tutorial version of the first office hours. In twenty minutes you
take a plain CSV sensor feed and turn it into three correctly routed outputs,
with every step deployed through Expanso Cloud and checked against what the
node actually wrote.

## What you will learn

- How a pipeline turns one line of CSV into a structured record.
- How to send different records to different outputs based on their content.
- How to keep malformed and schema-invalid rows out of your good data without
  losing them.
- How to replace an identifier with a hash so downstream consumers never see
  the raw value.
- How to prove all of that from the Cloud side, not just from a local file.

## Before you start

You need the [repository setup](../../README.md#setup) done and the
office-hours node running in another terminal. From this folder:

```sh
set -a; source ../../.env; set +a
expanso-cli node list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
uv run check.py
```

`node list` should show your node with `role=office-hours`. `check.py` runs
three offline tests of the simulator and helper and should print `OK`. If
either fails, fix that before continuing; nothing below will work without a
connected node.

## Step 1 — Look at the feed

The simulator writes ten CSV rows shaped `sequence,sensor_id,temperature_c,status`:

```sh
uv run simulate.py csv --count 10
```

You should see rows like `0,pump-demo-07,60,WARN`. Two rows are `WARN`, eight
are `OK`, and the temperatures climb from 60 to 69. Note the raw `sensor_id`;
by the end of the session no valid output will contain it.

## Step 2 — Read the pipeline before running it

Open [`sensor.yaml`](sensor.yaml) and follow it top to bottom:

1. **Input.** A `file` input with a `lines` scanner: one CSV row becomes one message.
2. **Parse.** A `mapping` splits the row on commas into `sequence`,
   `sensor_id`, `temperature_c`, and `status`.
3. **Validate.** A `json_schema` processor rejects anything missing a field or
   with a `status` outside `OK`, `WARN`, `ALARM`.
4. **Hash.** A second mapping adds `sensor_hash` (SHA-256 of `sensor_id`),
   deletes `sensor_id`, and stamps `source: synthetic-office-hours`.
5. **Catch.** Steps 2 to 4 sit inside a `try`. Anything that fails lands in
   the `catch` block, which rewrites the record as
   `{"route": "dead-letter", "raw": ..., "reason": ...}`.
6. **Route.** A `switch` output sends dead letters to one file, `OK` records
   through a Parquet encoder to per-record `.parquet` files, and everything
   else (the `WARN` rows) to `received.jsonl`.

The `${FEED_FILE}` and `${OUTPUT_FILE}` placeholders are filled in by the
helper at deploy time so every run gets fresh paths.

## Step 3 — Deploy it to Cloud and check the result

```sh
uv run rehearse.py csv
```

The helper generates the feed, appends one deliberately malformed row, renders
the job spec with a `role: office-hours` node selector, deploys it, waits for
the control plane to report the job complete, and checks the files the node
wrote. You should see:

```
Cloud node: <your node name> <node id>
Job 'office-hours-001-csv' created successfully in namespace ''
Cloud execution: e-... on node <node id> -> completed
Cloud job: j-... version 1 completed
PASS csv: 2 records written by the Cloud-managed node; evidence: .../.runtime/csv-<id>
```

Now open the evidence directory it printed:

```sh
run=$(ls -td .runtime/csv-*/ | head -1)
ls "$run"
cat "$run"received.jsonl
cat "$run"received.jsonl.dead-letter.jsonl
```

You should find:

- `received.jsonl` with two `WARN` records, each carrying a 64-character
  `sensor_hash` and no `sensor_id`.
- Eight files named `received.jsonl.normal-1.parquet` through `-8.parquet`,
  one per `OK` row.
- `received.jsonl.dead-letter.jsonl` with one record whose `raw` is
  `malformed,record` and whose `reason` names the failing step.
- `job.yaml`, the exact spec that was deployed.

## Step 4 — See the same run from the Cloud side

This is the part a local file cannot give you. The control plane recorded the
job, its version, the evaluation, the node it picked, and every state change:

```sh
expanso-cli job describe office-hours-001-csv --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
expanso-cli job history  office-hours-001-csv --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

`describe` shows the configuration as deployed and a `RECENT HISTORY` table
ending in `Job completed successfully`. `history` lists the same events with
the execution id and node id. Open the job in the Cloud web UI too; it is the
same object.

## Step 5 — Change the routing and rerun

Predict, then change, then check. In `sensor.yaml`, the Parquet branch is
selected by `this.status == "OK"`. Change it to route `WARN` instead:

```yaml
      - check: this.status == "WARN"
```

Before running, predict: how many Parquet files now, and how many lines in
`received.jsonl`? Then:

```sh
uv run rehearse.py csv
```

The helper's assertion will fail, because it expects the taught routing. That
is correct behaviour: the assertion is the contract for the teaching example.
Inspect the new evidence directory and compare with your prediction (two
Parquet files, eight JSON lines). Cloud shows `office-hours-001-csv` at
version 2. Then restore `"OK"` and rerun so the folder is back to a passing
baseline.

## Step 6 — Try it yourself

Each of these is a two-minute experiment. Restore the file between them.

| Try | Change | What to look for |
| --- | --- | --- |
| Add a second bad row | Append `1,pump-x,hot,OK` to the feed after generating it | Two dead letters; the `reason` says `temperature_c` is not a number |
| Reject WARN too | Add `"WARN"` removal: change the enum to `["OK","ALARM"]` | Two dead letters with schema reasons; `received.jsonl` is empty |
| Keep the raw ID | Delete the `root.sensor_id = deleted()` line | `sensor_id` reappears in output; the helper fails on that assertion |
| Batch the Parquet | Set `batching.count: 10` in the broker | One Parquet file instead of eight |

## What this does and does not show

- `source` is a literal label, not proof of provenance.
- SHA-256 is a deterministic hashing example, not anonymization; predictable
  identifiers can still be guessed.
- The dead-letter output keeps the raw input on purpose so you can debug it.
- One-record Parquet files make routing easy to count. Production pipelines
  batch; this example makes no throughput claim. Session 002 measures that.
- The Cloud validator is stricter than the offline one. `processors` directly
  under a switch case is rejected on deploy, which is why the Parquet branch
  uses a `broker` with batch processors.

## Checks

```sh
uv run check.py
uvx ruff check simulate.py rehearse.py check.py tests
uvx ruff format --check simulate.py rehearse.py check.py tests
FEED_FILE=input OUTPUT_FILE=output expanso-edge validate sensor.yaml
expanso-cli job validate .runtime/csv-*/job.yaml --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

`check.py` never contacts Cloud. `rehearse.py csv` is the real Cloud
execution. See [VERIFICATION.md](VERIFICATION.md) for what was last run and
what it produced.

## Provenance

This folder is a runnable reconstruction prepared September 7, 2026 from the
post-event runbook and transcript. It is **not an exact export of the live
job**. The pre-event Apache access-log plan was not what ran on air. The
original simulator and successive live YAML revisions have not been recovered.
