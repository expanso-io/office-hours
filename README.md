# Expanso Pipeline Office Hours

Runnable examples from the live sessions, with synthetic feeds and checks you can repeat.

| Session | Topic | Status |
| --- | --- | --- |
| [001 — August 28, 2026](sessions/001/README.md) | CSV filtering, Parquet routing, dead letters, hashing | Reconstructed teaching code; original live export not recovered |
| [002 — week of September 7, 2026](sessions/002/README.md) | Non-text feeds, multiline events, benchmarking | Preparation; simulators rehearsed locally |

## Run an example

Requirements: `uv`, Python 3.11+, and `expanso-edge` on PATH.

```sh
uv run rehearse.py csv
uv run rehearse.py binary
uv run rehearse.py multiline
```

`uv` installs the dependencies declared in the script's inline metadata.
Each command generates a finite synthetic feed, starts a separate local Edge,
submits the YAML through its loopback API, checks received output, and stops Edge.
Input, output, and logs remain in ignored `.runtime/` folders for inspection.
The tests do not connect to Expanso Cloud. Output order is not guaranteed.

The feeds also work independently:

```sh
uv run simulate.py csv --count 20
uv run simulate.py binary --count 20 --interval 0.2 > feed.gz
uv run simulate.py multiline --count 20 --interval 0.2 > feed.log
```

Binary mode writes bytes to stdout. Redirect it to a file, not a terminal.
For a Cloud run, put the input file on the selected Edge machine and replace
`FEED_FILE` and `OUTPUT_FILE` with paths on that machine. These YAML files are
pipeline configs; wrap them in a job specification with an explicit node selector.

## Checks

```sh
uv run -m unittest discover -s tests -v
uvx ruff check simulate.py rehearse.py tests
FEED_FILE=input OUTPUT_FILE=output expanso-edge validate sessions/001/sensor.yaml sessions/002/binary.yaml sessions/002/multiline.yaml
```

Run all three rehearsals above before publishing changes. Presenter web UIs stay
on localhost. Publishing code here does not authorize hosting a presenter UI.

After each session, add the exact demonstrated YAML, sample input, expected
output, version used, and replay link to its session folder. Identify any later
corrections explicitly. Keep the benchmark harness in its upstream repository.
