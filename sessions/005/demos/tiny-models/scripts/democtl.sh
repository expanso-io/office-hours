#!/usr/bin/env bash
# Lifecycle for the tiny-models demo. Run through the justfile; every command
# works from any directory.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$ROOT"

stage_file() {
  local file="pipelines/stage-$1.cloud.yaml"
  [[ -f "$file" ]] || die "no pipeline for stage $1 (expected $file)"
  printf '%s\n' "$file"
}

# ---------------------------------------------------------------- warm

warm_python() {
  uv sync --frozen --quiet
  uv run --frozen --quiet python scorer/train.py | sed "s#$ROOT/##"
}

warm_direct() {
  direct_is_ours || { say "direct model: using $DIRECT_MODEL_URL, nothing to download"; return; }
  mkdir -p "$MODELS"
  if [[ -s "$DIRECT_GGUF" ]]; then
    say "direct model: $(rel "$DIRECT_GGUF") already here"
  else
    say "direct model: downloading $(basename "$DIRECT_GGUF")"
    curl -fL --progress-bar -o "$DIRECT_GGUF.part" "$DIRECT_GGUF_URL"
    mv "$DIRECT_GGUF.part" "$DIRECT_GGUF"
  fi
}

ollama_up() { curl -fsS -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; }

warm_ollama() {
  ollama_up || die "Ollama is not answering at $OLLAMA_URL; start it (brew services start ollama, or the Ollama app)"
  OLLAMA_HOST="${OLLAMA_URL#http://}" ollama pull "$OLLAMA_MODEL"
}

cmd_warm() {
  need uv curl jq ollama
  direct_is_ours && need llama-server
  warm_python
  warm_direct
  warm_ollama
  mkdir -p "$RT"
  start_direct
  uv run --frozen --quiet python scripts/manifest.py "$MODELS" "$OLLAMA_URL" "$OLLAMA_MODEL" \
    "$DIRECT_MODEL_URL" "$DIRECT_MODEL_NAME" "$DIRECT_GGUF"
  stop_bg direct
  rm -rf "$RT"
  say "warm: models trained, downloaded and pulled; manifest written"
}

# ---------------------------------------------------------------- servers

start_direct() {
  direct_is_ours || return 0
  [[ -s "$DIRECT_GGUF" ]] || die "$(rel "$DIRECT_GGUF") missing; run just warm"
  port_open "$DIRECT_PORT" && die "port $DIRECT_PORT is already in use"
  start_bg direct llama-server -m "$DIRECT_GGUF" --alias "$DIRECT_MODEL_NAME" \
    --host 127.0.0.1 --port "$DIRECT_PORT" -c 2048 --parallel 1 --no-webui
  wait_for_url "http://127.0.0.1:${DIRECT_PORT}/health" 240 || {
    tail -5 "$RT/logs/direct.log" >&2; die "llama-server did not start"; }
  say "llama-server serving $DIRECT_MODEL_NAME on 127.0.0.1:$DIRECT_PORT"
}

preload_ollama() {
  ollama_up || die "Ollama is not answering at $OLLAMA_URL"
  curl -fsS -m 60 "$OLLAMA_URL/api/generate" \
    -d "{\"model\":\"$OLLAMA_MODEL\",\"keep_alive\":\"$OLLAMA_PRELOAD_KEEP_ALIVE\"}" >/dev/null ||
    die "Ollama could not load $OLLAMA_MODEL; run just warm"
  say "Ollama has $OLLAMA_MODEL loaded"
}

unload_ollama() {
  local model seen=""
  for model in "$OLLAMA_MODEL" "$(jq -r '.ollama.name // empty' "$MODELS/manifest.json" 2>/dev/null || true)"; do
    [[ -n "$model" && " $seen " != *" $model "* ]] || continue
    seen="$seen $model"
    curl -fsS -m 10 "$OLLAMA_URL/api/generate" -d "{\"model\":\"$model\",\"keep_alive\":0}" >/dev/null 2>&1 &&
      say "Ollama unloaded $model" || true
  done
}

