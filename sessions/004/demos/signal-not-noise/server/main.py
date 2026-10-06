from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections import Counter, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

VERIFICATION_INCIDENT_CODE = "COMPRESSOR_OVERHEAT"
VERIFICATION_INCIDENT_MESSAGE = "compressor temperature exceeded safe operating threshold"
ACTIVITY_FRESH_SECONDS = 3.0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class DemoState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.run_id = str(uuid.uuid4())
        self.started = time.monotonic()
        self.sequence = 0
        self.generated = 0
        self.generated_bytes = 0
        self.pipeline_accepted = 0
        self.pipeline_accepted_bytes = 0
        self.pipeline_rejected = 0
        self.downstream_acked = 0
        self.downstream_bytes = 0
        self.levels: Counter[str] = Counter()
        self.recent = deque(maxlen=20)
        self.pending_incidents: deque[str] = deque()
        self.incident_status: dict[str, dict[str, object]] = {}
        self.last_input_at: str | None = None
        self.last_generated_at: str | None = None
        self.last_output_at: str | None = None
        self.snapshot_seq = 0
        self.active_variant = os.getenv("DEMO_VARIANT", "baseline")
        self.revision_active_at: str | None = None
        self.action_phase = "ready" if self.active_variant == "baseline" else "measuring"
        self.idempotency: dict[str, dict[str, object]] = {}
        self.generated_window: deque[tuple[float, int]] = deque()
        self.accepted_window: deque[tuple[float, int]] = deque()
        self.delivered_window: deque[tuple[float, int]] = deque()
        self.faults_generated = 0
        self.faults_accepted = 0
        self.faults_received = 0
        self.latest_routine: dict[str, object] | None = None
        self.latest_fault: dict[str, object] | None = None
        self.latest_ack: dict[str, object] | None = None
        self.verification_incident: str | None = None
        self.verification_event: dict[str, object] | None = None
        self.verification_ack: dict[str, object] | None = None

    def make_event(self, forced_id: str | None = None) -> tuple[dict[str, object], bytes]:
        self.sequence += 1
        cycle = (self.sequence - 1) % 100
        level = (
            "DEBUG" if cycle < 70 else "INFO" if cycle < 94 else "WARN" if cycle < 99 else "ERROR"
        )
        if forced_id:
            level = "ERROR"
        event_id = (
            forced_id
            or hashlib.sha256(f"424242:{self.run_id}:{self.sequence}".encode()).hexdigest()[:16]
        )
        message = (
            VERIFICATION_INCIDENT_MESSAGE
            if forced_id
            else {
                "DEBUG": "cache probe completed",
                "INFO": "request completed",
                "WARN": "upstream latency elevated",
                "ERROR": "database connection pool exhausted",
            }[level]
        )
        event = {
            "event_id": event_id,
            "observed_at": now_iso(),
            "level": level,
            "message": message,
            "synthetic": True,
            "payload": "x" * 96,
        }
        if forced_id:
            event["code"] = VERIFICATION_INCIDENT_CODE
        body = json.dumps(event, separators=(",", ":")).encode()
        self.generated += 1
        self.generated_bytes += len(body)
        self.generated_window.append((time.monotonic(), len(body)))
        if level == "ERROR":
            self.faults_generated += 1
            self.latest_fault = event
        else:
            self.latest_routine = event
        self.last_generated_at = event["observed_at"]
        if forced_id:
            proof = self.incident_status.setdefault(
                forced_id, {"accepted": False, "delivered": False}
            )
            proof["emitted_code"] = event["code"]
        return event, body

    def local_activity(self, now: float | None = None) -> dict[str, bool]:
        observed_at = time.monotonic() if now is None else now
        return {
            "source": bool(
                self.generated_window
                and observed_at - self.generated_window[-1][0] <= ACTIVITY_FRESH_SECONDS
            ),
            "pipeline": bool(
                self.accepted_window
                and observed_at - self.accepted_window[-1][0] <= ACTIVITY_FRESH_SECONDS
            ),
            "receiver": bool(
                self.delivered_window
                and observed_at - self.delivered_window[-1][0] <= ACTIVITY_FRESH_SECONDS
            ),
        }

    def snapshot(self) -> dict[str, object]:
        self.snapshot_seq += 1
        now = time.monotonic()
        cutoff = now - 5
        while self.generated_window and self.generated_window[0][0] < cutoff:
            self.generated_window.popleft()
        while self.accepted_window and self.accepted_window[0][0] < cutoff:
            self.accepted_window.popleft()
        while self.delivered_window and self.delivered_window[0][0] < cutoff:
            self.delivered_window.popleft()
        elapsed = max(time.monotonic() - self.started, 0.001)
        delivered_ratio = self.downstream_acked / max(self.pipeline_accepted, 1)
        generated_5s = sum(size for _, size in self.generated_window)
        accepted_5s = sum(size for _, size in self.accepted_window)
        delivered_5s = sum(size for _, size in self.delivered_window)
        reduction = 100 * max(accepted_5s - delivered_5s, 0) / max(accepted_5s, 1)
        accepted_window_span = (
            self.accepted_window[-1][0] - self.accepted_window[0][0]
            if len(self.accepted_window) > 1
            else 0
        )
        full_accepted_window = accepted_window_span >= 4.5
        delivered_to_accepted = delivered_5s / max(accepted_5s, 1)
        observed_filter = full_accepted_window and accepted_5s > 0 and delivered_to_accepted <= 0.20
        mode = os.getenv("DEMO_MODE", "local")
        should_emit_verification_incident = mode == "cloud" or self.active_variant == "filtered"
        if (
            observed_filter
            and should_emit_verification_incident
            and self.verification_incident is None
        ):
            incident_id = f"incident-{uuid.uuid4().hex[:12]}"
            self.pending_incidents.append(incident_id)
            self.incident_status[incident_id] = {"accepted": False, "delivered": False}
            self.verification_incident = incident_id
            self.action_phase = "measuring"
        proof = self.incident_status.get(self.verification_incident or "", {})
        exact_code = (
            proof.get("accepted_code") == VERIFICATION_INCIDENT_CODE
            and proof.get("delivered_code") == VERIFICATION_INCIDENT_CODE
        )
        exact_incident = (
            exact_code and proof.get("accepted") is True and proof.get("delivered") is True
        )
        verified = observed_filter and exact_incident
        local_mode = mode == "local"
        activity = self.local_activity(now)
        edge_fresh = activity["pipeline"] and activity["receiver"]
        reported_variant = self.active_variant if local_mode else "unverified"
        reported_revision = f"{self.active_variant}-v1" if local_mode else None
        pipeline_status = (
            "running"
            if local_mode and activity["pipeline"]
            else "stale"
            if local_mode and self.last_input_at
            else "starting"
            if local_mode
            else "receiver-observed"
            if self.last_output_at
            else "unverified"
        )
        source_state = (
            "healthy"
            if local_mode and activity["source"]
            else "stale"
            if local_mode and self.last_generated_at
            else "starting"
            if local_mode
            else "source-observed"
            if self.last_generated_at
            else "unverified"
        )
        edge_state = (
            "healthy"
            if local_mode and edge_fresh
            else "stale"
            if local_mode and (self.last_input_at or self.last_output_at)
            else "starting"
            if local_mode
            else "receiver-observed"
            if self.last_output_at
            else "unverified"
        )
        evidence_payloads: list[dict[str, object]] = []
        seen_payload_ids: set[object] = set()
        for item in [self.verification_event, self.latest_routine, self.latest_fault]:
            if item and item.get("event_id") not in seen_payload_ids:
                evidence_payloads.append(item)
                seen_payload_ids.add(item.get("event_id"))
        evidence_acknowledgements: list[dict[str, object]] = []
        seen_ack_ids: set[object] = set()
        for item in [self.verification_ack, self.latest_ack]:
            if item and item.get("event_id") not in seen_ack_ids:
                evidence_acknowledgements.append(item)
                seen_ack_ids.add(item.get("event_id"))
        action_phase = "verified" if verified else self.action_phase
        return {
            "demo_id": "signal-not-noise",
            "snapshot_seq": self.snapshot_seq,
            "server_time": now_iso(),
            "metrics_window_ms": 5000,
            "synthetic": True,
            "seed": 424242,
            "schema_version": "1.0",
            "run_id": self.run_id,
            "mode": mode,
            "scenario": "signal-not-noise",
            "clock": now_iso(),
            "pipeline": {
                "variant": reported_variant,
                "expected_variant": self.active_variant,
                "status": pipeline_status,
                "last_input_at": self.last_input_at,
                "last_output_at": self.last_output_at,
                "receiver_fresh": activity["receiver"],
            },
            "truth": {
                "synthetic_source": True,
                "cloud_managed": mode == "cloud",
                "window_seconds": round(elapsed, 2),
            },
            "metrics": {
                "generated": self.generated,
                "generated_bytes": self.generated_bytes,
                "pipeline_http_accepted": self.pipeline_accepted,
                "pipeline_http_accepted_bytes": self.pipeline_accepted_bytes,
                "pipeline_http_rejected": self.pipeline_rejected,
                "downstream_acked": self.downstream_acked,
                "downstream_ack_bytes": self.downstream_bytes,
                "delivered_ratio": round(delivered_ratio, 4),
                "generated_per_second": round(self.generated / elapsed, 1),
                "acked_per_second": round(self.downstream_acked / elapsed, 1),
                "downstream_levels": dict(self.levels),
                "raw_bytes_total": self.pipeline_accepted_bytes,
                "generated_bytes_total": self.generated_bytes,
                "delivered_bytes_total": self.downstream_bytes,
                "generated_rate_bps_5s": round(generated_5s / 5, 1),
                "raw_rate_bps_5s": round(accepted_5s / 5, 1),
                "delivered_rate_bps_5s": round(delivered_5s / 5, 1),
                "records_generated_total": self.generated,
                "records_delivered_total": self.downstream_acked,
                "records_filtered_total": max(self.pipeline_accepted - self.downstream_acked, 0),
                "faults_generated_total": self.faults_generated,
                "faults_pipeline_accepted_total": self.faults_accepted,
                "faults_received_total": self.faults_received,
                "byte_reduction_percent": round(reduction, 1),
                "byte_reduction_numerator": max(accepted_5s - delivered_5s, 0),
                "byte_reduction_denominator": accepted_5s,
            },
            "control_plane": {
                "mode": mode,
                "state": "local" if local_mode else "unverified",
                "cloud_url": "https://cloud.expanso.io",
                "job_id": None,
                "pipeline_revision": reported_revision,
                "nodes_scheduled": 1 if local_mode else None,
                "nodes_running": int(edge_fresh) if local_mode else None,
            },
            "nodes": [
                {
                    "id": "compressor-service",
                    "kind": "synthetic-source",
                    "state": source_state,
                },
                {"id": "expanso-edge", "kind": "edge-pipeline", "state": edge_state},
            ],
            "edges": [
                {
                    "from": "compressor-service",
                    "to": "expanso-edge",
                    "state": (
                        "active"
                        if local_mode and activity["pipeline"]
                        else "stale"
                        if local_mode
                        else edge_state
                    ),
                },
                {
                    "from": "expanso-edge",
                    "to": "demo-receiver",
                    "state": (
                        "active"
                        if local_mode and activity["receiver"]
                        else "stale"
                        if local_mode
                        else edge_state
                    ),
                },
            ],
            "evidence": {
                "payloads": evidence_payloads,
                "acknowledgements": evidence_acknowledgements,
                "verification_event": self.verification_event,
                "verification_acknowledgement": self.verification_ack,
            },
            "action": {
                "id": "apply-filter",
                "label": "Apply edge filter" if self.active_variant == "baseline" else "Reset run",
                "enabled": local_mode and self.action_phase != "applying",
                "phase": action_phase,
            },
            "verification": {
                "state": "verified" if verified else "pending",
                "incident_id": self.verification_incident,
                "expected_code": VERIFICATION_INCIDENT_CODE,
                "assertions": [
                    {
                        "name": "accepted_window_filter_observed",
                        "passed": observed_filter,
                    },
                    {"name": "selected_incident_exact_code", "passed": exact_code},
                    {"name": "exact_accepted_incident_delivered", "passed": exact_incident},
                ],
            },
            "filter_observation": {
                "observed": observed_filter,
                "full_window": full_accepted_window,
                "accepted_window_span_seconds": round(accepted_window_span, 3),
                "delivered_to_accepted_byte_ratio": round(delivered_to_accepted, 4),
                "threshold_ratio": 0.20,
                "basis": "pipeline_http_accepted_bytes_vs_receiver_ack_bytes",
            },
            "filter_state": "observed" if observed_filter else "unobserved",
            "pipeline_revision": reported_revision,
            "revision_active_at": self.revision_active_at,
            "incidents": self.incident_status,
            "recent": list(self.recent),
        }


