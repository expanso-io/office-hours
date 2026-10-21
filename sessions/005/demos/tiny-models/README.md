# Tiny models on one Expanso Edge stream

Self-contained demo for Pipeline Office Hours #00005. See the session tutorial
in [`../../README.md`](../../README.md) and the presenter script in
[`../../RUN-THROUGH.md`](../../RUN-THROUGH.md).

## Commands

```sh
just warm            # train scorer.joblib, download SmolLM2-360M GGUF, pull qwen2.5:0.5b
just validate        # lint, unit tests, and offline job validation
just up              # start the Cloud-connected node, deploy stage 1, start feed and cockpit
just up-offline      # same pipeline on a local-mode Expanso Edge node without credentials
just deploy          # validate and deploy live.cloud.yaml after pasting a change
just stage 2         # fallback: deploy stage 2 (Python IsolationForest filter)
just stage 3         # fallback: deploy stage 3 (Ollama + direct HTTP + cache join)
just stage 4         # fallback: deploy stage 4 (wrong-on-purpose problem_reported schema)
just break           # stop llama-server under the running pipeline
just heal            # restart llama-server
just rollback        # roll the job back to the previous version's spec
just versions        # list job versions
just versions-diff   # diff version 1 against version 3
just ollama-model    # swap the Ollama model to gemma3:270m
just rate 200        # change the feed rate (readings per second) while running
just status          # print process, job, and cockpit counters
just down            # stop everything, unload the Ollama model, and verify teardown
```

The cockpit runs on `http://127.0.0.1:19500` and the edge node ingests POSTs at
`http://127.0.0.1:19501/ingest`.