start_cockpit() {
  port_open "$COCKPIT_PORT" && die "port $COCKPIT_PORT is already in use"
  start_bg cockpit env BROWSER=none OH5_RUNTIME="$RT" OH5_MODELS="$MODELS" \
    OLLAMA_URL="$OLLAMA_URL" OLLAMA_MODEL="$OLLAMA_MODEL" \
    uv run --frozen --quiet python cockpit/server.py --port "$COCKPIT_PORT"
  wait_for_url "http://127.0.0.1:${COCKPIT_PORT}/api/health" || {
    tail -5 "$RT/logs/cockpit.log" >&2; die "cockpit did not start"; }
}

start_feed() {
  start_bg feed env OH5_RUNTIME="$RT" uv run --frozen --quiet python feed.py \
    --url "http://127.0.0.1:${INGEST_PORT}/ingest"
}

start_edge_local() {
  port_open "$LOCAL_EDGE_PORT" && die "port $LOCAL_EDGE_PORT is already in use"
  mkdir -p "$RT/edge-local"
  edge_env_init
  start_bg edge env "${EDGE_ENV[@]}" expanso-edge run --local --no-watch \
    --data-dir "$RT/edge-local" --api-listen "127.0.0.1:${LOCAL_EDGE_PORT}"
  for _ in $(seq 1 80); do port_open "$LOCAL_EDGE_PORT" && { say "local-mode edge node up"; return 0; }; sleep 0.25; done
  die "local edge node did not start; see .runtime/logs/edge.log"
}

start_edge_cloud() {
  local data_dir
  data_dir="$(edge_data_dir)" || die "no node data; set OH5_EDGE_DATA_DIR or see the session README"
  [[ -d "$data_dir/config.d" ]] || die "no enrolled node found next to the .env (top-level README, setup step 3)"
  if pgrep -f -- "--data-dir $data_dir" >/dev/null; then
    die "an expanso-edge process is already using the office-hours node; stop it, just up starts the node itself"
  fi
  port_open "$CLOUD_EDGE_PORT" && die "port $CLOUD_EDGE_PORT is already in use"
  edge_env_init
  start_bg edge env "${EDGE_ENV[@]}" expanso-edge run --no-watch \
    --data-dir "$data_dir" --api-listen "127.0.0.1:${CLOUD_EDGE_PORT}"
  say "waiting for Expanso Cloud to see the office-hours node"
  for _ in $(seq 1 90); do
    if [[ "$(node_state)" == connected ]]; then say "node connected"; return 0; fi
    alive edge || die "edge node exited; see .runtime/logs/edge.log"
    sleep 1
  done
  die "the office-hours node did not show as connected in Expanso Cloud"
}

node_state() {
  cloud_cli node list --label role=office-hours --format json 2>/dev/null | json_only |
    jq -r 'if any(.[]; (.status.connection_state // "") == "connected") then "connected"
           elif length == 0 then "absent" else "disconnected" end'
}

# ---------------------------------------------------------------- jobs

job_record() {
  lane_cli job list --format json | json_only |
    jq -c --arg n "$JOB_NAME" '[.[] | select(.spec.name == $n)] | .[0] // empty'
}

job_version() {
  local job
  job="$(job_record)"
  [[ -n "$job" ]] || { echo 0; return; }
  jq -r '.version // .job_version // .status.version // 0' <<<"$job"
}

