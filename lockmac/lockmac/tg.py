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


def _dispatch(action: str, arg: str = "") -> str:
    if action == "veil":
        return core.start()[1]
    if action == "unveil":
        if core.totp_enabled():
            from lockmac import totp
            if not totp.verify_totp(core.get_totp_secret(), arg):
                return "需二步验证码：/unveil <6位码>"
        return core.stop()[1]
    if action == "syslock":
        return core.system_lock()[1]
    return core.status()


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


def heartbeat_due(last_sent: float, now: float, interval: int) -> bool:
    """True if it's time to send the next heartbeat (pure)."""
    return interval > 0 and (now - last_sent) >= interval


def deadman_triggered(last_sent: float, last_ack: float, now: float, grace: int) -> bool:
    """True if a sent heartbeat went unacked past the grace window (pure)."""
    return last_sent > 0 and last_ack < last_sent and (now - last_sent) >= grace


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
    offset = 0
    last_sent = 0.0
    last_ack = time.time()
    last_online = time.time()
    while True:
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
                    parts = text.split()
                    arg = parts[1] if len(parts) > 1 else ""
                    notify(_dispatch(act, arg))
            cb = item.get("callback_query")
            if cb and str(((cb.get("message") or {}).get("chat") or {}).get("id")) == str(chat):
                if cb.get("data") == "hb_ack":
                    last_ack = time.time()
                    answer_callback(cb.get("id", ""))
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