state = DemoState()


async def simulate() -> None:
    url = os.getenv("PIPELINE_URL", "http://pipeline:8080/ingest")
    next_send = time.monotonic()
    async with httpx.AsyncClient(timeout=2.5) as client:
        while True:
            forced_id = state.pending_incidents.popleft() if state.pending_incidents else None
            event, body = state.make_event(forced_id)
            try:
                response = await client.post(
                    url, content=body, headers={"content-type": "application/json"}
                )
                if response.is_success:
                    accepted_at = time.monotonic()
                    state.pipeline_accepted += 1
                    state.pipeline_accepted_bytes += len(body)
                    state.accepted_window.append((accepted_at, len(body)))
                    state.last_input_at = now_iso()
                    if event["level"] == "ERROR":
                        state.faults_accepted += 1
                    if forced_id:
                        state.incident_status[forced_id].update(
                            {"accepted": True, "accepted_code": event.get("code")}
                        )
                else:
                    state.pipeline_rejected += 1
            except httpx.HTTPError:
                state.pipeline_rejected += 1
            next_send += 0.02
            await asyncio.sleep(max(next_send - time.monotonic(), 0))


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if os.getenv("SIMULATOR_ENABLED", "true").lower() == "true":
        task = asyncio.create_task(simulate())
    yield
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Signal, not noise", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=Path(__file__).parents[1] / "web"), name="assets")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "scenario": "signal-not-noise"}


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


