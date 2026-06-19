"""Tests for the session-control menu additions + patches helper presence."""
from __future__ import annotations

import sys
from pathlib import Path

import tg_menu as m

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tg-relay"))
import tg_relay_patches as patches


def test_session_commands_in_menu():
    cmds = [c for c, _ in m.MENU_COMMANDS]
    for expected in ("stop", "reset", "compact", "model", "think"):
        assert expected in cmds


def test_model_and_think_submenus_exist():
    assert ("opus", "model:opus") in m.SUBMENUS["/model"]
    assert ("high", "think:high") in m.SUBMENUS["/think"]


def test_callback_maps_model_and_think():
    assert m.callback_to_command("model", "opus") == "/model opus"
    assert m.callback_to_command("think", "high") == "/think high"


def test_patches_exposes_inject_key():
    assert hasattr(patches, "_inject_key")
