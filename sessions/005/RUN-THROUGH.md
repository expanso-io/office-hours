# Office Hours #00005 presenter run-through

**Title:** Three tiny models, one stream, three ways in
**Date:** Thu 2026-10-22, 09:00-09:30 PT (30 minutes)
**Working directory:** `sessions/005/demos/tiny-models`
**Cockpit URL:** `http://127.0.0.1:19500` (1080p display at 125% browser zoom)

## Pre-flight

### Evening before and T-30 minutes

Run from `sessions/005/demos/tiny-models`:

```sh
just warm
just validate
just up
just status
just down
just teardown-check
```

Confirm:
- `just warm` prints sizes for all three models (`IsolationForest` 63,430 bytes, `qwen2.5:0.5b` ~398 MB, `smollm2-360m` ~386 MB).
- `just validate` passes `ruff`, `expanso-edge validate`, `expanso-cli job validate --offline`, and `pytest`.
- `just up` connects the `role=office-hours` node, deploys `office-hours-005-models` at version 1, preloads `qwen2.5:0.5b` in Ollama, and opens `http://127.0.0.1:19500`.
- `just down` and `just teardown-check` end with `teardown clean: ports, processes, runtime, Ollama model, containers. Cloud: job stopped, office-hours node disconnected`.

### T-10 minutes (before going live)

```sh
just up
```

Open `http://127.0.0.1:19500` at 125% zoom and open `live.cloud.yaml` in the editor. Keep only the cockpit browser tab, the editor with `live.cloud.yaml`, and a terminal inside `sessions/005/demos/tiny-models` on screen. Never display `.env` or any directory above the demo folder.

---

## 30-minute spine

### 0:00-2:00 - Cold open

**On screen:** Cockpit at `http://127.0.0.1:19500` and terminal in `sessions/005/demos/tiny-models`.

**Command:**

```sh
just status
```

**What to point out:**
- Header shows `Expanso Cloud · office-hours-005-models · version 1`.
- Three model columns (`Python`, `Ollama`, `Direct call`) show their wiring (`subprocess processor`, `ollama_chat processor`, `http processor`) and disk footprint (`63.4 kB`, `397.8 MB`, `386.4 MB`), with `0` calls on version 1.
- Frame the question: three tiny models wired into one Expanso Edge pipeline in three different ways, and the pipeline, not a model, decides what leaves the node.

### 2:00-5:00 - Baseline stream on version 1

**Say at minute 2 (truth boundary):**
> "Four pumps' readings and notes come from a generator built for this session; everything that happens to them is real: one Expanso Edge node, one Cloud-deployed job, three models running on this machine, and only what you see in the tail left the node."

**What to point out on the cockpit:**
- `Records in` (~20.2 /s) matches `Records out` (~20.2 /s).
- `Kept on this node` is `0.0%`.
- `Bytes in` (~2.1 kB/s) and `Bytes out` (~2.7 kB/s) move in lockstep.
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
```

**Deploy command (or fallback `just stage 2`):**

```sh
just deploy
```

**Expected numbers and behaviour:**
- Header advances to `version 2`.
- Within 10 seconds, `Records out` drops from ~20 /s to ~1-2 /s (`Kept on this node` rises to ~90-95%).
- `pump-03` overheating readings (`temp_c` climbing to `81.0 °C`, `vibration_mm_s` to `6.2 mm/s`) leave the node with `anomaly 0.65+` and appear in `Latest anomaly`.
- Python column shows `63.4 kB`, median call `~1.4 ms`, 95th percentile `~2.0 ms`.

### 11:00-19:00 - Change 2: Ollama + direct HTTP + in-memory join (version 3)

**Action:** Paste `pipelines/paste/change-2.yaml` into `live.cloud.yaml` directly above `# Paste each change above this line.`:

```yaml
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
```

**Deploy command (or fallback `just stage 3`):**

```sh
just deploy
```

**Important timing note:** After a redeploy the node's in-memory `notes` cache starts empty, so `pump-03`'s `last_note` is `null` until the next note arrives. Wait one note interval (6 seconds) after each deploy so the note lands in the cache and the join populates.

**Expected numbers and behaviour:**
- Header advances to `version 3`.
- Wait one note interval (6 seconds).
- `Latest note` shows `"Drive end bearing running hot and getting noisier."` with:
  - `ollama`: free-form JSON (`{"part": "drive end bearing", "symptom": "running hot and getting noisier", "call_ms": ...}`).
  - `direct`: grammar-constrained enum (`{"part": "bearing", "call_ms": ...}`).
- `Latest anomaly` shows the `pump-03` reading (`python.anomaly: true`) joined with `last_note` containing both language model extractions.
- Model comparison table:
  - `Python`: median `~1.4 ms`, touches ~99% of records in (every reading).
  - `Ollama` (`qwen2.5:0.5b`): median `~45-110 ms`, touches ~1% of records in (notes only).
  - `Direct call` (`smollm2-360m`): median `~80-150 ms`, touches ~1% of records in (notes only).

### 19:00-23:00 - Break and heal (no job revision)

**Break command:**

```sh
just break
```

**What to point out:**
- Wait one note interval (6 seconds).
- `llama-server` on `127.0.0.1:18085` is stopped.
- The pipeline does not halt. The `- catch:` block around the `http` branch records `direct: {"error": "...connection refused"}`.
- `Degraded calls` increments in the flow strip, and `Direct call` shows `call failed` in the tail while Python scores and Ollama extractions keep arriving.

**Heal command:**

```sh
just heal
```

**What to point out:**
- Wait one note interval (6 seconds).
- The next `pump-03` note succeeds against `127.0.0.1:18085`, overwrites the cached note in `notes`, and `Latest note` and `Latest anomaly` show `direct.part: "bearing"` again.

### 23:00-27:00 - Wrong on purpose (version 4) and rollback (version 5)

**Action:** In `live.cloud.yaml`, add `"problem_reported": {"type": "boolean"}` to the `direct` JSON schema and add `"problem_reported"` to `"required"`:

```yaml
                      "properties": {
                        "part": {"type": "string", "enum": ["bearing", "seal", "motor", "coupling", "strainer", "instrument", "valve", "none"]},
                        "problem_reported": {"type": "boolean"}
                      },
                      "required": ["part", "problem_reported"]
```

**Deploy command (or fallback `just stage 4`):**

```sh
just deploy
```

**What to point out:**
- Header advances to `version 4`.
- Wait one note interval (6 seconds).
- `Latest note` shows the routine maintenance note `"Cleaned the suction strainer basket, differential pressure back to normal."` with `"direct": {"part": "strainer", "problem_reported": true, ...}`.
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

   Wait one note interval (6 seconds) and compare the `Ollama` column in `The three models` (`291.5 MB`, `268.10M parameters`, ~45-70 ms call time).

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

- **Expanso Cloud unreachable at T-5:** run `just up-offline` and state that the node is running in local mode on `127.0.0.1:19510`. Every `just stage N`, `just deploy`, `just rollback`, `just break`, and `just heal` recipe works identically.
- **A live paste into `live.cloud.yaml` fails validation:** run `just stage 2`, `just stage 3`, or `just stage 4` to deploy the prepared stage file.
- **`llama-server` fails to start on the presenter machine:** skip the `just break` / `just heal` beat; the `catch` processor keeps the pipeline running and `Ollama` continues extracting parts on every note.
- **An LLM returns slightly different wording on a note:** the cache join and latency counters are unaffected; read the actual JSON shown in `Latest note`.
