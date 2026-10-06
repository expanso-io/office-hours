#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PROJECT=expanso-demo-outage-buffer-replay; PORT=19480
docker_public() { mkdir -p .runtime/docker-config; chmod 700 .runtime .runtime/docker-config; printf '%s\n' '{"auths":{"ghcr.io":{"auth":""}},"credsStore":""}' > .runtime/docker-config/config.json; chmod 600 .runtime/docker-config/config.json; DOCKER_CONFIG="$ROOT/.runtime/docker-config" docker "$@"; }
compose() { docker compose --project-name "$PROJECT" --env-file .runtime/demo.env "$@"; }
wait_healthy() { for _ in $(seq 1 100); do curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null && return 0; sleep .25; done; compose logs >&2; return 1; }
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
    docker run --rm -v "$ROOT/pipelines/pipeline.runtime.yaml:/config.yaml:ro" ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999 lint /config.yaml
    expanso-cli job validate pipelines/pipeline.cloud.yaml --offline
    [[ "$(docker image inspect ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999 --format '{{.Architecture}}')" == "$(docker version --format '{{.Server.Arch}}')" ]]
    [[ "$(docker image inspect ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a --format '{{.Architecture}}')" == "$(docker version --format '{{.Server.Arch}}')" ]]
    mkdir -p .runtime; printf 'DEMO_MODE=local\nDEMO_VARIANT=baseline\n' > .runtime/demo.env; compose config -q; rm -rf .runtime ;;
  start)
    mode="${2:-local}"; [[ "$mode" =~ ^(local|cloud)$ ]] || { echo "mode must be local or cloud" >&2; exit 2; }
    [[ "$mode" != cloud ]] || ./scripts/cloudctl.sh preflight
    "$0" stop; mkdir -p .runtime; chmod 700 .runtime
    printf '%s\n' "$mode" > .runtime/mode; printf 'durable\n' > .runtime/variant; trap cleanup_failed_start ERR
    if [[ "$mode" == cloud ]]; then printf 'DEMO_MODE=cloud\nDEMO_VARIANT=durable\nPIPELINE_URL=http://host.docker.internal:19080/ingest\n' > .runtime/demo.env; compose up -d --build demo-api; ./scripts/cloudctl.sh start
    else printf 'DEMO_MODE=local\nDEMO_VARIANT=durable\n' > .runtime/demo.env; compose up -d --build; fi
    wait_healthy
    if [[ "$mode" == local ]]; then
      for _ in $(seq 1 40); do sent="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq -r .metrics.sent_total)"; [[ "$sent" -ge 3 ]] && break; sleep .25; done
      curl -fsS -X POST "http://127.0.0.1:$PORT/api/control/reset" >/dev/null
    fi
    trap - ERR
    echo "Outage-buffer-replay ready at http://127.0.0.1:$PORT" ;;
  status) test -f .runtime/demo.env; compose ps; curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq . ;;
  reset) curl -fsS -X POST "http://127.0.0.1:$PORT/api/reset" | jq . ;;
  test) "$0" validate ;;
  test-live)
    trap '"$0" stop >/dev/null 2>&1 || true' EXIT
    "$0" start local; sleep 6
    before="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot")"; before_ack="$(jq -r .metrics.acknowledged_total <<<"$before")"
    jq -e '.metrics.sent_total >= 25 and .metrics.queued_total == 0 and .metrics.duplicate_successful_deliveries == 0' <<<"$before" >/dev/null
    curl -fsS -X POST -H 'Content-Type: application/json' -d '{"online":false}' "http://127.0.0.1:$PORT/api/control/uplink" >/dev/null
    sleep 5; compose restart pipeline; sleep 2
    offline="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot")"
    jq -e --argjson before "$before_ack" '.destination_state == "offline-simulated" and .metrics.acknowledged_total == $before and .metrics.queued_total >= 20' <<<"$offline" >/dev/null
    curl -fsS -X POST -H 'Content-Type: application/json' -d '{"online":true}' "http://127.0.0.1:$PORT/api/control/uplink" >/dev/null
    for _ in $(seq 1 120); do snap="$(curl -fsS "http://127.0.0.1:$PORT/api/snapshot")"; jq -e '.metrics.queued_total == 0' <<<"$snap" >/dev/null && break; sleep .25; done
    jq -e '.metrics.sent_total == .metrics.acknowledged_total and .metrics.missing_accepted_sequences == 0 and .metrics.duplicate_successful_deliveries == 0' <<<"$snap" >/dev/null
    "$0" stop; ./scripts/teardown-audit.sh
    "$0" start local; sleep 2; curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq -e '.metrics.sent_total > 0' >/dev/null
    "$0" stop; ./scripts/teardown-audit.sh; trap - EXIT; echo "live durable outage/restart/replay proof passed" ;;
  verify-browser)
    page="$(curl -fsS "http://127.0.0.1:$PORT/")"
    grep -q 'network fails' <<<"$page"
    curl -fsS "http://127.0.0.1:$PORT/api/snapshot" | jq -e '.metrics.buffer_capacity > 0' >/dev/null
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
