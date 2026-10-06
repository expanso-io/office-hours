> Vendored into Pipeline Office Hours #00004 from the private repo
> `expanso-io/demo-which-site-broke` at commit `694512558cbb`. The private repo stays the
> source of truth; change it there and re-vendor rather than editing here.

# Which site broke?

Ten deterministic synthetic sources each post a payload through their own Bento pipeline. Baseline receiver payloads have only event ID, time, level, code, and message. The solution pipeline adds stable source context before transmission, making the node-07 fault attributable to `wind-west / turbine-07 / 1.8.3`.

Run `just warm`, `just validate`, `just start local baseline`, and open <http://127.0.0.1:19450>. The production cockpit action copies the validated enrichment step; deployment remains visible and manual in Expanso Cloud. In local mode, the separately labeled `Run local rehearsal` action hot-reloads all ten private Bento streams. `just test-live` proves baseline unknown attribution, teardown, enriched attribution, and clean teardown.

For Cloud mode, copy `.env.example` to `.env`, set `EXPANSO_CLOUD_ENDPOINT` and `EXPANSO_CLOUD_API_KEY`, then run `chmod 600 .env`. The Cloud script materializes an ignored, isolated 0600 CLI profile; credentials never appear in CLI arguments. Cloud mode also requires ten pre-enrolled 0700 identities under `.cloud-state/node-01` through `node-10`. `just verify-cloud` fails when Cloud prerequisites are absent and `just verify-cloud-stopped` requires no matching active job or execution after cleanup. `just cloud-purge` resolves exact labels before deleting demo state.
