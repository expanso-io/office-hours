#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
CLOUD_HOME="$ROOT/.cloud-state/cli-home"; PROFILE=outage-buffer-replay-demo; ENV_FILE="$ROOT/.env"; PROFILE_PATH="$CLOUD_HOME/.expanso/cli-client/profiles/$PROFILE.yaml"; EDGE_DIR="$ROOT/.cloud-state/node-01"; EDGE_NAME=expanso-cloud-outage-buffer-replay-edge
EDGE_IMAGE=ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a
# JSON listings print "No ... found" or a "Showing ..." footer instead of
# clean JSON; normalize so jq always gets an array.
cloud_cli() {
  local output
  if ! output="$(HOME="$CLOUD_HOME" expanso-cli --profile "$PROFILE" "$@")"; then
    printf '%s\n' "$output" >&2
    return 1
  fi
  if [[ " $* " == *" --format json "* ]]; then
    output="${output%%$'\n\nShowing '*}"
    output="${output%%$'\nShowing '*}"
    [[ "$output" =~ ^No[[:space:]].*[[:space:]]found$ ]] && output='[]'
  fi
  printf '%s\n' "$output"
}
profile_file() { [[ -f "$PROFILE_PATH" ]] && printf '%s\n' "$PROFILE_PATH"; }
# GNU stat (Linux, WSL) takes -c; BSD stat (macOS) takes -f.
file_mode() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }
require_mode() { [[ "$(file_mode "$1")" == "$2" ]] || { echo "$1 must have mode $2" >&2; exit 1; }; }
dotenv_value() {
  awk -v target="$1" '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    { equal = index($0, "="); if (!equal) next; key = substr($0, 1, equal - 1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", key); if (key != target) next; value = substr($0, equal + 1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", value); if ((value ~ /^".*"$/) || (value ~ /^\047.*\047$/)) value = substr(value, 2, length(value) - 2); print value; exit }
  ' "$ENV_FILE"
}
bootstrap_profile_from_env() {
  [[ -f "$PROFILE_PATH" ]] && return; [[ -f "$ENV_FILE" ]] || return 0; require_mode "$ENV_FILE" 600
  endpoint="$(dotenv_value EXPANSO_CLOUD_ENDPOINT)"; api_key="$(dotenv_value EXPANSO_CLOUD_API_KEY)"
  [[ -n "$endpoint" && "$api_key" =~ ^exp_ak_[A-Za-z0-9._-]+$ ]] || { echo ".env must set EXPANSO_CLOUD_ENDPOINT and EXPANSO_CLOUD_API_KEY" >&2; return 1; }
  mkdir -p "$(dirname "$PROFILE_PATH")"; chmod 700 "$CLOUD_HOME" "$CLOUD_HOME/.expanso" "$CLOUD_HOME/.expanso/cli-client" "$(dirname "$PROFILE_PATH")"
  (umask 077; printf 'endpoint: %s\ntimeout: 30s\nauth:\n    api_key: %s\nadmin_auth: {}\ntls: {}\n' "$endpoint" "$api_key" > "$PROFILE_PATH"); chmod 600 "$PROFILE_PATH"
}
require_cloud_profile() {
  bootstrap_profile_from_env
  profile="$(profile_file || true)"; [[ -n "$profile" ]] || { echo "SKIP: no project-local Cloud profile"; return 2; }; require_mode "$profile" 600
  cloud_cli status >/dev/null
}
node_identity_present() { [[ -d "$1" ]] && find "$1" -type f -print -quit | grep -q .; }
# Enroll this demo's edge identity from EXPANSO_EDGE_BOOTSTRAP_TOKEN, as the sibling demos do,
# so a fresh machine does not need an identity copied in from elsewhere.
bootstrap_edge() {
  [[ -f "$ENV_FILE" ]] || { echo ".env must set EXPANSO_EDGE_BOOTSTRAP_TOKEN to create the project-local edge identity" >&2; return 1; }
  require_mode "$ENV_FILE" 600
  token="$(dotenv_value EXPANSO_EDGE_BOOTSTRAP_TOKEN)"
  [[ "$token" =~ ^exp_bk_[A-Za-z0-9._-]+$ ]] || { echo ".env must set a valid EXPANSO_EDGE_BOOTSTRAP_TOKEN" >&2; return 1; }
  mkdir -p "$EDGE_DIR"; chmod 700 "$EDGE_DIR"
  docker run --rm --user "$(id -u):$(id -g)" -v "$EDGE_DIR:/data" -v "$ROOT/cloud/node.yaml:/etc/expanso-edge.yaml:ro" "$EDGE_IMAGE" bootstrap --data-dir /data --config /etc/expanso-edge.yaml --token "$token" >/dev/null
  node_identity_present "$EDGE_DIR" || { echo "edge bootstrap completed without project-local identity material" >&2; return 1; }
}
preflight() {
  require_cloud_profile || return $?
  [[ -d "$EDGE_DIR" ]] || { echo "missing pre-enrolled identity" >&2; return 1; }; require_mode "$EDGE_DIR" 700
  unscoped="$(cloud_cli job list --format json | jq -r '.[] | select((.spec.selector // {}) == {}) | select((.status.state.state_type // "") != "stopped") | .spec.name')"; [[ -z "$unscoped" ]] || { echo "active jobs with empty selectors: $unscoped" >&2; return 1; }
}
matching_jobs() { cloud_cli job list --label demo=outage-buffer-replay --format json | jq -c '[.[] | select(.spec.name == "demo-outage-buffer-replay" and .spec.labels.demo == "outage-buffer-replay")]'; }
resolve_job_record() { matching_jobs | jq -c 'if length == 1 then .[0] else empty end'; }
resolve_job() { resolve_job_record | jq -r '.id // empty'; }
verify_stopped() {
  jobs="$(matching_jobs)"
  active_jobs="$(jq '[.[] | select((.status.state.state_type // .status.state_type // "") != "stopped")] | length' <<<"$jobs")"
  active_executions=0
  while read -r id; do
    [[ -z "$id" ]] && continue
    count="$(cloud_cli execution list --job-id "$id" --format json | jq '[.[] | select(((.status.observed_state.state_type // .status.state.state_type // "") as $state | ["completed", "failed", "lost", "stopped"] | index($state)) == null)] | length')"
    active_executions=$((active_executions + count))
  done < <(jq -r '.[].id' <<<"$jobs")
  [[ "$active_jobs" == 0 && "$active_executions" == 0 ]]
}
case "${1:-}" in
  preflight) preflight ;;
  bootstrap) require_cloud_profile || exit $?; node_identity_present "$EDGE_DIR" || bootstrap_edge; preflight ;;
  start) require_cloud_profile || exit $?; node_identity_present "$EDGE_DIR" || bootstrap_edge; preflight || exit $?; cloud_cli job validate pipelines/pipeline.cloud.yaml; cloud_cli job deploy pipelines/pipeline.cloud.yaml; docker rm -f "$EDGE_NAME" >/dev/null 2>&1 || true; docker run -d --user "$(id -u):$(id -g)" --name "$EDGE_NAME" --label io.expanso.demo=outage-buffer-replay -p 127.0.0.1:19080:8080 -v "$EDGE_DIR:/data" -v "$ROOT/cloud/node.yaml:/etc/expanso-edge.yaml:ro" -e DEMO_SINK_URL=http://host.docker.internal:19480/api/sink/events "$EDGE_IMAGE" run --config /etc/expanso-edge.yaml --data-dir /data --no-watch >/dev/null ;;
  verify)
    if preflight; then :; else rc=$?; exit "$rc"; fi
    job="$(resolve_job_record)"; [[ -n "$job" ]] || { echo "exact labeled job not found" >&2; exit 1; }
    id="$(jq -r .id <<<"$job")"; job_version="$(jq -r '.version // .job_version // .jobVersion // .status.version // .status.job_version // .status.jobVersion // empty' <<<"$job")"
    [[ "$job_version" =~ ^[0-9]+$ ]] || { echo "job version missing" >&2; exit 1; }
    cloud_cli node list --label demo=outage-buffer-replay --label role=remote-site --format json | jq -e 'length == 1' >/dev/null
    cloud_cli execution list --job-id "$id" --job-version "$job_version" --format json | jq -e 'any(.[]; (.status.observed_state.state_type // .status.state.state_type // "") == "running")' >/dev/null
    curl -fsS http://127.0.0.1:19480/api/snapshot | jq -e '.pipeline.receiver_fresh == true' >/dev/null
    echo "Cloud verified: exact durable job version, one selected node, running execution, fresh receiver data" ;;
  stop-local) docker rm -f "$EDGE_NAME" >/dev/null 2>&1 || true ;;
  stop)
    docker rm -f "$EDGE_NAME" >/dev/null 2>&1 || true; require_cloud_profile; jobs="$(matching_jobs)"
    while read -r id; do [[ -z "$id" ]] || cloud_cli job stop "$id" --force; done < <(jq -r '.[].id' <<<"$jobs")
    for _ in $(seq 1 40); do if verify_stopped; then echo "Cloud stopped: zero matching active jobs or executions"; exit 0; fi; sleep 0.5; done
    echo "Cloud stop incomplete: matching active job or execution remains" >&2; exit 1 ;;
  verify-stopped)
    require_cloud_profile; verify_stopped || { echo "matching active job or execution remains" >&2; exit 1; }
    echo "Cloud clean: zero matching active jobs or executions" ;;
  purge)
    if preflight; then :; else rc=$?; [[ $rc == 2 ]] && { rm -rf "$ROOT/.cloud-state"; echo "no Cloud profile; local identities purged"; exit 0; }; exit "$rc"; fi
    "$0" stop; id="$(resolve_job)"; [[ -z "$id" ]] || cloud_cli job delete "$id" --yes --reason "demo teardown"; nodes="$(cloud_cli node list --label demo=outage-buffer-replay --label role=remote-site --format json)"; jq -e 'all(.[]; .spec.labels.demo == "outage-buffer-replay" and .spec.labels.role == "remote-site")' <<<"$nodes" >/dev/null; jq -r '.[].id' <<<"$nodes" | while read -r node; do [[ -z "$node" ]] || cloud_cli node delete "$node" --yes --reason "demo teardown"; done; rm -rf "$ROOT/.cloud-state"; echo "exact Cloud targets and local identities purged" ;;
  *) echo "usage: $0 {preflight|start|verify|stop-local|stop|verify-stopped|purge}" >&2; exit 2 ;;
esac
