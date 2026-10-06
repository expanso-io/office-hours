#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."; fail=0
if lsof -nP -iTCP:19450 -sTCP:LISTEN 2>/dev/null | grep -q .; then echo "port 19450 still owned" >&2; fail=1; fi
if docker ps -a --filter label=io.expanso.demo=which-site-broke --format '{{.ID}}' | grep -q .; then echo "labeled containers remain" >&2; fail=1; fi
if docker network ls --filter name='^expanso-demo-which-site-broke_' --format '{{.Name}}' | grep -q .; then echo "project networks remain" >&2; fail=1; fi
if docker volume ls --filter name='^expanso-demo-which-site-broke_' --format '{{.Name}}' | grep -q .; then echo "project volumes remain" >&2; fail=1; fi
[[ ! -e .runtime ]] || { echo ".runtime remains" >&2; fail=1; }
(( fail == 0 )) || exit 1; echo "teardown clean: port, containers, networks, volumes, runtime"
