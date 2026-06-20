# term-bridge/target_default.py
"""Persistent default forwarding target for Telegram routing.

The chosen iTerm tab is stored in inbox/target-default.json and read fresh on
every message / monitor poll, so /tab takes effect without a restart. Corrupt
or missing state is treated as "unset" and callers fall back to resolve_target()
(the .env default). current_target() is the single source of truth shared by the
routing layer and the monitor daemon.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from iterm_target import ItermTarget, resolve_target

ROOT = Path(__file__).resolve().parent.parent


def default_path() -> Path:
    return ROOT / "inbox" / "target-default.json"


def parse_state(raw: str) -> ItermTarget | None:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    tab = data.get("tab")
    if not isinstance(tab, int) or isinstance(tab, bool) or tab < 1:
        return None
    window = data.get("window")
    if window is not None and (not isinstance(window, int) or isinstance(window, bool) or window < 1):
        return None
    session_id = data.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        return None
    return ItermTarget(window=window, tab=tab, session_id=session_id or None)


def dump_state(t: ItermTarget) -> str:
    data: dict[str, object] = {"window": t.window, "tab": t.tab}
    if t.session_id:
        data["session_id"] = t.session_id
    return json.dumps(data)


def read_default(path: Path | None = None) -> ItermTarget | None:
    p = path or default_path()
    try:
        raw = p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    return parse_state(raw)


def write_default(
    window: int | None, tab: int, session_id: str | None = None, path: Path | None = None
) -> ItermTarget:
    t = ItermTarget(window=window, tab=tab, session_id=session_id or None)
    p = path or default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(dump_state(t), encoding="utf-8")
    os.replace(tmp, p)
    return t


def clear_default(path: Path | None = None) -> None:
    p = path or default_path()
    try:
        p.unlink()
    except FileNotFoundError:
        pass


def current_target() -> ItermTarget:
    d = read_default()
    if d is None:
        return resolve_target()
    if d.session_id:
        # Anchor on the stable id: relocate to the session's *current* position so
        # the monitor follows it across tab reorders; if it's gone, use .env.
        try:
            from iterm_route import list_tabs  # lazy: avoid import cycle
            code, tabs = list_tabs()
        except Exception:
            return d
        if code == 0 and tabs:
            for t in tabs:
                if t.session_id and t.session_id == d.session_id:
                    return ItermTarget(window=t.window, tab=t.tab, session_id=t.session_id)
            return resolve_target()
    return d
