# Session 002 — non-text, multiline, and benchmarking

Prepared for the week of September 7, 2026. Broadcast date/time are not set here.

## Operator runbook: 20 minutes of hands-on work

Use this as a workbench, not spoken copy. Timings are pacing budgets. Each block
contains something to run, inspect, change, or compare. Audience questions can
extend a block; none are required to fill the twenty minutes.

| Elapsed | Work | Visible result |
| --- | --- | --- |
| 0–2 min | Inspect bytes and event boundaries | Gzip header, decompressed records, complete stack trace |
| 2–5 min | Run the binary pipeline | Ten decoded records with IDs 0–9 |
| 5–7 min | Add a derived field and rerun | Five records flagged by a threshold |
| 7–10 min | Break multiline framing | Fifty fragments instead of ten events |
| 10–13 min | Restore boundaries; inspect first and last events | Complete traces, nested causes, EOF handling |
| 13–16 min | Run a benchmark baseline | Calibration, two rungs, saved result |
| 16–19 min | Add processing; compare results | Same settings, different pipeline work |
| 19–20 min | Review runnable artifacts and choose a next experiment | Code, output, measurement, follow-up |

## Prepare the workspace before air

Terminal A: office-hours repository root. Terminal B: your benchmarking checkout.
Editor: `simulate.py`, `sessions/002/binary.yaml`, and
`sessions/002/multiline.yaml`. Leave room to open `received.jsonl` beside a YAML
file. Enlarge text until a five-line trace is readable in the recording preview.

Check tools and record versions:

```sh
command -v uv
command -v expanso-edge
command -v go
command -v jq
command -v od
command -v gzip
expanso-edge version
git status --short
git rev-parse HEAD
```

Warm dependencies and save known-good outputs before presenting:

```sh
uv run rehearse.py binary
uv run rehearse.py multiline
```

Each command prints a new `.runtime/<mode>-…` directory containing `input`,
`received.jsonl`, and `edge.log`. Keep a successful directory for each example as
a backup. Show it as an earlier rehearsal result if you need it on air.

The helper generates a finite file, starts isolated local Expanso Edge, submits
the YAML through its loopback API, checks the received file, and stops Edge.
It generates the entire input before processing. This is not a continuously
tailed feed or Cloud execution. The PASS line is a check; open the output to
demonstrate the result.

In Terminal B, run `go run ./cmd/expanso-bench run --help`, then preflight both
benchmark commands below. Keep their saved JSON result paths. Open one result
before air so you know where the configuration, pipeline, and measurements live.
Record a short local preview to check microphone and screen readability.

## 0–2 minutes: inspect the sources

In Terminal A, select the most recent binary rehearsal and inspect its bytes:

```sh
binary_run=$(ls -td .runtime/binary-*/ | head -1)
od -An -tx1 -N32 "${binary_run}input"
gzip -dc "${binary_run}input" | head -3
gzip -dc "${binary_run}input" | wc -l
```

Identify the `1f 8b` gzip header. Compare those bytes with the decompressed JSON.
Count ten source records. Open the binary branch in `simulate.py`: each record
is compressed into one member of a concatenated gzip stream.

Inspect the other source:

```sh
multiline_run=$(ls -td .runtime/multiline-*/ | head -1)
sed -n '1,12p' "${multiline_run}input"
```

Locate the timestamp header, exception, two stack-frame lines, and nested cause.
The blank line is visual spacing; the corrected scanner uses timestamp headers.
Explore what defines one message in each format. Decompression and identifying
record boundaries are separate operations.

## 2–5 minutes: decode and inspect actual output

Walk through `binary.yaml` in order: input file → gzip decoder → child line
scanner → JSON parser → added format label → JSONL output. Then run:

```sh
uv run rehearse.py binary
binary_run=$(ls -td .runtime/binary-*/ | head -1)
jq -s 'length' "${binary_run}received.jsonl"
jq -s 'map(.sequence) | sort' "${binary_run}received.jsonl"
jq -s 'sort_by(.sequence) | .[0]' "${binary_run}received.jsonl"
```

