from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
DEMOCTL = (ROOT / "scripts" / "democtl.sh").read_text()


def test_browser_ui_exposes_truthful_outage_story():
    assert "The network fails; the data doesn’t" in HTML
    assert "Synthetic records · simulated 12-second receiver 503 · at-least-once" in HTML
    assert "Cloud controls jobs." in HTML
    assert "Payloads stay on the data plane." in HTML
    assert "Run 12-second outage" in HTML
    assert 'fetch("/api/actions/run-outage"' in HTML
    assert "REAL HTTP 503" in HTML
    assert "Edge drop telemetry is not measured in this runtime." in HTML
    assert "Observed this run through seq" in HTML
    assert "At-least-once transport." in HTML


def test_phase_rail_covers_every_runtime_phase_in_order():
    labels = [
        "READY",
        "DESTINATION OFFLINE",
        "DRAINING",
        "RECEIVER AUDIT",
        "VERIFIED / FAILED",
    ]
    rail_start = HTML.index('<ol class="phase-progress"')
    rail_end = HTML.index("</ol>", rail_start)
    rail = HTML[rail_start:rail_end]
    positions = [rail.index(label) for label in labels]
    assert positions == sorted(positions)


def test_verified_snapshot_freezes_only_after_all_integrity_guards():
    guard_start = HTML.index("function terminalAudit(snapshot)")
    guard_end = HTML.index("function displayPhaseFor(snapshot)")
    guard = HTML[guard_start:guard_end]
    assert 'snapshot.phase !== "verified"' in guard
    assert 'snapshot.verification.state !== "verified"' in guard
    assert "allAssertionsPass(snapshot)" in guard
    assert "metrics.audit_high_water" in guard
    assert "metrics.audit_accepted_total" in guard
    assert "metrics.audit_acknowledged_total" in guard
    assert "audit.bounded" in guard
    assert "audit.admitted === audit.acknowledged" in guard
    assert "frozenVerifiedSnapshot = cloneSnapshot(snapshot)" in HTML


def test_terminal_evidence_keeps_audit_scope_separate_from_live_totals():
    assert "base.audit_scope = audit.scope" in HTML
    assert "base.audit_high_water = audit.highWater" in HTML
    assert "base.audit_admitted_total = audit.admitted" in HTML
    assert "base.audit_acknowledged_total = audit.acknowledged" in HTML
    assert "base.live_totals_at_freeze" in HTML
    assert "AUDIT HIGH-WATER ACKNOWLEDGEMENT" in HTML


def test_cloud_buffer_state_stays_explicitly_unverified():
    helper_start = HTML.index("function hasMeasuredLocalBuffer")
    helper_end = HTML.index("function terminalAudit", helper_start)
    helper = HTML[helper_start:helper_end]
    assert 'mode === "local"' in helper
    assert 'control.state === "local"' in helper
    assert 'pipeline.variant === "durable-sqlite"' in helper
    assert 'pipeline.status === "running"' in helper
    assert 'elements.edgeStatus.textContent = "UNVERIFIED"' in HTML
    assert (
        'elements.queue.textContent = bufferMeasured ? formatCount(metrics.queued_total) : "UNVERIFIED"'
        in HTML
    )
    assert "Expected durable SQLite buffer · Cloud execution unverified" in HTML
    assert "Expected Edge queue; Cloud execution unverified" in HTML


def test_cloud_copy_does_not_claim_queue_empty_or_observed_replay():
    assert 'base.edge_buffer_state = "expected-but-unverified"' in HTML
    assert 'base[bufferMeasured ? "edge_admitted_range" : "pipeline_accepted_range"]' in HTML
    assert '"Receiver acknowledgements resumed; replay state is unverified."' in HTML
    assert '"RECEIVER AUDIT PENDING · EDGE QUEUE UNVERIFIED"' in HTML
    assert "Cloud Edge buffer execution remains unverified." in HTML


def test_measured_local_sqlite_queue_and_replay_copy_is_preserved():
    assert 'elements.edgeStatus.textContent = "BUFFERING"' in HTML
    assert 'elements.edgeStatus.textContent = "REPLAYING"' in HTML
    assert 'elements.edgeStatus.textContent = "QUEUE EMPTY"' in HTML
    assert '"Receiver returning HTTP 503. Expanso Edge is buffering locally."' in HTML
    assert '"Destination restored. Replaying queued sequence IDs."' in HTML


def test_live_transport_is_atomic_monotonic_and_reconnect_safe():
    assert 'fetch("/api/snapshot"' in HTML
    assert 'new EventSource("/api/events")' in HTML
    assert 'eventSource.addEventListener("snapshot"' in HTML
    assert "snapshotSeq <= latestSnapshotSeq" in HTML
    assert "STALE_WARNING_MS = 2000" in HTML
    assert "STALE_DISABLE_MS = 5000" in HTML
    assert HTML.count("startFallbackPolling();") == 1


def test_copy_never_overstates_delivery_semantics():
    normalized = HTML.lower()
    assert "exactly once" not in normalized
    assert "exactly-once" not in normalized
    assert "100% reliable" not in normalized


def test_accessibility_and_recording_contracts_are_present():
    assert 'aria-live="polite"' in HTML
    assert 'aria-label="Outage run phase"' in HTML
    assert 'aria-label="Edge queue utilization"' in HTML
    assert "min-height: 48px" in HTML
    assert "min-height: 44px" in HTML
    assert "@media (prefers-reduced-motion: reduce)" in HTML
    assert "transition: all" not in HTML


def test_self_hosted_font_assets_are_bundled():
    expected = [
        "ibm-plex-sans-latin-400-normal.woff2",
        "ibm-plex-sans-latin-500-normal.woff2",
        "ibm-plex-mono-latin-400-normal.woff2",
        "ibm-plex-mono-latin-500-normal.woff2",
    ]
    for filename in expected:
        font = ROOT / "web" / "fonts" / filename
        assert font.read_bytes().startswith(b"wOF2")
        assert f"/assets/fonts/{filename}" in HTML


def test_browser_verifier_drains_the_page_response_before_matching():
    assert 'page="$(curl -fsS' in DEMOCTL
    assert "| grep -q 'network fails'" not in DEMOCTL