write_job_json() {
  local job
  job="$(job_record)"
  jq -n --arg name "$JOB_NAME" --arg lane "$(lane)" --argjson job "${job:-null}" \
    '{name: $name, lane: $lane, version: ($job.version // $job.job_version // $job.status.version // null),
      state: ($job.status.state.state_type // null)}' >"$RT/job.json"
}

wait_running() {
  for _ in $(seq 1 60); do
    if [[ "$(jq -r '.status.state.state_type // ""' <<<"$(job_record)")" == running ]]; then return 0; fi
    sleep 1
  done
  return 1
}

deploy_file() {
  local file="$1"
  expanso-edge validate "$file" >/dev/null || {
    expanso-edge validate "$file" | sed "s#$ROOT/##" >&2
    die "$(rel "$file") does not validate; fix the paste or use just stage N"
  }
  say "deploying $(rel "$file") to $(lane)"
  lane_cli job deploy "$file" --force
  wait_running || say "warning: job not reported running yet"
  write_job_json
  mkdir -p "$RT/versions"
  cp "$file" "$RT/versions/v$(jq -r .version "$RT/job.json").yaml"
  if grep -q problem_reported "$file"; then
    printf 'strainer\n' >"$RT/note-cue"
  else
    printf 'bearing\n' >"$RT/note-cue"
  fi
  say "$JOB_NAME is at version $(jq -r .version "$RT/job.json")"
}

# A fresh job for each session, so Cloud's version history starts at 1.
fresh_job() {
  local job id
  job="$(job_record)"
  [[ -n "$job" ]] || return 0
  id="$(jq -r .id <<<"$job")"
  say "removing the previous $JOB_NAME job so this run starts at version 1"
  lane_cli job stop "$id" --force >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do [[ "$(active_executions)" == 0 ]] && break; sleep 1; done
  lane_cli job delete "$id" --yes --reason "office hours 005: fresh run" >/dev/null
}

active_executions() {
  local job id
  job="$(job_record)"
  [[ -n "$job" ]] || { echo 0; return; }
  id="$(jq -r .id <<<"$job")"
  lane_cli execution list --job-id "$id" --format json | json_only |
    jq '[.[] | select(((.status.observed_state.state_type // .status.state.state_type // "") as $s |
      ["completed", "failed", "lost", "stopped", "cancelled"] | index($s)) == null)] | length'
}

stop_job() {
  local job id
  case "$(lane)" in
    cloud)
      job="$(job_record)"
      [[ -n "$job" ]] || { say "Cloud: no $JOB_NAME job"; return 0; }
      id="$(jq -r .id <<<"$job")"
      if [[ "$(jq -r '.status.state.state_type // ""' <<<"$job")" != stopped ]]; then
        cloud_cli job stop "$id" --force >/dev/null || true
      fi
      for _ in $(seq 1 60); do
        if [[ "$(active_executions)" == 0 ]]; then say "Cloud: $JOB_NAME stopped, no active executions"; return 0; fi
        sleep 1
      done
      echo "Cloud: $JOB_NAME still has an active execution" >&2
      return 1
      ;;
    local)
      if alive edge; then local_cli job stop "$JOB_NAME" --force >/dev/null 2>&1 || true; fi
      ;;
  esac
  return 0
}

# ---------------------------------------------------------------- preflight

preflight_common() {
  need uv jq curl expanso-edge expanso-cli
  direct_is_ours && need llama-server
  [[ -s "$SCORER_MODEL" ]] || warm_python
  [[ -s "$MODELS/manifest.json" ]] || die "no model manifest; run just warm"
  if direct_is_ours && [[ ! -s "$DIRECT_GGUF" ]]; then die "$(rel "$DIRECT_GGUF") missing; run just warm"; fi
  local port
  for port in "$COCKPIT_PORT" "$INGEST_PORT" "$DIRECT_PORT"; do
    port_open "$port" && die "port $port is in use; run just down first"
  done
  return 0
}

preflight_cloud() {
  local env_file unscoped
  env_file="$(find_env_file)" || die "no .env found; set OH5_ENV_FILE or put one at the repository root"
  [[ "$(stat -f '%Lp' "$env_file" 2>/dev/null || stat -c '%a' "$env_file")" == 600 ]] || die "the .env must be mode 600"
  cloud_cli status >/dev/null || die "Expanso Cloud did not answer"
  # A running job with an empty selector would land on this node too.
  unscoped="$(cloud_cli job list --format json | json_only |
    jq -r '.[] | select((.spec.selector // {}) == {}) | select((.status.state.state_type // "") == "running") | .spec.name')"
  [[ -z "$unscoped" ]] || die "running jobs with empty selectors would also run here: $unscoped"
}

