from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import Counter, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ACTIVITY_FRESH_SECONDS = 3.0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class DemoState:
    capacity = 10000

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.run_id = str(uuid.uuid4())
        self.started = time.monotonic()
        self.snapshot_seq = 0
        self.sequence = 0
        self.generated = 0
        self.generated_sequences: set[int] = set()
        self.accepted_sequences: set[int] = set()
        self.delivered_sequences: set[int] = set()
        self.delivery_counts: Counter[int] = Counter()
        self.destination_attempts = 0
        self.pipeline_rejected = 0
        self.uplink_online = True
        self.phase = "ready"
        self.outage_started_at: str | None = None
        self.outage_planned_end_at: str | None = None
        self.outage_actual_end_at: str | None = None
        self.audit_high_water: int | None = None
        self.backlog_at_restore: set[int] = set()
        self.replayed = 0
        self.last_input_at: str | None = None
        self.last_input_monotonic: float | None = None
        self.last_generated_at: str | None = None
        self.last_output_at: str | None = None
        self.last_output_monotonic: float | None = None
        self.last_ack: dict[str, object] | None = None
        self.idempotency: dict[str, dict[str, object]] = {}
        self.outage_task: asyncio.Task[None] | None = None
        self.recent = deque(maxlen=20)

    def input_is_fresh(self, now: float | None = None) -> bool:
        observed_at = time.monotonic() if now is None else now
        return bool(
            self.last_input_monotonic is not None
            and observed_at - self.last_input_monotonic <= ACTIVITY_FRESH_SECONDS
        )

    def receiver_is_fresh(self, now: float | None = None) -> bool:
        observed_at = time.monotonic() if now is None else now
        return bool(
            self.last_output_monotonic is not None
            and observed_at - self.last_output_monotonic <= ACTIVITY_FRESH_SECONDS
        )

    def make_event(self) -> dict[str, object]:
        self.sequence += 1
        self.generated += 1
        self.generated_sequences.add(self.sequence)
        self.last_generated_at = now_iso()
        return {
            "run_id": self.run_id,
            "stream_id": "remote-substation-a",
            "sequence": self.sequence,
            "observed_at": self.last_generated_at,
            "voltage_kv": round(115.0 + ((self.sequence % 7) - 3) * 0.1, 1),
            "frequency_hz": round(60.0 + ((self.sequence % 5) - 2) * 0.01, 2),
        }

    def audit(self) -> tuple[list[int], list[int]]:
        accepted_scope = (
            {seq for seq in self.accepted_sequences if seq <= self.audit_high_water}
            if self.audit_high_water is not None
            else set(self.accepted_sequences)
        )
        missing = sorted(accepted_scope - self.delivered_sequences)
        duplicates = sorted(
            seq
            for seq, count in self.delivery_counts.items()
            if count > 1 and (self.audit_high_water is None or seq <= self.audit_high_water)
        )
        return missing, duplicates

    def restore_uplink(self) -> None:
        self.audit_high_water = max(self.accepted_sequences, default=0)
        self.backlog_at_restore = self.accepted_sequences - self.delivered_sequences
        self.uplink_online = True
        self.outage_actual_end_at = now_iso()
        self.phase = "draining"

    def snapshot(self) -> dict[str, object]:
        self.snapshot_seq += 1
        missing, duplicates = self.audit()
        current_backlog = self.accepted_sequences - self.delivered_sequences
        outstanding = len(current_backlog)
        self.replayed = len(self.backlog_at_restore & self.delivered_sequences)
        accepted_sorted = sorted(self.accepted_sequences)
        delivered_sorted = sorted(self.delivered_sequences)
        audited_accepted = sorted(
            seq
            for seq in self.accepted_sequences
            if self.audit_high_water is not None and seq <= self.audit_high_water
        )
        audited_delivered = sorted(set(audited_accepted) & self.delivered_sequences)
        mode = os.getenv("DEMO_MODE", "local")
        local_mode = mode == "local"
        activity_now = time.monotonic()
        input_fresh = self.input_is_fresh(activity_now)
        receiver_fresh = self.receiver_is_fresh(activity_now)
        pipeline_status = (
            "running"
            if local_mode and input_fresh
            else "stale"
            if local_mode and self.last_input_at
            else "starting"
            if local_mode
            else "receiver-observed"
            if receiver_fresh
            else "receiver-stale"
            if self.last_output_at
            else "input-accepted"
            if self.last_input_at
            else "unverified"
        )
        edge_state = (
            "buffering"
            if local_mode and outstanding and input_fresh
            else "healthy"
            if local_mode and input_fresh and receiver_fresh
            else "stale"
            if local_mode and (self.last_input_at or self.last_output_at)
            else "starting"
            if local_mode
            else "receiver-observed"
            if receiver_fresh
            else "receiver-stale"
            if self.last_output_at
            else "input-accepted"
            if self.last_input_at
            else "unverified"
        )
        return {
            "demo_id": "outage-buffer-replay",
            "schema_version": "1.0",
            "run_id": self.run_id,
            "snapshot_seq": self.snapshot_seq,
            "server_time": now_iso(),
            "metrics_window_ms": 5000,
            "synthetic": True,
            "seed": 424242,
            "mode": mode,
            "scenario": "outage-buffer-replay",
            "clock": now_iso(),
            "pipeline": {
                "variant": "durable-sqlite" if local_mode else "unverified",
                "expected_variant": "durable-sqlite",
                "status": pipeline_status,
                "last_input_at": self.last_input_at,
                "last_output_at": self.last_output_at,
                "receiver_fresh": receiver_fresh,
            },
            "truth": {
                "synthetic_source": True,
                "cloud_managed": mode == "cloud",
                "window_seconds": round(time.monotonic() - self.started, 2),
            },
            "control_plane": {
                "mode": mode,
                "state": "local" if local_mode else "unverified",
                "cloud_url": "https://cloud.expanso.io",
                "job_id": None,
                "pipeline_revision": "durable-sqlite-v1" if local_mode else None,
                "nodes_scheduled": 1 if local_mode else None,
                "nodes_running": int(input_fresh) if local_mode else None,
            },
            "nodes": [
                {"id": "generator", "state": "healthy"},
                {"id": "expanso-edge-buffer", "state": edge_state},
                {
                    "id": "demo-receiver",
                    "state": "online" if self.uplink_online else "offline-simulated",
                },
            ],
            "edges": [
                {
                    "from": "generator",
                    "to": "expanso-edge-buffer",
                    "state": (
                        "active"
                        if local_mode and input_fresh
                        else "stale"
                        if local_mode
                        else "input-accepted"
                        if self.last_input_at
                        else "unverified"
                    ),
                },
                {
                    "from": "expanso-edge-buffer",
                    "to": "demo-receiver",
                    "state": (
                        "offline-simulated"
                        if not self.uplink_online
                        else "active"
                        if local_mode and receiver_fresh
                        else "stale"
                        if local_mode
                        else "receiver-observed"
                        if receiver_fresh
                        else "receiver-stale"
                        if self.last_output_at
                        else "unverified"
                    ),
                },
            ],
            "metrics": {
                "generated_total": self.generated,
                "sent_total": len(self.accepted_sequences),
                "acknowledged_total": len(self.delivered_sequences),
                "queued_total": outstanding,
                "replayed_total": self.replayed,
                "dropped_total": None,
                "dropped_state": "not_measured_from_edge",
                "source_generated_not_accepted_total": self.pipeline_rejected,
                "destination_attempts": self.destination_attempts,
                "pipeline_http_rejected": self.pipeline_rejected,
                "duplicate_successful_deliveries": len(duplicates),
                "missing_accepted_sequences": len(missing),
                "first_generated_seq": min(self.generated_sequences, default=None),
                "last_generated_seq": max(self.generated_sequences, default=None),
                "first_acknowledged_seq": delivered_sorted[0] if delivered_sorted else None,
                "last_acknowledged_seq": delivered_sorted[-1] if delivered_sorted else None,
                "first_accepted_seq": accepted_sorted[0] if accepted_sorted else None,
                "last_accepted_seq": accepted_sorted[-1] if accepted_sorted else None,
                "buffer_capacity": self.capacity,
                "buffer_utilization": round(outstanding / self.capacity, 5),
                "audit_high_water": self.audit_high_water,
                "audit_accepted_total": len(audited_accepted),
                "audit_acknowledged_total": len(audited_delivered),
                "audit_backlog_at_restore_total": len(self.backlog_at_restore),
            },
            "destination_state": "online" if self.uplink_online else "offline-simulated",
            "phase": self.phase,
            "outage_start_at": self.outage_started_at,
            "outage_planned_end_at": self.outage_planned_end_at,
            "outage_actual_end_at": self.outage_actual_end_at,
            "evidence": {
                "payloads": list(self.recent)[:4],
                "acknowledgements": [self.last_ack] if self.last_ack else [],
                "missing_sequence_ids": missing,
                "duplicate_sequence_ids": duplicates,
                "audit_high_water": self.audit_high_water,
                "audit_scope": "pipeline-accepted sequences through restore high-water",
                "backlog_at_restore_sequence_ids": sorted(self.backlog_at_restore),
                "accepted_sequence_range": [accepted_sorted[0], accepted_sorted[-1]]
                if accepted_sorted
                else None,
                "receiver_sequence_range": [delivered_sorted[0], delivered_sorted[-1]]
                if delivered_sorted
                else None,
            },
            "action": {
                "id": "run-outage",
                "label": "Run 12-second outage",
                "enabled": self.phase in {"ready", "verified", "failed"},
                "phase": self.phase,
            },
            "verification": {
                "state": "verified"
                if self.phase == "verified"
                else "failed"
                if self.phase == "failed"
                else "pending",
                "assertions": [
                    {"name": "receiver_missing_zero", "passed": not missing},
                    {"name": "receiver_duplicates_zero", "passed": not duplicates},
                    {
                        "name": "accepted_equals_delivered",
                        "passed": bool(audited_accepted) and not missing,
                    },
                ],
            },
        }


