#!/usr/bin/env python3
"""Shared helper for translating macOS TCC (Automation/Accessibility) failures.

When AppleScript injection is blocked because macOS has not granted the host
process Automation or Accessibility permission, ``osascript`` returns opaque
Apple error numbers (e.g. ``-1743`` "not authorized to send Apple events",
``-25211`` assistive-access denied). These helpers detect those failures and
append a friendly, actionable hint pointing the user at System Settings.

Pure, side-effect-free helpers (except :func:`probe_automation_permission`,
which intentionally shells out to ``osascript`` to trigger the real TCC prompt).
"""
from __future__ import annotations

import subprocess
import sys

# User-facing hint (中文): both 自动化 (Automation) and 辅助功能 (Accessibility).
ACCESS_HINT: str = (
    "需要授权宿主进程（Terminal / iTerm / Claude Code / Python）："
    "系统设置 → 隐私与安全性 → 辅助功能（发送按键），"
    "以及 自动化 中允许控制 “System Events” 与目标终端 App。"
)

# Apple error numbers raised by osascript on a TCC / authorization failure.
_TCC_ERROR_CODES: tuple[str, ...] = (
    "-1743",   # errAEEventNotPermitted: not authorized to send Apple events
    "-25211",  # accessibility / assistive access denied
)

# Lowercased textual fragments that also indicate an authorization failure.
_TCC_TEXT_PATTERNS: tuple[str, ...] = (
    "not authoriz",          # "not authorized to send Apple events"
    "not allowed to send",   # "is not allowed to send keystrokes"
    "assistive access",      # "assistive access" / "enable assistive access"
)

# Chinese fragments preserved from the original Terminal.app detection.
_TCC_CN_PATTERNS: tuple[str, ...] = (
    "辅助",   # 辅助功能 (Accessibility)
    "授权",   # authorization
)


def needs_access_hint(text: str) -> bool:
    """Return True when *text* indicates a macOS TCC/authorization failure."""
    if not text:
        return False
    low = text.lower()
    if any(code in text for code in _TCC_ERROR_CODES):
        return True
    if any(pattern in low for pattern in _TCC_TEXT_PATTERNS):
        return True
    return any(pattern in text for pattern in _TCC_CN_PATTERNS)


def with_access_hint(text: str) -> str:
    """Append :data:`ACCESS_HINT` to *text* on a TCC failure, else return as-is.

    Idempotent-safe: if the hint is already present, *text* is returned
    unchanged so it is never appended twice.
    """
    if not needs_access_hint(text):
        return text
    if ACCESS_HINT in text:
        return text
    return f"{text}\n\n{ACCESS_HINT}"


def probe_automation_permission(app: str) -> tuple[bool, str]:
    """Probe whether the host may drive *app* via AppleScript Automation.

    Runs a real, minimal ``osascript`` command so macOS surfaces the TCC prompt
    (a dry-run that only prints the script would not). Returns ``(ok, message)``:

    - ``(True, "ok")`` when the probe succeeds.
    - ``(False, ACCESS_HINT)`` when blocked by a TCC/authorization failure.
    - ``(False, <raw error>)`` for any other osascript failure.
    - ``(False, "needs macOS")`` on non-darwin platforms (no osascript / TCC).
    """
    if sys.platform != "darwin":
        return False, "needs macOS"

    script = f'tell application "{app}" to return name'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"osascript unavailable: {exc}"

    out = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode == 0:
        return True, out or "ok"
    if needs_access_hint(out):
        return False, ACCESS_HINT
    return False, out or "osascript failed"
