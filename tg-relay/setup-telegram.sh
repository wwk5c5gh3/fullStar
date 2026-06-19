#!/usr/bin/env bash
# mobile-agent — one-click Telegram (.env) setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

TOKEN=""
CHAT_ID=""
RUN_TEST=0
INTERACTIVE=1
FETCH_CHAT_ID=1          # 默认自动抓取 chat_id；用 --no-fetch-chat-id 关闭
INSTALL_RELAY_DEPS=1

usage() {
  cat <<'EOF'
Usage: setup-telegram.sh [options]

One-click configure TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in mobile-agent/.env

Options:
  --token TOKEN          Bot token from @BotFather (skip prompt)
  --chat-id ID           Your Telegram chat id (skip auto-fetch)
  --fetch-chat-id        Auto-fetch chat_id via getUpdates (default; kept for compat)
  --no-fetch-chat-id     Disable auto-fetch; prompt to type chat_id manually
  --test                 Send a test message after setup
  --non-interactive      Fail if token missing instead of prompting
  --no-relay-deps        Skip pip install python-telegram-bot (for tg-start)
  -h, --help             Show help

By default, after the token is set this script auto-fetches your chat_id via
getUpdates. If the bot has no messages yet, it tells you to send /start and
retries — you never need to paste the chat_id manually.

Examples:
  ./tg-relay/setup-telegram.sh
  ./tg-relay/setup-telegram.sh --test
  ./tg-relay/setup-telegram.sh --token "123:ABC" --chat-id 123456789 --test
  ./tg-relay/setup-telegram.sh --fetch-chat-id --test

Also available via: ./mob tg-setup [options]
EOF
}

write_env() {
  local key="$1" val="$2" file="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' "s|^${key}=.*|${key}=${val}|" "$file"
    else
      sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    fi
  else
    echo "${key}=${val}" >> "$file"
  fi
}

get_bot_username() {
  local token="$1"
  python3 - "$token" <<'PY'
import json, sys, urllib.request
token = sys.argv[1]
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
        data = json.load(r)
    print(data.get("result", {}).get("username", "") if data.get("ok") else "")
except Exception:
    print("")
PY
}

fetch_chat_id() {
  local token="$1"
  python3 - "$token" <<'PY'
import json, sys, urllib.request
token = sys.argv[1]
url = f"https://api.telegram.org/bot{token}/getUpdates"
try:
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.load(r)
except Exception as e:
    print(f"error: cannot reach Telegram API: {e}", file=sys.stderr)
    sys.exit(1)
if not data.get("ok"):
    print(f"error: {data}", file=sys.stderr)
    sys.exit(1)
results = data.get("result") or []
ids = []
for item in reversed(results):
    msg = item.get("message") or item.get("edited_message") or {}
    chat = msg.get("chat") or {}
    cid = chat.get("id")
    if cid is not None and cid not in ids:
        ids.append(cid)
if not ids:
    print("error: no messages found. Open Telegram, find your bot, send /start, then re-run --fetch-chat-id", file=sys.stderr)
    sys.exit(1)
print(ids[0])
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) TOKEN="${2:-}"; shift 2 ;;
    --chat-id) CHAT_ID="${2:-}"; shift 2 ;;
    --fetch-chat-id) FETCH_CHAT_ID=1; shift ;;
    --no-fetch-chat-id) FETCH_CHAT_ID=0; shift ;;
    --test) RUN_TEST=1; shift ;;
    --non-interactive) INTERACTIVE=0; shift ;;
    --no-relay-deps) INSTALL_RELAY_DEPS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

echo "╔══════════════════════════════════════════╗"
echo "║  mobile-agent — Telegram setup           ║"
echo "╚══════════════════════════════════════════╝"
echo "root : $ROOT"
echo ""

# --- 1. Python ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 required" >&2
  exit 1
fi
echo "▶ python3 $(python3 --version 2>&1)"

# --- 2. Install tg-notify ---
echo "▶ Install tg-notify"
if [[ -f "$ROOT/tg-notify/pyproject.toml" ]]; then
  python3 -m pip install -e "$ROOT/tg-notify[dotenv]" -q
else
  python3 -m pip install "tg-notify[dotenv]" -q
fi

if [[ "$INSTALL_RELAY_DEPS" -eq 1 ]]; then
  echo "▶ Install python-telegram-bot (for ./mob tg-start)"
  python3 -m pip install "python-telegram-bot>=20,<22" -q 2>/dev/null \
    || python3 -m pip install "python-telegram-bot>=12.8,<13" -q
fi

# --- 3. .env file ---
echo "▶ Configure .env"
if [[ -f "$ENV_FILE" ]]; then
  echo "  existing: $ENV_FILE"
else
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "  created from .env.example"
fi

# shellcheck disable=SC1090
set -a && source "$ENV_FILE" && set +a
TOKEN="${TOKEN:-${TELEGRAM_BOT_TOKEN:-}}"
CHAT_ID="${CHAT_ID:-${TELEGRAM_CHAT_ID:-}}"

if [[ -z "$TOKEN" && "$INTERACTIVE" -eq 1 ]]; then
  echo ""
  echo "  Get token: Telegram → @BotFather → /newbot"
  read -r -p "  TELEGRAM_BOT_TOKEN: " TOKEN
fi

if [[ -z "$TOKEN" ]]; then
  echo "error: TELEGRAM_BOT_TOKEN is required" >&2
  echo "  edit $ENV_FILE or re-run with --token" >&2
  exit 1
fi

