# Session 002 — Binary feeds, multiline events, and measuring throughput

Prepared for the week of September 7, 2026. Broadcast date and time are not set here.

Session 001 dealt with one line per record. This session removes that comfort.
You will watch a feed that is not text stream into an edge node, frame a feed
where one event spans several lines, break both on purpose to see what failure
looks like, and then put a number on how fast this machine runs a pipeline.
Every pipeline is deployed through Expanso Cloud, every feed is live, and every
benchmark is a Cloud job too.

## What you will learn

- What actually arrives on the wire, byte by byte, and how to tell a gzip
  member from JSON.
- Why "what is one record" is a decision you make, not something a parser can
  infer, and what happens when you get it wrong.
- How to change a running pipeline and watch Cloud roll the new version onto
  the node without stopping the feed.
- How to read a benchmark result and tell *slow* from *lost*.

## The three consoles

The demo is three terminals side by side, all visible on stream, plus one
to type in. Each shows one stage of the same flow:

| Console | Command | What the audience sees |
| --- | --- | --- |
| 1 · Node | `expanso-edge run --no-watch --data-dir "$REPO/.expanso-edge"` | The node connect to Cloud, the job arrive, the pipeline go healthy |
| 2 · Raw | `uv run demo.py binary raw` | Bytes arriving from the device: gzip hex and its decompressed JSON, or stack-trace lines |
| 3 · Out | `uv run demo.py binary out` | One processed record per line, the moment the node writes it |
| you | `uv run demo.py binary deploy`, `feed`, edit YAML, `deploy` again | The cause of everything the other three show |

The pipeline listens on a TCP port (4002 for binary, 4003 for multiline).
The simulator connects to it like a device would, and also appends the same
bytes to a file so console 2 can show them. The pipeline fans out to a file
for console 3 and to stdout so the records also appear in console 1 and in
`expanso-cli job logs`. All live files sit under `.runtime/live/<mode>/`.

`uv run demo.py binary` (no action) prints every command for the current
folder so you can paste one per tab.

## Before you start

