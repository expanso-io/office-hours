# Truth contract

- Ten deterministic synthetic sources emit one heartbeat per second. Node 07 emits `SENSOR_TIMEOUT` every five seconds and runs app version 1.8.3; all other nodes run 2.4.1.
- Raw source JSON contains no origin fields. A private transport header lets the server validate routing but is never shown as receiver attribution.
- Baseline snapshots expose ten anonymous stable slots, never the simulator-private site, node, asset, region, or app version. A slot gains identity only after those fields arrive in receiver JSON.
- Attribution is counted only when the receiver JSON itself contains site, node, app, and pipeline fields.
- Enrichment applies only to new events. Historical baseline faults remain unknown.
- Local mode proves ten Bento 1.19.0 instances. Cloud mode is accepted only with exactly ten selected connected nodes, ten running executions, and fresh receiver data.
- Before that Cloud proof exists, pipeline, anonymous-slot health, fleet-edge state, and online-site count remain explicitly `unverified` or null. Receiver payload context may label only the specific observed slot and data path as `receiver-observed`; it does not prove the other nine nodes healthy.
- In Cloud mode, the browser does not call local Bento hot-reload endpoints. The revision must be applied in Expanso Cloud, and the demo infers enrichment only from context arriving in receiver payloads.
- Expanso Cloud is a control plane and receives no payload data.