write_env "TELEGRAM_BOT_TOKEN" "$TOKEN" "$ENV_FILE"

# bot 自身 id = token 冒号前部分；用于识别"把 chat_id 误填成 bot 自己"的情况
BOT_ID="${TOKEN%%:*}"
BOT_USERNAME="$(get_bot_username "$TOKEN")"
BOT_LABEL="${BOT_USERNAME:+@$BOT_USERNAME}"; BOT_LABEL="${BOT_LABEL:-你的 bot}"

# 已有的 chat_id 若等于 bot 自身 id（无法给自己发消息），视为无效，强制重新获取
if [[ -n "$CHAT_ID" && "$CHAT_ID" == "$BOT_ID" ]]; then
  echo "  ! 现有 TELEGRAM_CHAT_ID 等于 bot 自身 id（bot 不能给自己发消息），将重新获取"
  CHAT_ID=""
fi

# 自动获取 chat_id（默认开启）：抓不到就提示发 /start 并重试，无需手动粘贴
if [[ -z "$CHAT_ID" && "$FETCH_CHAT_ID" -eq 1 ]]; then
  echo "▶ 自动获取 chat_id"
  while :; do
    CHAT_ID="$(fetch_chat_id "$TOKEN" 2>/dev/null)" || true
    if [[ -n "$CHAT_ID" ]]; then
      echo "  ✓ 已获取 chat_id: $CHAT_ID"
      break
    fi
    if [[ "$INTERACTIVE" -ne 1 ]]; then
      echo "  ! 未获取到 chat_id —— 请先在 Telegram 给 $BOT_LABEL 发送 /start，再重跑" >&2
      break
    fi
    echo ""
    echo "  ▶ 请在 Telegram 打开 $BOT_LABEL 并发送 /start（或任意消息）"
    echo "    然后直接按【回车】即可自动获取 —— 不要粘贴 token！"
    read -r -p "     [回车]=自动获取  s=跳过  (chat_id 是纯数字，一般无需手填): " ans
    ans="${ans// /}"
    case "$ans" in
      s|S|skip) CHAT_ID=""; break ;;
      "")       : ;;                                   # 回车 → 重试
      *:*)      echo "  ✗ 你粘贴的是 bot token，不是 chat_id。请改为给 $BOT_LABEL 发 /start 后按回车。" ;;
      *)
        if [[ "$ans" =~ ^-?[0-9]+$ ]]; then
          CHAT_ID="$ans"; echo "  使用手动输入: $CHAT_ID"; break
        else
          echo "  ✗ chat_id 必须是纯数字（群组为负数）。请重试或按回车自动获取。"
        fi
        ;;
    esac
  done
fi

# 关闭了自动获取（--no-fetch-chat-id）时，回退到手动输入
if [[ -z "$CHAT_ID" && "$FETCH_CHAT_ID" -ne 1 && "$INTERACTIVE" -eq 1 ]]; then
  echo ""
  echo "  Get chat_id: message your bot, then visit:"
  echo "  https://api.telegram.org/bot<TOKEN>/getUpdates"
  read -r -p "  TELEGRAM_CHAT_ID (Enter to skip): " CHAT_ID
fi

# 最终校验：chat_id 必须是纯数字、且不等于 bot 自身 id（拒绝误填 token / 非数字）
if [[ -n "$CHAT_ID" ]]; then
  if [[ ! "$CHAT_ID" =~ ^-?[0-9]+$ ]]; then
    echo "  ✗ chat_id 非法（应为纯数字，疑似误填 token）—— 已忽略，不写入" >&2
    CHAT_ID=""
  elif [[ "$CHAT_ID" == "$BOT_ID" ]]; then
    echo "  ✗ chat_id 不能等于 bot 自身 id（$BOT_ID）—— 已忽略，不写入" >&2
    CHAT_ID=""
  fi
fi

if [[ -n "$CHAT_ID" ]]; then
  write_env "TELEGRAM_CHAT_ID" "$CHAT_ID" "$ENV_FILE"
fi

echo "  saved: $ENV_FILE"

# --- 4. Verify ---
echo "▶ Verify"
export TGKIT_ENV_FILE="$ENV_FILE"
if command -v tg-notify >/dev/null 2>&1; then
  echo "  ✓ tgkit: $(command -v tg-notify)"
else
  echo "  ✗ tg-notify not on PATH" >&2
  exit 1
fi

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  :
elif [[ -f "$ENV_FILE" ]]; then
  set -a && source "$ENV_FILE" && set +a
fi

if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "  ! TELEGRAM_CHAT_ID not set — sending photos may fail; tg-relay still works"
else
  echo "  ✓ TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}"
fi

# --- 5. Test send ---
if [[ "$RUN_TEST" -eq 1 ]]; then
  if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    echo "  ! skip test send (no chat_id)"
  else
    echo "▶ Send test message"
    (
      cd "$ROOT"
      export TGKIT_ENV_FILE="$ENV_FILE"
      set -a && source "$ENV_FILE" && set +a
      tg-notify send "mobile-agent Telegram setup OK ✓"
    )
    echo "  check your Telegram for the test message"
  fi
fi

cat <<EOF

╔══════════════════════════════════════════╗
║  Telegram setup complete                 ║
╚══════════════════════════════════════════╝

Config file : $ENV_FILE

Next steps:
  ./mob check              # verify environment
  ./mob tg-start           # start command bot (receive /shot /tap)
  tg-notify send "hello"            # send a message manually
  ./mob shot-android       # screenshot → Telegram (needs device)

Docs: docs/TELEGRAM_SETUP.md

EOF
