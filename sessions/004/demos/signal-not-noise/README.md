> Vendored into Pipeline Office Hours #00004 from the private repo
> `expanso-io/demo-signal-not-noise` at commit `be60e58d90f2`. The private repo stays the
> source of truth; change it there and re-vendor rather than editing here.

# Signal, not noise

A five-minute browser-first proof that an Expanso Edge pipeline can remove routine synthetic logs before transmission while preserving the fault an operator needs. The page displays simulator admissions and receiver acknowledgements; Expanso Cloud is the optional control plane and never receives payload data.

## Run

```bash
just warm
just validate
just start local baseline
just status
just test-live
just stop
just teardown-check
```

Open <http://127.0.0.1:19440>. The production cockpit action copies the validated pipeline step; deployment remains visible and manual in Expanso Cloud. In local mode, the separately labeled `Run local rehearsal` action hot-reloads the real Bento stream and waits for subsequent receiver evidence. `just start local filtered` starts directly in the solution state.

For Cloud mode, copy `.env.example` to `.env`, set `EXPANSO_CLOUD_ENDPOINT` and `EXPANSO_CLOUD_API_KEY`, then run `chmod 600 .env`. The Cloud script materializes an ignored, isolated 0600 CLI profile under `.cloud-state/cli-home`; credentials are never passed on a command line. Cloud mode also requires a pre-enrolled identity at `.cloud-state/node-01` (0700). `just verify-cloud` fails rather than treating missing prerequisites as success, and `just verify-cloud-stopped` requires zero matching active jobs or executions after Cloud teardown. `just cloud-purge` resolves exact labels before deleting demo state.
