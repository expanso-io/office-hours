# Truth contract

- The source is deterministic and synthetic: seed 424242, 50 attempted messages per second, with a 100-event cycle of 70 DEBUG, 24 INFO, 5 WARN, and 1 ERROR.
- `pipeline_http_accepted` is counted only after the Bento HTTP input responds successfully. Downstream counts and bytes are recorded only by the receiver endpoint.
- The displayed reduction uses only bytes accepted by the pipeline HTTP input versus receiver-acknowledged bytes in a full five-second window. Generated attempts that the pipeline rejects are reported separately and cannot be credited as filtering.
- A filter is `observed` only when a complete accepted-input window has a receiver-to-ingress byte ratio at or below 0.20. This observation does not invent a Cloud job revision.
- Local mode proves Bento 1.19.0 behavior. Cloud mode proves scheduling only when `verify-cloud` sees the exact job, selected node, running execution, and fresh receiver data.
- In Cloud mode, pipeline, Edge-node, and topology states remain `unverified` until receiver evidence is observed; receiver observation is labeled as such and is not promoted to a Cloud health claim.
- Expanso Cloud is a control plane. This demo sends no payloads to Cloud.
- The deterministic verification ERROR is emitted only after the filter is observed and has exact code `COMPRESSOR_OVERHEAT`. It is proven only when that selected post-filter event ID and code are both observed at admission and receiver acknowledgement; an earlier incident or a different code cannot satisfy the proof. Its receiver event and acknowledgement remain pinned in evidence while routine traffic continues.
