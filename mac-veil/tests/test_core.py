"""Tests for mac_veil.core pure logic (no GUI / no swiftc)."""
from pathlib import Path

import pytest

from mac_veil import core


def test_needs_build_when_binary_missing():
    assert core.needs_build(100.0, False, 0.0) is True


def test_needs_build_when_binary_stale():
    assert core.needs_build(200.0, True, 100.0) is True


def test_no_build_when_binary_fresh():
    assert core.needs_build(100.0, True, 200.0) is False


def test_build_argv_plain():
    assert core.build_argv(Path("/x/mac-veil"), None, 0) == ["/x/mac-veil"]


def test_build_argv_with_timeout_and_message():
    assert core.build_argv(Path("/x/mac-veil"), "hi", 8) == [
        "/x/mac-veil", "--timeout", "8", "--message", "hi",
    ]


def test_hash_password_matches_swift_algorithm():
    # MUST equal Swift sha256Hex(salt + password)
    assert core.hash_password("1234", "S4LT") == (
        "2d2dbba6d3316056f7bd4d797c1b6f41477d6c51ee335726ca31bf57e2d78dc8"
    )


def test_set_password_and_verify(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    core.set_password("hunter2")
    cfg = core.load_config()
    assert cfg["salt"] and cfg["pwd_hash"]
    assert core.verify_password("hunter2", cfg) is True
    assert core.verify_password("wrong", cfg) is False


def test_set_password_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    with pytest.raises(ValueError):
        core.set_password("")


def test_verify_password_no_config():
    assert core.verify_password("x", {}) is False
    assert core.verify_password("x", {"pwd_hash": "h"}) is False  # missing salt


def test_set_boot_toggles(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    core.set_boot(True)
    assert core.load_config()["enable_on_boot"] is True
    core.set_boot(False)
    assert core.load_config()["enable_on_boot"] is False
