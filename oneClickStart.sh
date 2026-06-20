#!/usr/bin/env bash
# oneClickStart.sh — 一键开启 mob-remote 全部服务
#
# 启动：
#   • tg-relay      —— Telegram 收令 → 注入 iTerm（TG → iTerm）
#   • iterm-monitor —— 抓取 iTerm 输出 → 回传 Telegram（iTerm → TG）
#   （二者即 ./mob up 的内容）
#
# 用法:
#   ./oneClickStart.sh          # 开启 TG 全栈（relay + monitor）
#   ./oneClickStart.sh --ios    # 额外启动 iproxy（iOS WDA 需要）
#   ./oneClickStart.sh --watch  # 开启后监视代码/.env 变化，自动重启加载（开发用）
#   ./oneClickStart.sh --stop   # 关闭全部服务（= ./mob down）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi
step() { echo "${BOLD}${GREEN}▸ $*${RESET}"; }
warn() { echo "${YELLOW}⚠ $*${RESET}" >&2; }

WITH_IOS=0
WATCH=0
for arg in "$@"; do
  case "$arg" in
    --ios) WITH_IOS=1 ;;
    --watch) WATCH=1 ;;
    --stop|down) step "关闭全部服务"; exec "$ROOT/mob" down ;;
    -h|--help) awk 'NR>1 && /^#/{sub(/^# ?/,"");print;next} NR>1{exit}' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) warn "未知参数: $arg（忽略）" ;;
  esac
done

# 监视的源文件/配置签名（mtime+名称）。变化即触发自动重启。
WATCH_INTERVAL="${WATCH_INTERVAL:-2}"
watch_signature() {
  {
    find "$ROOT/tg-relay" "$ROOT/term-bridge" -type f \
         \( -name '*.py' -o -name '*.sh' \) -exec stat -f '%m %N' {} + 2>/dev/null
    stat -f '%m %N' "$ROOT/.env" 2>/dev/null || true
  } | sort
}

run_watch() {
  step "监视模式开启：tg-relay/、term-bridge/ 的 *.py/*.sh 及 .env 变化将自动重启（Ctrl-C 退出监视，服务继续后台运行）"
  trap 'echo; echo "${DIM}已退出监视；服务仍在后台。停止请： ./oneClickStart.sh --stop${RESET}"; exit 0' INT TERM
  local sig
  sig="$(watch_signature)"
  while true; do
    sleep "$WATCH_INTERVAL"
    local new
    new="$(watch_signature)"
    if [[ "$new" != "$sig" ]]; then
      echo
      step "检测到变化 → 自动重启加载（$(date '+%H:%M:%S')）"
      "$ROOT/mob" up >/dev/null 2>&1 && echo "  ${GREEN}✓ 已重载${RESET}" || warn "重载失败，请看日志"
      sig="$(watch_signature)"
    fi
  done
}

# 前置检查
[[ -f "$ROOT/.env" ]] || warn ".env 不存在 —— 先运行 ./oneClickSetup.sh 或 ./mob tg-setup"
command -v python3 >/dev/null 2>&1 || { echo "${RED}✗ 未找到 python3${RESET}" >&2; exit 1; }

echo "${BOLD}mob-remote · 一键开启服务${RESET}"
echo

# 1. Telegram 全栈（relay + monitor）
step "启动 TG 全栈（tg-relay + iterm-monitor）"
"$ROOT/mob" up

# 2. 可选：iOS iproxy（WDA）
if [[ "$WITH_IOS" -eq 1 ]]; then
  echo
  step "启动 iproxy（iOS WDA）"
  "$ROOT/mob" ios-start || warn "iproxy 启动失败（检查 USB 连接 / IOS_UDID）"
fi

# 3. 状态汇总
echo
step "服务状态"
"$ROOT/mob" tg-status || true

echo
echo "${BOLD}${GREEN}✓ 服务已开启${RESET}"
cat <<EOF
${DIM}从 Telegram 发： [t1] 列出当前目录   → 注入 iTerm w1/t1，约 45s 后回传${RESET}
${DIM}查看状态： ./mob tg-status   关闭： ./oneClickStart.sh --stop（= ./mob down）${RESET}
EOF

# 4. 可选：监视自动重载（阻塞，直到 Ctrl-C）
if [[ "$WATCH" -eq 1 ]]; then
  echo
  run_watch
fi
