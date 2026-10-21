#!/usr/bin/env bash
# Shared settings and helpers for the tiny-models demo. Sourced, not run.
#
# Everything this demo starts is recorded under .runtime/pids and stopped by
# `democtl.sh stop`. Everything listens on 127.0.0.1 only. Messages printed to
# the terminal use paths relative to this folder, so nothing under the home
# directory shows on a shared screen.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RT="$ROOT/.runtime"
MODELS="$ROOT/.models"
JOB_NAME="office-hours-005-models"
LIVE_FILE="$ROOT/live.cloud.yaml"

# Ports, all on 127.0.0.1.
COCKPIT_PORT=19500
INGEST_PORT=19501
LOCAL_EDGE_PORT=19510
CLOUD_EDGE_PORT=19511
DIRECT_PORT=18085

# Model 1: Python. `warm` trains it with scorer/train.py.
SCORER_MODEL="$MODELS/scorer.joblib"

# Model 2: Ollama. The machine's own Ollama; this demo never starts or stops
# the daemon, it only loads and unloads its model.
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:0.5b}"
# Loaded at `up` so the first note on air does not wait 5 to 7 s for a cold
# load. Each pipeline call then resets Ollama's idle timer to its default
# (5 minutes), and `down` unloads the model at once.
OLLAMA_PRELOAD_KEEP_ALIVE="45m"

# Model 3: direct call to an OpenAI-compatible endpoint. By default that is
# llama-server on this machine serving a GGUF that `warm` downloads. Set
# DIRECT_MODEL_URL (and DIRECT_MODEL_NAME, DIRECT_MODEL_TOKEN) to point the
# same pipeline somewhere else; the demo then starts no llama-server.
DIRECT_GGUF_URL="${DIRECT_GGUF_URL:-https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF/resolve/main/smollm2-360m-instruct-q8_0.gguf}"
DIRECT_GGUF="$MODELS/$(basename "$DIRECT_GGUF_URL")"
DIRECT_DEFAULT_URL="http://127.0.0.1:${DIRECT_PORT}/v1/chat/completions"
DIRECT_MODEL_URL="${DIRECT_MODEL_URL:-$DIRECT_DEFAULT_URL}"
DIRECT_MODEL_NAME="${DIRECT_MODEL_NAME:-smollm2-360m}"

