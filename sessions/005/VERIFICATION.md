# Verification - session 005

Every claim below is backed by a command and its recorded output on 2026-10-22
across both the Expanso Cloud lane (`just up`) and the offline local-mode lane
(`just up-offline`).

| Claim | Command | Evidence |
| --- | --- | --- |
| Models warm locally and write `.models/manifest.json` | `just warm` | `warm: models trained, downloaded and pulled; manifest written` (`IsolationForest` 63,430 B, `qwen2.5:0.5b` 397,821,319 B, `smollm2-360m` 386,404,992 B) |
| Lint, job spec validation, and unit tests pass | `just validate` | `All checks passed!`, `[OK] pipelines/stage-{1..4}.cloud.yaml: valid`, `17 passed` |
| Cloud stage 1 deploys and passes all records through | `just up && just status` | `Job 'office-hours-005-models' created successfully`, `version 1, running`, `in_per_s: 20.2`, `out_per_s: 20.2`, `kept_on_node_pct: 0.0` |
| Cloud stage 2 runs Python `IsolationForest` via `subprocess` and filters healthy readings | `just stage 2 && just status` | `version 2, running`, `python p50: 2.4 ms`, `p95: 4.6 ms` |
| Cloud stage 3 runs `ollama_chat` + `http` and joins the bearing note to `pump-03` anomalies | `just stage 3 && just status` | `version 4, running`, `kept_on_node_pct: 85.6`, `python p50: 2.9 ms`, `ollama p50: 115.4 ms`, `direct p50: 64.5 ms`, `last_note.direct.part: "bearing"` |
| Stopping `llama-server` degrades gracefully and restarting heals on the next note | `just break && just heal` | `degraded` increments while alerts continue leaving the node; `llama-server serving smollm2-360m on 127.0.0.1:18085` restores `direct.part: "bearing"` |
| Cloud stage 4 demonstrates the 360M boolean false positive on routine strainer cleaning | `just stage 4` | `version 5`, `direct: {"part": "strainer", "problem_reported": true, "call_ms": 109.221}` on `"Cleaned the suction strainer basket, differential pressure back to normal."` |
| Cloud rollback restores the previous stage spec | `just rollback` | `Job 'j-dd375a02-92f4-4ba1-aca8-7f67782843dc' rolled back successfully`, `From version: 5, To version: 6`, `direct: {"part": "bearing", "call_ms": 75.787}` |
| Offline lane runs the same stages without credentials | `just up-offline`, `just stage 2..4`, `just break`, `just heal`, `just rollback`, `just down` | Local-mode `expanso-edge` on `127.0.0.1:19510` passes versions 1 through 5 and tears down cleanly |
| Cockpit passes headless layout and font checks across 4 widths and 2 themes | `./scripts/browser-check.sh` | `hscroll: false`, `inner: []`, `plexLoaded: true` at `320`, `400`, `768`, and `1440` px in `light` and `dark`, with theme persistence (`afterToggleAndReload: "dark"`) |
| Teardown stops the Cloud job, node, processes, and ports, and unloads the Ollama model | `just down` | `teardown clean: ports, processes, runtime, Ollama model, containers. Cloud: job stopped, office-hours node disconnected` |

## Recorded outputs (2026-10-22)

### 1. `just warm` and `just validate`

```text
wrote .models/scorer.joblib (63430 bytes, 2442 nodes)
direct model: .models/smollm2-360m-instruct-q8_0.gguf already here
llama-server serving smollm2-360m on 127.0.0.1:18085
python  IsolationForest        63,430 bytes  32 trees, 2,442 nodes, scikit-learn
ollama  qwen2.5:0.5b      397,821,319 bytes  494.03M parameters, Q4_K_M
direct  smollm2-360m      386,404,992 bytes  361.8M parameters, Q8_0
stopped direct
warm: models trained, downloaded and pulled; manifest written

All checks passed!
13 files already formatted
[OK] pipelines/stage-1.cloud.yaml: valid
[OK] pipelines/stage-1.cloud.yaml: job spec
[OK] pipelines/stage-2.cloud.yaml: valid
[OK] pipelines/stage-2.cloud.yaml: job spec
[OK] pipelines/stage-3.cloud.yaml: valid
[OK] pipelines/stage-3.cloud.yaml: job spec
[OK] pipelines/stage-4.cloud.yaml: valid
[OK] pipelines/stage-4.cloud.yaml: job spec
.................                                                        [100%]
17 passed in 2.02s
```

### 2. Expanso Cloud lane (`just up`, stages 2-4, break/heal, rollback, `just down`)

