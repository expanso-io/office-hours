# Session 002 verification

## Live three-console demo — 10 September 2026

Both feeds now stream over TCP into a `socket_server` input and fan out to a
file and stdout. Verified on the `expanso-demos` cluster with the office-hours
node connected:

- `demo.py binary deploy` deployed `office-hours-002-binary` (version 4) and
  waited for the scheduler; `demo.py binary feed` streamed two records a second;
  12 records reached `received.jsonl` in six seconds, the raw file began
  `1f 8b`, the node log carried the same 12 records on stdout, and both
  `raw` and `out` consoles showed them live.
- `demo.py multiline deploy` deployed `office-hours-002-multiline` (version 2);
  10 traces became 10 events with `line_count: 5` in the output console.
- `rehearse.py` for both modes, converted to the same TCP flow, passed (jobs
  at versions 8 and 3), streaming ten records and stopping the job.
- `expanso-edge validate` accepts both YAML files; the `tail` input was ruled
  out because it rejects `scanner` and has no multiline option.

## Cloud execution — 9 September 2026

Both modes deployed to the `expanso-demos` Expanso Cloud cluster (control plane
v2.1.20) and ran on node `M5-Max.local`
(`d6a9eba7-c98f-4302-be57-284b473b2b4c`, Expanso Edge v2.1.21, macOS arm64):

| Mode | Cloud job | Result |
| --- | --- | --- |
| `binary` | `office-hours-002-binary` (redeployed; latest version 3) | 10 records, sequence IDs 0–9 exactly once |
| `multiline` | `office-hours-002-multiline` | 10 events, each with 5 lines and its nested cause |

Each run printed the node, job, version and execution the control plane used,
and the execution's observed state was `completed`.

Benchmarks ran through `uv run bench.py`, which drives the pinned harness
(`vendor/benchmarking` at `40bf64623e3d1aff3ad33671d8ea5d38ae698d71`) in Cloud
mode. The harness enrolled node `bench-m5-max`
(`01cebf11-0c4d-4930-ba1a-61a0aa57cb03`) and deployed each run as a Cloud job:

| Scenario | 1,000/s | 5,000/s | Dropped | Mode |
| --- | --- | --- | --- | --- |
| `passthrough` | pass, edge CPU 9% | pass, edge CPU 29% | 0 | cloud |
| `json-transform` | pass, edge CPU 12% | pass, edge CPU 33% | 0 | cloud |

Metrics dataset, TCP input, TCP sink, batch 1,000, 3-second rungs. Host: Apple
M5 Max, 18 cores, 64 GB RAM. These are short operation checks, not capacity
claims. The bench node and server stopped cleanly after each run. No standalone local engine
was started. Offline `uv run check.py` passed three tests, and Ruff lint/format
passed. Both YAML files pass offline `expanso-edge validate`; the rendered job
specs passed Cloud validation on deploy.

## Remaining boundaries

- Presenter/OBS rehearsal is separate and not covered here.
- Benchmark rungs are three seconds at low rates; they establish operation, not
  capacity. The harness's CLI `run` subcommand is local-only and is not used.
- Gzip is a compressed structured feed, not a general proprietary binary decoder.
