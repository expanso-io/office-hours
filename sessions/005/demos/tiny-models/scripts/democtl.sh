#!/usr/bin/env bash
# Lifecycle for the tiny-models demo: warm, validate, up, stage, status, stop.
# Run through the justfile; every command works from any directory.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$ROOT"

stage_file() {
  local file
  file="$(ls pipelines/stage-"$1"-*.yaml 2>/dev/null | head -1)"
  [[ -n "$file" ]] || die "no pipeline for stage $1 (expected pipelines/stage-$1-*.yaml)"
  printf '%s\n' "$file"
}

# ---------------------------------------------------------------- warm

warm_python() {
  uv sync --frozen --quiet
  uv run --frozen --quiet python scorer/train.py
}

warm_direct() {
  direct_is_ours || { say "direct model: using $DIRECT_MODEL_URL, nothing to download"; return; }
  mkdir -p "$MODELS"
  if [[ -s "$DIRECT_GGUF" ]]; then
    say "direct model: $(basename "$DIRECT_GGUF") already present"
  else
    say "direct model: downloading $(basename "$DIRECT_GGUF")"
    curl -fL --progress-bar -o "$DIRECT_GGUF.part" "$DIRECT_GGUF_URL"
    mv "$DIRECT_GGUF.part" "$DIRECT_GGUF"
  fi
  say "direct model: $(wc -c <"$DIRECT_GGUF" | tr -d ' ') bytes"
}

warm_ollama() {
  ollama_is_ours || { say "ollama: using $OLLAMA_URL, pull $OLLAMA_MODEL there yourself"; return; }
  start_ollama
  OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" ollama pull "$OLLAMA_MODEL"
  stop_bg ollama
}

# ---------------------------------------------------------------- servers

start_ollama() {
  ollama_is_ours || return 0
  port_open "$OLLAMA_PORT" && die "port $OLLAMA_PORT is already in use"
  # One request at a time, one model, a 2k context (the notes are one line),
  # and NOPRUNE because this server shares the model store with any other
  # Ollama on the machine and must not tidy away blobs that one is fetching.
  start_bg ollama env OLLAMA_HOST="127.0.0.1:${OLLAMA_PORT}" \
    OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE_SECONDS}s" OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_CONTEXT_LENGTH=2048 OLLAMA_NOPRUNE=1 ollama serve
  wait_for_url "$OLLAMA_URL/api/version" || { cat "$RT/logs/ollama.log" >&2; die "ollama did not start"; }
}

start_direct() {
  direct_is_ours || return 0
  [[ -s "$DIRECT_GGUF" ]] || die "$DIRECT_GGUF missing; run just warm"
  port_open "$DIRECT_PORT" && die "port $DIRECT_PORT is already in use"
  start_bg direct llama-server -m "$DIRECT_GGUF" --alias "$DIRECT_MODEL_NAME" \
    --host 127.0.0.1 --port "$DIRECT_PORT" -c 2048 --parallel 1 --no-webui
  wait_for_url "http://127.0.0.1:${DIRECT_PORT}/health" 240 || { tail -20 "$RT/logs/direct.log" >&2; die "llama-server did not start"; }
}

start_cockpit() {
  port_open "$COCKPIT_PORT" && die "port $COCKPIT_PORT is already in use"
  start_bg cockpit env BROWSER=none OH5_RUNTIME="$RT" OH5_MODELS="$MODELS" \
    OLLAMA_URL="$OLLAMA_URL" OLLAMA_MODEL="$OLLAMA_MODEL" \
    DIRECT_MODEL_URL="$DIRECT_MODEL_URL" DIRECT_MODEL_NAME="$DIRECT_MODEL_NAME" \
    DIRECT_GGUF="$DIRECT_GGUF" \
    uv run --frozen --quiet python cockpit/server.py --port "$COCKPIT_PORT"
  wait_for_url "http://127.0.0.1:${COCKPIT_PORT}/api/health" || { cat "$RT/logs/cockpit.log" >&2; die "cockpit did not start"; }
}

start_edge_local() {
  port_open "$LOCAL_EDGE_PORT" && die "port $LOCAL_EDGE_PORT is already in use"
  mkdir -p "$RT/edge-local"
  edge_env_init
  start_bg edge env "${EDGE_ENV[@]}" expanso-edge run --local --no-watch \
    --data-dir "$RT/edge-local" --api-listen "127.0.0.1:${LOCAL_EDGE_PORT}"
  for _ in $(seq 1 80); do port_open "$LOCAL_EDGE_PORT" && return 0; sleep 0.25; done
  tail -20 "$RT/logs/edge.log" >&2; die "local edge node did not start"
}

