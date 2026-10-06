# Four-minute recording script

1. In Cloud, show ten selected nodes running the baseline revision.
2. Open <http://127.0.0.1:19450>. Wait for the deterministic node-07 fault and read `SOURCE UNKNOWN` from the raw receiver payload.
3. Click **Copy pipeline step** once, return to Expanso Cloud, paste the step, and deploy it visibly. Copying does not mutate the cockpit or Cloud.
4. Return to the cockpit and wait for the next enriched receiver fault. Read `wind-west / turbine-07 / 1.8.3` and the `lineage-v2` pipeline version from `source_context` in the payload itself.

Do not attribute historical baseline faults from simulator internals.
