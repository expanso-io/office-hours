#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="expanso-demo-signal-not-noise"
PORT=19440
LABEL="signal-not-noise"

docker_public() {
  mkdir -p .runtime/docker-config
  chmod 700 .runtime .runtime/docker-config
  printf '%s\n' '{"auths":{"ghcr.io":{"auth":""}},"credsStore":""}' > .runtime/docker-config/config.json
  chmod 600 .runtime/docker-config/config.json
  DOCKER_CONFIG="$ROOT/.runtime/docker-config" docker "$@"
}

compose() {
  docker compose --project-name "$PROJECT" --env-file .runtime/demo.env "$@"
}

wait_healthy() {
  for _ in $(seq 1 80); do
    if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null; then return 0; fi
    sleep 0.25
  done
  compose logs >&2
  echo "demo API did not become healthy" >&2
  return 1
}

cleanup_failed_start() {
  start_rc=$?
  trap - ERR
  set +e
  "$0" stop
  cleanup_rc=$?
  set -e
  if (( cleanup_rc != 0 )); then
    echo "start failed and Cloud cleanup could not be verified" >&2
    exit "$cleanup_rc"
  fi
  exit "$start_rc"
}

case "${1:-}" in
  warm)
    command -v uv >/dev/null; command -v docker >/dev/null; command -v expanso-cli >/dev/null
    mkdir -p .runtime
    docker_public pull ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999
    docker_public pull ghcr.io/astral-sh/uv@sha256:020e9eefae64e99ea2da39bcd1af1294be0a0b01e98ebad4dbedfd8b729500f7
    docker_public pull ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a
    uv sync --frozen
    ;;
  validate)
    bash -n scripts/*.sh
    uv sync --frozen
    uv run ruff check server tests
    uv run ruff format --check server tests
    uv run pytest -q
    for file in pipelines/*.runtime.yaml; do
      docker run --rm -v "$ROOT/$file:/config.yaml:ro" ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999 lint /config.yaml
    done
    for file in pipelines/*.cloud.yaml; do expanso-cli job validate "$file" --offline; done
    [[ "$(docker image inspect ghcr.io/warpstreamlabs/bento@sha256:f9c60f8890f5c9e770a79497cc3fb44346bbc25ca8949a5a87bf000b14df4999 --format '{{.Architecture}}')" == "$(docker version --format '{{.Server.Arch}}')" ]]
    [[ "$(docker image inspect ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a --format '{{.Architecture}}')" == "$(docker version --format '{{.Server.Arch}}')" ]]
    mkdir -p .runtime
    printf 'DEMO_MODE=local\nDEMO_VARIANT=baseline\n' > .runtime/demo.env
    docker compose --project-name "$PROJECT" --env-file .runtime/demo.env config -q
    rm -rf .runtime
    ;;
  start)
    mode="${2:-local}"; variant="${3:-baseline}"
    [[ "$mode" == "local" || "$mode" == "cloud" ]] || { echo "mode must be local or cloud" >&2; exit 2; }
    [[ "$variant" == "baseline" || "$variant" == "filtered" ]] || { echo "variant must be baseline or filtered" >&2; exit 2; }
    if [[ "$mode" == "cloud" ]]; then ./scripts/cloudctl.sh bootstrap; fi
    "$0" stop
    mkdir -p .runtime
    chmod 700 .runtime
    printf '%s\n' "$mode" > .runtime/mode
    printf '%s\n' "$variant" > .runtime/variant
    trap cleanup_failed_start ERR
    if [[ "$mode" == "cloud" ]]; then
      printf 'DEMO_MODE=cloud\nDEMO_VARIANT=%s\nPIPELINE_URL=http://host.docker.internal:19040/ingest\n' "$variant" > .runtime/demo.env
      compose up -d --build demo-api
      ./scripts/cloudctl.sh start "$variant"
      ./scripts/cloudctl.sh await-scheduled "$variant"
    else
      printf 'DEMO_MODE=local\nDEMO_VARIANT=%s\n' "$variant" > .runtime/demo.env
      compose up -d --build
    fi
    wait_healthy
    if [[ "$mode" == "local" ]]; then
      for _ in $(seq 1 40); do
        accepted="$(curl -fsS "http://127.0.0.1:${PORT}/api/snapshot" | jq -r .metrics.pipeline_http_accepted)"
        [[ "$accepted" -ge 3 ]] && break
        sleep 0.25
      done
      curl -fsS -X POST "http://127.0.0.1:${PORT}/api/control/reset-counters" >/dev/null
    fi
    trap - ERR
    echo "Signal-not-noise ready at http://127.0.0.1:${PORT}"
    ;;
  status)
    test -f .runtime/demo.env
    compose ps
    curl -fsS "http://127.0.0.1:${PORT}/api/snapshot" | jq .
    ;;
  reset)
    curl -fsS -X POST "http://127.0.0.1:${PORT}/api/reset" | jq .
    ;;
  test)
    "$0" validate
    ;;
  test-live)
    trap '"$0" stop >/dev/null 2>&1 || true' EXIT
    "$0" start local baseline
    sleep 6
    baseline="$(curl -fsS "http://127.0.0.1:${PORT}/api/snapshot")"
    jq -e '.metrics.generated > 150 and .metrics.delivered_ratio > 0.90' <<<"$baseline" >/dev/null
    curl -fsS -X POST -H 'Idempotency-Key: lifecycle-filter-rollout' "http://127.0.0.1:${PORT}/api/actions/apply-filter" | jq -e '.accepted == true' >/dev/null
    for _ in $(seq 1 80); do
      rollout="$(curl -fsS "http://127.0.0.1:${PORT}/api/snapshot")"
      if jq -e '.pipeline.variant == "filtered" and .action.phase == "measuring"' <<<"$rollout" >/dev/null; then break; fi
      sleep 0.25
    done
    jq -e '.pipeline.variant == "filtered" and .action.phase == "measuring"' <<<"$rollout" >/dev/null
    # The proof window starts after the hot reload; baseline receiver bytes must age out.
    sleep 6
    incident="$(curl -fsS -X POST "http://127.0.0.1:${PORT}/api/control/incident" | jq -r .event_id)"
    for _ in $(seq 1 20); do
      snap="$(curl -fsS "http://127.0.0.1:${PORT}/api/snapshot")"
      if jq -e --arg id "$incident" '.incidents[$id].delivered == true' <<<"$snap" >/dev/null; then break; fi
      sleep 0.25
    done
    jq -e --arg id "$incident" '
      .pipeline.variant == "filtered" and
      .filter_observation.observed == true and
      .filter_observation.delivered_to_accepted_byte_ratio <= .filter_observation.threshold_ratio and
      .metrics.generated > 200 and .metrics.records_filtered_total > 0 and
      .incidents[$id].accepted == true and .incidents[$id].delivered == true and
      .incidents[$id].accepted_code == "COMPRESSOR_OVERHEAT" and
      .incidents[$id].delivered_code == "COMPRESSOR_OVERHEAT" and
      .evidence.verification_event.event_id == $id and
      .evidence.verification_acknowledgement.event_id == $id
    ' <<<"$snap" >/dev/null
    "$0" stop
    ./scripts/teardown-audit.sh
    trap - EXIT
    echo "live baseline/filter/incident proof passed"
    ;;
  verify-browser)
    page="$(curl -fsS "http://127.0.0.1:${PORT}/")"
    grep -q 'Signal, not noise' <<<"$page"
    curl -fsS "http://127.0.0.1:${PORT}/api/snapshot" | jq -e '.snapshot_seq > 0 and .metrics.records_generated_total >= 0' >/dev/null
    echo "browser contract passed"
    ;;
  stop)
    mode=local; [[ ! -f .runtime/mode ]] || mode="$(cat .runtime/mode)"
    cloud_rc=0; local_rc=0
    if [[ "$mode" == cloud ]]; then ./scripts/cloudctl.sh stop || cloud_rc=$?; else ./scripts/cloudctl.sh stop-local || cloud_rc=$?; fi
    if compose_output="$(docker compose --project-name "$PROJECT" down --volumes --remove-orphans --timeout 20 2>&1)"; then :; else local_rc=$?; printf '%s\n' "$compose_output" >&2; fi
    if (( local_rc == 0 && cloud_rc == 0 )); then rm -rf .runtime; fi
    (( local_rc == 0 )) || exit "$local_rc"
    (( cloud_rc == 0 )) || exit "$cloud_rc"
    ;;
  logs)
    compose logs -f
    ;;
  *) echo "usage: $0 {warm|validate|start|status|reset|test|test-live|verify-browser|stop|logs}" >&2; exit 2 ;;
esac
