#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE="$COMPOSE_ROOT/.ios-proxy.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "iproxy not running"
  exit 0
fi
pid="$(cat "$PIDFILE")"
kill "$pid" 2>/dev/null && echo "stopped iproxy (pid $pid)" || echo "process $pid not found"
rm -f "$PIDFILE"
