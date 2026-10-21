#!/usr/bin/env bash
# Prove the demo is gone: no listening port, no process, no runtime state, no
# Ollama model in memory, no container, and no running job in Expanso Cloud.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$ROOT"

fail=0
bad() { echo "NOT CLEAN: $*" >&2; fail=1; }

for port in "$COCKPIT_PORT" "$LOCAL_EDGE_PORT" "$CLOUD_EDGE_PORT" "$OLLAMA_PORT" "$DIRECT_PORT"; do
  port_open "$port" && bad "port $port is still listening"
done

pgrep -f -- "cockpit/server.py --port $COCKPIT_PORT" >/dev/null && bad "cockpit process still running"
pgrep -f -- "llama-server -m $MODELS/" >/dev/null && bad "llama-server still running"
pgrep -f -- "--data-dir $RT/edge-local" >/dev/null && bad "local edge node still running"
pgrep -f -- "--api-listen 127.0.0.1:$CLOUD_EDGE_PORT" >/dev/null && bad "office-hours edge node still running"
pgrep -f -- "$ROOT/scorer/score.py" >/dev/null && bad "Python scorer still running"

[[ -e "$RT" ]] && bad ".runtime still exists"

# Our own Ollama server is gone (port check above), and with it any model it
# had loaded. If OLLAMA_URL points at someone else's Ollama, make sure this
# demo's model is no longer in that server's memory.
if ! ollama_is_ours && curl -fsS -m 2 "$OLLAMA_URL/api/ps" >/tmp/oh5-ollama-ps.$$ 2>/dev/null; then
  jq -e --arg m "$OLLAMA_MODEL" 'any(.models[]?; .name == $m or .model == $m)' /tmp/oh5-ollama-ps.$$ >/dev/null &&
    bad "$OLLAMA_MODEL is still loaded in the Ollama at $OLLAMA_URL"
fi
rm -f /tmp/oh5-ollama-ps.$$

if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  docker ps -a --format '{{.Names}} {{.Labels}}' | grep -E 'office-hours-005|tiny-models' >/dev/null &&
    bad "a container from this demo exists"
fi

cloud_note="Cloud: skipped, no .env found"
if find_env_file >/dev/null; then
  jobs_json="$(cloud_cli job list --format json 2>/dev/null | json_only)" || { bad "could not list Cloud jobs"; jobs_json='[]'; }
  state="$(jq -r --arg n "$JOB_NAME" '[.[] | select(.spec.name == $n)] | .[0].status.state.state_type // "none"' <<<"$jobs_json")"
  case "$state" in
    none|stopped|completed|failed) cloud_note="Cloud: $JOB_NAME is $state" ;;
    *) bad "Cloud job $JOB_NAME is $state" ;;
  esac
  rm -rf "$RT/cli-config"; rmdir "$RT" 2>/dev/null || true
fi

(( fail == 0 )) || exit 1
echo "teardown clean: ports, processes, runtime, Ollama model, containers. $cloud_note"