@app.post("/api/sink/logs")
async def sink(request: Request) -> dict[str, object]:
    body = await request.body()
    event = json.loads(body)
    state.downstream_acked += 1
    state.downstream_bytes += len(body)
    state.delivered_window.append((time.monotonic(), len(body)))
    state.levels[event["level"]] += 1
    state.last_output_at = now_iso()
    state.recent.appendleft(event)
    ack = {
        "event_id": event["event_id"],
        "code": event.get("code"),
        "acknowledged_at": state.last_output_at,
    }
    state.latest_ack = ack
    if event["level"] == "ERROR":
        state.faults_received += 1
    event_id = event["event_id"]
    if event_id in state.incident_status:
        state.incident_status[event_id].update(
            {"delivered": True, "delivered_code": event.get("code")}
        )
    if event_id == state.verification_incident:
        state.verification_event = event
        state.verification_ack = ack
    return {"acknowledged": True, "event_id": event_id}


@app.post("/api/control/incident")
async def incident() -> dict[str, object]:
    event_id = f"incident-{uuid.uuid4().hex[:12]}"
    state.pending_incidents.append(event_id)
    state.incident_status[event_id] = {"accepted": False, "delivered": False}
    if state.active_variant == "filtered":
        state.verification_incident = event_id
        state.action_phase = "measuring"
    return {"queued": True, "event_id": event_id}


