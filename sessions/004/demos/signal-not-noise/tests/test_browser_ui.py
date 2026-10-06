from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
DEMOCTL = (ROOT / "scripts" / "democtl.sh").read_text()


def test_browser_ui_preserves_production_control_plane_boundary():
    assert "Signal, not noise" in HTML
    assert "Copy pipeline step" in HTML
    assert "Pipeline step copied. Deploy it in Expanso Cloud." in HTML
    assert "Apply edge filter" not in HTML
    assert "Cloud is the control plane" in HTML
    assert "/api/actions/apply-filter" in HTML
    assert 'document.execCommand("copy")' in HTML
    assert "LOCAL REHEARSAL" in HTML


def test_browser_ui_labels_simulation_and_the_pre_snapshot_truth_boundary():
    assert "SIMULATED SOURCE" in HTML
    assert "CONTROL: EXPANSO CLOUD · runtime proof pending." in HTML
    assert "AWAITING SNAPSHOT" in HTML
    assert (
        'els["receiver-node"].classList.toggle("active", Boolean(evidence.ack?.event_id))' in HTML
    )


def test_browser_ui_contains_exact_validated_filter_fragment():
    assert (
        '- mapping: \'root = if [\\"WARN\\", \\"ERROR\\"].contains(this.level) '
        "{ this } else { deleted() }'"
    ) in HTML


def test_browser_ui_waits_for_receiver_derived_proof():
    assert "/api/snapshot" in HTML
    assert 'new EventSource("/api/events")' in HTML
    assert 'addEventListener("snapshot"' in HTML
    assert "next.snapshot_seq <= lastSnapshotSeq" in HTML
    assert "const filterVerified = (data) => data.filter_observation?.observed === true" in HTML
    assert 'data.verification?.state !== "verified"' in HTML
    assert "!allAssertionsPass(data)" in HTML
    assert "assertions.length > 0" in HTML
    assert "assertions.every" in HTML
    assert "acknowledgement?.event_id !== eventId" in HTML
    assert "data.verification?.incident_id !== eventId" in HTML
    assert 'event?.code !== "COMPRESSOR_OVERHEAT"' in HTML
    assert 'acknowledgement?.code !== "COMPRESSOR_OVERHEAT"' in HTML
    assert "verifiedIncidentId(data) === protectedIncidentId" in HTML
    assert "next.verification?.incident_id || verifiedIncidentId(next)" in HTML
    assert "item?.event_id === latestAck?.event_id" in HTML
    assert "COMPRESSOR_OVERHEAT" in HTML


def test_cloud_observation_is_not_presented_as_control_plane_verification():
    assert 'data.filter_state === "observed"' in HTML
    assert "const cloudControlPlaneVerified = !isLocal" in HTML
    assert 'control.state !== "unverified"' in HTML
    assert 'data.pipeline?.status === "running"' in HTML
    assert '"FILTER OBSERVED BY RECEIVER"' in HTML
    assert '"Cloud revision unverified"' in HTML
    assert '"RECEIVER OBSERVED"' in HTML
    assert '"FILTER OBSERVED · COMPLETE"' in HTML
    assert '"REVISION ACTIVE · MEASURING"' not in HTML


def test_local_mode_alone_cannot_render_edge_healthy():
    assert (
        'const localPipelineHealthy = isLocal && ["running", "healthy"].includes(data.pipeline?.status)'
        in HTML
    )
    assert 'localPipelineHealthy ? "HEALTHY"' in HTML
    assert 'data.pipeline?.status === "stale" ? "STALE" : "WAITING"' in HTML
    assert "const controlPlaneVerified = isLocal ||" not in HTML


def test_cloud_story_has_one_operator_action_then_waits_for_auto_incident():
    assert "Copy pipeline step" in HTML
    assert '"Waiting for protected incident…"' in HTML
    assert '"Incident verified"' in HTML
    assert 'fetch("/api/control/incident"' not in HTML
    assert "els.primary.disabled = actionBusy || filtered" in HTML


def test_browser_ui_bundles_required_fonts():
    fonts = ROOT / "web" / "fonts"
    assert (fonts / "ibm-plex-sans-latin-400-normal.woff2").is_file()
    assert (fonts / "ibm-plex-sans-latin-500-normal.woff2").is_file()
    assert (fonts / "ibm-plex-mono-latin-400-normal.woff2").is_file()
    assert (fonts / "ibm-plex-mono-latin-500-normal.woff2").is_file()


def test_browser_ui_avoids_unsupported_delivery_claims():
    lowered = HTML.lower()
    assert "exactly once" not in lowered
    assert "exactly-once" not in lowered
    assert "100% reliable" not in lowered


def test_filter_proof_has_no_revision_age_or_byte_denominator_fallback():
    proof_start = HTML.index("const filterVerified")
    proof_end = HTML.index("const hasFilteredRevision", proof_start)
    proof = HTML[proof_start:proof_end]
    assert "filter_observation?.observed === true" in proof
    assert "revisionAge" not in proof
    assert "byte_reduction_denominator" not in proof


def test_browser_verifier_does_not_short_circuit_the_page_download():
    assert 'page="$(curl -fsS "http://127.0.0.1:${PORT}/")"' in DEMOCTL
    assert "grep -q 'Signal, not noise' <<<\"$page\"" in DEMOCTL
    assert 'curl -fsS "http://127.0.0.1:${PORT}/" | grep -q' not in DEMOCTL
