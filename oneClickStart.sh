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
for arg in "$@"; do
  case "$arg" in
    --ios) WITH_IOS=1 ;;
    --stop|down) step "关闭全部服务"; exec "$ROOT/mob" down ;;
    -h|--help) awk 'NR>1 && /^#/{sub(/^# ?/,"");print;next} NR>1{exit}' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) warn "未知参数: $arg（忽略）" ;;
  esac
done

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
