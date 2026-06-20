"""Tests for the --key (enter/esc) mode of the Terminal.app inject backend."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import terminal_inject_lib as lib

CLI = Path(__file__).resolve().parent / "terminal-inject.py"


def test_key_script_enter_uses_keystroke_return():
    s = lib.build_key_script(window=1, tab=2, key="enter")
    assert "keystroke return" in s
    assert "tab 2" in s


def test_key_script_esc_uses_key_code_53():
    s = lib.build_key_script(window=None, tab=1, key="esc")
    assert "key code 53" in s
    assert "tab 1" in s


def test_key_script_ctrl_c_sends_control_c():
    s = lib.build_key_script(window=1, tab=2, key="ctrl-c")
    assert 'keystroke "c" using control down' in s
    assert "tab 2" in s


def test_key_script_unknown_key_raises():
    with pytest.raises(ValueError):
        lib.build_key_script(window=1, tab=1, key="tab")


def test_cli_dry_run_key_enter():
    r = subprocess.run(
        [sys.executable, str(CLI), "--key", "enter", "--tab", "3", "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    assert "would press enter" in r.stdout.lower()
