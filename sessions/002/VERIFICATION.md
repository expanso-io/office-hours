# Session 002 verification

## Packaging checks — 9 September 2026

The session contains its own binary/multiline simulator, rehearsal helper, YAML,
offline checks and ignore rules. `uv run check.py` passed three tests covering both
feed modes: exact source output from an unrelated working directory, invalid
argument rejection, and session-local simulator/configuration resolution by the
rehearsal. The path check stops before Edge startup; it is not fresh engine evidence.

An isolated copy of this session, with no repository-root helpers present, also
passed all three tests, rehearsal CLI help and offline validation of both YAML files.
The checks were launched from outside the copied session directory.

Ruff lint/format checks and offline validation of both YAML files passed. No
repository-root Python helper or Session 001 file is required. `uv` and Expanso Edge
remain host prerequisites; `uv` manages Python and declared PyYAML dependencies.
The optional benchmark segment uses the separate upstream tool described in README.

## Historical local execution — 7–8 September 2026

On macOS with Expanso Edge v2.1.21:

- Gzip input produced ten records, sequence IDs 0–9 exactly once.
- Multiline input produced ten events with five lines and a nested cause each.
- A threshold edit produced five flagged records.
- Replacing timestamp framing with line framing produced 50 fragments and the
  expected failed assertion; restoring it produced ten complete events, including EOF.
- The helpers stopped their isolated Edge processes after success or failure.

Historical benchmark smokes used upstream commit
`40bf64623e3d1aff3ad33671d8ea5d38ae698d71`: Apple M5 Max, 18 cores, 64 GB RAM,
metrics dataset, TCP input/sink, batch 1,000, three-second rungs at 1,000/s and 5,000/s.
Passthrough and JSON-transform runs passed both rungs with zero reported drops.
Other local work overlapped part of that window. These are operation smokes, not
capacity or comparative performance claims. Filter throughput was input-equivalent.

The relocated full rehearsals and benchmark were not rerun in this packaging pass.
Presenter/recording and any Cloud path still need separate acceptance.
