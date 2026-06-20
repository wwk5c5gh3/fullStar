"""Tests for approval mode — strip auto-approve so the agent prompts (#2)."""
from __future__ import annotations

import agent_cli as ac


def test_approval_launch_strips_bypass_flag():
    out = ac.approval_launch("claude --permission-mode bypassPermissions --model opus")
    assert "bypassPermissions" not in out
    assert "claude" in out and "--model opus" in out


def test_approval_launch_strips_dangerous_flag():
    assert "skip-permissions" not in ac.approval_launch("codex --dangerously-skip-permissions")


def test_approval_launch_noop_when_no_flag():
    assert ac.approval_launch("codex") == "codex"


def test_set_and_read_approve_mode_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("TG_AGENT_APPROVE", raising=False)
    monkeypatch.setattr(ac, "_approve_mode_path", lambda: tmp_path / "approve-mode")
    assert ac.read_approve_mode() is False
    ac.set_approve_mode(True)
    assert ac.read_approve_mode() is True
    ac.set_approve_mode(False)
    assert ac.read_approve_mode() is False


def test_env_forces_approve_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "_approve_mode_path", lambda: tmp_path / "absent")
    monkeypatch.setenv("TG_AGENT_APPROVE", "1")
    assert ac.read_approve_mode() is True


def test_get_agent_applies_approval_when_on(monkeypatch):
    monkeypatch.setenv("TG_AGENT_APPROVE", "1")
    monkeypatch.delenv("AGENT_CLAUDE_LAUNCH", raising=False)
    spec = ac.get_agent("claude")
    assert spec is not None
    assert "bypassPermissions" not in spec.launch


def test_get_agent_keeps_bypass_when_off(monkeypatch, tmp_path):
    monkeypatch.delenv("TG_AGENT_APPROVE", raising=False)
    monkeypatch.setattr(ac, "_approve_mode_path", lambda: tmp_path / "absent")
    monkeypatch.delenv("AGENT_CLAUDE_LAUNCH", raising=False)
    spec = ac.get_agent("claude")
    assert "bypassPermissions" in spec.launch
