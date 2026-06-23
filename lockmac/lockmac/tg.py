"""Self-contained Telegram remote control for lockmac (stdlib only).

Lets lockmac be driven from Telegram WITHOUT any host project:
  lockmac tg-setup   — store bot token + chat id (auto-fetches chat id)
  lockmac tg-test    — send a test message
  lockmac tg-listen  — long-poll getUpdates; /lock /unlock /status from the
                       configured chat run core.start/stop/status and reply.

Token/chat live in the lockmac config (~/.config/lockmac/config.json).

IMPORTANT: getUpdates allows ONE consumer per bot token. If you also run another
poller (e.g. mob-remote's relay) on the SAME token, they conflict (Telegram
409). Give lockmac its own bot, or don't run both pollers on one token.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from lockmac import core

_API = "https://api.telegram.org/bot{token}/{method}"
# Telegram command → action. /veil & /unveil drive the removable overlay;
# /lock is the REAL system lock (one-way: cannot be undone remotely).
_COMMANDS = {
    "/veil": "veil",
    "/unveil": "unveil",
    "/lock": "syslock",
    "/status": "status",
    "/deadman": "deadman",   # configure dead-man timers from Telegram
    "/purge": "purgecfg",    # manage purge dir list from Telegram
    "/help": "help",
}


def _api(token: str, method: str, params: dict | None = None, timeout: int = 35) -> dict:
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(url, data=data, timeout=timeout) as r:
        return json.load(r)


def parse_command(text: str) -> str | None:
    """Map a Telegram message to 'lock' | 'unlock' | 'status' | None (pure)."""
    if not text:
        return None
    token = text.strip().lower().split()[0].split("@")[0]
    return _COMMANDS.get(token)


def extract_chat_id(updates: dict) -> str | None:
    """Most-recent chat id from a getUpdates response (pure)."""
    for item in reversed(updates.get("result") or []):
        msg = item.get("message") or item.get("edited_message") or {}
        cid = (msg.get("chat") or {}).get("id")
        if cid is not None:
            return str(cid)
    return None


def set_tg(token: str, chat_id: str) -> None:
    cfg = core.load_config()
    cfg["tg_token"] = token
    cfg["tg_chat"] = str(chat_id)
    core.save_config(cfg)


def _creds() -> tuple[str, str]:
    cfg = core.load_config()
    return cfg.get("tg_token", ""), cfg.get("tg_chat", "")


def notify(text: str) -> bool:
    """Send a message to the configured chat. Best-effort (returns False if unset)."""
    token, chat = _creds()
    if not token or not chat:
        return False
    try:
        _api(token, "sendMessage", {"chat_id": chat, "text": text}, timeout=15)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def fetch_chat_id(token: str) -> str | None:
    """getUpdates → most recent chat id (send the bot a message first)."""
    try:
        return extract_chat_id(_api(token, "getUpdates", {}, timeout=15))
    except (urllib.error.URLError, OSError, ValueError):
        return None


# Commands shown in the Telegram "/" menu (registered via setMyCommands on listen).
_MENU = [
    ("veil", "开隐私遮罩（盖屏不锁机）"),
    ("unveil", "解除遮罩（启用2FA则 /unveil <6位码>）"),
    ("lock", "系统真锁屏（单向，需系统密码解）"),
    ("status", "查看状态"),
    ("deadman", "配置死手开关：<签到> <宽限> <动作> [失联]"),
    ("purge", "删除清单：/purge add|list|clear"),
    ("help", "命令详细说明"),
]

_HELP = """🔒 lockmac 命令帮助

【遮罩 / 锁定】
/veil — 开隐私遮罩（盖屏防窥，不锁机；远程操作/截图照常）
/unveil — 解除遮罩（启用 2FA 则 /unveil <6位码>）
/lock — 系统真锁屏（⚠ 单向：能远程锁，但只能到机器前输系统密码解）
/status — 查看状态（遮罩/密码/2FA/dead-man/绑定）

【死手开关 dead-man（无响应/失联→自动执行）】
/deadman — 查看当前配置
/deadman <签到秒> <宽限秒> <lock|veil|purge> [失联秒]
  · /deadman 0 0 purge 3600 → 连不上 TG 满 1 小时则删目录
  · /deadman 1800 600 lock → 每30min签到，10min不点则系统锁
  心跳来时点「✅ 我在」即重置计时

