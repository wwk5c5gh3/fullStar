"""Tests for terminal_inject_lib — Terminal.app clipboard+Cmd-V inject builder."""
from __future__ import annotations

from terminal_inject_lib import build_inject_script


def test_sets_clipboard_from_injected_file():
    s = build_inject_script(window=1, tab=1, submit_enter=True)
    assert "set the clipboard to" in s


def test_activates_terminal_and_pastes():
    s = build_inject_script(window=1, tab=1, submit_enter=True)
    assert 'tell application "Terminal"' in s
    assert 'keystroke "v" using command down' in s


def test_submit_presses_return_after_paste_settles():
    s = build_inject_script(window=1, tab=1, submit_enter=True)
    assert "keystroke return" in s
    # a delay must sit between the paste and Return so the async paste lands
    # in the input buffer before Enter submits it
    paste = s.index('keystroke "v"')
    ret = s.index("keystroke return")
    assert "delay" in s[paste:ret]


def test_no_submit_omits_return():
    s = build_inject_script(window=1, tab=1, submit_enter=False)
    assert "keystroke return" not in s


def test_restores_previous_frontmost_app():
    s = build_inject_script(window=1, tab=1, submit_enter=True)
    # captures the prior frontmost app, then reactivates it after pasting
    assert "set priorApp to name of first process whose frontmost is true" in s
    assert "tell application priorApp to activate" in s
    # restore must come after the paste
    assert s.index("priorApp to activate") > s.index('keystroke "v"')


def test_front_window_uses_front_not_index():
    s = build_inject_script(window=None, tab=1, submit_enter=True)
    assert "front window" in s


def test_indexed_window_referenced():
    s = build_inject_script(window=2, tab=3, submit_enter=True)
    assert "window 2" in s
    assert "tab 3" in s


def test_guards_not_running_to_avoid_autolaunch():
    assert "is not running" in build_inject_script(window=1, tab=1, submit_enter=True)


def test_waits_for_terminal_frontmost_before_pasting():
    # activate is async; paste must wait until Terminal is actually frontmost,
    # else Cmd-V lands in whatever window was focused (e.g. iTerm).
    s = build_inject_script(window=1, tab=1, submit_enter=True)
    assert "frontmost of process" in s
    assert "exit repeat" in s
    # the wait loop must come before the paste keystroke
    assert s.index("frontmost of process") < s.index('keystroke "v"')


def test_raises_terminal_via_system_events_frontmost():
    # `tell app "Terminal" to activate` does NOT reliably raise it from a
    # background osascript; System Events set-frontmost does.
    s = build_inject_script(window=1, tab=1, submit_enter=True)
    assert 'set frontmost of process "Terminal" to true' in s
    assert s.index('set frontmost of process "Terminal" to true') < s.index('keystroke "v"')
