# Session 002 verification

## Cloud execution — 9 September 2026

Both modes deployed to the `expanso-demos` Expanso Cloud cluster (control plane
v2.1.20) and ran on node `M5-Max.local`
(`d6a9eba7-c98f-4302-be57-284b473b2b4c`, Expanso Edge v2.1.21, macOS arm64):

| Mode | Cloud job | Result |
| --- | --- | --- |
| `binary` | `office-hours-002-binary` (redeployed; latest version 3) | 10 records, sequence IDs 0–9 exactly once |
| `multiline` | `office-hours-002-multiline` | 10 events, each with 5 lines and its nested cause |

Each run printed the node, job, version and execution the control plane used,
and the execution's observed state was `completed`. No standalone local engine
was started. Offline `uv run check.py` passed three tests, and Ruff lint/format
passed. Both YAML files pass offline `expanso-edge validate`; the rendered job
specs passed Cloud validation on deploy.

## Remaining boundaries

- Presenter/OBS rehearsal is separate and not covered here.
- The benchmark segment uses the external harness's own bounded Edge; it is not a
  Cloud measurement and makes no capacity claim.
- Gzip is a compressed structured feed, not a general proprietary binary decoder.
