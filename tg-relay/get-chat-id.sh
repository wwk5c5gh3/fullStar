#!/usr/bin/env bash
# get-chat-id.sh — 配好 TELEGRAM_BOT_TOKEN 后，自动获取并写入 TELEGRAM_CHAT_ID
#
# 做的事：
#   1. 从 .env（或 --token）取 bot token
#   2. 若 tg-relay 正在轮询 getUpdates，临时停掉它（否则它会抢走你的消息）
#   3. 调 getUpdates 抓取你的 chat_id；抓不到就提示发 /start 并重试
#   4. 校验（纯数字、且不等于 bot 自身 id）后写入 .env
#   5. 如之前停了 relay，则自动恢复
#
# 用法：
#   ./tg-relay/get-chat-id.sh                 # 读 .env 里的 token，自动获取
#   ./tg-relay/get-chat-id.sh --token 123:ABC # 顺便写入该 token
#   ./tg-relay/get-chat-id.sh --test          # 写入后发一条测试消息
#   ./tg-relay/get-chat-id.sh --timeout 180   # 等待发送 /start 的轮询总时长（秒）
#   ./tg-relay/get-chat-id.sh --no-stop-relay # 不要自动停 relay（默认会停）
#   也可经 ./mob tg-chatid 调用

set -euo pipefail

# ── 确保以真正的 bash 运行（被 sh 调用时自动改用 bash）──
case "${BASH_VERSION:-}:${SHELLOPTS:-}" in
  :*)        exec bash "$0" "$@" ;;
  *:*posix*) exec bash "$0" "$@" ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"
MOB="$ROOT/mob"

TOKEN_ARG=""
DO_TEST=0
POLL_TIMEOUT=120
STOP_RELAY=1

# ── 输出辅助 ──
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi
info() { echo "  ${DIM}$*${RESET}"; }
ok()   { echo "  ${GREEN}✓ $*${RESET}"; }
warn() { echo "${YELLOW}⚠ $*${RESET}" >&2; }
die()  { echo "${RED}✗ $*${RESET}" >&2; exit 1; }

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) TOKEN_ARG="${2:-}"; shift 2 ;;
    --test) DO_TEST=1; shift ;;
    --timeout) POLL_TIMEOUT="${2:-120}"; shift 2 ;;
    --no-stop-relay) STOP_RELAY=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知参数: $1（用 -h 查看帮助）" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "未找到 python3"

# ── .env 准备 ──
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE" ]]; then cp "$ENV_EXAMPLE" "$ENV_FILE"; info "已从 .env.example 创建 .env"
  else : > "$ENV_FILE"; info "已创建空 .env"; fi
fi

write_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    if [[ "$(uname -s)" == "Darwin" ]]; then sed -i '' "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"; fi
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

# ── 取 token ──
TOKEN="$TOKEN_ARG"
if [[ -z "$TOKEN" ]]; then
  TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)"
fi
[[ -n "$TOKEN" ]] || die "缺少 token：先在 .env 配 TELEGRAM_BOT_TOKEN，或用 --token 传入"
[[ "$TOKEN" == *:* ]] || die "token 格式不对（应为 数字:字母，来自 @BotFather）"
if [[ -n "$TOKEN_ARG" ]]; then write_env "TELEGRAM_BOT_TOKEN" "$TOKEN"; ok "已写入 TELEGRAM_BOT_TOKEN"; fi

BOT_ID="${TOKEN%%:*}"

# ── getMe：取 bot 用户名，顺便验证 token 有效 ──
get_bot_username() {
  python3 - "$1" <<'PY'
import json, sys, urllib.request
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{sys.argv[1]}/getMe", timeout=15) as r:
        d = json.load(r)
    print(d.get("result", {}).get("username", "") if d.get("ok") else "")
except Exception:
    print("")
PY
}
BOT_USERNAME="$(get_bot_username "$TOKEN")"
[[ -n "$BOT_USERNAME" ]] || die "token 无效或无法连到 Telegram（请检查 token / 网络）"
BOT_LABEL="@$BOT_USERNAME"
echo "${BOLD}Telegram bot: ${BOT_LABEL}${RESET}  ${DIM}(id=$BOT_ID)${RESET}"

