# Expanso Pipeline Office Hours

Runnable examples from the live sessions, with synthetic feeds and checks you can repeat.

**Every session runs on the Expanso Cloud cluster, never on a standalone local
engine.** The feed is generated on the edge node, the job is deployed through the
control plane with `expanso-cli job deploy`, and the job, execution, and node are
inspected in Expanso Cloud. See [CLUSTER.md](CLUSTER.md) for the one-time node
setup and the credentials layout.

Each session is self-contained. Open or copy its directory: its simulator,
rehearsal helper, YAML, tests, verification notes and runtime output live together.
There are no executable helpers at the repository root.

| Session | Topic | Entry point |
| --- | --- | --- |
| [001 — August 28, 2026](sessions/001/README.md) | CSV filtering, Parquet routing, dead letters, hashing | `cd sessions/001`, then `uv run rehearse.py csv` |
| [002 — week of September 7, 2026](sessions/002/README.md) | Non-text feeds, multiline events, benchmarking | `cd sessions/002`, then `uv run rehearse.py binary` or `uv run rehearse.py multiline` |

Run `uv run check.py` within either session for its offline checks. Those never
contact Cloud. Follow that session's README for prerequisites, standalone feed
commands, expected outputs, validation and cleanup. Scripts also resolve their
files correctly when invoked by full path from another directory. New runtime
files stay under that session's ignored `.runtime/`.

Session 001 is reconstructed teaching code, not the original live export.
Session 002 remains preparation, not a published recording. Its benchmark segment
uses the separately maintained [benchmarking tool](https://github.com/expanso-io/benchmarking),
which is an explicit external prerequisite rather than a root-level helper.

After each session, keep the demonstrated YAML, sample input, expected output,
version used and replay link in that session's folder. Identify later corrections
explicitly. Presenter web UIs stay on localhost; publishing code does not authorize
hosting a presenter UI.

[Historical cross-session verification](VERIFICATION.md) is retained for context;
each session contains the verification notes needed to travel on its own.
