# 005 - Three tiny models, one stream, three ways in

**Session:** Pipeline Office Hours #00005, Thu 2026-10-22, 09:00-09:30 PT
**Stream:** https://www.twitch.tv/expansoio

Four pumps send numeric readings at 20 per second and operator notes every 6
seconds into one Expanso Edge node. Three tiny models run on the same machine,
wired into the pipeline in three different ways: a 63 kB scikit-learn
IsolationForest through `subprocess`, `qwen2.5:0.5b` through `ollama_chat`, and
`SmolLM2-360M` over a grammar-constrained `http` call to `llama-server`. The
models score and extract; the pipeline decides what leaves the node.

## What you will be able to do

By the end you can wire a Python model, an Ollama model, and an
OpenAI-compatible HTTP model into one Expanso Edge pipeline, measure each
model's latency inside the record, join operator notes to anomalous sensor
readings in memory on the node, and roll back a schema change when a tiny
language model is asked to make a severity judgement it cannot support.

## The demo

| Demo | Page | What it proves |
| --- | --- | --- |
| [`demos/tiny-models`](demos/tiny-models) | 127.0.0.1:19500 | Three model wiring paths on one stream: Python drops ~95% of healthy readings on the node, two sub-1B language models extract the part from each operator note, and Bloblang joins the note to the anomaly |

| Path | Processor | Model | Job in the pipeline |
| --- | --- | --- | --- |
| Python | `subprocess` | scikit-learn `IsolationForest` (32 trees, 63 kB) | Scores every reading (`temp_c`, `vibration_mm_s`, `current_a`); normal readings are deleted on the node |
| Ollama | `ollama_chat` | `qwen2.5:0.5b` (Q4_K_M, 398 MB) | Reads each operator note in JSON mode and returns `{"part": "...", "symptom": "..."}` |
| Direct HTTP | `http` | `SmolLM2-360M-Instruct` Q8_0 (386 MB) via `llama-server` on `127.0.0.1:18085` | Reads the same note with a `json_schema` enum so `part` is guaranteed to be one of eight machine parts |

## Before you start

You need `expanso-edge`, `expanso-cli`, `ollama`, `llama-server` (`llama.cpp`),
`uv`, `jq`, and `just` on your PATH, with the machine's Ollama service running
on `127.0.0.1:11434`.

For `just up`, you also need an Expanso Cloud workspace and an enrolled
`role=office-hours` node (see the top-level [Setup](../../README.md#setup)):
copy `demos/tiny-models/.env.example` to `.env`, fill in `EXPANSO_ENDPOINT` and
`EXPANSO_API_KEY`, and set `chmod 600 .env`. To rehearse on this machine with
no Cloud credentials, run `just up-offline`.

## Run

```sh
just warm        # train the IsolationForest, download the GGUF, pull the Ollama model
just validate    # lint, unit tests, and offline validation of all four stages
just up          # deploy stage 1 through Expanso Cloud and start the feed and cockpit
just status
```

Open `http://127.0.0.1:19500`. On stage 1, every reading and note passes
straight through the node (`Records in` matches `Records out` at ~20 records/s).

Move through the revisions the same way the live session does (see
[RUN-THROUGH.md](RUN-THROUGH.md) for the exact pastes and presenter script):

```sh
just stage 2     # Change 1: Python IsolationForest scores readings and drops healthy ones
just stage 3     # Change 2: Ollama + direct HTTP extract parts from notes and join on the node
just break       # stop llama-server while the pipeline keeps running
just heal        # start llama-server again; recovery happens on the next note
just stage 4     # Wrong on purpose: ask the 360M model for problem_reported: boolean
just rollback    # roll the job back to stage 3's spec
just down        # stop everything, unload the Ollama model, and run the teardown audit
```

After each deploy or rollback, wait one note interval (6 seconds) so the
in-memory `notes` cache on the node receives a fresh operator note for
`pump-03`.

## What happens when it is wrong

Every model call runs inside a `branch` with a `catch` block that writes
`{"error": error()}` onto the record instead of dropping the stream. When
`just break` stops `llama-server`, alerts keep leaving the node with Python's
anomaly score and Ollama's note extraction intact while `direct` records the
connection failure and the cockpit's `Degraded calls` counter increments. When
`just stage 4` asks the 360M model whether a note reports a problem, the model
flags routine strainer cleaning as `problem_reported: true`, showing why tiny
language models belong on extraction while the pipeline owns the decision.

## Check the output

`just validate` runs `ruff`, `expanso-edge validate`, `expanso-cli job validate
--offline`, and `pytest` across the scorer, pipeline stages, cockpit ledger,
and house rules. `just teardown-check` verifies that ports `19500`, `19501`,
`18085`, `19510`, and `19511` are closed, no demo process is running, the
Ollama model is unloaded from memory, and the Expanso Cloud job is stopped with
the node disconnected.

## Truth boundary

Four pumps' readings and notes come from `feed.py`, a deterministic generator
built for this session. Everything that happens to them is real: one Expanso
Edge node, one Cloud-deployed job (`office-hours-005-models`), three models
running on this machine, and only the records shown in the cockpit tail leave
the node.
