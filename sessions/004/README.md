# 004 — {{TOPIC TITLE}}

> Status: scaffold. The topic is not yet confirmed; every `{{slot}}` below is
> filled once it is. Everything else matches the shape of sessions 001 and 002.

**Session:** Pipeline Office Hours #00004, Thu 2026-10-08, 09:00–10:00 PT
**Stream:** https://www.twitch.tv/expansoio

## What you will be able to do

By the end of this session you can {{OUTCOME — the concrete thing the viewer
can do afterwards, in their own environment}}.

## Before you start

You need `uv`, `expanso-cli` and `expanso-edge` on your PATH and an Expanso
Cloud workspace, exactly as in [the cluster setup](../../CLUSTER.md). This
session adds: {{EXTRA PREREQUISITES — hardware, models, containers, or none}}.

Start the node and leave it running:

```sh
expanso-edge run --no-watch --data-dir "$PWD/../../.expanso-edge"
```

## The pipeline

{{WHAT THE PIPELINE DOES — the stages in order, named plainly.}}

```sh
uv run rehearse.py {{mode}}
```

It prints the Cloud node, job, version and execution it used, so you can find
the same objects in Expanso Cloud.

## What happens when it is wrong

{{THE FAILURE PATH — what gets held, dead-lettered or refused, and how to see
it. Every session covers this; it is the part people remember.}}

## Check the output

```sh
uv run check.py
```

{{WHAT THE CHECK PROVES — the specific property, not "it works".}}

## Truth boundary

{{What is synthetic, what is simulated, what is real.}}