Expect ten records, IDs 0–9 exactly once, and original fields plus
`input_format: gzip-jsonl`. Parallel processing can change order; sorting for
inspection distinguishes reordering from loss.

Open `rehearse.py` briefly if the audience asks where execution happens. The
generator creates source bytes; actual Expanso Edge executes the YAML. These
output files prove local processing, not a remote receiver or Cloud job.

## 5–7 minutes: make a useful live edit

Add this line inside the existing mapping block in `binary.yaml`, aligned with
`root.input_format`:

```bloblang
root.needs_attention = this.temperature_c >= 65
```

Predict the outcome before running: synthetic temperatures are 60–69, so IDs 5–9
should qualify. Run the same input again and inspect the new directory:

```sh
uv run rehearse.py binary
binary_run=$(ls -td .runtime/binary-*/ | head -1)
jq -s 'sort_by(.sequence) | map({sequence, temperature_c, needs_attention})' "${binary_run}received.jsonl"
jq -s '[.[] | select(.needs_attention == true)] | length' "${binary_run}received.jsonl"
```

Expect five flagged records. The helper checks count and sequence IDs; this
explicit output inspection verifies the new field. Change 65 to 68 for a second
variation if useful: expect two flagged records.

Discuss retaining a flag versus deleting a record. Filtering would change the
expected output count and require a deliberate change to the helper's assertion.
Remove the added line afterward, or retain it intentionally for the session's
post-event commit. Do not let an accidental edit become the next demo's baseline.

## 7–10 minutes: break the multiline boundary

Establish a successful `uv run rehearse.py multiline` baseline first. Replace
only this scanner block in `multiline.yaml`:

```yaml
      re_match:
        pattern: '(?m)^\d{4}-\d{2}-\d{2}T'
        max_buffer_size: 65536
```

with:

```yaml
      lines:
        omit_empty: true
```

Keep the mapping and output unchanged. Run and inspect:

```sh
uv run rehearse.py multiline
multiline_run=$(ls -td .runtime/multiline-*/ | head -1)
jq -s 'length' "${multiline_run}received.jsonl"
jq -s '.[0:6] | map({line_count, message})' "${multiline_run}received.jsonl"
```

The helper should exit nonzero: ten five-line traces became 50 fragments, each
with `line_count: 1`. Its evidence files remain available after failure and Edge
is stopped by cleanup. Locate a `Caused by:` fragment and a header fragment.
They no longer belong to one event. More output messages here mean broken
framing, not improved throughput.

If there is no output file, inspect `edge.log`: that is a different failure from
the expected count mismatch. Do not explain an unrelated startup error as the
intended demonstration.

## 10–13 minutes: repair grouping and inspect EOF

Restore the exact `re_match` block above. Point out that `(?m)^` recognizes a
timestamp at the beginning of any line, while retaining the following stack
frames and nested cause until the next header.

```sh
uv run rehearse.py multiline
multiline_run=$(ls -td .runtime/multiline-*/ | head -1)
jq -s 'length' "${multiline_run}received.jsonl"
jq -s 'map(.line_count) | unique' "${multiline_run}received.jsonl"
jq -r 'select(.message | contains("sequence=0 ")) | .message' "${multiline_run}received.jsonl"
jq -r 'select(.message | contains("sequence=9 ")) | .message' "${multiline_run}received.jsonl"
```

Expect ten events, distinct line counts `[5]`, and complete first and last traces.
Sequence 9 has no following timestamp: EOF flushes it in this finite replay.
An indefinitely open stream needs an explicit policy for an idle final event.
This replay does not prove timeout-based flushing.

Inspect the 64 KiB buffer limit. Explore the assumptions: what if a trace exceeds
it, or its body contains a timestamp at column zero? These are format contracts,
not something a parser can infer universally.

