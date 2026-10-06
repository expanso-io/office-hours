#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PROJECT=expanso-demo-which-site-broke; PORT=19450
docker_public() { mkdir -p .runtime/docker-config; chmod 700 .runtime .runtime/docker-config; printf '%s\n' '{"auths":{"ghcr.io":{"auth":""}},"credsStore":""}' > .runtime/docker-config/config.json; chmod 600 .runtime/docker-config/config.json; DOCKER_CONFIG="$ROOT/.runtime/docker-config" docker "$@"; }
compose() { docker compose --project-name "$PROJECT" --env-file .runtime/demo.env "$@"; }
wait_healthy() { for _ in $(seq 1 120); do curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null && return 0; sleep .25; done; compose logs >&2; return 1; }
cleanup_failed_start() {
  start_rc=$?; trap - ERR; set +e; "$0" stop; cleanup_rc=$?; set -e
  if (( cleanup_rc != 0 )); then echo "start failed and Cloud cleanup could not be verified" >&2; exit "$cleanup_rc"; fi
  exit "$start_rc"
}
case "${1:-}" in
  warm)
    command -v uv >/dev/null; command -v docker >/dev/null; command -v expanso-cli >/dev/null
    mkdir -p .runtime
    docker_public pull ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999
    docker_public pull ghcr.io/astral-sh/uv@sha256:020e9eefae64e99ea2da39bcd1af1294be0a0b01e98ebad4dbedfd8b729500f7
    docker_public pull ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a
    uv sync --frozen ;;
  validate)
    bash -n scripts/*.sh; uv sync --frozen; uv run ruff check server tests; uv run ruff format --check server tests; uv run pytest -q
    for f in pipelines/*.runtime.yaml; do docker run --rm -v "$ROOT/$f:/config.yaml:ro" ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999 lint /config.yaml; done
    for f in pipelines/*.cloud.yaml; do expanso-cli job validate "$f" --offline; done
    [[ "$(docker image inspect ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999 --format '{{.Architecture}}')" == "$(docker version --format '{{.Server.Arch}}')" ]]
    [[ "$(docker image inspect ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a --format '{{.Architecture}}')" == "$(docker version --format '{{.Server.Arch}}')" ]]
    mkdir -p .runtime; printf 'DEMO_MODE=local\nDEMO_VARIANT=baseline\n' > .runtime/demo.env; compose config -q; rm -rf .runtime ;;
  start)
    mode="${2:-local}"; variant="${3:-baseline}"
    [[ "$mode" =~ ^(local|cloud)$ ]] && [[ "$variant" =~ ^(baseline|enriched)$ ]] || { echo "invalid mode/variant" >&2; exit 2; }
    [[ "$mode" != cloud ]] || ./scripts/cloudctl.sh bootstrap
    "$0" stop; mkdir -p .runtime; chmod 700 .runtime
    printf '%s\n' "$mode" > .runtime/mode; printf '%s\n' "$variant" > .runtime/variant; trap cleanup_failed_start ERR
    if [[ "$mode" == cloud ]]; then
      urls=""; for i in $(seq -w 1 10); do urls+="${urls:+,}http://host.docker.internal:190${i}/ingest"; done
      printf 'DEMO_MODE=cloud\nDEMO_VARIANT=%s\nPIPELINE_URLS=%s\n' "$variant" "$urls" > .runtime/demo.env
      compose up -d --build demo-api
      ./scripts/cloudctl.sh start "$variant"
      ./scripts/cloudctl.sh await-scheduled "$variant"
    else printf 'DEMO_MODE=local\nDEMO_VARIANT=%s\n' "$variant" > .runtime/demo.env; compose up -d --build; fi
    wait_healthy
    if [[ "$mode" == local ]]; then
      for _ in $(seq 1 60); do accepted="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq -r .metrics.pipeline_http_accepted)"; [[ "$accepted" -ge 10 ]] && break; sleep .25; done
      curl -fsS -X POST "http://127.0.0.1:$PORT/api/control/reset-counters" >/dev/null
    fi
    trap - ERR
    echo "Which-site-broke ready at http://127.0.0.1:$PORT" ;;
  status) test -f .runtime/demo.env; compose ps; curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq . ;;
  reset) curl -fsS -X POST "http://127.0.0.1:$PORT/api/reset" | jq . ;;
  test) "$0" validate ;;
  test-live)
    trap '"$0" stop >/dev/null 2>&1 || true' EXIT
    "$0" start local baseline; sleep 11
    snap="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot")"
    jq -e '.metrics.records_received_total >= 90 and .metrics.faults_received_total >= 2 and .metrics.faults_attributable_total == 0 and .evidence.baseline_fault.source_context == null and .evidence.baseline_acknowledgement.event_id == .evidence.baseline_fault.event_id' <<<"$snap" >/dev/null
    curl -fsS -X POST -H 'Idempotency-Key: lifecycle-lineage-rollout' "http://127.0.0.1:$PORT/api/actions/add-context" | jq -e '.accepted == true' >/dev/null
    for _ in $(seq 1 80); do
      snap="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot")"
      if jq -e '.pipeline.variant == "enriched" and .verification.state == "verified" and (.evidence.context_by_node | length) == 10' <<<"$snap" >/dev/null; then break; fi
      sleep 0.25
    done
    jq -e '
      .pipeline.variant == "enriched" and
      .verification.state == "verified" and
      .metrics.records_received_total >= 120 and .metrics.faults_attributable_total >= 1 and
      (.evidence.context_by_node | length) == 10 and
      .evidence.context_by_node["edge-01"].asset_id == "turbine-01" and
      .evidence.context_by_node["edge-10"].asset_id == "turbine-10" and
      .evidence.first_enriched_fault.source_context.node_id == "edge-07" and
      .evidence.first_enriched_fault.source_context.site_id == "wind-west" and
      .evidence.first_enriched_fault.source_context.asset_id == "turbine-07" and
      .evidence.first_enriched_fault.source_context.app_version == "1.8.3" and
      .evidence.first_enriched_fault.source_context.pipeline_version == "lineage-v2" and
      .evidence.first_enriched_acknowledgement.event_id == .evidence.first_enriched_fault.event_id
    ' <<<"$snap" >/dev/null
    "$0" stop; ./scripts/teardown-audit.sh; trap - EXIT; echo "live unknown/enriched attribution proof passed" ;;
  verify-browser)
    page="$(curl -fsS "http://127.0.0.1:$PORT/")"
    grep -q 'Which site broke' <<<"$page"
    curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq -e '.nodes | length == 10' >/dev/null
    echo "browser contract passed" ;;
  stop)
    mode=local; [[ ! -f .runtime/mode ]] || mode="$(cat .runtime/mode)"; cloud_rc=0; local_rc=0
    if [[ "$mode" == cloud ]]; then ./scripts/cloudctl.sh stop || cloud_rc=$?; else ./scripts/cloudctl.sh stop-local || cloud_rc=$?; fi
    if compose_output="$(docker compose --project-name "$PROJECT" down --volumes --remove-orphans --timeout 20 2>&1)"; then :; else local_rc=$?; printf '%s\n' "$compose_output" >&2; fi
    if (( local_rc == 0 && cloud_rc == 0 )); then rm -rf .runtime; fi
    (( local_rc == 0 )) || exit "$local_rc"; (( cloud_rc == 0 )) || exit "$cloud_rc" ;;
  logs) compose logs -f ;;
  *) echo "usage: $0 {warm|validate|start|status|reset|test|test-live|verify-browser|stop|logs}" >&2; exit 2 ;;
esac
