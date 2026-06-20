"""Detect interactive arrow-select prompts and decide when to auto-default.

Pure helpers for iterm-monitor: detect Claude Code's AskUserQuestion / yes-no
widget (a `❯ … Enter to select` list) and decide when a stuck menu should be
auto-resolved by pressing Enter. The monitor loop owns the side effects.
"""
from __future__ import annotations

import re

_CURSOR = "❯"
_OPTION_RE = re.compile(r"^\s*(?:❯\s*)?(\d+)\.\s+(.+?)\s*$")


def extract_select_options(capture: str) -> list[tuple[int, str]]:
    """Parse a select menu's options as [(number, label)].

    Returns the last contiguous block of `N. label` lines that starts at 1 (the
    menu is at the bottom of the capture), so stray numbered lines higher up in
    the scrollback don't leak in. Empty when no menu-like block is found.
    """
    groups: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for line in capture.splitlines():
        m = _OPTION_RE.match(line)
        if m:
            cur.append((int(m.group(1)), m.group(2).strip()))
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    for group in reversed(groups):
        if group and group[0][0] == 1:
            return group
    return []


def detect_select_prompt(capture: str) -> bool:
    """True when the capture shows an arrow-select menu awaiting a choice."""
    if not capture:
        return False
    low = capture.lower()
    has_footer = "enter to select" in low and (
        "to navigate" in low or "↑" in capture or "↓" in capture
    )
    return has_footer and _CURSOR in capture


def should_auto_default(
    *,
    is_prompt: bool,
    stable_elapsed: float,
    threshold: float,
    stable_key: str,
    last_fired_key: str,
) -> bool:
    """Fire iff enabled, a prompt is shown, it has been stable past the
    threshold, and we have not already fired for this exact screen."""
    if threshold <= 0 or not is_prompt:
        return False
    if stable_elapsed < threshold:
        return False
    return stable_key != last_fired_key