## 13–16 minutes: measure a baseline

Switch to Terminal B and run the passthrough command in the benchmarking section
below. Show the configuration before the measurements start.

Follow the actual output through five stages:

1. Local Edge starts and the job reaches running state.
2. Calibration measures how many records emerge per input record.
3. The offered rate rises from 1,000 to 5,000 records/sec.
4. Received/processed rate, CPU, and RSS change during each rung.
5. The result is saved with its configuration and exact pipeline.

Open the saved JSON at the printed path. Select two measurements that explain
what happened. Check whether the generator offered its target and whether the
pipeline kept up. If every rung passes, the experiment established a tested
floor under these conditions, not the machine's maximum throughput.

## 16–19 minutes: add processing and compare

Open `scenarios/json-transform.yaml` in the benchmark checkout. Inspect the
transformation and filtering condition before running its command below.
Predict whether every input record will be forwarded.

Keep host, version, dataset, transport, batching, threads, ladder, and duration
identical. Avoid simultaneous local work while comparing. Watch calibration:
intentional filtering changes raw receiver counts. The harness uses measured
selectivity to report input-equivalent processing throughput.

Open both saved results side by side and work through:

- Did both generators actually offer the requested rate?
- Did each pipeline pass the same rung?
- How did CPU and memory differ at that rung?
- Was a lower receiver count intentional filtering, temporary lag, or loss?
- What would you change for the next experiment: duration, offered rate,
  batching, or processor cost? Pick one variable.

Three-second rungs keep the presentation moving. They do not support production
capacity or cost claims. If a run fails, retain and inspect it. Do not quietly
lower the target and present a replacement as though the first run passed.

## 19–20 minutes: review the artifacts

Return to the session folder. Show the simulator, two YAML files, one received
output, and the benchmark source link. Review the actual changes you made and
which checks verified them. Choose one audience-inspired next experiment.

The audience should leave able to identify the bytes arriving, the boundary of
one event, the required transformation, and the conditions behind a measurement.

## Optional exercises

Choose one if a question opens it up. These are experiments; not all outcomes
have been pre-verified. Restore one experiment before starting the next.

| Exercise | Action | Inspect | Extra time |
| --- | --- | --- | --- |
| Slower source | `uv run simulate.py multiline --count 3 --interval 1` | Source events arriving gradually; not an Edge tailing test | 1 min |
| Different threshold | Change 65 to 68 in the added binary field | Two flagged records instead of five | 1–2 min |
| Extra context | Add `root.demo_site = "west"` to the binary mapping | Literal label on every record; not measured node identity | 1–2 min |
| Wrong boundary | Change the multiline pattern to `(?m)^Caused by:` | Incorrect grouping and why it happens | 2–3 min |
| Buffer limit | Reduce multiline `max_buffer_size` to 64 | Scanner error in `edge.log`; restore 65536 | 2 min |
| Batching | Change only benchmark `--batch 1000` to `--batch 0` | Measurement differences with other settings unchanged | 3–5 min |
| Longer observation | Repeat one benchmark with `--step-seconds 20` | Behavior over a longer window | 2–3 min |

## Recovery at the keyboard

| Symptom | Next action |
| --- | --- |
| Dependency download blocks | Use an earlier labeled result if offline; warm dependencies before air |
| YAML validation fails | Inspect indentation and the last changed line; validate with the command below |
| Assertion fails | Inspect actual received records in the newest directory, then `edge.log` |
| No received file | Check startup, input path, scanner, and output errors in `edge.log` |
| Multiline count explodes | Confirm the timestamp scanner was restored |
| Binary IDs appear out of order | Sort and verify completeness; order alone is not loss |
| Benchmark fails to start | Inspect its printed Edge log tail and current CLI help |
| Experiment consumes the segment | Interrupt with Ctrl-C, check cleanup, and use the labeled backup |

