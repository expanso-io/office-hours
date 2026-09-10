# Session 001 verification

## Packaging checks — 9 September 2026

The session now contains its own simulator, rehearsal helper, YAML, offline checks
and ignore rules. `uv run check.py` passed three tests: exact synthetic CSV output
from an unrelated working directory, invalid argument rejection, and session-local
simulator/configuration resolution by the rehearsal. The path check stops before
Edge startup; it is not a new engine execution result.

An isolated copy of this session, with no repository-root helpers present, also
passed all three tests, rehearsal CLI help and offline YAML validation. The checks
were launched from outside the copied session directory.

Ruff lint/format checks and offline `expanso-edge validate sensor.yaml` passed.
Host prerequisites remain `uv` and Expanso Edge; `uv` manages Python and the
declared PyYAML dependency. No repository-root Python helper is required.

## Historical local execution — 7 September 2026

The earlier common-helper rehearsal ran on macOS with Expanso Edge v2.1.21:

- Two warning JSON records and eight normal-record Parquet files.
- One malformed row routed to the dead-letter file.
- Raw sensor IDs replaced by SHA-256 hashes in valid output.
- The rehearsal stopped its isolated Edge process.

Parquet files were checked for count and envelope markers, not independently
decoded. These are local execution observations, not Cloud or recording evidence.
This folder is reconstructed teaching code, not the original live export.
The relocated full rehearsal has not been rerun against Edge in this packaging pass.
