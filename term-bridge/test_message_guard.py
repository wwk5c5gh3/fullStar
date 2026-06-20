"""Tests for message_guard — sanitize inbound text before terminal injection."""
from __future__ import annotations

import message_guard as mg


def test_strip_control_chars_removes_c0_and_del():
    raw = "a\x00b\x03c\x1bd\x7fe"
    assert mg.strip_control_chars(raw) == "abcde"


def test_strip_control_chars_keeps_tab_and_newline():
    assert mg.strip_control_chars("a\tb\nc") == "a\tb\nc"


def test_sanitize_truncates_over_limit():
    clean, truncated = mg.sanitize_injection("x" * 50, max_chars=10)
    assert clean == "x" * 10
    assert truncated is True


def test_sanitize_under_limit_not_truncated():
    clean, truncated = mg.sanitize_injection("hello", max_chars=10)
    assert clean == "hello"
    assert truncated is False


def test_sanitize_strips_then_truncates():
    # control chars removed first, then length measured
    clean, truncated = mg.sanitize_injection("a\x00b\x00c", max_chars=10)
    assert clean == "abc"
    assert truncated is False


def test_max_inject_chars_default(monkeypatch):
    monkeypatch.delenv("TG_RELAY_MAX_INJECT_CHARS", raising=False)
    assert mg.max_inject_chars() == mg.DEFAULT_MAX_CHARS


def test_max_inject_chars_from_env(monkeypatch):
    monkeypatch.setenv("TG_RELAY_MAX_INJECT_CHARS", "500")
    assert mg.max_inject_chars() == 500


def test_max_inject_chars_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("TG_RELAY_MAX_INJECT_CHARS", "abc")
    assert mg.max_inject_chars() == mg.DEFAULT_MAX_CHARS
