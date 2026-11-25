#!/usr/bin/env bash
# Prove the demo is gone: no listening port, no process, no runtime state, the
# Ollama model out of memory, no container, and in Expanso Cloud the node
# disconnected with no active job or execution.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
cd "$ROOT"

fail=0
bad() { echo "NOT CLEAN: $*" >&2; fail=1; }

for port in "$COCKPIT_PORT" "$INGEST_PORT" "$DIRECT_PORT" "$LOCAL_EDGE_PORT" "$CLOUD_EDGE_PORT"; do
  port_open "$port" && bad "port $port is still listening"
done

pgrep -f -- "llama-server -m $MODELS/" >/dev/null && bad "llama-server still running"
pgrep -f -- "feed.py --url http://127.0.0.1:$INGEST_PORT" >/dev/null && bad "feed.py still running"
pgrep -f -- "$ROOT/scorer/score.py" >/dev/null && bad "score.py still running"
pgrep -f -- "cockpit/server.py --port $COCKPIT_PORT" >/dev/null && bad "cockpit still running"
pgrep -f -- "--data-dir $RT/edge-local" >/dev/null && bad "local-mode expanso-edge still running"
pgrep -f -- "expanso-edge run .*--api-listen 127.0.0.1:$CLOUD_EDGE_PORT" >/dev/null && bad "office-hours expanso-edge still running"

[[ -e "$RT" ]] && bad ".runtime still exists"
[[ -e "$LIVE_FILE" ]] && bad "live.cloud.yaml still exists"

# The machine's Ollama keeps running; only this demo's model must be out of
# its memory. (Another client on this machine loading the same model would
# also show here.)
if curl -fsS -m 2 "$OLLAMA_URL/api/ps" >/tmp/oh5-ollama-ps.$$ 2>/dev/null; then
  jq -e --arg m "$OLLAMA_MODEL" 'any(.models[]?; .name == $m or .model == $m)' /tmp/oh5-ollama-ps.$$ >/dev/null &&
    bad "$OLLAMA_MODEL is still loaded in Ollama"
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
    none|stopped|completed|failed) ;;
    *) bad "Cloud job $JOB_NAME is $state" ;;
  esac
  # A stopped node can take a few seconds to show as disconnected.
  node="unknown"
  for _ in $(seq 1 45); do
    node="$(cloud_cli node list --label role=office-hours --format json 2>/dev/null | json_only |
      jq -r 'if any(.[]; (.status.connection_state // "") == "connected") then "connected"
             elif length == 0 then "absent" else "disconnected" end')"
    [[ "$node" != connected ]] && break
    sleep 2
  done
  [[ "$node" == connected ]] && bad "the office-hours node still shows connected in Cloud"
  cloud_note="Cloud: job $state, office-hours node $node"
  rm -rf "$RT/cli-config"; rmdir "$RT" 2>/dev/null || true
fi

(( fail == 0 )) || exit 1
echo "teardown clean: ports, processes, runtime, Ollama model, containers. $cloud_note"
