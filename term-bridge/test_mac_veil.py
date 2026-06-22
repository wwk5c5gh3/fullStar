"""Tests for mac_veil control helpers (pure logic — no GUI / no swiftc)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "term-bridge"))

import mac_veil


def test_needs_build_when_binary_missing():
    assert mac_veil.needs_build(src_mtime=100.0, bin_exists=False, bin_mtime=0.0) is True


def test_needs_build_when_binary_stale():
    assert mac_veil.needs_build(src_mtime=200.0, bin_exists=True, bin_mtime=100.0) is True


def test_no_build_when_binary_fresh():
    assert mac_veil.needs_build(src_mtime=100.0, bin_exists=True, bin_mtime=200.0) is False


def test_build_argv_plain():
    argv = mac_veil.build_argv(Path("/x/mac-veil"), message=None, timeout=0)
    assert argv == ["/x/mac-veil"]


def test_build_argv_with_timeout_and_message():
    argv = mac_veil.build_argv(Path("/x/mac-veil"), message="hi", timeout=8)
    assert argv == ["/x/mac-veil", "--timeout", "8", "--message", "hi"]


def test_build_argv_zero_timeout_omitted():
    argv = mac_veil.build_argv(Path("/x/mac-veil"), message="m", timeout=0)
    assert "--timeout" not in argv
    assert argv[-2:] == ["--message", "m"]
