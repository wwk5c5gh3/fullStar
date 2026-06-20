"""Tests for git_diff_report.format_diff_reply — Telegram-friendly diff summary."""
from __future__ import annotations

from git_diff_report import format_diff_reply


def test_empty_diff_says_no_changes():
    assert "无改动" in format_diff_reply("", "")


def test_includes_stat_summary():
    stat = " foo.py | 3 +++\n 1 file changed, 3 insertions(+)"
    out = format_diff_reply(stat, "diff --git a/foo.py b/foo.py\n+x")
    assert "foo.py" in out
    assert "1 file changed" in out


def test_long_body_is_truncated_within_budget():
    body = "\n".join(f"+line {i}" for i in range(5000))
    out = format_diff_reply("stat", body, max_chars=2000)
    assert len(out) <= 2000
    assert "截断" in out


def test_short_body_not_truncated():
    out = format_diff_reply("stat", "+only one line", max_chars=4000)
    assert "+only one line" in out
    assert "截断" not in out
