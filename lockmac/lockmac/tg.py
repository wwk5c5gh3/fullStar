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
# action keyword → which command; the only texts lockmac's listener acts on.
_COMMANDS = {"/lock": "lock", "/unlock": "unlock", "/status": "status"}


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


def _dispatch(action: str) -> str:
    if action == "lock":
        return core.start()[1]
    if action == "unlock":
        return core.stop()[1]
    return core.status()


def listen(poll_timeout: int = 25) -> int:
    """Long-poll getUpdates; act on /lock /unlock /status from the saved chat.

    Only the configured chat id is honored (fail-closed). Runs until killed.
    """
    token, chat = _creds()
    if not token or not chat:
        print("tg-listen: no token/chat — run `lockmac tg-setup` first")
        return 1
    print(f"lockmac tg-listen: polling (chat={chat})")
    offset = 0
    while True:
        try:
            resp = _api(token, "getUpdates",
                        {"offset": offset, "timeout": poll_timeout},
                        timeout=poll_timeout + 10)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"getUpdates error: {exc}")
            time.sleep(3)
            continue
        for item in resp.get("result") or []:
            offset = item["update_id"] + 1
            msg = item.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) != str(chat):
                continue  # fail-closed: ignore everyone but the configured chat
            action = parse_command(msg.get("text") or "")
            if action:
                notify(_dispatch(action))