state = DemoState()


async def simulate() -> None:
    url = os.getenv("PIPELINE_URL", "http://pipeline:8080/ingest")
    async with httpx.AsyncClient(timeout=2.5) as client:
        while True:
            event = state.make_event()
            try:
                response = await client.post(url, json=event)
                if response.is_success:
                    state.accepted_sequences.add(int(event["sequence"]))
                    state.last_input_at = now_iso()
                    state.last_input_monotonic = time.monotonic()
                else:
                    state.pipeline_rejected += 1
            except httpx.HTTPError:
                state.pipeline_rejected += 1
            await asyncio.sleep(0.2)


async def run_outage(seconds: float = 12) -> None:
    state.phase = "offline"
    state.uplink_online = False
    state.outage_started_at = now_iso()
    state.outage_planned_end_at = (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
    await asyncio.sleep(seconds)
    state.restore_uplink()
    await finish_audit()


async def finish_audit() -> None:
    for _ in range(120):
        missing, _ = state.audit()
        if not missing:
            state.phase = "auditing"
            await asyncio.sleep(0.5)
            missing, duplicates = state.audit()
            state.phase = "verified" if not missing and not duplicates else "failed"
            return
        await asyncio.sleep(0.25)
    state.phase = "failed"


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if os.getenv("SIMULATOR_ENABLED", "true").lower() == "true":
        task = asyncio.create_task(simulate())
    yield
    for running in [task, state.outage_task]:
        if running:
            running.cancel()
    await asyncio.gather(
        *[running for running in [task, state.outage_task] if running], return_exceptions=True
    )


app = FastAPI(title="The network fails; the data doesn't", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=Path(__file__).parents[1] / "web"), name="assets")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "scenario": "outage-buffer-replay"}


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    local_mode = os.getenv("DEMO_MODE", "local") == "local"
    input_fresh = state.input_is_fresh()
    receiver_fresh = state.receiver_is_fresh()
    return {
        "simulator": {"state": "healthy", "last_input_at": state.last_input_at},
        "edge": {
            "state": (
                "healthy"
                if local_mode and input_fresh and receiver_fresh
                else "stale"
                if local_mode and (state.last_input_at or state.last_output_at)
                else "receiver-observed"
                if not local_mode and receiver_fresh
                else "receiver-stale"
                if not local_mode and state.last_output_at
                else "input-accepted"
                if not local_mode and state.last_input_at
                else "unverified"
                if not local_mode
                else "starting"
            )
        },
        "receiver": {"state": "healthy" if state.uplink_online else "offline-simulated"},
        "cloud_control": {"state": "not-used" if local_mode else "unverified"},
    }


