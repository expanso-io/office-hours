# Office Hours #00005 presenter run-through

**Title:** Three tiny models, one stream, three ways in
**Date:** Thu 2026-11-05, 09:00-09:30 PT (30 minutes)
**Working directory:** `sessions/005/demos/tiny-models`
**Cockpit URL:** `http://127.0.0.1:19500` (1080p display, split layout with cockpit left and terminal right at 110-125% zoom)

## Pre-flight

### Evening before and T-30 minutes

Log in to Expanso Cloud and Claude before opening the stream layout so neither sign-in prompt, account chooser, email address, nor OAuth URL ever appears on screen.

Run from `sessions/005/demos/tiny-models`:

```sh
just warm
just doctor
just validate
just up
just status
just down
just teardown-check
```

Confirm:
- `just warm` prints sizes for all three models (`IsolationForest` 63,430 bytes, `qwen2.5:0.5b` ~398 MB, `smollm2-360m` ~386 MB).
- `just doctor` passes PATH (`expanso-edge`, `expanso-cli`, `ollama`, `llama-server`, `uv`, `jq`, `just`), Ollama on `127.0.0.1:11434`, `.env` mode `600`, Expanso Cloud reachability, and the enrolled `role=office-hours` node.
- `just validate` passes `ruff`, `expanso-edge validate`, `expanso-cli job validate --offline`, and `pytest`.
- `just up` connects the `role=office-hours` node, deploys `office-hours-005-models` at version 1, preloads `qwen2.5:0.5b` in Ollama, and opens `http://127.0.0.1:19500`.
- `just down` and `just teardown-check` end with `teardown clean: ports, processes, runtime, Ollama model, containers. Cloud: job stopped, office-hours node disconnected`.

### T-10 minutes (before going live)

1. Confirm you are already signed in to Expanso Cloud and Claude before starting the broadcast.
2. Run `just doctor` on the machine you will stream from, then bring up stage 1:

```sh
just doctor
just up
```

Open `http://127.0.0.1:19500` and keep the cockpit browser tab and a terminal inside `sessions/005/demos/tiny-models` visible on screen. Never display `.env` or any directory above the demo folder.

## On-screen figures worth saying aloud

Read the live cockpit numbers rather than quoting runbook estimates:
- **Model sizes on disk:** `63.4 kB` (`IsolationForest`), `397.8 MB` (`qwen2.5:0.5b`), and `386.4 MB` (`smollm2-360m`).
- **Filter rate after Change 1:** read `Records out` and `Kept on this node` from the flow strip (`5.4 /s` out and `73.1%` kept while `pump-03` is faulting, settling to `0.2 /s` out and `99.0%` kept between fault windows).
- **Python latency and anomaly score:** read the Python median call time (`~1.4-3.2 ms`) and the IsolationForest score on each alert (`0.62-0.75`).
- **Language model latencies on the host:** read the measured `Ollama` and `Direct call` median and 95th percentile timings from the table (`~45-150 ms` on Apple Silicon or GPU; `~204-310 ms` median and up to `1.30 s` p95 on CPU-only hosts).
- **Outage counters during `just break`:** read `Degraded calls` (climbing, e.g. `1,285`) next to `Dead letters: 0`.

---

## 30-minute spine

### 0:00-2:00 - Cold open

**On screen:** Cockpit at `http://127.0.0.1:19500` and terminal in `sessions/005/demos/tiny-models`.

**Command:**

```sh
just status
```

**What to point out:**
- Header shows `Expanso Cloud · office-hours-005-models · version 1` (polled from `expanso-cli job describe`) and `Python 60s: 0 calls`.
- State the three wiring paths cleanly: only the Python model uses `subprocess`; `qwen2.5:0.5b` uses `ollama_chat`, and `SmolLM2-360M` uses an OpenAI-compatible `http` processor against `llama-server`.
- Read the three disk footprints aloud from `The three models`: `63.4 kB`, `397.8 MB`, and `386.4 MB`, with `0` calls on version 1.
- Frame the question: three tiny models wired into one Expanso Edge pipeline in three different ways, and the pipeline, not a model, decides what leaves the node.

### 2:00-5:00 - Baseline stream on version 1

**Say at minute 2 (truth boundary):**
> "Four pumps' readings and notes come from a generator built for this session; everything that happens to them is real: one Expanso Edge node, one Cloud-deployed job, three models running on this machine, and only what you see in the tail left the node."

