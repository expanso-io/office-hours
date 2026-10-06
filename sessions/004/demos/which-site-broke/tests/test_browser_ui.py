from pathlib import Path


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "web" / "index.html").read_text()
DEMOCTL = (ROOT / "scripts" / "democtl.sh").read_text()


def test_browser_ui_preserves_cloud_deployment_boundary():
    assert "Which site broke?" in HTML
    assert "Copy pipeline step" in HTML
    assert "Pipeline step copied. Deploy it in Expanso Cloud." in HTML
    assert "Add source context" not in HTML
    assert "/api/actions/add-context" in HTML
    assert 'document.execCommand("copy")' in HTML
    assert "LOCAL REHEARSAL" in HTML


def test_browser_ui_labels_simulation_and_the_pre_snapshot_truth_boundary():
    assert "SIMULATED SOURCE" in HTML
    assert "CONTROL: EXPANSO CLOUD · runtime proof pending." in HTML
    assert "AWAITING SNAPSHOT" in HTML
    assert (
        'els["receiver-node"].classList.toggle("active", Boolean(acknowledgement?.event_id))'
        in HTML
    )


def test_browser_ui_contains_exact_enrichment_fields():
    assert (
        'root.source_context.node_id = env("DEMO_NODE_ID").or(metadata("node_label_node_id")).or(metadata("node_id"))'
        in HTML
    )
    assert (
        'root.source_context.site_id = env("DEMO_SITE_ID").or(metadata("node_label_site_id"))'
        in HTML
    )
    assert (
        'root.source_context.asset_id = env("DEMO_ASSET_ID").or(metadata("node_label_asset_id"))'
        in HTML
    )
    assert 'root.source_context.pipeline_version = "lineage-v2"' in HTML


def test_browser_ui_uses_only_receiver_context_for_visible_attribution():
    assert "SOURCE UNKNOWN" in HTML
    assert "SENSOR_TIMEOUT" in HTML
    assert "sourceContext(data)" in HTML
    assert "visibleAsset(context)" in HTML
    assert "source_context.asset_id" in HTML
    assert "edge-07" not in HTML


def test_browser_ui_distinguishes_anonymous_source_slots():
    assert 'node.asset_id || node.label?.replace("Source ", "SRC ") || "source"' in HTML
    assert 'assetId.replace("turbine-", "TURB ")' in HTML
    assert "receiver-observed SENSOR_TIMEOUT; runtime still" in HTML


def test_cloud_unknown_health_is_unverified_instead_of_zero():
    health_start = HTML.index("const fleetHealthLabel")
    health_end = HTML.index("function displayPayload", health_start)
    health = HTML[health_start:health_end]
    assert "isMeasuredCount(metrics.sites_online)" in health
    assert "control.nodes_running" in health
    assert "`UNVERIFIED / ${Number(expected)}`" in health
    assert "metrics.sites_online || control.nodes_running || 0" not in HTML


def test_measured_local_zero_and_ten_are_preserved_as_real_counts():
    assert 'value !== null && value !== undefined && value !== ""' in HTML
    assert "Number.isFinite(Number(value))" in HTML
    assert "`${Number(online)} / ${Number(expected)}`" in HTML
    assert 'els["nodes-online"].textContent = fleetHealthLabel(data)' in HTML


def test_browser_ui_uses_the_pinned_acknowledgement_for_the_pinned_fault():
    assert "data.evidence?.first_enriched_acknowledgement" in HTML
    assert "data.evidence?.baseline_acknowledgement" in HTML


def test_browser_ui_preserves_an_explicit_fleet_selection_after_attribution():
    assert "if (faultAsset && !selectedAsset)" in HTML
    assert "if (faultAsset && selectedAsset !== faultAsset)" not in HTML


def test_browser_ui_has_atomic_snapshot_and_url_selection():
    assert "/api/snapshot" in HTML
    assert 'new EventSource("/api/events")' in HTML
    assert 'addEventListener("snapshot"' in HTML
    assert "next.snapshot_seq <= lastSnapshotSeq" in HTML
    assert 'url.searchParams.set("node", assetId)' in HTML
    assert "history.replaceState" in HTML


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


def test_browser_verifier_does_not_short_circuit_the_page_download():
    assert 'page="$(curl -fsS "http://127.0.0.1:$PORT/")"' in DEMOCTL
    assert "grep -q 'Which site broke' <<<\"$page\"" in DEMOCTL
    assert 'curl -fsS "http://127.0.0.1:$PORT/" | grep -q' not in DEMOCTL
