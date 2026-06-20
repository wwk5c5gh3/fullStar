#!/usr/bin/env bash
# Claude Code Stop / Notification hook → Telegram ping.
#
# Fires when a Claude Code session pauses: Stop = it finished and is waiting for
# you; Notification = it needs input/permission. So you know from your phone when
# it's your turn to act. Reads the hook JSON on stdin; sends via tg-notify using
# the bot token + chat id from this repo's .env.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ENV_FILE="${TGKIT_ENV_FILE:-$SCRIPT_DIR/../.env}"
if [ -f "$ENV_FILE" ]; then
  TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
  TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"'')"
  export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
fi

payload="$(cat)"
read -r EVENT DIR NOTE <<EOF
$(printf '%s' "$payload" | /usr/bin/python3 -c '
import sys, json, os
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
event = d.get("hook_event_name", "")
cwd = os.path.basename((d.get("cwd") or "").rstrip("/")) or "?"
note = (d.get("message") or "").replace("\n", " ")[:120]
print(event, cwd, note)
' 2>/dev/null)
EOF

case "$EVENT" in
  Stop|SubagentStop) MSG="✅ Claude 停了 @ [$DIR] — 该你回复了" ;;
  Notification)      MSG="🔔 Claude 需要你 @ [$DIR]: ${NOTE:-等待输入}" ;;
  *)                 MSG="Claude 事件 ${EVENT:-?} @ [$DIR]" ;;
esac

tg-notify send --text "$MSG" >/dev/null 2>&1 || true
exit 0
