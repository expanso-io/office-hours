#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
CLOUD_HOME="$ROOT/.cloud-state/cli-home"; PROFILE=which-site-broke-demo; ENV_FILE="$ROOT/.env"; PROFILE_PATH="$CLOUD_HOME/.expanso/cli-client/profiles/$PROFILE.yaml"
EDGE_IMAGE=ghcr.io/expanso-io/expanso-edge@sha256:105e9e0a90624bbbe39429c931b7eb3434f38a0a6ea5a87289479e3ed686cc1a
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
deploy_job() {
  local output
  if output="$(cloud_cli job deploy "$1" 2>&1)"; then
    printf '%s\n' "$output"
  elif [[ "$output" == *"job_unchanged"* ]]; then
    echo "Cloud job is already the requested revision"
  else
    printf '%s\n' "$output" >&2
    return 1
  fi
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
node_identity_present() {
  [[ -d "$1" ]] && find "$1" -type f -print -quit | grep -q .
}
bootstrap_edge() {
local directory="$1" config="$2"
[[ -f "$ENV_FILE" ]] || { echo ".env must set EXPANSO_EDGE_BOOTSTRAP_TOKEN to create project-local edge identities" >&2; return 1; }
require_mode "$ENV_FILE" 600
token="$(dotenv_value EXPANSO_EDGE_BOOTSTRAP_TOKEN)"
[[ "$token" =~ ^exp_bk_[A-Za-z0-9._-]+$ ]] || { echo ".env must set a valid EXPANSO_EDGE_BOOTSTRAP_TOKEN" >&2; return 1; }
mkdir -p "$directory"
chmod 700 "$directory"
force=()
if node_identity_present "$directory" && ! grep -q '^    credentials_path: /data/' "$directory/config.d/50-connection.yaml"; then force=(--force); fi
docker run --rm --user "$(id -u):$(id -g)" -v "$directory:/data" -v "$config:/etc/expanso-edge.yaml:ro" "$EDGE_IMAGE" bootstrap --data-dir /data --config /etc/expanso-edge.yaml --token "$token" "${force[@]}" >/dev/null
node_identity_present "$directory" || { echo "edge bootstrap completed without project-local identity material" >&2; return 1; }
}
bootstrap_edges() {
  for i in $(seq -w 1 10); do
    bootstrap_edge "$ROOT/.cloud-state/node-$i" "$ROOT/cloud/nodes/node-$i.yaml"
  done
}
preflight() {
  require_cloud_profile || return $?
  for i in $(seq -w 1 10); do [[ -d "$ROOT/.cloud-state/node-$i" ]] || { echo "missing pre-enrolled identity node-$i" >&2; return 1; }; require_mode "$ROOT/.cloud-state/node-$i" 700; done
  unscoped="$(cloud_cli job list --format json | jq -r '.[] | select((.spec.selector // {}) == {}) | select((.status.state.state_type // "") != "stopped") | .spec.name')"; [[ -z "$unscoped" ]] || { echo "active jobs with empty selectors: $unscoped" >&2; return 1; }
}
matching_jobs() { cloud_cli job list --label demo=which-site-broke --format json | jq -c '[.[] | select(.spec.name == "demo-which-site-broke" and .spec.labels.demo == "which-site-broke")]'; }
resolve_job_record() {
  variant="${1:-}"
  matching_jobs | jq -c --arg variant "$variant" '[.[] | select($variant == "" or .spec.labels.variant == $variant)] | if length == 1 then .[0] else empty end'
}
resolve_job() { resolve_job_record "${1:-}" | jq -r '.id // empty'; }
scheduled() {
  variant="$1"
  job="$(resolve_job_record "$variant")"
  [[ -n "$job" ]] || return 1
  id="$(jq -r .id <<<"$job")"
  job_version="$(jq -r '.version // .job_version // .jobVersion // .status.version // .status.job_version // .status.jobVersion // empty' <<<"$job")"
  [[ "$job_version" =~ ^[0-9]+$ ]] || return 1
  cloud_cli node list --label demo=which-site-broke --label role=turbine --format json | jq -e 'length == 10' >/dev/null || return 1
  cloud_cli execution list --job-id "$id" --job-version "$job_version" --format json | jq -e '[.[] | select((.status.observed_state.state_type // .status.state.state_type // "") == "running")] | length == 10' >/dev/null
}
await_scheduled() {
  variant="$1"
  for _ in $(seq 1 100); do
    if scheduled "$variant"; then
      echo "Cloud scheduled: exact $variant job, ten selected nodes, ten running executions"
      return 0
    fi
    sleep 0.5
  done
  echo "Cloud scheduling timed out: exact $variant job did not reach ten running executions" >&2
  return 1
}
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
start_edges() {
  for number in $(seq 1 10); do
    i="$(printf '%02d' "$number")"; name="expanso-cloud-which-site-broke-$i"; edge_dir="$ROOT/.cloud-state/node-$i"; docker rm -f "$name" >/dev/null 2>&1 || true
    rm -rf "$edge_dir/state" "$edge_dir/executions" "$edge_dir/metrics" "$edge_dir/temp"
    version=2.4.1; [[ "$number" == 7 ]] && version=1.8.3
    docker run -d --user "$(id -u):$(id -g)" --name "$name" --label io.expanso.demo=which-site-broke -p "127.0.0.1:190${i}:8080" -v "$edge_dir:/data" -v "$ROOT/cloud/nodes/node-$i.yaml:/etc/expanso-edge.yaml:ro" -e DEMO_SINK_URL=http://host.docker.internal:19450/api/sink/events -e DEMO_NODE_ID="edge-$i" -e DEMO_SITE_ID=wind-west -e DEMO_ASSET_ID="turbine-$i" -e DEMO_REGION=us-west -e DEMO_APP_VERSION="$version" "$EDGE_IMAGE" run --config /etc/expanso-edge.yaml --data-dir /data --no-watch >/dev/null
  done
}
stop_edges() { for i in $(seq -w 1 10); do docker rm -f "expanso-cloud-which-site-broke-$i" >/dev/null 2>&1 || true; done; }
case "${1:-}" in
  preflight) preflight ;;
  bootstrap)
    require_cloud_profile
    bootstrap_edges
    preflight
    ;;
  start)
    require_cloud_profile
    bootstrap_edges
    preflight
    variant="${2:-enriched}"
    [[ "$variant" =~ ^(baseline|enriched)$ ]] || { echo "invalid variant: $variant" >&2; exit 2; }
    start_edges
    cloud_cli job validate "pipelines/$variant.cloud.yaml"
    deploy_job "pipelines/$variant.cloud.yaml"
    ;;
  await-scheduled)
    preflight
    variant="${2:-enriched}"
    [[ "$variant" =~ ^(baseline|enriched)$ ]] || { echo "invalid variant: $variant" >&2; exit 2; }
    await_scheduled "$variant"
    ;;
  verify)
    if preflight; then :; else rc=$?; exit "$rc"; fi
    variant="${2:-enriched}"; [[ "$variant" =~ ^(baseline|enriched)$ ]] || { echo "invalid variant: $variant" >&2; exit 2; }
    job="$(resolve_job_record "$variant")"; [[ -n "$job" ]] || { echo "exact labeled $variant job not found" >&2; exit 1; }
    id="$(jq -r .id <<<"$job")"; job_version="$(jq -r '.version // .job_version // .jobVersion // .status.version // .status.job_version // .status.jobVersion // empty' <<<"$job")"
    [[ "$job_version" =~ ^[0-9]+$ ]] || { echo "job version missing for $variant" >&2; exit 1; }
    cloud_cli node list --label demo=which-site-broke --label role=turbine --format json | jq -e 'length == 10' >/dev/null
    cloud_cli execution list --job-id "$id" --job-version "$job_version" --format json | jq -e '[.[] | select((.status.observed_state.state_type // .status.state.state_type // "") == "running")] | length == 10' >/dev/null
    curl -fsS http://127.0.0.1:19450/api/snapshot | jq -e '.pipeline.receiver_fresh_nodes == 10' >/dev/null
    echo "Cloud verified: exact $variant job version, ten selected nodes/executions, fresh receiver data" ;;
  stop-local) stop_edges ;;
  stop)
    stop_edges; require_cloud_profile; jobs="$(matching_jobs)"
    while read -r id; do [[ -z "$id" ]] || cloud_cli job stop "$id" --force; done < <(jq -r '.[].id' <<<"$jobs")
    for _ in $(seq 1 40); do if verify_stopped; then echo "Cloud stopped: zero matching active jobs or executions"; exit 0; fi; sleep 0.5; done
    echo "Cloud stop incomplete: matching active job or execution remains" >&2; exit 1 ;;
  verify-stopped)
    require_cloud_profile; verify_stopped || { echo "matching active job or execution remains" >&2; exit 1; }
    echo "Cloud clean: zero matching active jobs or executions" ;;
  purge)
    if preflight; then :; else rc=$?; [[ $rc == 2 ]] && { rm -rf "$ROOT/.cloud-state"; echo "no Cloud profile; local identities purged"; exit 0; }; exit "$rc"; fi
    "$0" stop; id="$(resolve_job)"; [[ -z "$id" ]] || cloud_cli job delete "$id" --yes --reason "demo teardown"
    nodes="$(cloud_cli node list --label demo=which-site-broke --label role=turbine --format json)"; jq -e 'all(.[]; .spec.labels.demo == "which-site-broke" and .spec.labels.role == "turbine")' <<<"$nodes" >/dev/null
    jq -r '.[].id' <<<"$nodes" | while read -r node; do [[ -z "$node" ]] || cloud_cli node delete "$node" --yes --reason "demo teardown"; done
    rm -rf "$ROOT/.cloud-state"; echo "exact labeled Cloud job/nodes and local identities purged" ;;
  *) echo "usage: $0 {preflight|bootstrap|start|await-scheduled|verify|stop-local|stop|verify-stopped|purge}" >&2; exit 2 ;;
esac