@app.post("/api/control/reset")
async def reset() -> dict[str, object]:
    if os.getenv("SIMULATOR_ENABLED", "true").lower() == "true":
        config = (Path(__file__).parents[1] / "pipelines" / "baseline.runtime.yaml").read_text()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.put(
                "http://pipeline:4195/streams/active",
                content=config,
                headers={"content-type": "application/yaml"},
            )
            response.raise_for_status()
    state.reset()
    return {"reset": True, "run_id": state.run_id}


@app.post("/api/control/reset-counters")
async def reset_counters() -> dict[str, object]:
    state.reset()
    return {"reset": True, "run_id": state.run_id}


@app.post("/api/reset")
async def reset_ui() -> dict[str, object]:
    return await reset()


async def apply_filtered_pipeline() -> None:
    state.action_phase = "applying"
    try:
        config = (Path(__file__).parents[1] / "pipelines" / "filtered.runtime.yaml").read_text()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.put(
                "http://pipeline:4195/streams/active",
                content=config,
                headers={"content-type": "application/yaml"},
            )
            response.raise_for_status()
        state.active_variant = "filtered"
        state.revision_active_at = now_iso()
        state.action_phase = "measuring"
    except Exception:
        state.action_phase = "failed"


@app.post("/api/actions/{action_id}")
async def action(action_id: str, request: Request) -> dict[str, object]:
    if action_id != "apply-filter":
        return {"accepted": False, "reason": "unknown action"}
    key = request.headers.get("idempotency-key") or "browser-default"
    if key in state.idempotency:
        return state.idempotency[key]
    if os.getenv("DEMO_MODE", "local") == "cloud":
        return {
            "accepted": False,
            "action_id": action_id,
            "reason": "apply the pipeline revision in Expanso Cloud; this runtime verifies observed data-plane behavior",
        }
    result: dict[str, object] = {"accepted": True, "action_id": action_id, "idempotency_key": key}
    state.idempotency[key] = result
    asyncio.create_task(apply_filtered_pipeline())
    return result


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    local_mode = os.getenv("DEMO_MODE", "local") == "local"
    activity = state.local_activity()
    edge_fresh = activity["pipeline"] and activity["receiver"]
    return {
        "simulator": {
            "state": (
                "healthy"
                if local_mode and activity["source"]
                else "stale"
                if local_mode and state.last_generated_at
                else "starting"
                if local_mode
                else "unverified"
            ),
            "last_input_at": state.last_input_at,
        },
        "edge": {
            "state": (
                "healthy"
                if local_mode and edge_fresh
                else "stale"
                if local_mode and (state.last_input_at or state.last_output_at)
                else "receiver-observed"
                if not local_mode and state.last_output_at
                else "unverified"
                if not local_mode
                else "starting"
            )
        },
        "receiver": {
            "state": (
                "healthy"
                if local_mode and activity["receiver"]
                else "stale"
                if local_mode and state.last_output_at
                else "starting"
                if local_mode
                else "receiver-observed"
                if state.last_output_at
                else "unverified"
            )
        },
        "cloud_control": {"state": "not-used" if local_mode else "unverified"},
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parents[1] / "web" / "index.html")
