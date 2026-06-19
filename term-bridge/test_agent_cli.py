"""Tests for agent_cli — the claude/codex launch + installer registry."""
from __future__ import annotations

import agent_cli


def test_valid_keys():
    assert agent_cli.valid_keys() == ("claude", "codex")


def test_get_claude():
    spec = agent_cli.get_agent("claude")
    assert spec is not None
    assert spec.check == "claude"
    assert spec.launch == "claude --permission-mode bypassPermissions"
    assert "claude.ai/install.sh" in spec.installer


def test_get_codex():
    spec = agent_cli.get_agent("codex")
    assert spec is not None
    assert spec.check == "codex"
    assert spec.launch == "codex"
    assert "@openai/codex" in spec.installer


def test_get_is_case_insensitive_and_trimmed():
    assert agent_cli.get_agent("  Claude ") is agent_cli.get_agent("claude")


def test_get_unknown_returns_none():
    assert agent_cli.get_agent("kitty") is None
