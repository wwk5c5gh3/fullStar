#!/usr/bin/env python3
"""Unit tests for the shared macOS access-hint helper."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import access_hint  # noqa: E402
from access_hint import (  # noqa: E402
    ACCESS_HINT,
    needs_access_hint,
    probe_automation_permission,
    with_access_hint,
)


@pytest.mark.parametrize(
    "sample",
    [
        "execution error: Not authorized to send Apple events (-1743)",
        "error -25211: assistive access denied",
        "osascript is not authorized to control the computer",
        "System Events got an error: not allowed to send keystrokes",
        "执行失败：需要辅助功能授权",
    ],
)
def test_needs_access_hint_true_on_tcc_failures(sample: str) -> None:
    assert needs_access_hint(sample) is True


@pytest.mark.parametrize(
    "sample",
    [
        "",
        "ok",
        "execution error: window not found (-1719)",
        "some unrelated runtime error",
    ],
)
def test_needs_access_hint_false_on_non_tcc(sample: str) -> None:
    assert needs_access_hint(sample) is False


def test_with_access_hint_appends_on_failure() -> None:
    result = with_access_hint("boom -1743")
    assert result == f"boom -1743\n\n{ACCESS_HINT}"


def test_with_access_hint_passthrough_on_normal_text() -> None:
    assert with_access_hint("ok") == "ok"
    assert with_access_hint("") == ""


def test_with_access_hint_appends_exactly_once_and_idempotent() -> None:
    once = with_access_hint("denied -25211")
    twice = with_access_hint(once)
    assert twice == once
    assert once.count(ACCESS_HINT) == 1


def test_probe_returns_tuple() -> None:
    ok, message = probe_automation_permission("System Events")
    assert isinstance(ok, bool)
    assert isinstance(message, str)


def test_probe_non_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(access_hint.sys, "platform", "linux")
    ok, message = probe_automation_permission("System Events")
    assert ok is False
    assert message == "needs macOS"