start_edge_cloud() {
  local data_dir
  data_dir="$(edge_data_dir)" || die "no node data; set OH5_EDGE_DATA_DIR or see the session README"
  [[ -d "$data_dir/config.d" ]] || die "$data_dir is not an enrolled node (see the top-level README, step 3)"
  if pgrep -f -- "--data-dir $data_dir" >/dev/null; then
    die "an expanso-edge process is already using $data_dir; stop it, just up starts the node itself"
  fi
  port_open "$CLOUD_EDGE_PORT" && die "port $CLOUD_EDGE_PORT is already in use"
  edge_env_init
  start_bg edge env "${EDGE_ENV[@]}" expanso-edge run --no-watch \
    --data-dir "$data_dir" --api-listen "127.0.0.1:${CLOUD_EDGE_PORT}"
  say "waiting for Expanso Cloud to see the office-hours node"
  for _ in $(seq 1 60); do
    if cloud_cli node list --label role=office-hours --format json 2>/dev/null | json_only |
      jq -e 'any(.[]; (.status.connection_state // .status.connection // "") == "connected")' >/dev/null; then
      say "node connected"
      return 0
    fi
    alive edge || { tail -20 "$RT/logs/edge.log" >&2; die "edge node exited"; }
    sleep 1
  done
  die "the office-hours node did not show as connected in Expanso Cloud"
}

# ---------------------------------------------------------------- jobs

deploy_stage() {
  local stage="$1" file
  file="$(stage_file "$stage")"
  say "deploying $file to $(lane)"
  # --force makes a new revision even when the file is unchanged, so every
  # deploy starts a fresh, capped run.
  lane_cli job deploy "$file" --force
  printf '%s\n' "$stage" >"$RT/stage"
}

job_record() {
  lane_cli job list --format json | json_only | jq -c --arg n "$JOB_NAME" '[.[] | select(.spec.name == $n)] | .[0] // empty'
}

job_state() {
  local job
  job="$(job_record)"
  [[ -n "$job" ]] || { echo none; return; }
  jq -r '.status.state.state_type // "unknown"' <<<"$job"
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

wait_first_record() {
  for _ in $(seq 1 120); do
    [[ -s "$RT/enriched.jsonl" ]] && { say "first record written"; return 0; }
    sleep 0.5
  done
  tail -30 "$RT/logs/edge.log" >&2
  die "no record reached $RT/enriched.jsonl within 60 s"
}

# ---------------------------------------------------------------- preflight

preflight_common() {
  need uv jq curl expanso-edge expanso-cli
  ollama_is_ours && need ollama
  direct_is_ours && need llama-server
  [[ -s "$SCORER_MODEL" ]] || warm_python
  if direct_is_ours && [[ ! -s "$DIRECT_GGUF" ]]; then die "$DIRECT_GGUF missing; run just warm"; fi
}

preflight_cloud() {
  local env_file unscoped
  env_file="$(find_env_file)" || die "no .env found; set OH5_ENV_FILE or put one at the repository root"
  [[ "$(stat -f '%Lp' "$env_file" 2>/dev/null || stat -c '%a' "$env_file")" == 600 ]] || die "$env_file must be mode 600"
  cloud_cli status >/dev/null || die "Expanso Cloud did not answer"
  # A running job with an empty selector would land on this node too.
  unscoped="$(cloud_cli job list --format json | json_only |
    jq -r '.[] | select((.spec.selector // {}) == {}) | select((.status.state.state_type // "") == "running") | .spec.name')"
  [[ -z "$unscoped" ]] || die "running jobs with empty selectors would also run here: $unscoped"
}

# ---------------------------------------------------------------- commands

cmd_up() {
  local mode="$1" stage="${2:-3}"
  [[ "$mode" == cloud || "$mode" == local ]] || die "mode must be cloud or local"
  stage_file "$stage" >/dev/null
  preflight_common
  [[ "$mode" == cloud ]] && preflight_cloud
  if [[ -d "$RT" ]]; then cmd_stop; fi
  mkdir -p "$RT"; chmod 700 "$RT"
  printf '%s\n' "$mode" >"$RT/lane"
  # die() exits rather than returning, so clean up from an EXIT trap.
  trap 'echo "start failed, stopping what was started" >&2; cmd_stop || true' EXIT
  start_ollama
  start_direct
  start_cockpit
  if [[ "$mode" == cloud ]]; then start_edge_cloud; else start_edge_local; fi
  deploy_stage "$stage"
  wait_first_record
  trap - EXIT
  say "Tiny models cockpit: http://127.0.0.1:${COCKPIT_PORT}  (lane: $mode, stage $stage)"
}

cmd_stage() {
  [[ -d "$RT" ]] || die "nothing is up; run just up or just up-offline first"
  deploy_stage "${1:?stage number}"
}