**What to point out on the cockpit:**
- `Records in` (~20.2 /s) matches `Records out` (~20.2 /s).
- `Kept on this node` is `0.0%`.
- `Bytes in` (~2.1 kB/s) and `Bytes out` (~2.7 kB/s) move in lockstep. State the unit as **kilobytes per second (`kB/s`)**, not megabytes or kilobits per second.
- `feed.py` sends four pumps' readings (`pump-01` through `pump-04`) at 20/s and one operator note every 6 seconds into `127.0.0.1:19501/ingest`.

### 5:00-11:00 - Change 1: Python IsolationForest over `subprocess` (version 2)

**Action:** Paste `pipelines/paste/change-1.yaml` into `live.cloud.yaml` directly above `# Paste each change above this line.`:

```yaml
      # Change 1: the Python model scores every reading on this node, and only
      # the anomalies leave. Notes pass straight through.
      - switch:
          - check: this.kind == "reading"
            processors:
              - mutation: meta t0 = timestamp_unix_nano()
              - branch:
                  request_map: root = this.without("kind", "asset", "ts")
                  processors:
                    - subprocess:
                        name: ${OH5_UV:uv}
                        args: [run, --project, "${OH5_DEMO_DIR}", --frozen, --quiet, python, "${OH5_DEMO_DIR}/scorer/score.py"]
                  result_map: |
                    root.python = this
                    root.python.call_ms = ((timestamp_unix_nano() - metadata("t0")) / 1000).round() / 1000
              - catch:
                  - mutation: 'root.python = {"error": error()}'
              - mapping: root = if this.python.anomaly == false { deleted() } else { this }
      # Paste change 2 below change 1.
```

**Deploy command (or `just stage 2`):**

```sh
just deploy
```

**Read the cockpit (do not quote static estimates):**
- Header advances to `version 2`.
- Read `Records out` and `Kept on this node` directly from the cockpit as the 10-second window settles: during a `pump-03` fault window it reads around `5.4 /s` out (`73.1%` kept), and between fault windows it settles to `0.2 /s` out (`99.0%` kept on the node).
- Point out `pump-03` overheating readings (`temp_c` climbing to `81.0 °C`, `vibration_mm_s` to `6.2 mm/s`) in `Latest anomaly` and read the IsolationForest score aloud (`0.62` to `0.75`).
- Read the Python column's size (`63.4 kB`) and measured median call time (`~1.4 ms` on Apple Silicon, `~3.2 ms` on CPU-only Linux/WSL, 95th percentile `~2.0-5.2 ms`).

### 11:00-19:00 - Change 2: Ollama + direct HTTP + in-memory join (version 3)

