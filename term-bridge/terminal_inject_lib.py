"""AppleScript builder for injecting text into Terminal.app via clipboard + Cmd-V.

Terminal.app has no silent write-into-running-program API (unlike iTerm), so we
put the text on the clipboard, bring the target window to the front, paste with
System Events (needs Accessibility), optionally press Return, then restore the
prior frontmost app and the previous clipboard. The text is read from a file
named by the TERM_INJECT_FILE env var to avoid AppleScript string escaping.
"""
from __future__ import annotations

_KEY_ACTIONS = {
    "enter": "keystroke return",
    "esc": "key code 53",
    "ctrl-c": 'keystroke "c" using control down',
}


def _window_ref(window: int | None) -> str:
    # Stable `window id` — Terminal.app's plain `window N` is z-order (frontmost=1),
    # which drifts as focus changes, so a stored target would point elsewhere later.
    return "front window" if window is None else f"window id {int(window)}"


def _focus_block(window: int | None, tab: int, session_id: str | None) -> str:
    """AppleScript (inside `tell application "Terminal"`) that focuses the target.

    When session_id (a tty like /dev/ttys003) is given, scan every window/tab for
    the matching tty and select it — position-independent, so reordering/closing
    other tabs can't misroute. Falls back to the positional window/tab if the tty
    is no longer open. Without a session_id, use the positional path directly.
    """
    win = _window_ref(window)
    positional = (
        f"    try\n"
        f"        set index of {win} to 1\n"
        f"    end try\n"
        f"    try\n"
        f"        set selected of tab {int(tab)} of {win} to true\n"
        f"    end try\n"
    )
    if not session_id:
        return positional
    tty = session_id.replace('"', '')  # tty has no quotes; strip defensively
    return (
        f"    set didFocus to false\n"
        f"    repeat with aWin in windows\n"
        f"        repeat with aTab in tabs of aWin\n"
        f"            try\n"
        f'                if (tty of aTab) is "{tty}" then\n'
        f"                    set index of aWin to 1\n"
        f"                    set selected of aTab to true\n"
        f"                    set didFocus to true\n"
        f"                    exit repeat\n"
        f"                end if\n"
        f"            end try\n"
        f"        end repeat\n"
        f"        if didFocus then exit repeat\n"
        f"    end repeat\n"
        f"    if not didFocus then\n"
        f"{positional}"
        f"    end if\n"
    )


def build_key_script(*, window: int | None, tab: int, key: str, session_id: str | None = None) -> str:
    """`on run` AppleScript that focuses the target Terminal tab and presses one key."""
    if key not in _KEY_ACTIONS:
        raise ValueError(f"unknown key: {key!r}")
    action = _KEY_ACTIONS[key]
    focus_window = _focus_block(window, tab, session_id)
    return (
        "on run\n"
        '    if application "Terminal" is not running then error "No Terminal running"\n'
        '    tell application "Terminal"\n'
        f"{focus_window}"
        "    end tell\n"
        '    tell application "System Events"\n'
        '        set frontmost of process "Terminal" to true\n'
        "        repeat 40 times\n"
        '            if frontmost of process "Terminal" then exit repeat\n'
        "            delay 0.05\n"
        "        end repeat\n"
        f"        {action}\n"
        "    end tell\n"
        "end run\n"
    )


def build_inject_script(
    *,
    window: int | None,
    tab: int,
    submit_enter: bool,
    enter_twice: bool = False,
    clear_line: bool = False,
    session_id: str | None = None,
) -> str:
    """Full `on run` AppleScript for one clipboard-paste injection.

    enter_twice: send Return a second time. Needed for slash commands in TUIs
    (e.g. Claude Code), where the first Return is swallowed by the slash-command
    autocomplete menu instead of submitting the line.
    clear_line: press Ctrl-U before pasting to wipe any leftover/unsubmitted
    input, so a prior command never concatenates onto this one (e.g. the
    "/model sonnet/model opus" run-together bug).
    """
    # Wipe the input line first so a stale, unsubmitted command can't concatenate.
    clear = '        keystroke "u" using control down\n        delay 0.1\n' if clear_line else ""
    # Paste is async; let it settle into the input buffer before Return submits.
    if submit_enter:
        submit = "        delay 0.2\n        keystroke return\n"
        if enter_twice:
            submit += "        delay 0.25\n        keystroke return\n"
    else:
        submit = ""
    # Best-effort focus of the requested tab (by tty when known, else position);
    # wrapped so a read-only property or single-window setup never aborts paste.
    focus_window = _focus_block(window, tab, session_id)
    return (
        "on run\n"
        '    if application "Terminal" is not running then error "No Terminal running"\n'
        '    set msgPath to system attribute "TERM_INJECT_FILE"\n'
        '    set theText to read POSIX file msgPath as «class utf8»\n'
        "    if theText ends with (return) then\n"
        "        set theText to text 1 thru -2 of theText\n"
        "    end if\n"
        '    set savedClip to ""\n'
        "    try\n"
        "        set savedClip to (the clipboard as text)\n"
        "    end try\n"
        "    set the clipboard to theText\n"
        "    tell application \"System Events\"\n"
        "        set priorApp to name of first process whose frontmost is true\n"
        "    end tell\n"
        '    tell application "Terminal"\n'
        f"{focus_window}"
        "    end tell\n"
        '    tell application "System Events"\n'
        # `tell app to activate` does NOT reliably raise Terminal from a
        # background osascript; set-frontmost does. Then wait until it's really
        # frontmost so Cmd-V doesn't land in the previously focused window.
        '        set frontmost of process "Terminal" to true\n'
        "        repeat 40 times\n"
        '            if frontmost of process "Terminal" then exit repeat\n'
        "            delay 0.05\n"
        "        end repeat\n"
        f"{clear}"
        '        keystroke "v" using command down\n'
        f"{submit}"
        "    end tell\n"
        "    try\n"
        "        tell application priorApp to activate\n"
        "    end try\n"
        "    try\n"
        "        set the clipboard to savedClip\n"
        "    end try\n"
        "end run\n"
    )
