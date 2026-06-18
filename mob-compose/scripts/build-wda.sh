#!/usr/bin/env bash
# Build WebDriverAgentRunner to device via xcodebuild (semi-automatic)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MONOREPO_ROOT="$(cd "$COMPOSE_ROOT/.." && pwd)"
WDA_DIR="${WDA_DIR:-$MONOREPO_ROOT/WebDriverAgent}"

[[ -f "$COMPOSE_ROOT/devkit.env" ]] && set -a && source "$COMPOSE_ROOT/devkit.env" && set +a

TEAM="${IOS_DEVELOPMENT_TEAM:-}"
UDID="${IOS_UDID:-}"

if [[ ! -d "$WDA_DIR/WebDriverAgent.xcodeproj" ]]; then
  echo "→ cloning WebDriverAgent"
  "$MONOREPO_ROOT/iphone-ctl-skill/scripts/setup-wda.sh" --no-open
fi

if [[ -z "$TEAM" ]]; then
  cat <<'EOF'
IOS_DEVELOPMENT_TEAM not set — cannot xcodebuild automatically.

Option A (one-time manual):
  open WebDriverAgent/WebDriverAgent.xcodeproj
  → WebDriverAgentRunner → Signing → Team → Run on iPhone

Option B (automated next time):
  cp mob-compose/compose.env.example mob-compose/compose.env
  # set IOS_DEVELOPMENT_TEAM=YOUR_10_CHAR_TEAM_ID
  ./mob-compose/scripts/build-wda.sh

Find Team ID: Xcode → Settings → Accounts → Team → copy ID
EOF
  exit 1
fi

if [[ -z "$UDID" ]] && command -v iphone-ctl >/dev/null 2>&1; then
  UDID="$(ioskit devices 2>/dev/null | head -1 || true)"
fi
[[ -n "$UDID" ]] || { echo "error: set IOS_UDID or connect iPhone" >&2; exit 1; }

echo "→ xcodebuild WebDriverAgentRunner"
echo "  team=$TEAM udid=$UDID"

cd "$WDA_DIR"
xcodebuild \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "id=$UDID" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$TEAM" \
  build test 2>&1 | tail -20

echo ""
echo "→ if build succeeded, start proxy:"
echo "  ./mob-compose/scripts/start-ios-proxy.sh"