【删除清单（purge 动作使用）】
/purge list — 查看
/purge add <绝对路径> — 加入（/、家目录、系统目录自动拒绝）
/purge clear — 清空

仅响应绑定的 chat（fail-closed）。本地用 `lockmac <命令>` 同样可操作。"""


def set_my_commands() -> bool:
    """Register the '/' command menu for the bound bot."""
    token, _ = _creds()
    if not token:
        return False
    cmds = json.dumps([{"command": c, "description": d} for c, d in _MENU])
    try:
        _api(token, "setMyCommands", {"commands": cmds}, timeout=15)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _dispatch(action: str, args: list[str] | None = None) -> str:
    args = args or []
    if action == "veil":
        return core.start()[1]
    if action == "unveil":
        if core.totp_enabled():
            from lockmac import totp
            if not totp.verify_totp(core.get_totp_secret(), args[0] if args else ""):
                return "需二步验证码：/unveil <6位码>"
        return core.stop()[1]
    if action == "syslock":
        return core.system_lock()[1]
    if action == "deadman":
        return _cfg_deadman(args)
    if action == "purgecfg":
        return _cfg_purge(args)
    if action == "help":
        return _HELP
    return core.status()


def _cfg_deadman(args: list[str]) -> str:
    """/deadman [interval grace action [offline]] — show or set from Telegram."""
    if not args:
        iv, gr, ac, off = core.heartbeat_cfg()
        return (f"dead-man: 签到{iv}s/宽限{gr}s · 失联{off}s · 动作{ac}\n"
                "设置: /deadman <签到秒> <宽限秒> <lock|veil|purge> [失联秒]")
    try:
        iv = int(args[0])
        gr = int(args[1]) if len(args) > 1 else 300
        ac = args[2] if len(args) > 2 else "lock"
        off = int(args[3]) if len(args) > 3 else 0
        core.set_heartbeat(iv, gr, ac, off)
        iv, gr, ac, off = core.heartbeat_cfg()
        return f"✓ dead-man 已更新（即时生效）：签到{iv}s/宽限{gr}s · 失联{off}s · 动作{ac}"
    except ValueError:
        return "用法: /deadman <签到秒> <宽限秒> <lock|veil|purge> [失联秒]"


def _cfg_purge(args: list[str]) -> str:
    """/purge [add <path> | clear | list] — manage the purge dir list from Telegram."""
    sub = args[0].lower() if args else "list"
    if sub == "list" or not args:
        return f"删除清单：{core.get_purge_dirs() or '(空)'}"
    if sub == "clear":
        core.set_purge_dirs([])
        return "✓ 删除清单已清空"
    if sub == "add" and len(args) > 1:
        path = args[1]
        if not core.is_safe_purge_path(path):
            return f"拒绝：{path} 是危险/系统路径"
        dirs = core.get_purge_dirs()
        if path not in dirs:
            dirs.append(path)
            core.set_purge_dirs(dirs)
        return f"✓ 已加入：{path}\n当前：{core.get_purge_dirs()}"
    return "用法: /purge add <绝对路径> | list | clear"


def send_heartbeat() -> bool:
    """Send a check-in message with an inline '✅ 我在' button (dead-man switch)."""
    token, chat = _creds()
    if not token or not chat:
        return False
    markup = json.dumps({"inline_keyboard": [[{"text": "✅ 我在", "callback_data": "hb_ack"}]]})
    try:
        _api(token, "sendMessage", {
            "chat_id": chat,
            "text": "⏰ 心跳签到：在吗？未在宽限内点击将自动锁定。",
            "reply_markup": markup,
        }, timeout=15)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def answer_callback(cb_id: str, text: str = "已签到 ✓") -> None:
    token, _ = _creds()
    if not token or not cb_id:
        return
    try:
        _api(token, "answerCallbackQuery",
             {"callback_query_id": cb_id, "text": text}, timeout=10)
    except (urllib.error.URLError, OSError, ValueError):
        pass


def mark_heartbeat_acked(chat: str, message_id: int) -> None:
    """Edit the heartbeat message to '✅ 已签到' (removes the button) as feedback."""
    token, _ = _creds()
    if not token or not message_id:
        return
    try:
        _api(token, "editMessageText", {
            "chat_id": chat,
            "message_id": message_id,
            "text": "✅ 已签到，计时已重置。",
        }, timeout=10)
    except (urllib.error.URLError, OSError, ValueError):
        pass


def heartbeat_due(last_sent: float, now: float, interval: int) -> bool:
    """True if it's time to send the next heartbeat (pure)."""
    return interval > 0 and (now - last_sent) >= interval


