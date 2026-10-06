from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ACTIVITY_FRESH_SECONDS = 3.0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def node_record(index: int) -> dict[str, object]:
    return {
        "site_id": "wind-west",
        "node_id": f"edge-{index:02d}",
        "asset_id": f"turbine-{index:02d}",
        "region": "us-west",
        "app_version": "1.8.3" if index == 7 else "2.4.1",
    }


class DemoState:
    def __init__(self) -> None:
        self.expected = {f"edge-{i:02d}": node_record(i) for i in range(1, 11)}
        self.reset()

    def reset(self) -> None:
        self.run_id = str(uuid.uuid4())
        self.started = time.monotonic()
        self.tick = 0
        self.snapshot_seq = 0
        self.generated = 0
        self.accepted = 0
        self.received = 0
        self.faults_generated = 0
        self.faults_received = 0
        self.faults_attributable = 0
        self.configured_variant = os.getenv("DEMO_VARIANT", "baseline")
        self.active_variant = (
            self.configured_variant if os.getenv("DEMO_MODE", "local") == "local" else "unverified"
        )
        self.action_phase = "ready" if self.configured_variant == "baseline" else "measuring"
        self.revision_active_at: str | None = None
        self.last_input_at: str | None = None
        self.last_generated_at: str | None = None
        self.last_output_at: str | None = None
        self.last_admitted_monotonic: dict[str, float] = {}
        self.last_received_monotonic: dict[str, float] = {}
        self.baseline_fault: dict[str, object] | None = None
        self.baseline_acknowledgement: dict[str, object] | None = None
        self.first_enriched_fault: dict[str, object] | None = None
        self.first_enriched_acknowledgement: dict[str, object] | None = None
        self.recent = deque(maxlen=30)
        self.idempotency: dict[str, dict[str, object]] = {}
        self.forced_fault = False
        self.received_context: dict[str, dict[str, object]] = {}
        self.observed_pipeline_revision: str | None = None

    def make_event(self, index: int) -> dict[str, object]:
        is_fault = index == 7 and (self.tick % 5 == 0 or self.forced_fault)
        if is_fault:
            self.forced_fault = False
        event_id = hashlib.sha256(
            f"which-site:424242:{self.run_id}:{self.tick}:{index}".encode()
        ).hexdigest()[:16]
        event = {
            "event_id": event_id,
            "observed_at": now_iso(),
            "level": "ERROR" if is_fault else "INFO",
            "code": "SENSOR_TIMEOUT" if is_fault else "HEARTBEAT",
            "message": "sensor response timed out" if is_fault else "service healthy",
        }
        self.generated += 1
        self.last_generated_at = event["observed_at"]
        if is_fault:
            self.faults_generated += 1
        return event

    def local_node_activity(self, now: float | None = None) -> dict[str, str]:
        observed_at = time.monotonic() if now is None else now
        activity: dict[str, str] = {}
        for node_id in self.expected:
            admitted_at = self.last_admitted_monotonic.get(node_id)
            received_at = self.last_received_monotonic.get(node_id)
            fresh = (
                admitted_at is not None
                and received_at is not None
                and observed_at - admitted_at <= ACTIVITY_FRESH_SECONDS
                and observed_at - received_at <= ACTIVITY_FRESH_SECONDS
            )
            previously_seen = admitted_at is not None or received_at is not None
            activity[node_id] = "healthy" if fresh else "stale" if previously_seen else "starting"
        return activity

    def recent_receiver_count(self, now: float | None = None) -> int:
        observed_at = time.monotonic() if now is None else now
        return sum(
            observed_at - received_at <= ACTIVITY_FRESH_SECONDS
            for received_at in self.last_received_monotonic.values()
        )

    def snapshot(self) -> dict[str, object]:
        self.snapshot_seq += 1
        verified = self.first_enriched_fault is not None
        next_fault = datetime.now(UTC) + timedelta(seconds=max(5 - (self.tick % 5), 1))
        mode = os.getenv("DEMO_MODE", "local")
        local_mode = mode == "local"
        activity_now = time.monotonic()
        local_activity = self.local_node_activity(activity_now)
        receiver_fresh_nodes = self.recent_receiver_count(activity_now)
        local_running = sum(state == "healthy" for state in local_activity.values())
        local_seen = any(state != "starting" for state in local_activity.values())
        pipeline_status = (
            "running"
            if local_mode and local_running == 10
            else "degraded"
            if local_mode and local_running
            else "stale"
            if local_mode and local_seen
            else "starting"
            if local_mode
            else "receiver-observed"
            if self.last_output_at
            else "unverified"
        )
        nodes = []
        for index in range(1, 11):
            node_id = f"edge-{index:02d}"
            context = self.received_context.get(node_id)
            if context:
                nodes.append(
                    {
                        "id": f"source-slot-{index:02d}",
                        "health": local_activity[node_id] if local_mode else "receiver-observed",
                        "identity_state": "receiver-observed",
                        "site_id": context["site_id"],
                        "node_id": context["node_id"],
                        "asset_id": context.get("asset_id"),
                        "region": context.get("region"),
                        "app_version": context["app_version"],
                        "deployed_revision": context["pipeline_version"],
                    }
                )
            else:
                nodes.append(
                    {
                        "id": f"source-slot-{index:02d}",
                        "label": f"Source {index:02d}",
                        "health": local_activity[node_id] if local_mode else "unverified",
                        "identity_state": "anonymous",
                    }
                )
        return {
            "demo_id": "which-site-broke",
            "schema_version": "1.0",
            "run_id": self.run_id,
            "snapshot_seq": self.snapshot_seq,
            "server_time": now_iso(),
            "metrics_window_ms": 5000,
            "synthetic": True,
            "seed": 424242,
            "mode": mode,
            "scenario": "which-site-broke",
            "clock": now_iso(),
            "pipeline": {
                "variant": self.active_variant,
                "expected_variant": self.configured_variant,
                "status": pipeline_status,
                "last_input_at": self.last_input_at,
                "last_output_at": self.last_output_at,
                "receiver_fresh_nodes": receiver_fresh_nodes,
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
                "pipeline_revision": self.observed_pipeline_revision
                or (f"{self.configured_variant}-v1" if local_mode else None),
                "nodes_scheduled": 10 if local_mode else None,
                "nodes_running": local_running if local_mode else None,
            },
            "nodes": nodes,
            "edges": [
                {
                    "from": "fleet",
                    "to": "receiver",
                    "state": (
                        "active"
                        if local_mode and local_running == 10
                        else "degraded"
                        if local_mode and local_running
                        else "stale"
                        if local_mode and local_seen
                        else "starting"
                        if local_mode
                        else "receiver-observed"
                        if self.last_output_at
                        else "unverified"
                    ),
                }
            ],
            "metrics": {
                "records_generated_total": self.generated,
                "pipeline_http_accepted": self.accepted,
                "records_received_total": self.received,
                "faults_generated_total": self.faults_generated,
                "faults_received_total": self.faults_received,
                "faults_attributable_total": self.faults_attributable,
                "sites_online": local_running if local_mode else None,
                "sites_expected": 10,
                "fault_schedule_ms": 5000,
                "next_fault_at": next_fault.isoformat(),
            },
            "evidence": {
                "payloads": [
                    event for event in [self.baseline_fault, self.first_enriched_fault] if event
                ],
                "acknowledgements": list(self.recent)[:4],
                "baseline_fault": self.baseline_fault,
                "baseline_acknowledgement": self.baseline_acknowledgement,
                "first_enriched_fault": self.first_enriched_fault,
                "first_enriched_acknowledgement": self.first_enriched_acknowledgement,
                "context_by_node": self.received_context,
            },
            "action": {
                "id": "add-context",
                "label": "Add source context",
                "enabled": local_mode and self.action_phase != "applying",
                "phase": self.action_phase,
            },
            "verification": {
                "state": "verified" if verified else "pending",
                "assertions": [
                    {
                        "name": "receiver_enrichment_observed",
                        "passed": self.observed_pipeline_revision is not None,
                    },
                    {"name": "receiver_context_present", "passed": verified},
                ],
            },
        }


