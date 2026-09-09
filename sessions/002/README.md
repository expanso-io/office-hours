# Session 002 — non-text, multiline, and benchmarking

Prepared for the week of September 7, 2026. Broadcast date/time are not set here.

## Run of show (45 minutes)

1. 0–3 min: show the source bytes and predict how many output events should exist.
2. 3–13 min: gzip feed → decompress → JSON parsing → received records.
3. 13–25 min: stack traces → event boundary detection → one event per trace.
4. 25–37 min: benchmark a baseline and a transformation on the same host.
5. 37–45 min: audience variations and recap.

## Non-text feed

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

## Multiline feed

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

## Benchmarking

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

## Before air

- Run all three rehearsals and inspect actual output.
- Complete both benchmark smoke tests on the presentation machine.
- Check microphone and screen readability in a local recording.
- If demonstrating Cloud, separately verify selected node, running execution,
  received payload, and teardown. Local rehearsals do not establish Cloud proof.

After the call, record the exact files/commit demonstrated and add the replay link.
