# Verification — session 004

Every claim below is backed by a command and its real output. The dry run
recorded here was executed on 2026-10-06 offline (`just up-offline`); the Cloud lane is run
again at pre-flight the night before the session.

| Claim | Command | Evidence |
| --- | --- | --- |
| The filter demo starts, filters, and keeps the one line that matters | `just test-live` in `demos/signal-not-noise` | `live baseline/filter/incident proof passed` |
| The outage demo survives a 12-second outage with no lost records | `just test-live` in `demos/outage-buffer-replay` | `live durable outage/restart/replay proof passed` |
| The fleet demo attributes a fault to one turbine after the revision | `just test-live` in `demos/which-site-broke` | `live unknown/enriched attribution proof passed` |
| Nothing is left running afterwards | `just teardown-check` in each demo | `teardown clean: port, containers, networks, volumes, runtime` |

## Rehearsal log

- [x] Local dry run of all three, start through teardown, 2026-10-06
- [ ] Cloud dry run of all three (`just up`), pre-flight the night before
- [ ] Deployed from Expanso Cloud, not a local engine
- [ ] No credentials, customer names or prospect names on screen
