# Truth contract

- The source is deterministic and synthetic at five events per second.
- Only the destination link is modeled offline. The receiver returns real HTTP 503 and records no successful delivery while offline.
- Bento’s SQLite buffer acknowledges accepted messages after durable admission and retains them across a pipeline-container restart while the named volume exists.
- `queued_total` is the current receiver-auditable difference between successfully admitted and uniquely acknowledged sequence IDs. At restore, the audit freezes the accepted high-water mark and exact backlog; final missing/duplicate claims cover only accepted records through that boundary, and replay count covers only that frozen backlog.
- The demo does not claim an Edge-derived dropped count. Generated attempts that never received pipeline admission are reported separately as source/pipeline rejections.
- The delivery model is at-least-once. “Zero duplicates” is an observed controlled-run result, not an exactly-once guarantee.
- Full stop removes the buffer volume. Project-local Cloud identity is retained unless `cloud-purge` is explicitly run.
- In Cloud mode, the configured durable-buffer variant is only an expectation until separately verified. Pipeline and Edge execution state remain `unverified`, or are labeled only as input/receiver observation, rather than being promoted to Cloud health. Generator and receiver-link states describe local demo components.
- Expanso Cloud is a control plane and receives no payload data.
