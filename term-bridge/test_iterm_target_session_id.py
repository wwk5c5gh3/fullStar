"""Stable-session-id support in iterm_target: env wiring + GUID-first AppleScript."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iterm_target import (
    ItermTarget,
    applescript_session_block,
    applescript_session_close,
    apply_target_env,
    resolve_target,
)


def test_env_map_includes_session_id():
    t = ItermTarget(window=1, tab=2, session_id="GUID-7")
    assert t.env_map()["ITERM_TARGET_SESSION_ID"] == "GUID-7"


def test_env_map_blank_session_id_when_none():
    assert ItermTarget(window=1, tab=2).env_map()["ITERM_TARGET_SESSION_ID"] == ""


def test_apply_target_env_sets_session_id():
    env = apply_target_env(ItermTarget(window=1, tab=2, session_id="GUID-7"), env={})
    assert env["TG_ITERM_SESSION_ID"] == "GUID-7"
    assert env["ITERM_TARGET_SESSION_ID"] == "GUID-7"


def test_resolve_target_reads_session_id_env(monkeypatch):
    monkeypatch.setenv("TG_ITERM_SESSION_ID", "GUID-from-env")
    assert resolve_target().session_id == "GUID-from-env"


def test_resolve_target_blank_session_id_is_none(monkeypatch):
    monkeypatch.setenv("TG_ITERM_SESSION_ID", "")
    assert resolve_target().session_id is None


def test_applescript_scans_sessions_for_matching_id():
    block = applescript_session_block()
    assert 'system attribute "ITERM_TARGET_SESSION_ID"' in block
    assert "if (id of aSess) is sessId then" in block
    # positional fallback still present
    assert "tell tab tabIdx" in block
    assert "tell targetSession" in block


def test_block_and_close_balance_tells():
    # two opened tells (application + targetSession) → two closing end tells
    block = applescript_session_block()
    close = applescript_session_close()
    assert close.strip().count("end tell") == 2
    assert block.rstrip().endswith("tell targetSession")