@app.get("/api/snapshot")
async def snapshot() -> dict[str, object]:
    return state.snapshot()


@app.get("/api/events")
async def events() -> StreamingResponse:
    async def stream():
        while True:
            yield f"event: snapshot\ndata: {json.dumps(state.snapshot())}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/sink/events")
async def sink(request: Request) -> Response:
    state.destination_attempts += 1
    if not state.uplink_online:
        return Response(
            content='{"acknowledged":false}', status_code=503, media_type="application/json"
        )
    event = await request.json()
    sequence = int(event["sequence"])
    state.delivery_counts[sequence] += 1
    state.delivered_sequences.add(sequence)
    state.last_output_at = now_iso()
    state.last_output_monotonic = time.monotonic()
    state.last_ack = {"sequence": sequence, "acknowledged_at": state.last_output_at}
    state.recent.appendleft(event)
    return Response(
        content=json.dumps({"acknowledged": True, "sequence": sequence}),
        media_type="application/json",
    )


@app.post("/api/control/uplink")
async def uplink(request: Request) -> dict[str, object]:
    body = await request.json()
    online = bool(body["online"])
    state.uplink_online = online
    if online:
        state.restore_uplink()
        if state.outage_task is None or state.outage_task.done():
            state.outage_task = asyncio.create_task(finish_audit())
    else:
        state.outage_started_at = now_iso()
        state.phase = "offline"
    return {"online": online}


@app.post("/api/actions/{action_id}")
async def action(action_id: str, request: Request) -> dict[str, object]:
    if action_id != "run-outage":
        return {"accepted": False, "reason": "unknown action"}
    key = request.headers.get("idempotency-key") or "browser-default"
    if key in state.idempotency:
        return state.idempotency[key]
    result: dict[str, object] = {"accepted": True, "action_id": action_id, "idempotency_key": key}
    state.idempotency[key] = result
    state.outage_task = asyncio.create_task(run_outage())
    return result


@app.post("/api/control/reset")
@app.post("/api/reset")
async def reset() -> dict[str, object]:
    state.reset()
    return {"reset": True, "run_id": state.run_id, "seed": 424242}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parents[1] / "web" / "index.html")