```sh
FEED_FILE=input OUTPUT_FILE=output expanso-edge validate sessions/002/binary.yaml sessions/002/multiline.yaml
```

Validation proves configuration syntax, not correct output. Rerun and inspect
after a repair. Cap an unexpected environment repair at about two minutes, then
use the backup or move to the next independent example.

## Reference: non-text feed

```sh
uv run rehearse.py binary
```

This is real binary input: concatenated gzip members containing synthetic JSONL.
Each member carries one event. Inspect the input in a hex viewer: the gzip header
starts `1f 8b`. The pipeline must decompress bytes before parsing JSON. Ten source
events must yield exactly sequence IDs 0–9, with no duplicates or missing IDs.

Failure challenge: remove the decompress scanner and try parsing the compressed
bytes as JSON. Restore it and rerun. A gzip decoder does not decode arbitrary
device protocols, images, Protobuf, or a proprietary binary schema. Those require
their own framing and decoder. This is a concrete first non-text example.

## Reference: multiline feed

```sh
uv run rehearse.py multiline
```

Each event contains five lines, including a timestamp header, stack frames, and
a nested cause. The scanner starts a new event only at an ISO date at column zero.
Ten traces must become ten JSON events, each retaining all five lines.

Failure challenge: replace `re_match` with `lines: {}`. The trace becomes multiple
unrelated events. Restore the timestamp boundary and rerun. Show the nested cause
inside its original event. The next timestamp or EOF flushes the last event;
an indefinitely idle open stream needs a separate timeout/framing design.
The scanner buffer is capped at 64 KiB. A trace containing a date at column zero
would violate this format contract.

## Reference: benchmarking commands

Use [expanso-io/benchmarking](https://github.com/expanso-io/benchmarking).
Keep its presenter UI on localhost. Do not depend on the hosted URL for the call.
From a checkout of that repository, start with its documented bounded local run:

```sh
go run ./cmd/expanso-bench run --scenario passthrough --ladder 1000,5000 --step-seconds 3
go run ./cmd/expanso-bench run --scenario json-transform --ladder 1000,5000 --step-seconds 3
```

At reviewed commit `40bf64623e3d1aff3ad33671d8ea5d38ae698d71`, the CLI `run`
command selects local mode internally; it does not accept `--local` despite the
upstream README example. Use the commands above. The separate `serve` command
does accept `--local`; bind it explicitly with `--addr 127.0.0.1:8080`.

Record the exact commit, Edge version, machine, dataset, batching, offered rate,
received rate, and run duration. These low-rate smoke tests establish operation,
not maximum throughput. Increase the ladder only during a planned benchmark.
Do not compare local and hosted numbers as if they describe the same machine.

## Final preflight

- Run all three rehearsals and inspect actual output.
- Complete both benchmark smoke tests on the presentation machine.
- Check microphone and screen readability in a local recording.
- If demonstrating Cloud, separately verify selected node, running execution,
  received payload, and teardown. Local rehearsals do not establish Cloud proof.

## After the call

1. Confirm each helper printed `Local Edge stopped`. Stop any manually started
   benchmark UI with Ctrl-C and check its terminal exit.
2. Review `git diff`. Undo temporary experiments in the editor, or retain the
   intentional demonstrated changes for the post-session commit.
3. Preserve useful output and benchmark results; review machine-specific paths
   and identifiers before publishing result files.
4. Add the actual broadcast date, replay link, demonstrated commit, and changes
   made during the session. Distinguish later corrections from live artifacts.

Current verified scope is local engine execution and short benchmark operation;
see [VERIFICATION.md](../../VERIFICATION.md). Presenter/OBS and any Cloud path
still need their own rehearsal.

Runbook checks repeated September 8, 2026: the threshold edit produced five
flagged records; the line-scanner experiment produced 50 one-line fragments and
the expected failed assertion; restoring timestamp framing produced ten
five-line events, including the final event at EOF. The original YAML files
were restored and all three baseline rehearsals passed afterward.