```text
./scripts/democtl.sh up cloud "1"
Ollama has qwen2.5:0.5b loaded
llama-server serving smollm2-360m on 127.0.0.1:18085
waiting for Expanso Cloud to see the office-hours node
node connected
deploying live.cloud.yaml to cloud
Job 'office-hours-005-models' created successfully in namespace 'default'
office-hours-005-models is at version 1
waiting for the first record to leave the node
cockpit: http://127.0.0.1:19500
edit live.cloud.yaml and run just deploy, or run just stage N

./scripts/democtl.sh status
lane: cloud
  direct: running
  cockpit: running
  edge: running
  feed: running
  job office-hours-005-models: version 1, running
{
  "records_in": 528,
  "records_out": 547,
  "kept_on_node_pct": 0.0,
  "in_per_s": 20.2,
  "out_per_s": 20.2,
  "degraded": 0,
  "dead_letters": 0,
  "ms_p50": { "python": null, "ollama": null, "direct": null },
  "ms_p95": { "python": null, "ollama": null, "direct": null }
}

./scripts/democtl.sh stage "2"
deploying live.cloud.yaml to cloud
Job 'office-hours-005-models' updated successfully in namespace 'default' (version: 2)
office-hours-005-models is at version 2

./scripts/democtl.sh stage "3"
deploying live.cloud.yaml to cloud
Job 'office-hours-005-models' updated successfully in namespace 'default' (version: 4)
office-hours-005-models is at version 4
{
  "records_in": 4541,
  "records_out": 1069,
  "kept_on_node_pct": 85.6,
  "in_per_s": 20.6,
  "out_per_s": 3.0,
  "degraded": 0,
  "dead_letters": 0,
  "ms_p50": { "python": 2.9, "ollama": 115.4, "direct": 64.5 },
  "ms_p95": { "python": 4.9, "ollama": 153.6, "direct": 91.9 }
}

./scripts/democtl.sh break
stopped direct
llama-server is down; the pipeline keeps running
# status: degraded: 8 while alerts continue flowing

./scripts/democtl.sh heal
llama-server serving smollm2-360m on 127.0.0.1:18085

./scripts/democtl.sh stage "4"
deploying live.cloud.yaml to cloud
Job 'office-hours-005-models' updated successfully in namespace 'default' (version: 5)
office-hours-005-models is at version 5
{
  "asset": "pump-01",
  "direct": { "call_ms": 109.221, "part": "strainer", "problem_reported": true },
  "kind": "note",
  "ollama": {
    "call_ms": 162.323,
    "part": "suction strainer basket",
    "symptom": "suction strainer basket, differential pressure back to normal"
  },
  "text": "Cleaned the suction strainer basket, differential pressure back to normal."
}

./scripts/democtl.sh rollback
rolling office-hours-005-models back to the spec of version 4
Job 'j-dd375a02-92f4-4ba1-aca8-7f67782843dc' rolled back successfully
  From version: 5
  To version:   6
  Target spec:  version 4
office-hours-005-models is at version 6
{
  "asset": "pump-03",
  "direct": { "call_ms": 75.787, "part": "bearing" },
  "kind": "note",
  "ollama": {
    "call_ms": 108.152,
    "part": "drive end bearing",
    "symptom": "running hot and getting noisier"
  },
  "text": "Drive end bearing running hot and getting noisier."
}

./scripts/democtl.sh stop
stopped feed
Cloud: office-hours-005-models stopped, no active executions
stopped edge
stopped cockpit
stopped direct
Ollama unloaded qwen2.5:0.5b
./scripts/teardown-audit.sh
teardown clean: ports, processes, runtime, Ollama model, containers. Cloud: job stopped, office-hours node disconnected
```

### 3. Offline local-mode lane (`just up-offline`, stages 2-4, break/heal, rollback, `just down`)

```text
./scripts/democtl.sh up local "1"
Ollama has qwen2.5:0.5b loaded
llama-server serving smollm2-360m on 127.0.0.1:18085
local-mode edge node up
deploying live.cloud.yaml to local
Job 'office-hours-005-models' created successfully in namespace 'default'
office-hours-005-models is at version 1
waiting for the first record to leave the node
cockpit: http://127.0.0.1:19500

# Stage 2 steady state:
{
  "records_in": 1293,
  "records_out": 571,
  "kept_on_node_pct": 96.5,
  "in_per_s": 20.1,
  "out_per_s": 0.7,
  "degraded": 0,
  "dead_letters": 0,
  "ms_p50": { "python": 2.6, "ollama": null, "direct": null },
  "ms_p95": { "python": 5.2, "ollama": null, "direct": null }
}

# Stage 3 joined alert:
{
  "asset": "pump-03",
  "current_a": 18.3,
  "kind": "reading",
  "last_note": {
    "direct": { "call_ms": 98.966, "part": "bearing" },
    "ollama": { "call_ms": 124.021, "part": "drive end bearing", "symptom": "running hot and getting noisier" },
    "text": "Drive end bearing running hot and getting noisier."
  },
  "python": { "anomaly": true, "call_ms": 4.32, "infer_ms": 4.047, "score": 0.729 },
  "temp_c": 69.7,
  "vibration_mm_s": 3.81
}

# Teardown:
./scripts/democtl.sh stop
stopped feed
stopped edge
stopped cockpit
stopped direct
Ollama unloaded qwen2.5:0.5b
./scripts/teardown-audit.sh
teardown clean: ports, processes, runtime, Ollama model, containers. Cloud: skipped, no .env found
```

### 4. Headless cockpit verification (`./scripts/browser-check.sh`)

```text
"{\"theme\":\"light\",\"width\":320,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"light\",\"width\":400,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"light\",\"width\":768,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"light\",\"width\":1440,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"dark\",\"width\":320,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"dark\",\"width\":400,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"dark\",\"width\":768,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"theme\":\"dark\",\"width\":1440,\"hscroll\":false,\"inner\":[],\"fonts\":[\"\\\"IBM Plex Sans\\\", sans-serif\",\"\\\"IBM Plex Mono\\\", monospace\"],\"plexLoaded\":true,\"records\":8}"
"{\"afterToggleAndReload\":\"dark\",\"stored\":\"dark\"}"
```

## Rehearsal log

- [x] Local dry run (`just up-offline`), start through teardown, 2026-10-22
- [x] Cloud dry run (`just up`), stages 1-4, rollback, break/heal, and teardown, 2026-10-22
- [x] Deployed from Expanso Cloud (`office-hours-005-models`)
- [x] No credentials, customer names, or private paths on screen
