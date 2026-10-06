# 004 — Three demos, twelve edge nodes

**Session:** Pipeline Office Hours #00004, Thu 2026-10-08, 09:00–10:00 PT
**Stream:** https://www.twitch.tv/expansoio

One story told on twelve Expanso Edge nodes, all controlled from Expanso
Cloud: collect it, cut the noise at the source, survive the outage, update the
fleet, and see exactly which site broke. Ten of the twelve are wind turbines
at one site, one is an industrial compressor's log stream, one is a remote
site with a flaky uplink.

## What you will be able to do

By the end you can run all three demos on your own machine, point them at your
own Expanso Cloud workspace, and change a live pipeline the same way the
session does: edit the job, deploy the revision, watch every node pick it up.

## The three demos

| Demo | Page | What it proves |
| --- | --- | --- |
| [`demos/signal-not-noise`](demos/signal-not-noise) | 127.0.0.1:19440 | One processor line keeps WARN and ERROR and deletes the rest, on the machine, before anything touches the network |
| [`demos/outage-buffer-replay`](demos/outage-buffer-replay) | 127.0.0.1:19480 | A 12-second outage against a disk-backed buffer on the node: no records lost, no duplicates |
| [`demos/which-site-broke`](demos/which-site-broke) | 127.0.0.1:19450 | One revision to ten turbines; each node stamps its own site, asset and version, so the broken one names itself |

Each demo is a copy of its own repository, with its own README, justfile and
tests. The provenance note at the top of each README says which commit it came
from; change the source repo and re-vendor rather than editing here.

## Before you start

You need `docker`, `just` and `uv` on your PATH. For Cloud mode you also need
an Expanso Cloud workspace: copy each demo's `.env.example` to `.env`, fill in
the endpoint and API key, and `chmod 600 .env`. Local mode needs no
credentials at all and is the right way to rehearse.

## Run all three

```sh
just warm        # pull and build, so nothing downloads on air
just validate    # config-only checks
just up          # start all three in their baseline (pre-fix) state
just status
just down        # stop, then prove every port, container and volume is gone
```

`just up cloud` runs the same thing against Expanso Cloud. Any demo can also
be driven on its own from its own directory, which is what the run sheet does
when one of them needs attention.

## What happens when it is wrong

Each demo carries its own failure path and says so in its README: the filter
demo keeps the one line an operator needs while dropping the chatter around
it, the outage demo returns real 503s and lets the queue grow on disk, and the
fleet demo shows faults arriving with no attribution until the enrichment
revision lands. Records are held, buffered or dead-lettered, never silently
dropped.

## Check the output

Each demo's `just test-live` runs its own proof against the running system,
and `just teardown-check` refuses to call a stopped demo clean until the port,
containers, networks, volumes and runtime state are all actually gone.

## Truth boundary

Twelve real Expanso Edge nodes running real pipelines, deployed from Expanso
Cloud. The log stream and the turbine faults come from generators built for
these demos, so the data is manufactured and everything that happens to it is
real: the filtering, the outage, the buffer on disk, the replay, the revision
rollout and the attribution.