**Action:** Replace the `processors:` block in `live.cloud.yaml` with `pipelines/paste/change-2.yaml` (stage 3's full `processors:` block verbatim, which keeps Change 1 above `# Paste change 2 below change 1.` and adds Change 2 below it), or run `just stage 3`:

```yaml
    processors:
      # Change 1: the Python model scores every reading on this node, and only
      # the anomalies leave. Notes pass straight through.
      - switch:
          - check: this.kind == "reading"
            processors:
              - mutation: meta t0 = timestamp_unix_nano()
              - branch:
                  request_map: root = this.without("kind", "asset", "ts")
                  processors:
                    - subprocess:
                        name: ${OH5_UV:uv}
                        args: [run, --project, "${OH5_DEMO_DIR}", --frozen, --quiet, python, "${OH5_DEMO_DIR}/scorer/score.py"]
                  result_map: |
                    root.python = this
                    root.python.call_ms = ((timestamp_unix_nano() - metadata("t0")) / 1000).round() / 1000
              - catch:
                  - mutation: 'root.python = {"error": error()}'
              - mapping: root = if this.python.anomaly == false { deleted() } else { this }
      # Paste change 2 below change 1.
      # Change 2: two language models read each note, one through Ollama and
      # one by a direct HTTP call, and an anomalous reading picks up the last
      # note about its pump.
      - switch:
          - check: this.kind == "note"
            processors:
              - mutation: meta t0 = timestamp_unix_nano()
              - branch:
                  request_map: root = this.text
                  processors:
                    - ollama_chat:
                        server_address: ${OLLAMA_URL:http://127.0.0.1:11434}
                        model: ${OLLAMA_MODEL:qwen2.5:0.5b}
                        system_prompt: 'Read the factory maintenance note. Reply with JSON {"part": "<the machine part the note is about>", "symptom": "<what the note says about it, in a few words>"}.'
                        prompt: 'Maintenance note: "${! content() }"'
                        response_format: json
                        temperature: 0
                        max_tokens: 60
                  result_map: |
                    root.ollama = content().string().parse_json().catch({"unparsed": content().string()})
                    root.ollama.call_ms = ((timestamp_unix_nano() - metadata("t0")) / 1000).round() / 1000
              - catch:
                  - mutation: 'root.ollama = {"error": error()}'
              - mutation: meta t0 = timestamp_unix_nano()
              - branch:
                  request_map: |
                    root.model = "${DIRECT_MODEL_NAME:smollm2-360m}"
                    root.temperature = 0
                    root.max_tokens = 40
                    root.messages = [
                      {"role": "system", "content": "Name the machine part this maintenance note is about. Use none if it names no part."},
                      {"role": "user", "content": this.text}
                    ]
                    root.response_format = {"type": "json_schema", "json_schema": {"name": "part", "schema": {
                      "type": "object",
                      "properties": {
                        "part": {"type": "string", "enum": ["bearing", "seal", "motor", "coupling", "strainer", "instrument", "valve", "none"]}
                      },
                      "required": ["part"]
                    }}}
                  processors:
                    - http:
                        url: ${DIRECT_MODEL_URL:http://127.0.0.1:18085/v1/chat/completions}
                        verb: POST
                        headers:
                          Content-Type: application/json
                          Authorization: Bearer ${DIRECT_MODEL_TOKEN:none}
                        timeout: 10s
                        retries: 0
                  result_map: |
                    root.direct = this.choices.index(0).message.content.parse_json().catch({"unparsed": this.choices.index(0).message.content})
                    root.direct.call_ms = ((timestamp_unix_nano() - metadata("t0")) / 1000).round() / 1000
              - catch:
                  - mutation: 'root.direct = {"error": error()}'
              - cache:
                  resource: notes
                  operator: set
                  key: ${! this.asset }
                  value: ${! content() }
          - check: this.kind == "reading"
            processors:
              - branch:
                  request_map: root = this.asset
                  processors:
                    - cache:
                        resource: notes
                        operator: get
                        key: ${! content() }
                  result_map: root.last_note = if this == null { null } else { this.without("kind", "asset") }
              - catch:
                  - mutation: root.last_note = null
      # Paste each change above this line.
      - mutation: root.left_node_at = now()
```

**Deploy command (or primary CLI path `just stage 3`):**

```sh
just stage 3
```

(If you pasted into `live.cloud.yaml`, run `just deploy`; `just deploy` refuses a stage-3 file that is missing the `subprocess` processor from Change 1, and the cockpit badge turns red if `version >= 3` has zero Python calls in the last 60 seconds.)

**Important timing note:** After a redeploy the node's in-memory `notes` cache starts empty, so `pump-03`'s `last_note` is `null` until the next note arrives. Wait one note interval (6 seconds) after each deploy so the note lands in the cache and the join populates.

**Read the cockpit:**
- Header advances to `version 3`, and the `Python 60s` badge stays green/neutral because Python continues filtering readings.
- Wait one note interval (6 seconds).
- `Latest note` shows `"Drive end bearing running hot and getting noisier."` with:
  - `ollama`: free-form JSON (`{"part": "drive end bearing", "symptom": "running hot and getting noisier", "call_ms": ...}`).
  - `direct`: grammar-constrained enum (`{"part": "bearing", "call_ms": ...}`).
- `Latest anomaly` shows the `pump-03` reading (`python.anomaly: true`) joined with `last_note` containing both language model extractions.
- Read the measured model timings on screen (and note whether the host is GPU/Apple Silicon or CPU-only):
  - `Python` (`63.4 kB`): median `~1.4-3.2 ms`, touches ~99% of records in (every reading).
  - `Ollama` (`qwen2.5:0.5b`, `397.8 MB`): median `~45-110 ms` on Apple Silicon/GPU, `~200-310 ms` on CPU-only hosts; touches ~1% of records in (notes only).
  - `Direct call` (`smollm2-360m`, `386.4 MB`): median `~80-150 ms` on Apple Silicon/GPU, `~200-310 ms` median (up to `~1.30 s` 95th percentile) on CPU-only hosts; touches ~1% of records in (notes only).

### 19:00-23:00 - Break and heal (no job revision)

Keep the terminal visible next to the cockpit so viewers see `just break` and `just heal` run.

**Break command:**

```sh
just break
```

**What to point out (attribute resilience to `catch`, not caching or dead letters):**
- Wait one note interval (6 seconds).
- `llama-server` on `127.0.0.1:18085` is stopped.
- Say: **"The `catch` block writes the error onto the record and the record keeps moving."**
- Point out that `Dead letters` stays `0` while `Degraded calls` climbs (read the live `Degraded calls` number from the flow strip, e.g. `1,285`). What keeps the stream alive is the `catch` block around each model call, not caching and not a dead-letter queue (`notes` is the in-memory join cache, and the dead-letter file only catches cockpit sink output failures).
- `Direct call` shows `call failed` in the tail while Python anomaly scores and Ollama extractions keep arriving.

**Heal command:**

```sh
just heal
```

**What to point out:**
- Wait one note interval (6 seconds).
- The next `pump-03` note succeeds against `127.0.0.1:18085`, overwrites the cached note in `notes`, and `Latest note` and `Latest anomaly` show `direct.part: "bearing"` again.

### 23:00-27:00 - Wrong on purpose (version 4) and rollback (version 5)

**Primary path:** Deploy stage 4 with `just stage 4`, inspect the schema change with `just versions-diff 3 4` instead of hand-editing `live.cloud.yaml`, and wait for the strainer verdict with `just expect strainer`:

```sh
just stage 4
just versions-diff 3 4
just expect strainer
```

`just versions-diff 3 4` shows the exact schema addition on screen:

```yaml
                      "properties": {
                        "part": {"type": "string", "enum": ["bearing", "seal", "motor", "coupling", "strainer", "instrument", "valve", "none"]},
                        "problem_reported": {"type": "boolean"}
                      },
                      "required": ["part", "problem_reported"]
```

**What to point out:**
- Header advances to `version 4`.
- `just expect strainer` waits for the routine strainer note (`"Cleaned the suction strainer basket, differential pressure back to normal."`) and prints the model's verdict in the terminal (`verdict: asset=pump-01 part=strainer problem_reported=true ...`).
- In the cockpit, `"problem_reported": true` is highlighted in red in `Latest note` and in the `Direct call` column of `Leaving the node`.
- Point out the lesson: a 360M parameter model is reliable at extracting which part a note mentions (`"strainer"`), and unreliable at judging whether routine cleaning is a fault. Keep extraction in the small language model; keep the threshold and routing decision in the pipeline.

**Rollback command:**

```sh
just rollback
```

**What to point out:**
- Header advances to `version 5` (rolled back to version 3's specification).
- Wait one note interval (6 seconds) so the `notes` cache refills under the clean schema.
- `Latest note` and `Latest anomaly` return to `{part: "bearing"}` without `problem_reported`.

### 27:00-30:00 - Truth boundary and teardown

**Say at minute 27 (truth boundary):**
> "Four pumps' readings and notes come from a generator built for this session; everything that happens to them is real: one Expanso Edge node, one Cloud-deployed job, three models running on this machine, and only what you see in the tail left the node."

**Teardown command:**

```sh
just down
```

**What to point out:**
- `just down` stops the feed, stops the Cloud job (`no active executions`), stops the edge node, cockpit, and `llama-server`, unloads `qwen2.5:0.5b` from Ollama memory while leaving the machine's Ollama daemon running, and runs `teardown-audit.sh`.
- Terminal prints: `teardown clean: ports, processes, runtime, Ollama model, containers. Cloud: job stopped, office-hours node disconnected`.

---

## Bench (pull in order if time remains before minute 27)

1. **Swap the Ollama model to `gemma3:270m` (291 MB):**

   ```sh
   just ollama-model gemma3:270m
   ```

   Wait one note interval (6 seconds) and compare the `Ollama` column in `The three models` (`291.5 MB`, `268.10M parameters`, read the measured call time from the cockpit).

2. **Inspect job revision history and diff in Expanso Cloud:**

   ```sh
   just versions
   just versions-diff 1 3
   ```

3. **Raise the feed rate to 200 readings per second:**

   ```sh
   just rate 200
   ```

   Watch `Records in` climb toward ~200 /s while Python's 95th percentile stays in single-digit milliseconds and the language models still run only once every 6 seconds on operator notes. Reset with `just rate 20`.

---

## Fallbacks

- **Expanso Cloud unreachable at T-5:** run `just up-offline` and state that the node is running in local mode on `127.0.0.1:19510`. Every `just stage N`, `just deploy`, `just expect strainer`, `just rollback`, `just break`, and `just heal` recipe works identically.
- **A live paste into `live.cloud.yaml` fails validation:** run `just stage 2`, `just stage 3`, or `just stage 4` to deploy the prepared stage file.
- **`llama-server` fails to start on the presenter machine:** skip the `just break` / `just heal` beat; the `catch` processor keeps the pipeline running and `Ollama` continues extracting parts on every note.
- **An LLM returns slightly different wording on a note:** the cache join and latency counters are unaffected; read the actual JSON shown in `Latest note`.