die() { echo "error: $*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
rel() { printf '%s\n' "${1#"$ROOT"/}"; }

need() {
  local tool
  for tool in "$@"; do command -v "$tool" >/dev/null || die "$tool is not on PATH"; done
}

direct_is_ours() { [[ "$DIRECT_MODEL_URL" == "$DIRECT_DEFAULT_URL" ]]; }

port_open() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Credentials are looked up, never copied: OH5_ENV_FILE if set, else a .env
# beside this demo, beside the session, or at the repository root.
find_env_file() {
  local candidate
  for candidate in "${OH5_ENV_FILE:-}" "$ROOT/.env" "$ROOT/../../.env" "$ROOT/../../../../.env"; do
    if [[ -n "$candidate" && -f "$candidate" ]]; then
      (cd "$(dirname "$candidate")" && printf '%s/%s\n' "$(pwd -P)" "$(basename "$candidate")")
      return 0
    fi
  done
  return 1
}

# The office-hours node's data directory: OH5_EDGE_DATA_DIR if set, else the
# .expanso-edge folder next to the .env (see the top-level README, setup).
edge_data_dir() {
  if [[ -n "${OH5_EDGE_DATA_DIR:-}" ]]; then printf '%s\n' "$OH5_EDGE_DATA_DIR"; return; fi
  local env_file
  env_file="$(find_env_file)" || return 1
  printf '%s/.expanso-edge\n' "$(dirname "$env_file")"
}

dotenv_value() {
  awk -v target="$1" '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    {
      eq = index($0, "="); if (!eq) next
      key = substr($0, 1, eq - 1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      if (key != target) next
      value = substr($0, eq + 1); gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if ((value ~ /^".*"$/) || (value ~ /^\047.*\047$/)) value = substr(value, 2, length(value) - 2)
      print value; exit
    }
  ' "$2"
}

# expanso-cli against Expanso Cloud. The key travels in the environment, never
# on the command line, and an empty config dir keeps any personal profile out.
cloud_cli() {
  local env_file endpoint key
  env_file="$(find_env_file)" || die "no .env found; set OH5_ENV_FILE or see the session README"
  endpoint="$(dotenv_value EXPANSO_ENDPOINT "$env_file")"
  key="$(dotenv_value EXPANSO_API_KEY "$env_file")"
  [[ -n "$endpoint" && "$key" == exp_ak_* ]] || die "the .env must set EXPANSO_ENDPOINT and EXPANSO_API_KEY"
  mkdir -p "$RT/cli-config"
  EXPANSO_CLI_CONFIG_DIR="$RT/cli-config" EXPANSO_CLI_ENDPOINT="$endpoint" EXPANSO_CLI_AUTH_API_KEY="$key" \
    expanso-cli "$@"
}

# A local-mode node serves the same job API on 127.0.0.1.
local_cli() {
  mkdir -p "$RT/cli-config"
  EXPANSO_CLI_CONFIG_DIR="$RT/cli-config" expanso-cli --endpoint "http://127.0.0.1:${LOCAL_EDGE_PORT}" "$@"
}

lane() { if [[ -f "$RT/lane" ]]; then cat "$RT/lane"; else echo none; fi; }

lane_cli() {
  case "$(lane)" in
    cloud) cloud_cli "$@" ;;
    local) local_cli "$@" ;;
    *) die "nothing is up; run just up or just up-offline first" ;;
  esac
}

# expanso-cli appends a "Showing N of M" footer even to JSON; strip it.
json_only() {
  sed -e '/^Showing /,$d' -e '/^No .* found$/c\
[]'
}

# Start a background process in its own session, remember its pid and keep its log.
start_bg() {
  local name="$1"; shift
  mkdir -p "$RT/pids" "$RT/logs"
  (nohup perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV' "$@" >"$RT/logs/$name.log" 2>&1 </dev/null & echo $! >"$RT/pids/$name.pid")
}

pid_of() { [[ -f "$RT/pids/$1.pid" ]] && cat "$RT/pids/$1.pid"; }

alive() {
  local pid
  pid="$(pid_of "$1")" || return 1
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

stop_bg() {
  local name="$1" pid
  pid="$(pid_of "$name")" || return 0
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" "-$pid" 2>/dev/null || true
    for _ in $(seq 1 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    if kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" "-$pid" 2>/dev/null || true; sleep 0.5; fi
    say "stopped $name"
  fi
  rm -f "$RT/pids/$name.pid"
}

wait_for_url() {
  local url="$1" tries="${2:-80}"
  for _ in $(seq 1 "$tries"); do
    curl -fsS -m 2 "$url" >/dev/null 2>&1 && return 0
    sleep 0.25
  done
  return 1
}

# Environment the edge node needs to resolve the ${...} values in the job.
# Used as: start_bg edge env "${EDGE_ENV[@]}" expanso-edge run ...
edge_env_init() {
  EDGE_ENV=(
    "OH5_DEMO_DIR=$ROOT"
    "OH5_UV=$(command -v uv)"
    "OH5_SINK_URL=http://127.0.0.1:${COCKPIT_PORT}/api/sink"
    "OH5_DEAD_LETTER_FILE=$RT/dead-letter.jsonl"
    "OLLAMA_URL=$OLLAMA_URL"
    "OLLAMA_MODEL=$OLLAMA_MODEL"
    "DIRECT_MODEL_URL=$DIRECT_MODEL_URL"
    "DIRECT_MODEL_NAME=$DIRECT_MODEL_NAME"
    "DIRECT_MODEL_TOKEN=${DIRECT_MODEL_TOKEN:-none}"
  )
}
