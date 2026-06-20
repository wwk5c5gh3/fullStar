"""Tests for terminal_tabs._parse — Terminal.app window/tab enumeration parser.

Terminal.app addresses each terminal as `tab T of window W`; a typical layout is
several windows each holding one tab. The AppleScript emits
`window|||tab|||tty|||process|||winName` per line, where winName is the window's
full title bar (cwd + custom title + ttys + shortcut). _parse keeps the cwd +
title (dropping the volatile ttys/shortcut tail) as a stable, identifying name,
and exposes the tty as session_id.
"""
from __future__ import annotations

from terminal_tabs import _clean_window_name, _parse

# Real osascript output: first field is the window's STABLE id; last field is the
# window's full title bar (cwd — title — ttys — ⌥⌘N).
SAMPLE = (
    "72|||1|||/dev/ttys000|||claude|||~/Documents/aiTrees/fullStar — ⠐ 新增功能 — ttys000 — ⌥⌘1\n"
    "172|||1|||/dev/ttys003|||claude|||~/fullStar — ✳ 重新告诉我 — ttys003 — ⌥⌘3\n"
    "153|||1|||/dev/ttys005|||-zsh|||~/Documents/aiTrees/fullStar — maxwell@Mac — ttys005 — ⌥⌘2\n"
)


def test_parse_window_field_is_stable_id():
    rows = _parse(SAMPLE)
    assert [(r["window"], r["tab"]) for r in rows] == [(72, 1), (172, 1), (153, 1)]


def test_name_keeps_cwd_and_title_drops_tty_and_shortcut():
    rows = _parse(SAMPLE)
    assert rows[0]["name"] == "~/Documents/aiTrees/fullStar · ⠐ 新增功能"
    assert "ttys000" not in rows[0]["name"]
    assert "⌥⌘1" not in rows[0]["name"]


def test_name_distinguishes_same_dir_tabs_and_different_dirs():
    rows = _parse(SAMPLE)
    # different dirs are visible (~/Documents/.../fullStar vs ~/fullStar)
    assert rows[0]["name"] != rows[1]["name"]
    assert rows[1]["name"].startswith("~/fullStar")
    # same dir, different title still distinguishable
    assert rows[0]["name"] != rows[2]["name"]


def test_clean_window_name_strips_noise():
    assert (
        _clean_window_name("~/proj — working on X — ttys009 — ⌥⌘5")
        == "~/proj · working on X"
    )


def test_clean_window_name_without_separators():
    assert _clean_window_name("just-a-title") == "just-a-title"


def test_clean_window_name_strips_window_size():
    assert _clean_window_name("fullStar — git-branch — -zsh — 159×47") == "fullStar · git-branch · -zsh"


def test_parse_exposes_tty_as_session_id():
    rows = _parse(SAMPLE)
    assert [r["session_id"] for r in rows] == ["/dev/ttys000", "/dev/ttys003", "/dev/ttys005"]


def test_parse_sessions_always_one():
    rows = _parse(SAMPLE)
    assert all(r["sessions"] == 1 for r in rows)


def test_parse_falls_back_to_process_when_winname_empty():
    rows = _parse("1|||1|||/dev/ttys000|||claude||| \n")
    assert rows[0]["name"] == "claude"


def test_parse_falls_back_to_tab_label_when_winname_and_proc_empty():
    rows = _parse("2|||1|||/dev/ttys000|||  |||  \n")
    assert rows[0]["name"] == "tab1"


def test_parse_missing_tty_yields_none_session_id():
    rows = _parse("1|||1||| |||claude|||~/p — t — ttys000 — ⌥⌘1\n")
    assert rows[0]["session_id"] is None


def test_parse_skips_blank_and_malformed_lines():
    rows = _parse("\n1|||1|||tty|||p|||t\nGARBAGE\n2|||x|||tty|||p|||t\n")
    assert [(r["window"], r["tab"]) for r in rows] == [(1, 1)]


def test_parse_empty_input():
    assert _parse("") == []