state = DemoState()


async def simulate() -> None:
    raw_urls = os.getenv(
        "PIPELINE_URLS", ",".join(f"http://pipeline-{i:02d}:8080/ingest" for i in range(1, 11))
    )
    urls = raw_urls.split(",")
    async with httpx.AsyncClient(timeout=2.5) as client:
        while True:
            state.tick += 1
            for index, url in enumerate(urls, start=1):
                event = state.make_event(index)
                try:
                    response = await client.post(url, json=event)
                    if response.is_success:
                        state.accepted += 1
                        state.last_input_at = now_iso()
                        state.last_admitted_monotonic[f"edge-{index:02d}"] = time.monotonic()
                except httpx.HTTPError:
                    pass
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if os.getenv("SIMULATOR_ENABLED", "true").lower() == "true":
        task = asyncio.create_task(simulate())
    yield
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Which site broke?", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=Path(__file__).parents[1] / "web"), name="assets")


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "scenario": "which-site-broke"}


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    local_mode = os.getenv("DEMO_MODE", "local") == "local"
    local_activity = state.local_node_activity()
    local_running = sum(value == "healthy" for value in local_activity.values())
    local_seen = any(value != "starting" for value in local_activity.values())
    receiver_fresh = state.recent_receiver_count()
    return {
        "simulator": {
            "state": "healthy" if state.last_generated_at else "starting",
            "last_input_at": state.last_input_at,
        },
        "edge": {
            "state": (
                "healthy"
                if local_mode and local_running == 10
                else "degraded"
                if local_mode and local_running
                else "stale"
                if local_mode and local_seen
                else "unverified"
                if not local_mode
                else "starting"
            ),
            "running": local_running if local_mode else None,
        },
        "receiver": {
            "state": (
                "healthy"
                if local_mode and receiver_fresh == 10
                else "degraded"
                if local_mode and receiver_fresh
                else "stale"
                if local_mode and state.last_output_at
                else "starting"
                if local_mode
                else "receiver-observed"
                if receiver_fresh
                else "receiver-stale"
                if state.last_output_at
                else "unverified"
            )
        },
        "cloud_control": {
            "state": "not-used" if os.getenv("DEMO_MODE", "local") == "local" else "unverified"
        },
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
async def sink(request: Request) -> dict[str, object]:
    event = await request.json()
    private_origin = request.headers.get("x-demo-transport-origin", "unknown")
    state.received += 1
    state.last_output_at = now_iso()
    if private_origin in state.expected:
        state.last_received_monotonic[private_origin] = time.monotonic()
    is_fault = event.get("level") == "ERROR"
    context = event.get("source_context")
    expected = state.expected.get(private_origin)
    attributable = bool(
        context
        and expected
        and all(context.get(key) == value for key, value in expected.items())
        and context.get("pipeline_version") == "lineage-v2"
    )
    if is_fault:
        state.faults_received += 1
        if attributable:
            state.faults_attributable += 1
            if state.first_enriched_fault is None:
                state.first_enriched_fault = event
                state.action_phase = "verified"
        elif state.baseline_fault is None:
            state.baseline_fault = event
    if attributable:
        state.received_context[str(context["node_id"])] = context
        state.active_variant = "enriched"
        state.observed_pipeline_revision = str(context["pipeline_version"])
        state.revision_active_at = state.revision_active_at or state.last_output_at
        if state.action_phase == "applying":
            state.action_phase = "measuring"
    accepted_origin = bool(
        expected
        and (not context or all(context.get(key) == value for key, value in expected.items()))
    )
    ack = {
        "event_id": event["event_id"],
        "acknowledged_at": state.last_output_at,
        "origin_check": accepted_origin,
    }
    state.recent.appendleft(ack)
    if is_fault and attributable and state.first_enriched_fault == event:
        state.first_enriched_acknowledgement = state.first_enriched_acknowledgement or ack
    elif is_fault and not attributable and state.baseline_fault == event:
        state.baseline_acknowledgement = state.baseline_acknowledgement or ack
    return {"acknowledged": True, "event_id": event["event_id"]}


@app.post("/api/control/fault")
async def fault() -> dict[str, object]:
    state.forced_fault = True
    return {"queued": True}


async def deploy_enriched() -> None:
    state.action_phase = "applying"
    config = (Path(__file__).parents[1] / "pipelines" / "enriched.runtime.yaml").read_text()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            pending = {i for i in range(1, 11)}
            for _ in range(40):
                failed = set()
                for i in pending:
                    try:
                        response = await client.put(
                            f"http://pipeline-{i:02d}:4195/streams/active",
                            content=config,
                            headers={"content-type": "application/yaml"},
                        )
                        response.raise_for_status()
                    except httpx.HTTPError:
                        failed.add(i)
                pending = failed
                if not pending:
                    break
                await asyncio.sleep(0.25)
            if pending:
                raise RuntimeError(f"pipelines did not accept revision: {sorted(pending)}")
        state.forced_fault = True
    except Exception:
        state.action_phase = "failed"


@app.post("/api/actions/{action_id}")
async def action(action_id: str, request: Request) -> dict[str, object]:
    if action_id != "add-context":
        return {"accepted": False, "reason": "unknown action"}
    key = request.headers.get("idempotency-key") or "browser-default"
    if key in state.idempotency:
        return state.idempotency[key]
    if os.getenv("DEMO_MODE", "local") == "cloud":
        return {
            "accepted": False,
            "action_id": action_id,
            "reason": "apply the pipeline revision in Expanso Cloud; this runtime verifies receiver-observed source context",
        }
    result: dict[str, object] = {"accepted": True, "action_id": action_id, "idempotency_key": key}
    state.idempotency[key] = result
    asyncio.create_task(deploy_enriched())
    return result


@app.post("/api/control/reset")
@app.post("/api/reset")
async def reset() -> dict[str, object]:
    if os.getenv("SIMULATOR_ENABLED", "true").lower() == "true":
        config = (Path(__file__).parents[1] / "pipelines" / "baseline.runtime.yaml").read_text()
        async with httpx.AsyncClient(timeout=10) as client:
            responses = await asyncio.gather(
                *[
                    client.put(
                        f"http://pipeline-{i:02d}:4195/streams/active",
                        content=config,
                        headers={"content-type": "application/yaml"},
                    )
                    for i in range(1, 11)
                ]
            )
            for response in responses:
                response.raise_for_status()
    state.reset()
    return {"reset": True, "run_id": state.run_id, "seed": 424242}


@app.post("/api/control/reset-counters")
async def reset_counters() -> dict[str, object]:
    state.reset()
    return {"reset": True, "run_id": state.run_id, "seed": 424242}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parents[1] / "web" / "index.html")
