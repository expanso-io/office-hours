> Vendored into Pipeline Office Hours #00004 from the private repo
> `expanso-io/demo-outage-buffer-replay` at commit `c68fffd1e003`. The private repo stays the
> source of truth; change it there and re-vendor rather than editing here.

# The network fails; the data doesn’t

A browser-first proof using a real Bento 1.19.0 SQLite buffer. The simulated destination returns real HTTP 503 responses during the modeled outage. Source admissions continue, the receiver reconnects, and the page audits successful sequence IDs through a frozen high-water mark.

Run `just warm`, `just validate`, `just start`, then open <http://127.0.0.1:19480>. The browser action exercises the recordable 12-second 503, buffer, recovery, drain, and receiver audit. The separate `just test-live` engineering gate additionally restarts the pipeline container during a five-second outage to prove the SQLite backlog survives restart; that restart is not part of the browser recording claim. `just stop && just teardown-check` removes the demo-owned volume and all runtime state.

For Cloud mode, copy `.env.example` to `.env`, set `EXPANSO_CLOUD_ENDPOINT` and `EXPANSO_CLOUD_API_KEY`, then run `chmod 600 .env`. The Cloud script materializes an ignored, isolated 0600 CLI profile; credentials never appear in CLI arguments. Cloud mode also needs a 0700 edge identity under `.cloud-state/node-01`; set `EXPANSO_EDGE_BOOTSTRAP_TOKEN` in `.env` and `./scripts/cloudctl.sh bootstrap` (or the first Cloud start) creates it. `just verify-cloud` fails rather than treating missing prerequisites as success, and `just verify-cloud-stopped` requires zero matching active jobs or executions after Cloud teardown. `just cloud-purge` resolves exact labels before deletion.