# ── 临时停掉 relay（它会抢走 getUpdates）──
RELAY_WAS_RUNNING=0
if pgrep -f 'run_tg_relay\.py' >/dev/null 2>&1; then
  RELAY_WAS_RUNNING=1
  if [[ "$STOP_RELAY" -eq 1 ]]; then
    info "检测到 tg-relay 正在运行 —— 临时停掉以释放 getUpdates"
    "$MOB" tg-stop >/dev/null 2>&1 || true
    sleep 1
  else
    warn "tg-relay 正在运行且 --no-stop-relay：它可能抢走你的 /start，导致抓不到"
  fi
fi

restore_relay() {
  if [[ "$RELAY_WAS_RUNNING" -eq 1 && "$STOP_RELAY" -eq 1 ]]; then
    info "恢复 tg-relay…"
    "$MOB" tg-restart >/dev/null 2>&1 || "$MOB" up >/dev/null 2>&1 || warn "自动恢复失败，请手动 ./mob up"
  fi
}
trap restore_relay EXIT

# ── 抓取 chat_id：取最近一条消息、纯数字、且 != bot id ──
fetch_chat_id() {
  python3 - "$1" "$BOT_ID" <<'PY'
import json, sys, urllib.request
token, bot_id = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15) as r:
        data = json.load(r)
except Exception:
    sys.exit(0)
if not data.get("ok"):
    sys.exit(0)
for item in reversed(data.get("result") or []):
    msg = item.get("message") or item.get("edited_message") or item.get("channel_post") or {}
    cid = (msg.get("chat") or {}).get("id")
    if cid is None:
        continue
    if str(cid) == str(bot_id):   # 跳过 bot 自身
        continue
    print(cid)
    break
PY
}

echo "${BOLD}▶ 自动获取 chat_id${RESET}"
CHAT_ID=""
deadline=$(( $(date +%s) + POLL_TIMEOUT ))
prompted=0
while :; do
  CHAT_ID="$(fetch_chat_id "$TOKEN")"
  if [[ -n "$CHAT_ID" ]]; then ok "已获取 chat_id: ${BOLD}$CHAT_ID${RESET}"; break; fi

  if [[ "$prompted" -eq 0 ]]; then
    echo ""
    echo "  ▶ 请在 Telegram 打开 ${BOLD}${BOT_LABEL}${RESET} 并发送 ${BOLD}/start${RESET}（或任意消息）"
    echo "    ${DIM}发完无需任何操作，脚本会自动检测（最多等 ${POLL_TIMEOUT}s）${RESET}"
    prompted=1
  fi

  if [[ "$(date +%s)" -ge "$deadline" ]]; then
    if [[ -t 0 ]]; then
      read -r -p "  仍未检测到。已发 /start？[回车]=继续等  s=放弃: " ans
      case "${ans// /}" in
        s|S) die "已放弃。确认消息发给的是 ${BOT_LABEL} 后重试" ;;
        *) deadline=$(( $(date +%s) + POLL_TIMEOUT )) ;;
      esac
    else
      die "超时未获取到 chat_id（请先给 ${BOT_LABEL} 发 /start）"
    fi
  fi
  sleep 2
done

# ── 校验 + 写入 ──
[[ "$CHAT_ID" =~ ^-?[0-9]+$ ]] || die "抓到的 chat_id 非纯数字：$CHAT_ID（异常，已中止）"
[[ "$CHAT_ID" != "$BOT_ID" ]] || die "chat_id 不能等于 bot 自身 id"
write_env "TELEGRAM_CHAT_ID" "$CHAT_ID"
ok "已写入 .env: TELEGRAM_CHAT_ID=$CHAT_ID"

# ── 可选测试 ──
if [[ "$DO_TEST" -eq 1 ]]; then
  echo "${BOLD}▶ 发送测试消息${RESET}"
  if command -v tg-notify >/dev/null 2>&1; then
    ( cd "$ROOT"; export TGKIT_ENV_FILE="$ENV_FILE"; set -a && . "$ENV_FILE" && set +a
      tg-notify send "✅ chat_id 配置成功（get-chat-id.sh）" ) \
      && ok "测试消息已发送，请查看 Telegram" \
      || warn "测试发送失败（chat_id 已写入，可单独排查 tg-notify）"
  else
    warn "未找到 tg-notify，跳过测试（chat_id 已写入）"
  fi
fi

echo ""
echo "${BOLD}${GREEN}✓ 完成${RESET}  ${DIM}chat_id=$CHAT_ID${RESET}"
[[ "$RELAY_WAS_RUNNING" -eq 1 ]] && info "relay 将自动恢复" || info "如需启动服务： ./mob up"
