#!/usr/bin/env bash
# Start iproxy 8100→8100 in background for WDA
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE="$COMPOSE_ROOT/.ios-proxy.pid"
LOG="$COMPOSE_ROOT/.ios-proxy.log"

[[ -f "$COMPOSE_ROOT/devkit.env" ]] && set -a && source "$COMPOSE_ROOT/devkit.env" && set +a

command -v iproxy >/dev/null 2>&1 || { echo "error: iproxy not found (brew install libimobiledevice)" >&2; exit 1; }
command -v iphone-ctl >/dev/null 2>&1 || { echo "error: iphone-ctl not found" >&2; exit 1; }

UDID="${IOS_UDID:-}"
if [[ -z "$UDID" ]]; then
  UDID="$(ioskit devices 2>/dev/null | head -1 || true)"
fi
[[ -n "$UDID" ]] || { echo "error: no iOS device — set IOS_UDID" >&2; exit 1; }

if [[ -f "$PIDFILE" ]]; then
  old="$(cat "$PIDFILE")"
  if kill -0 "$old" 2>/dev/null; then
    echo "iproxy already running (pid $old)"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

echo "→ mounting Developer Disk Image (iOS 17+)"
xcrun devicectl device info ddiServices --device "$UDID" --auto-mount-ddis -q 2>/dev/null || true

echo "starting iproxy 8100 8100 -u $UDID"
nohup iproxy 8100 8100 -u "$UDID" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
sleep 1

if iphone-ctl wda status 2>/dev/null | grep -q ready; then
  echo "✓ WDA ready at http://127.0.0.1:8100"
else
  echo "iproxy started (pid $(cat "$PIDFILE"))"
  echo "! WDA not ready yet — start WebDriverAgentRunner on iPhone (Xcode Run)"
  echo "  log: $LOG"
fi
