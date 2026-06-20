"""List open Terminal.app windows/tabs via AppleScript.

Mirrors iterm_tabs.list_targets so the routing layer can enumerate whichever
backend TG_TERM_BACKEND selects. Terminal.app addresses each terminal as
`tab T of window W`; a common layout is several windows each with one tab. The
AppleScript emits `window|||tab|||tty|||process|||winName` per line, where
`window` is the window's *stable id* (not its z-order position, which drifts as
focus changes). winName is the window's full title bar (cwd + custom title +
ttys + shortcut); _clean_window_name keeps the cwd + title as a stable,
identifying name. The tty (e.g. /dev/ttys003) is the stable per-session id,
exposed as session_id.
"""
from __future__ import annotations

import re
import subprocess
import sys

LIST_SCRIPT = r"""
set out to ""
tell application "Terminal"
    set wCount to count of windows
    repeat with w from 1 to wCount
        set theWin to window w
        set wid to id of theWin
        set tCount to count of tabs of theWin
        repeat with t from 1 to tCount
            set theTab to tab t of theWin
            set winName to ""
            try
                set winName to name of theWin
            end try
            set proc to ""
            try
                set pl to processes of theTab
                if (count of pl) > 0 then set proc to item -1 of pl
            end try
            set ttyStr to ""
            try
                set ttyStr to tty of theTab
            end try
            set out to out & wid & "|||" & t & "|||" & ttyStr & "|||" & proc & "|||" & winName & linefeed
        end repeat
    end repeat
end tell
return out
"""


_TTY_SEG = re.compile(r"^/?dev/ttys?\w*\d|^ttys?\w*\d", re.I)
_SHORTCUT_SEG = re.compile(r"^[⌥⌘⌃⇧]")
_SIZE_SEG = re.compile(r"^\d+\s*[×x]\s*\d+$")  # window size, e.g. 159×47


def _clean_window_name(win_name: str) -> str:
    """Window title bar → '<cwd> · <title>', dropping the ttys/shortcut tail.

    Terminal.app names windows '<cwd> — <custom title> — ttysNNN — ⌥⌘N'. The cwd
    is a stable, identifying anchor (the volatile custom title alone is not), so
    keep the meaningful segments and drop the tty + keyboard-shortcut noise.
    """
    segs = [s.strip() for s in win_name.split(" — ") if s.strip()]
    kept = [
        s for s in segs
        if not _TTY_SEG.match(s) and not _SHORTCUT_SEG.match(s) and not _SIZE_SEG.match(s)
    ]
    return " · ".join(kept)


def _parse(stdout: str) -> list[dict]:
    # Layout: window|||tab|||tty|||process|||winName  (winName last)
    rows: list[dict] = []
    for line in (stdout or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("|||", 4)
        if len(parts) < 5:
            continue
        try:
            window = int(parts[0])
            tab = int(parts[1])
        except ValueError:
            continue
        tty = parts[2].strip()
        proc = parts[3].strip()
        name = _clean_window_name(parts[4].strip()) or proc or f"tab{tab}"
        rows.append(
            {
                "window": window,
                "tab": tab,
                "name": name,
                "sessions": 1,
                "session_id": tty or None,
            }
        )
    return rows


def list_targets() -> tuple[int, list[dict]]:
    if sys.platform != "darwin":
        return 1, []
    try:
        r = subprocess.run(
            ["osascript", "-e", LIST_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, [{"error": str(e)}]
    if r.returncode != 0:
        return r.returncode, [{"error": (r.stderr or r.stdout or "osascript failed").strip()}]
    return 0, _parse(r.stdout or "")
