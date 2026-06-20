"""List open Terminal.app windows/tabs via AppleScript.

Mirrors iterm_tabs.list_targets so the routing layer can enumerate whichever
backend TG_TERM_BACKEND selects. Terminal.app addresses each terminal as
`tab T of window W`; a common layout is several windows each with one tab. The
AppleScript emits `window|||tab|||tty|||process|||title` per line. The tty (e.g.
/dev/ttys003) is Terminal.app's *stable* per-session id — unchanged by tab
reordering or closing other tabs — so routing can anchor on it like iTerm's GUID.
The title is emitted last so it may safely contain the delimiter.
"""
from __future__ import annotations

import subprocess
import sys

LIST_SCRIPT = r"""
set out to ""
tell application "Terminal"
    set wCount to count of windows
    repeat with w from 1 to wCount
        set tCount to count of tabs of window w
        repeat with t from 1 to tCount
            set theTab to tab t of window w
            set tTitle to ""
            try
                set tTitle to custom title of theTab
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
            set out to out & w & "|||" & t & "|||" & ttyStr & "|||" & proc & "|||" & tTitle & linefeed
        end repeat
    end repeat
end tell
return out
"""


def _parse(stdout: str) -> list[dict]:
    # Layout: window|||tab|||tty|||process|||title  (title last → may contain |||)
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
        title = parts[4].strip()
        name = title or proc or f"tab{tab}"
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