# ---------------------------------------------------------------- commands

cmd_up() {
  local mode="$1" stage="${2:-1}"
  [[ "$mode" == cloud || "$mode" == local ]] || die "mode must be cloud or local"
  stage_file "$stage" >/dev/null
  if [[ -d "$RT" ]]; then cmd_stop; fi
  preflight_common
  [[ "$mode" == cloud ]] && preflight_cloud
  mkdir -p "$RT"; chmod 700 "$RT"
  printf '%s\n' "$mode" >"$RT/lane"
  # die() exits rather than returning, so clean up from an EXIT trap.
  trap 'echo "start failed, stopping what was started" >&2; cmd_stop || true' EXIT
  preload_ollama
  start_direct
  start_cockpit
  if [[ "$mode" == cloud ]]; then start_edge_cloud; else start_edge_local; fi
  [[ "$mode" == cloud ]] && fresh_job
  cp "$(stage_file "$stage")" "$LIVE_FILE"
  deploy_file "$LIVE_FILE"
  start_feed
  say "waiting for the first record to leave the node"
  for _ in $(seq 1 60); do
    if [[ "$(curl -fsS "http://127.0.0.1:${COCKPIT_PORT}/api/state" | jq .records_out)" -gt 0 ]]; then
      trap - EXIT
      say "cockpit: http://127.0.0.1:${COCKPIT_PORT}"
      say "edit live.cloud.yaml and run just deploy, or run just stage N"
      return 0
    fi
    sleep 1
  done
  die "no record reached the cockpit within 60 s; see .runtime/logs"
}

cmd_stage() {
  [[ -d "$RT" ]] || die "nothing is up; run just up or just up-offline first"
  cp "$(stage_file "${1:?stage number}")" "$LIVE_FILE"
  deploy_file "$LIVE_FILE"
}

cmd_deploy() {
  [[ -d "$RT" ]] || die "nothing is up; run just up or just up-offline first"
  [[ -f "$LIVE_FILE" ]] || die "live.cloud.yaml missing; run just stage N"
  deploy_file "$LIVE_FILE"
}

cmd_rollback() {
  local version target
  version="$(job_version)"
  (( version > 1 )) || die "nothing to roll back to"
  target="$((version - 1))"
  say "rolling $JOB_NAME back to the spec of version $target"
  if [[ -f "$RT/versions/v${target}.yaml" ]]; then
    cp "$RT/versions/v${target}.yaml" "$LIVE_FILE"
  else
    cp "$(stage_file 3)" "$LIVE_FILE"
  fi
  if ! lane_cli job rollback "$JOB_NAME" --to-version "$target" --reason "office hours 005: rollback" --force 2>/dev/null; then
    lane_cli job deploy "$LIVE_FILE" --force
  fi
  wait_running || true
  write_job_json
  mkdir -p "$RT/versions"
  cp "$LIVE_FILE" "$RT/versions/v$(jq -r .version "$RT/job.json").yaml" 2>/dev/null || true
  printf 'bearing\n' >"$RT/note-cue"
  say "$JOB_NAME is at version $(jq -r .version "$RT/job.json")"
}

cmd_versions() {
  lane_cli job versions "$JOB_NAME"
}

cmd_versions_diff() {
  local from="${1:-1}" to="${2:-3}"
  if ! lane_cli job versions-diff "$JOB_NAME" --from "$from" --to "$to" 2>/dev/null; then
    diff -u "$RT/versions/v${from}.yaml" "$RT/versions/v${to}.yaml" || true
  fi
}

cmd_ollama_model() {
  [[ -d "$RT" ]] || die "nothing is up; run just up or just up-offline first"
  local model="${1:?model name, e.g. gemma3:270m}"
  OLLAMA_MODEL="$model" warm_ollama
  OLLAMA_MODEL="$model" preload_ollama
  uv run --frozen --quiet python scripts/manifest.py "$MODELS" "$OLLAMA_URL" "$model" \
    "$DIRECT_MODEL_URL" "$DIRECT_MODEL_NAME" "$DIRECT_GGUF"
  [[ -f "$LIVE_FILE" ]] || cp "$(stage_file 3)" "$LIVE_FILE"
  sed -i.bak -E "s|^([[:space:]]*model: ).*|\1$model|" "$LIVE_FILE" && rm -f "$LIVE_FILE.bak"
  deploy_file "$LIVE_FILE"
}

cmd_break() {
  direct_is_ours || die "the direct model is external; nothing local to stop"
  alive direct || die "llama-server is not running"
  stop_bg direct
  printf 'bearing\n' >"$RT/note-cue"
  say "llama-server is down; the pipeline keeps running"
}

cmd_heal() {
  alive direct && { say "llama-server is already running"; return 0; }
  start_direct
  printf 'bearing\n' >"$RT/note-cue"
}

cmd_rate() {
  [[ -d "$RT" ]] || die "nothing is up"
  [[ "${1:-}" =~ ^[0-9]+$ ]] || die "usage: just rate READINGS_PER_SECOND"
  printf '%s\n' "$1" >"$RT/feed-rate"
  say "feed set to $1 readings per second"
}

cmd_status() {
  if [[ ! -d "$RT" ]]; then say "down"; return 0; fi
  say "lane: $(lane)"
  local name
  for name in direct cockpit edge feed; do
    if alive "$name"; then say "  $name: running"
    elif [[ -f "$RT/pids/$name.pid" ]]; then say "  $name: EXITED, see .runtime/logs/$name.log"
    fi
  done
  if alive edge; then
    write_job_json
    say "  job $JOB_NAME: version $(jq -r .version "$RT/job.json"), $(jq -r .state "$RT/job.json")"
  fi
  curl -fsS -m 3 "http://127.0.0.1:${COCKPIT_PORT}/api/state" | jq '{
    records_in, records_out, kept_on_node_pct: .rates.kept_pct, in_per_s: .rates.in_per_s,
    out_per_s: .rates.out_per_s, degraded, dead_letters,
    ms_p50: (.models | map_values(.p50_ms)), ms_p95: (.models | map_values(.p95_ms))}' || true
}

cmd_stop() {
  [[ -d "$RT" ]] || { say "already down"; return 0; }
  local rc=0
  stop_bg feed
  stop_job || rc=$?
  stop_bg edge
  stop_bg cockpit
  stop_bg direct
  unload_ollama
  if (( rc == 0 )); then rm -rf "$RT" "$LIVE_FILE"; fi
  return "$rc"
}

cmd_validate() {
  bash -n scripts/*.sh
  uv sync --frozen --quiet
  uv run --frozen ruff check .
  uv run --frozen ruff format --check .
  local file
  for file in pipelines/stage-*.cloud.yaml; do
    expanso-edge validate "$file" | sed "s#$ROOT/##"
    expanso-cli job validate "$file" --offline >/dev/null && say "[OK] $file: job spec"
  done
  uv run --frozen pytest -q
}

case "${1:-}" in
  warm) cmd_warm ;;
  validate) cmd_validate ;;
  up) cmd_up "${2:-cloud}" "${3:-1}" ;;
  stage) cmd_stage "${2:-}" ;;
  deploy) cmd_deploy ;;
  rollback) cmd_rollback ;;
  versions) cmd_versions ;;
  versions-diff) cmd_versions_diff "${2:-1}" "${3:-3}" ;;
  ollama-model) cmd_ollama_model "${2:-}" ;;
  break) cmd_break ;;
  heal) cmd_heal ;;
  rate) cmd_rate "${2:-}" ;;
  status) cmd_status ;;
  stop) cmd_stop ;;
  logs) tail -n 30 "$RT"/logs/*.log ;;
  *) echo "usage: $0 {warm|validate|up cloud|local [stage]|stage N|deploy|rollback|versions|versions-diff [from] [to]|ollama-model MODEL|break|heal|rate N|status|stop|logs}" >&2; exit 2 ;;
esac
