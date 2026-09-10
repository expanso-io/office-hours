# Session 002 — Binary feeds, multiline events, and measuring throughput

Prepared for the week of September 7, 2026. Broadcast date and time are not set here.

Session 001 dealt with one line per record. This session removes that comfort.
You will decode a feed that is not text, frame a feed where one event spans
several lines, break both on purpose to see what failure looks like, and then
put a number on how fast this machine runs a pipeline. Every pipeline is
deployed through Expanso Cloud, and every benchmark is a Cloud job too.

## What you will learn

- What actually arrives on the wire, byte by byte, and how to tell a gzip
  member from JSON.
- Why "what is one record" is a decision you make, not something a parser can
  infer, and what happens when you get it wrong.
- How to add derived fields and predict their effect before you run.
- How to read a benchmark result and tell *slow* from *lost*.
- How to make a fair comparison between two pipelines.

## Before you start

You need the [repository setup](../../README.md#setup) done, including the
benchmark submodule, and the office-hours node running in its own terminal.
Open two terminals in this folder and an editor on `simulate.py`,
`binary.yaml`, and `multiline.yaml`. Then:

```sh
set -a; source ../../.env; set +a
command -v uv expanso-cli expanso-edge go jq od gzip
expanso-edge version
expanso-cli node list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
uv run check.py
```

Every `command -v` line should print a path, `node list` should show your
node with `role=office-hours` and state `connected`, and `check.py` should
print `OK`. Build the benchmark harness once (it is cached under `.runtime/`):

```sh
(cd ../../vendor/benchmarking && go build -o ../../.runtime/bin/expanso-bench ./cmd/expanso-bench)
../../.runtime/bin/expanso-bench doctor
```

`doctor` should report your edge binary, `cloud: ... ok, N node(s) visible`,
and `bootstrap: token present`. `bench.py` builds the binary itself if it is
missing, so this step is a check, not a requirement.

Finally, warm everything and save a known-good result for each mode:

```sh
uv run rehearse.py binary
uv run rehearse.py multiline
uv run bench.py passthrough
```

Each rehearsal prints the Cloud node, job, version, and execution it used and a
`PASS` line. Keep those `.runtime/` directories; they are your fallback if
something goes wrong on air.

## The twenty minutes at a glance

| Elapsed | Step | What you will see |
| --- | --- | --- |
| 0–2 | [Inspect the bytes](#step-1--inspect-the-bytes) | Gzip header, decompressed records, a complete stack trace |
| 2–5 | [Decode the binary feed](#step-2--decode-the-binary-feed-through-cloud) | Ten records, IDs 0–9, deployed as a Cloud job |
| 5–7 | [Add a derived field](#step-3--add-a-derived-field-and-predict-the-result) | Five records flagged by a threshold |
| 7–10 | [Break the multiline boundary](#step-4--break-the-multiline-boundary) | Fifty fragments instead of ten events |
| 10–13 | [Repair it and inspect EOF](#step-5--repair-the-boundary-and-inspect-eof) | Complete traces, nested causes, last event flushed |
| 13–16 | [Measure a baseline](#step-6--measure-a-baseline-through-cloud) | Calibration, two rungs, a saved result |
| 16–19 | [Add work and compare](#step-7--add-processing-and-compare) | Same settings, different pipeline cost |
| 19–20 | [Review](#step-8--review-what-you-built) | Code, output, measurement, next experiment |

Timings are pacing budgets. Audience questions can stretch a step; none is
required to fill the time.

## Step 1 — Inspect the bytes

Pick the most recent binary rehearsal and look at its input before trusting
any tool's opinion of it:

```sh
binary_run=$(ls -td .runtime/binary-*/ | head -1)
od -An -tx1 -N32 "${binary_run}input"
gzip -dc "${binary_run}input" | head -3
gzip -dc "${binary_run}input" | wc -l
```

The first two bytes are `1f 8b`, the gzip magic number. Decompressed, you get
JSON lines, ten of them. Open the `binary` branch of `simulate.py`: each
record is compressed into its own member of a concatenated gzip stream, which
is what many devices and log shippers actually emit.

Now the other feed:

```sh
multiline_run=$(ls -td .runtime/multiline-*/ | head -1)
sed -n '1,12p' "${multiline_run}input"
```

Find the timestamp header, the exception line, two stack-frame lines, and the
`Caused by:` nested cause. The blank line between events is decoration; the
pipeline will use the timestamp as the boundary. Two separate questions are on
the table: how do I decompress this, and where does one message end?

## Step 2 — Decode the binary feed through Cloud

Read [`binary.yaml`](binary.yaml) in order: file input, `decompress` scanner
with `gzip`, a child `lines` scanner inside it, a mapping that parses JSON and
stamps `input_format: gzip-jsonl`, a JSONL file output. Then deploy it:

```sh
uv run rehearse.py binary
binary_run=$(ls -td .runtime/binary-*/ | head -1)
jq -s 'length' "${binary_run}received.jsonl"
jq -s 'map(.sequence) | sort' "${binary_run}received.jsonl"
jq -s 'sort_by(.sequence) | .[0]' "${binary_run}received.jsonl"
```

You should see `10`, `[0,1,2,...,9]`, and a record with its original fields
plus `input_format`. Order can vary because the pipeline is parallel; sorting
for inspection is how you separate reordering from loss.

Show the same run from the control plane. This is the difference between "a
file appeared" and "the platform ran my job on that node":

```sh
expanso-cli job describe office-hours-002-binary --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
expanso-cli job history  office-hours-002-binary --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

`describe` shows the version (it increments every rerun), the deployed
configuration, and a history ending in `Job completed successfully`. If the
audience asks where execution happens: the simulator wrote bytes, the control
plane scheduled a job onto the `role=office-hours` node, and that node ran the
YAML. `${binary_run}job.yaml` is the exact spec that was deployed.

## Step 3 — Add a derived field and predict the result

Inside the mapping in `binary.yaml`, aligned with `root.input_format`, add:

```bloblang
root.needs_attention = this.temperature_c >= 65
```

Before running, predict: synthetic temperatures run 60 to 69, so which
sequence IDs will be flagged, and how many? Then:

```sh
uv run rehearse.py binary
binary_run=$(ls -td .runtime/binary-*/ | head -1)
jq -s 'sort_by(.sequence) | map({sequence, temperature_c, needs_attention})' "${binary_run}received.jsonl"
jq -s '[.[] | select(.needs_attention == true)] | length' "${binary_run}received.jsonl"
```

Five flagged records, IDs 5 to 9. The helper only checks count and IDs; the
`jq` inspection is what verifies your new field. Change 65 to 68 for a second
variation if it helps: two flagged records.

Talk about flagging versus filtering. Filtering would change the output count
and require a deliberate change to the helper's assertion. Remove the line
afterwards, or keep it on purpose for the post-session commit. Do not let an
accidental edit become the next demo's baseline.

## Step 4 — Break the multiline boundary

Make sure a clean `uv run rehearse.py multiline` baseline exists. Then in
[`multiline.yaml`](multiline.yaml) replace only the scanner block:

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

Keep the mapping and output as they are. Run and inspect:

```sh
uv run rehearse.py multiline
multiline_run=$(ls -td .runtime/multiline-*/ | head -1)
jq -s 'length' "${multiline_run}received.jsonl"
jq -s '.[0:6] | map({line_count, message})' "${multiline_run}received.jsonl"
```

The helper exits non-zero. Ten five-line traces became fifty fragments, every
one with `line_count: 1`. Find a `Caused by:` fragment and a header fragment;
they used to be one event. More output messages here is not more throughput,
it is broken framing. The evidence directory stays for inspection and the
completed job stays visible in Cloud.

If there is no output file at all, that is a different failure. Check the job
with `expanso-cli job describe` and `job history`, and the node's terminal.
Do not explain an unrelated startup error as the intended demonstration.

## Step 5 — Repair the boundary and inspect EOF

Restore the exact `re_match` block. Point out that `(?m)^` matches a
timestamp at the start of any line, and everything until the next match
belongs to the current event.

```sh
uv run rehearse.py multiline
multiline_run=$(ls -td .runtime/multiline-*/ | head -1)
jq -s 'length' "${multiline_run}received.jsonl"
jq -s 'map(.line_count) | unique' "${multiline_run}received.jsonl"
jq -r 'select(.message | contains("sequence=0 ")) | .message' "${multiline_run}received.jsonl"
jq -r 'select(.message | contains("sequence=9 ")) | .message' "${multiline_run}received.jsonl"
```

Ten events, distinct line counts `[5]`, and complete first and last traces.
Sequence 9 has no timestamp after it; end of file flushed it. An open stream
that goes idle needs an explicit policy for its last event, and this finite
replay does not prove timeout-based flushing.

Look at `max_buffer_size: 65536`. Ask what happens to a trace larger than
64 KiB, or a trace whose body contains a date at column zero. Those are format
contracts, not things a parser can infer.

## Step 6 — Measure a baseline through Cloud

Switch to your second terminal. `bench.py` starts the harness from the
[`vendor/benchmarking`](../../vendor/benchmarking) submodule in Cloud mode: it
enrols this machine as a `bench-<host>` node in your workspace, deploys the
scenario as a Cloud job, generates load into it, counts what comes out, and
stops everything when the run ends. Its web UI binds to `127.0.0.1` only.

```sh
uv run bench.py passthrough
```

Walk the output through five stages:

1. `Cloud bench node: bench-... ` and the mode note: the harness's node
   connected and every benchmark will be a Cloud job.
2. Calibration measures how many output records emerge per input record
   (1.0 for passthrough).
3. The ladder rises from 1,000 to 5,000 records/s, three seconds each.
4. Processed rate, edge CPU, and RSS are reported per rung.
5. The result is saved as JSON under `.runtime/bench/results/`, with the
   machine, edge version, mode, node id, and the exact pipeline.

You should see two `pass` rows, `0` dropped, and a summary sentence ending in
"every rung passed. Raise the ladder to find the limit." Open the saved JSON
and find two things that explain the run: did the generator offer the target
rate, and did the pipeline keep up? A passing ladder at these rates is a
tested floor, not the machine's maximum.

Longer or steeper runs are one flag away:

```sh
uv run bench.py passthrough --ladder 1000,5000,10000,25000 --step-seconds 10
```

## Step 7 — Add processing and compare

Open `scenarios/json-transform.yaml` in the submodule and read its processor
chain: it reshapes records into an OTel-style envelope, derives fields, and
drops low-value records. Predict whether every input record will be forwarded.
Then run it with the same settings as the baseline:

```sh
uv run bench.py json-transform
```

Watch calibration: intentional filtering changes the raw receiver count, and
the harness uses the measured selectivity to report input-equivalent
throughput. Keep host, edge version, dataset, transport, batch, threads,
ladder, and step length identical between the two runs, and avoid other heavy
work on the machine while comparing.

Open both results side by side:

```sh
ls -t .runtime/bench/results/*.json | head -2 | xargs -n1 jq '{scenario: .scenario.id, mode, selectivity, steps: [.steps[] | {target_rate, process_rate, edge_cpu_avg, dropped, passed}]}'
```

Work through: did both generators offer the requested rate? Did each pipeline
pass the same rung? How did CPU differ at that rung? Was a lower receiver
count intentional filtering, temporary lag, or loss? What one variable would
you change next: duration, offered rate, batch size, or processor cost?

Three-second rungs keep a presentation moving. They do not support capacity
or cost claims. If a run fails, keep it and inspect it. Do not quietly lower
the target and present a replacement as though the first run passed.

## Step 8 — Review what you built

Back in the first terminal, show the simulator, the two YAML files, one
received output, one saved benchmark result, and the jobs in Cloud:

```sh
expanso-cli job list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

Review the actual changes you made and which check verified each one. Pick
one audience-inspired experiment from the table below as the next thing to
try.

The audience should leave able to identify the bytes arriving, the boundary of
one event, the transformation required, and the conditions behind a number.

## Try it yourself

Each is an experiment; not every outcome is pre-verified. Restore one before
starting the next.

| Try | Change | What to look for | Time |
| --- | --- | --- | --- |
| Slower source | `uv run simulate.py multiline --count 3 --interval 1` | Events arriving gradually; not a tailing test | 1 min |
| Different threshold | 65 → 68 in the added binary field | Two flagged records instead of five | 1–2 min |
| Extra context | Add `root.demo_site = "west"` to the binary mapping | A literal label on every record, not measured node identity | 1–2 min |
| Wrong boundary | Multiline pattern `(?m)^Caused by:` | Incorrect grouping and why | 2–3 min |
| Buffer limit | `max_buffer_size: 64` | Scanner error in the job's Cloud history; restore 65536 | 2 min |
| No batching | `uv run bench.py passthrough --batch 0` | Per-message cost with everything else unchanged | 3–5 min |
| Longer window | `uv run bench.py json-transform --step-seconds 20` | Behaviour over a longer rung | 2–3 min |
| Different scenario | `uv run bench.py log-parse` or `enrich-hash` | Where CPU goes for parse-heavy work | 3–5 min |

## Recovery at the keyboard

| Symptom | Next action |
| --- | --- |
| `No eligible node labelled {'role': 'office-hours'}` | Start the node per [CLUSTER.md](../../CLUSTER.md); confirm with `expanso-cli node list` |
| Credentials missing | Create `.env` at the repository root or beside this folder |
| YAML validation fails on deploy | Check indentation and the last changed line; the Cloud validator is stricter than the offline one |
| Assertion fails | Inspect the received records in the newest `.runtime/` directory, then the job in Cloud |
| No received file | `expanso-cli job describe` and `job history`; check the node is connected and labelled |
| Multiline count explodes | Confirm the timestamp scanner was restored |
| Binary IDs out of order | Sort and check completeness; order alone is not loss |
| Bench node never reaches Cloud mode | Read `.runtime/bench/serve.log`; `EXPANSO_BOOTSTRAP_TOKEN` is required the first time |
| Benchmark fails to start | `../../.runtime/bin/expanso-bench doctor` |
| Experiment eats the segment | Ctrl-C, check cleanup, use the saved baseline |

Validate configuration without deploying:

```sh
FEED_FILE=input OUTPUT_FILE=output expanso-edge validate binary.yaml multiline.yaml
expanso-cli job validate .runtime/binary-*/job.yaml --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

Validation proves syntax, not correct output. Rerun and inspect after a repair.
Cap an unexpected environment fix at about two minutes, then use the saved
baseline or move to the next independent step.

## Reference

**Binary feed.** Concatenated gzip members, one synthetic JSON event each.
The pipeline must decompress before it can parse. Ten events must yield
sequence IDs 0–9 exactly once. A gzip decoder does not decode device
protocols, images, Protobuf, or a proprietary binary schema; those need their
own framing and decoder. This is a concrete first non-text example.

**Multiline feed.** Five lines per event: timestamp header, exception, two
stack frames, nested cause. A new event starts only at an ISO date at column
zero. The next timestamp or EOF flushes the current event; an idle open stream
needs a separate timeout design. The buffer is capped at 64 KiB.

**Benchmark harness.** [expanso-io/benchmarking](https://github.com/expanso-io/benchmarking),
pinned as a submodule at commit `40bf64623e3d1aff3ad33671d8ea5d38ae698d71`.
Its CLI `run` subcommand only knows local mode; `bench.py` drives `serve`,
which is the Cloud path, through its localhost API. Record the commit, edge
version, machine, dataset, batch, offered rate, processed rate, and step
length with any number you quote. Do not compare numbers from different
machines as if they were the same.

## After the session

1. Stop the office-hours node with Ctrl-C and confirm with
   `expanso-cli node list` that it disconnected. `bench.py` stops its own
   node and server; check nothing is left with `pgrep -fl expanso`.
2. Review `git diff`. Undo temporary experiments, or keep the intentional
   demonstrated changes for the post-session commit.
3. Keep useful outputs and benchmark results; strip machine-specific paths
   before publishing result files.
4. Add the broadcast date, replay link, demonstrated commit, and changes made
   live. Separate later corrections from live artifacts.

## Offline checks

```sh
uv run check.py
uvx ruff check simulate.py rehearse.py bench.py check.py tests
uvx ruff format --check simulate.py rehearse.py bench.py check.py tests
```

These exercise both feed formats, invalid arguments, and session-relative
helper paths from an unrelated working directory. They never contact Cloud or
run the benchmark harness. See [VERIFICATION.md](VERIFICATION.md) for what was
last executed through Cloud and what it produced.