def deadman_triggered(last_sent: float, last_ack: float, now: float, grace: int) -> bool:
    """True if a heartbeat is outstanding and no ack for `grace` since last ack.

    Measured from last_ack (not last_sent): heartbeats keep resending and would
    otherwise keep pushing the deadline forward, so it could never fire.
    last_sent > last_ack means there's an unacked heartbeat in flight.
    """
    return last_sent > last_ack and (now - last_ack) >= grace


def offline_triggered(last_online: float, now: float, offline: int) -> bool:
    """True if we've been unable to reach Telegram for >= offline seconds (pure)."""
    return offline > 0 and (now - last_online) >= offline


def _do_action(action: str) -> str:
    """Run the dead-man action locally (works offline). Returns a summary."""
    if action == "veil":
        return core.start()[1]
    if action == "purge":
        return core.purge_dirs_now()[1]
    return core.system_lock()[1]


def listen(poll_timeout: int = 10) -> int:
    """Long-poll getUpdates; act on /veil /unveil /lock /status, run the dead-man
    heartbeat, and honor '✅ 我在' button acks. Only the configured chat is
    honored (fail-closed). Runs until killed.
    """
    token, chat = _creds()
    if not token or not chat:
        print("tg-listen: no token/chat — run `lockmac tg-setup` first")
        return 1
    interval, grace, action, offline = core.heartbeat_cfg()
    parts_desc = []
    if interval > 0:
        parts_desc.append(f"heartbeat {interval}s/grace {grace}s")
    if offline > 0:
        parts_desc.append(f"offline {offline}s")
    extra = (f" · {' · '.join(parts_desc)}→{action}") if parts_desc else ""
    print(f"lockmac tg-listen: polling (chat={chat}){extra}")
    set_my_commands()  # register the "/" menu for the bot
    offset = 0
    last_sent = 0.0
    last_ack = time.time()
    last_online = time.time()
    while True:
        # re-read config each loop so /deadman changes from Telegram take effect live
        interval, grace, action, offline = core.heartbeat_cfg()
        online = True
        try:
            resp = _api(token, "getUpdates",
                        {"offset": offset, "timeout": poll_timeout},
                        timeout=poll_timeout + 10)
            last_online = time.time()  # reached Telegram successfully
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"getUpdates error: {exc}")
            online = False
            time.sleep(3)
            resp = {}
        for item in resp.get("result") or []:
            offset = item["update_id"] + 1
            msg = item.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) == str(chat):
                text = msg.get("text") or ""
                act = parse_command(text)
                if act:
                    notify(_dispatch(act, text.split()[1:]))
            cb = item.get("callback_query")
            if cb and str(((cb.get("message") or {}).get("chat") or {}).get("id")) == str(chat):
                if cb.get("data") == "hb_ack":
                    last_ack = time.time()
                    answer_callback(cb.get("id", ""))
                    mark_heartbeat_acked(chat, (cb.get("message") or {}).get("message_id"))
        now = time.time()
        # Trigger 1: heartbeat sent but not acked within grace (online, person AWOL)
        if interval > 0:
            if heartbeat_due(last_sent, now, interval) and send_heartbeat():
                last_sent = now
            if deadman_triggered(last_sent, last_ack, now, grace):
                out = _do_action(action)
                notify(f"⏰ 未响应心跳，已执行 {action}：{out}")  # best-effort if online
                last_ack = now  # fire once per missed beat
        # Trigger 2: lost contact with Telegram for too long (offline / removed)
        if offline_triggered(last_online, now, offline):
            _do_action(action)  # runs locally even with no network
            last_online = now   # fire once per offline window