You need the [repository setup](../../README.md#setup) done, including the
benchmark submodule. Open four Ghostty tabs in this folder and an editor on
`binary.yaml` and `multiline.yaml`. In the tab you will type in:

```sh
set -a; source ../../.env; set +a
command -v uv expanso-cli expanso-edge go jq od gzip
uv run check.py
uv run demo.py binary
```

Every `command -v` should print a path, `check.py` should print `OK`, and the
last command prints the console commands. Start console 1 with the node
command it shows and wait for `Edge connected to orchestrator`. Confirm from
the Cloud side:

```sh
expanso-cli node list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

Your node should be `connected` with `role=office-hours`. Then warm every
path once so nothing downloads on air, and keep the results as fallbacks:

```sh
uv run rehearse.py binary
uv run rehearse.py multiline
uv run bench.py passthrough
```

`rehearse.py` is the offline correctness check: it deploys, streams ten
records over TCP, verifies the output, and stops the job. It is the same
pipeline as the live demo, just finite.

## The twenty minutes at a glance

| Elapsed | Step | What you will see |
| --- | --- | --- |
| 0–3 | [Bring the binary feed up](#step-1--bring-the-binary-feed-up) | Node gets the job, hex turns into JSON, records flow |
| 3–6 | [Change the running pipeline](#step-2--change-the-running-pipeline) | New version rolls out; console 3 changes shape, console 2 does not |
| 6–9 | [Bring the multiline feed up](#step-3--bring-the-multiline-feed-up) | Five lines in, one event out, one event behind |
| 9–12 | [Break the boundary](#step-4--break-the-boundary) | Five fragments per trace instead of one event |
| 12–13 | [Repair it](#step-5--repair-it) | Whole traces again |
| 13–17 | [Measure a baseline](#step-6--measure-a-baseline-through-cloud) | Two rungs pass, a saved result |
| 17–19 | [Add work and compare](#step-7--add-processing-and-compare) | Same settings, different cost |
| 19–20 | [Review](#step-8--review-what-you-built) | Jobs in Cloud, code, output, numbers |

Timings are pacing budgets. Questions can stretch a step; none is required
to fill the time.

## Step 1 — Bring the binary feed up

Read [`binary.yaml`](binary.yaml) with the audience: a `socket_server` input
on TCP, a `decompress` scanner for gzip with a child `lines` scanner inside
it, a mapping that parses JSON and stamps `input_format: gzip-jsonl`, and a
`broker` that fans out to a file and to stdout.

Deploy it. This is the moment console 1 lights up:

```sh
uv run demo.py binary deploy
```

Console 1 logs `Execution created`, then `Pipeline is ready`. The command
waits for the scheduler (it reconciles about every thirty seconds) and prints
`Running on 127.0.0.1:4002`. Start consoles 2 and 3, then the feed:

```sh
uv run demo.py binary raw     # console 2
uv run demo.py binary out     # console 3
uv run demo.py binary feed    # your tab, two records a second
```

Console 2 shows each gzip member as hex (`1f 8b ...`) and, beneath it, the
JSON it decompresses to. Console 3 shows the processed record within a
fraction of a second: same fields plus `input_format`. Console 1 shows the
same record on stdout. Point at the three in order: bytes, decode, result.

Ask where execution happens. The simulator wrote bytes to a socket. Cloud
scheduled a job onto the `role=office-hours` node, and that node ran the
YAML. Show it from the control plane in your tab:

```sh
expanso-cli job describe office-hours-002-binary --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

## Step 2 — Change the running pipeline

Leave the feed and both watchers running. In `binary.yaml`, inside the
mapping, aligned with `root.input_format`, add:

```bloblang
root.needs_attention = this.temperature_c >= 65
```

Predict out loud: temperatures cycle 60 to 99, so which records will be
flagged? Then redeploy:

```sh
uv run demo.py binary deploy
```

Console 1 shows the old execution stop and the new one start; Cloud shows
version 2 of the job. Console 2 does not change, the bytes are the same.
Console 3 starts showing `needs_attention` on every record, `true` for
temperatures at 65 and above. The feed reconnects by itself if the listener
was briefly gone during the rollout.

Talk about flagging versus filtering: a filter would make records vanish
from console 3 while console 2 kept scrolling, which is exactly the picture
you want an audience to hold onto. Remove the line afterwards or keep it on
purpose for the post-session commit; do not let an accidental edit become the
next demo's baseline. Stop this feed with Ctrl-C in its tab and the job with:

```sh
uv run demo.py binary stop
```

## Step 3 — Bring the multiline feed up

Same shape, different framing. Read [`multiline.yaml`](multiline.yaml): the
scanner is `re_match` on `(?m)^\d{4}-\d{2}-\d{2}T`, so a new event starts
only where a line begins with an ISO timestamp. Deploy, restart consoles 2
and 3 in multiline mode, start the feed:

```sh
uv run demo.py multiline deploy
uv run demo.py multiline raw
uv run demo.py multiline out
uv run demo.py multiline feed
```

Console 2 shows five lines per trace: timestamp header, exception, two stack
frames, `Caused by:`. Console 3 shows one JSON event per trace with
`line_count: 5`. Watch the timing: console 3 is one event behind console 2.
The scanner cannot know a trace is finished until it sees the next
timestamp. That lag is the framing decision made visible, and an idle stream
needs an explicit policy for its last event.

## Step 4 — Break the boundary

Leave everything running. In `multiline.yaml` replace only the scanner:

```yaml
      re_match:
        pattern: '(?m)^\d{4}-\d{2}-\d{2}T'
        max_buffer_size: 65536
```

with:

```yaml
      lines: {}
```

Redeploy:

```sh
uv run demo.py multiline deploy
```

Console 3 changes character immediately: five records per trace, every one
`line_count: 1`, `Caused by:` lines arriving as events of their own. Console
2 is unchanged. More output here is not more throughput, it is broken
framing, and a downstream consumer would never be able to reassemble it.

If console 3 goes silent instead, that is a different failure. Look at
console 1 and at `expanso-cli job history office-hours-002-multiline`. Do
not explain an unrelated error as the intended demonstration.

## Step 5 — Repair it

Restore the exact `re_match` block and redeploy. Console 3 returns to whole
traces. Point at `max_buffer_size: 65536` and ask what happens to a trace
larger than 64 KiB, or one whose body has a date at column zero. Those are
format contracts, not things a parser can infer. Stop the feed and the job:

```sh
uv run demo.py multiline stop
```

## Step 6 — Measure a baseline through Cloud

`bench.py` starts the harness from the
[`vendor/benchmarking`](../../vendor/benchmarking) submodule in Cloud mode:
it enrols this machine as a second node named `bench-<host>`, deploys the
scenario as a Cloud job, generates load into it, counts what comes out, and
stops everything when the run ends. Its web UI binds to `127.0.0.1` only.
Run it in your tab:

```sh
uv run bench.py passthrough
```

Console 1 stays quiet: the benchmark runs on the bench node, not the
office-hours node, so the two never interfere. Walk the output through five
stages: the bench node connects and the mode note confirms every run is a
Cloud job; calibration measures output records per input record; the ladder
rises from 1,000 to 5,000 records/s, three seconds each; processed rate,
edge CPU, and RSS are reported per rung; the result is saved as JSON under
`.runtime/bench/results/` with machine, edge version, mode, node id, and
the exact pipeline.

You should see two `pass` rows, `0` dropped, and a summary ending in "every
rung passed. Raise the ladder to find the limit." A passing ladder at these
rates is a tested floor, not the machine's maximum. Steeper is one flag away:

```sh
uv run bench.py passthrough --ladder 1000,5000,10000,25000 --step-seconds 10
```

## Step 7 — Add processing and compare

Open `scenarios/json-transform.yaml` in the submodule and read its processor
chain: it reshapes records into an OTel-style envelope, derives fields, and
drops low-value records. Predict whether every input record will be
forwarded. Run it with the same settings:

```sh
uv run bench.py json-transform
```

Watch calibration: intentional filtering changes the raw receiver count, and
the harness uses the measured selectivity to report input-equivalent
throughput. Compare the two results:

```sh
ls -t .runtime/bench/results/*.json | head -2 | xargs -n1 jq -c '{scenario: .scenario.id, mode, selectivity, steps: [.steps[] | {target_rate, process_rate, edge_cpu_avg, dropped, passed}]}'
```

Did both generators offer the requested rate? Did each pipeline pass the same
rung? How did CPU differ? Was a lower receiver count filtering, lag, or loss?
What one variable would you change next? Three-second rungs keep a
presentation moving; they do not support capacity claims. If a run fails,
keep it and inspect it rather than quietly lowering the target.

## Step 8 — Review what you built

Show the jobs in Cloud, then the code and one saved result:

```sh
expanso-cli job list --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

The audience should leave able to identify the bytes arriving, the boundary
of one event, the transformation required, and the conditions behind a
number.

## Try it yourself

Restore between experiments. All of these work with the feed left running.

| Try | Change | What to look for | Time |
| --- | --- | --- | --- |
| Faster feed | `uv run demo.py binary feed --interval 0.1` | Console 3 keeps up; note edge CPU in console 1 | 1 min |
| Different threshold | 65 → 90 in the added field | Only the top of each temperature cycle flags | 1–2 min |
| Filter instead of flag | Add `root = if this.temperature_c < 65 { deleted() }` | Console 3 shows gaps; console 2 does not | 2 min |
| Extra context | `root.demo_site = "west"` | A literal label on every record, not measured node identity | 1 min |
| Wrong boundary | Multiline pattern `(?m)^Caused by:` | Events split in the wrong place | 2–3 min |
| Buffer limit | `max_buffer_size: 64` | Scanner error in console 1 and in the job's Cloud history; restore 65536 | 2 min |
| Watch Cloud logs | `expanso-cli job logs office-hours-002-binary ...` | The stdout fan-out streamed from the control plane | 1 min |
| No batching | `uv run bench.py passthrough --batch 0` | Per-message cost with everything else unchanged | 3–5 min |

## Recovery at the keyboard

| Symptom | Next action |
| --- | --- |
| `waiting for matching nodes` | The scheduler has not reconciled yet; `deploy` waits up to eight minutes. If it never runs, check `expanso-cli node list` shows `role=office-hours` and `connected` |
| Feed prints `waiting for 127.0.0.1:4002` | The job is not running yet, or was redeployed; it reconnects by itself |
| Console 3 silent, console 2 scrolling | Job crashed on the new YAML: console 1 and `expanso-cli job history` |
| Console 2 shows only hex | The decompress in `demo.py raw` waits for a whole member; give it a record or two |
| Credentials missing | Create `.env` at the repository root or beside this folder |
| YAML rejected on deploy | Indentation and the last changed line; the Cloud validator is stricter than the offline one |
| Bench node never reaches Cloud mode | `.runtime/bench/serve.log`; `EXPANSO_BOOTSTRAP_TOKEN` is required the first time |
| Anything stuck | Ctrl-C the feed, `uv run demo.py <mode> stop`, redeploy |

Validate without deploying:

```sh
PORT=4002 OUTPUT_FILE=out expanso-edge validate binary.yaml multiline.yaml
expanso-cli job validate .runtime/live/binary/job.yaml --endpoint "$EXPANSO_ENDPOINT" --api-key "$EXPANSO_API_KEY"
```

## Reference

**Binary feed.** Concatenated gzip members, one synthetic JSON event each,
pushed over TCP. The pipeline must decompress before it can parse. A gzip
decoder does not decode device protocols, images, Protobuf, or a proprietary
binary schema; those need their own framing and decoder.

**Multiline feed.** Five lines per event: timestamp header, exception, two
stack frames, nested cause. A new event starts only at an ISO date at column
zero. The next timestamp flushes the current event, so live output runs one
event behind; a closed connection flushes the last one. Buffer capped at
64 KiB.

**Why TCP and not a tailed file.** The `tail` input in Edge v2.1.21 is
line-oriented and accepts no scanner, so it cannot frame gzip members or
stack traces. `socket_server` takes any scanner and is how a device or
shipper would actually deliver these bytes.

**Benchmark harness.** [expanso-io/benchmarking](https://github.com/expanso-io/benchmarking),
pinned as a submodule at `40bf64623e3d1aff3ad33671d8ea5d38ae698d71`. Its
CLI `run` subcommand only knows local mode; `bench.py` drives `serve`, the
Cloud path, through its localhost API. Record commit, edge version, machine,
dataset, batch, offered rate, processed rate, and step length with any number
you quote.

## After the session

1. Ctrl-C any feed. `uv run demo.py binary stop` and `... multiline stop`.
   Ctrl-C the node in console 1 and confirm with `expanso-cli node list`
   that it disconnected. `bench.py` stops its own node and server; check with
   `pgrep -fl expanso` that nothing is left.
2. Review `git diff`. Undo temporary experiments, or keep intentional
   demonstrated changes for the post-session commit.
3. Keep useful outputs and results; strip machine-specific paths before
   publishing result files.
4. Add the broadcast date, replay link, demonstrated commit, and changes made
   live. Separate later corrections from live artifacts.

## Offline checks

```sh
uv run check.py
uvx ruff check simulate.py rehearse.py demo.py bench.py check.py tests
uvx ruff format --check simulate.py rehearse.py demo.py bench.py check.py tests
```

These exercise both feed formats, invalid arguments, and session-relative
helper paths from an unrelated working directory. They never contact Cloud.
See [VERIFICATION.md](VERIFICATION.md) for what was last executed through
Cloud and what it produced.
