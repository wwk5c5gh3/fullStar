#!/usr/bin/env python3
"""Capture iTerm2 first window and send to Telegram via tg_notify."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_path = ROOT / ".env"
    if os.environ.get("TGKIT_ENV_FILE"):
        env_path = Path(os.environ["TGKIT_ENV_FILE"])
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def _chat_id() -> str | None:
    raw = (
        os.environ.get("TG_ITERM_MONITOR_CHAT_ID", "").strip()
        or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    )
    return raw or None


def capture_and_send(*, caption: str | None = None) -> tuple[int, str]:
    if sys.platform != "darwin":
        return 1, "iTerm screenshot requires macOS"

    _load_env()
    chat = _chat_id()
    if not chat:
        return 1, "TELEGRAM_CHAT_ID not set"

    # iTerm2's launch/scripting name is "iTerm" but its System Events *process*
    # name is "iTerm2" — window lookup needs the process name.
    app = os.environ.get("TG_ITERM_SCREENSHOT_APP", "iTerm").strip() or "iTerm"
    proc = os.environ.get("TG_ITERM_SCREENSHOT_PROCESS", "iTerm2").strip() or "iTerm2"
    wait = os.environ.get("TG_ITERM_SCREENSHOT_WAIT", "0.3").strip() or "0.3"
    cap = caption or os.environ.get("TG_ITERM_SCREENSHOT_CAPTION", "iTerm").strip() or "iTerm"

    env = {**os.environ}
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        env["TELEGRAM_BOT_TOKEN"] = os.environ["TELEGRAM_BOT_TOKEN"]

    cmd = [
        "tg-notify",
        "screenshot",
        "--app",
        app,
        "--process",
        proc,
        "--wait",
        wait,
        "--window-index",
        "1",
        "--chat-id",
        chat,
        "--caption",
        cap,
    ]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode == 0:
        return 0, out or "screenshot sent"
    return r.returncode, out or "screenshot failed"


def main() -> int:
    parser = argparse.ArgumentParser(description="iTerm window screenshot -> Telegram")
    parser.add_argument("--caption", help="Telegram photo caption")
    args = parser.parse_args()
    code, msg = capture_and_send(caption=args.caption)
    print(msg)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