cmd_status() {
  if [[ ! -d "$RT" ]]; then say "down"; return 0; fi
  say "lane: $(lane)   stage: $(cat "$RT/stage" 2>/dev/null || echo none)"
  local name
  for name in ollama direct cockpit edge; do
    if alive "$name"; then say "  $name: running (pid $(pid_of "$name"))"
    elif [[ -f "$RT/pids/$name.pid" ]]; then say "  $name: EXITED, see .runtime/logs/$name.log"
    fi
  done
  ollama_is_ours || say "  ollama: external at $OLLAMA_URL"
  direct_is_ours || say "  direct: external at $DIRECT_MODEL_URL"
  if [[ "$(lane)" != none ]] && alive edge; then
    say "  job $JOB_NAME: $(job_state), active executions: $(active_executions)"
  fi
  if [[ -s "$RT/enriched.jsonl" ]]; then
    say "  records written: $(wc -l <"$RT/enriched.jsonl" | tr -d ' ')"
    say "latest record:"
    tail -1 "$RT/enriched.jsonl" | jq .
  fi
}

stop_job() {
  local job id
  case "$(lane)" in
    cloud)
      job="$(job_record)"
      [[ -n "$job" ]] || { say "Cloud: no $JOB_NAME job"; return 0; }
      id="$(jq -r .id <<<"$job")"
      if [[ "$(jq -r '.status.state.state_type // ""' <<<"$job")" != stopped ]]; then
        cloud_cli job stop "$id" --force || true
      fi
      for _ in $(seq 1 60); do
        if [[ "$(active_executions)" == 0 ]]; then say "Cloud: $JOB_NAME stopped, no active executions"; return 0; fi
        sleep 1
      done
      die "Cloud: $JOB_NAME still has an active execution"
      ;;
    local)
      if alive edge; then local_cli job stop "$JOB_NAME" --force >/dev/null 2>&1 || true; fi
      ;;
  esac
  return 0
}

unload_ollama_model() {
  ollama_is_ours || return 0
  curl -fsS -m 5 "$OLLAMA_URL/api/generate" -d "{\"model\":\"$OLLAMA_MODEL\",\"keep_alive\":0}" >/dev/null 2>&1 || true
}

cmd_stop() {
  [[ -d "$RT" ]] || { say "already down"; return 0; }
  local rc=0
  stop_job || rc=$?
  stop_bg edge
  stop_bg cockpit
  stop_bg direct
  unload_ollama_model
  stop_bg ollama
  if (( rc == 0 )); then rm -rf "$RT"; fi
  return "$rc"
}

cmd_validate() {
  bash -n scripts/*.sh
  uv sync --frozen --quiet
  uv run --frozen ruff check scorer cockpit tests
  uv run --frozen ruff format --check scorer cockpit tests
  local file
  for file in pipelines/*.yaml; do
    expanso-edge validate "$file"
    expanso-cli job validate "$file" --offline >/dev/null && say "[OK] $file: job spec"
  done
  uv run --frozen pytest -q
}

cmd_test_live() {
  trap '"$0" stop >/dev/null 2>&1 || true' EXIT
  cmd_up local 3
  say "waiting for six records with all three answers"
  local n=0
  for _ in $(seq 1 60); do
    n="$(wc -l <"$RT/enriched.jsonl" | tr -d ' ')"
    (( n >= 6 )) && break
    sleep 1
  done
  (( n >= 6 )) || die "only $n records after 60 s"
  head -6 "$RT/enriched.jsonl" | jq -se '
    length == 6 and all(.[];
      (.python.score | type) == "number" and (.python.anomaly | type) == "boolean" and
      ((.ollama.severity // "") | IN("low", "medium", "high")) and
      ((.direct.part // "") | length) > 0 and
      (.python.call_ms | type) == "number" and (.ollama.call_ms | type) == "number" and
      (.direct.call_ms | type) == "number")' >/dev/null || {
    head -6 "$RT/enriched.jsonl" >&2; die "records are missing a model answer or a timing"; }
  curl -fsS "http://127.0.0.1:${COCKPIT_PORT}/api/state" | jq -e '
    (.records | length) >= 6 and
    ([.models[] | .calls] | all(. >= 6)) and
    (.models.python.bytes > 0) and (.models.ollama.bytes > 0) and (.models.direct.bytes > 0)' >/dev/null ||
    die "cockpit state does not match the records"
  trap - EXIT
  cmd_stop
  "$ROOT/scripts/teardown-audit.sh"
  say "live offline proof passed: six records, three answers each, timings and sizes on the cockpit"
}

case "${1:-}" in
  warm) need uv ollama llama-server curl; warm_python; warm_direct; warm_ollama; rm -rf "$RT" ;;
  validate) cmd_validate ;;
  up) cmd_up "${2:-cloud}" "${3:-3}" ;;
  stage) cmd_stage "${2:-}" ;;
  status) cmd_status ;;
  stop) cmd_stop ;;
  test-live) cmd_test_live ;;
  logs) tail -n 40 "$RT"/logs/*.log ;;
  *) echo "usage: $0 {warm|validate|up cloud|local [stage]|stage N|status|stop|test-live|logs}" >&2; exit 2 ;;
esac
