"""Sanitize inbound Telegram text before it is typed into a live terminal.

The relay injects message text into a terminal running an agent with bypassed
permissions. Two cheap, high-value guards before injection:

  1. Strip C0 control characters (U+0000-001F) and DEL (U+007F), which could
     otherwise inject Ctrl-C / Ctrl-D / ESC sequences or a raw NUL into the
     terminal. Tab and newline are preserved (legitimate in pasted text).
  2. Cap the length so a single message can't dump an unbounded blob into the
     session. Configurable via TG_RELAY_MAX_INJECT_CHARS (default 2000).
"""
from __future__ import annotations

import os

DEFAULT_MAX_CHARS = 2000

# Control chars to drop: C0 range + DEL, EXCEPT tab (\x09) and newline (\x0a).
_ALLOWED_CONTROL = {"\t", "\n"}
_STRIP = {chr(c) for c in range(0x20)} | {"\x7f"}
_STRIP -= _ALLOWED_CONTROL


def strip_control_chars(text: str) -> str:
    """Remove C0/DEL control characters except tab and newline."""
    return "".join(ch for ch in text if ch not in _STRIP)


def max_inject_chars() -> int:
    """Length cap from TG_RELAY_MAX_INJECT_CHARS (default 2000, min 1)."""
    raw = os.environ.get("TG_RELAY_MAX_INJECT_CHARS", "").strip()
    if not raw:
        return DEFAULT_MAX_CHARS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CHARS


def sanitize_injection(text: str, max_chars: int | None = None) -> tuple[str, bool]:
    """Return (clean_text, was_truncated).

    Strips control chars then truncates to max_chars. `was_truncated` lets the
    caller surface a notice to the user instead of silently dropping input.
    """
    limit = max_chars if max_chars is not None else max_inject_chars()
    clean = strip_control_chars(text)
    if len(clean) > limit:
        return clean[:limit], True
    return clean, False
