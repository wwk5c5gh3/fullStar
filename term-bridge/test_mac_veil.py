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


def test_hash_password_matches_swift_algorithm():
    # MUST equal Swift sha256Hex(salt + password); known vector for "S4LT"+"1234"
    assert mac_veil.hash_password("1234", "S4LT") == (
        "2d2dbba6d3316056f7bd4d797c1b6f41477d6c51ee335726ca31bf57e2d78dc8"
    )


def test_set_password_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_veil, "CONFIG", tmp_path / "veil-config.json")
    mac_veil.set_password("hunter2")
    cfg = mac_veil.load_config()
    assert cfg["salt"]
    assert cfg["pwd_hash"] == mac_veil.hash_password("hunter2", cfg["salt"])
    # salt is random → hash is not the bare unsalted digest
    import hashlib
    assert cfg["pwd_hash"] != hashlib.sha256(b"hunter2").hexdigest()


def test_set_password_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_veil, "CONFIG", tmp_path / "veil-config.json")
    import pytest
    with pytest.raises(ValueError):
        mac_veil.set_password("")


def test_set_boot_toggles(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_veil, "CONFIG", tmp_path / "veil-config.json")
    mac_veil.set_boot(True)
    assert mac_veil.load_config()["enable_on_boot"] is True
    mac_veil.set_boot(False)
    assert mac_veil.load_config()["enable_on_boot"] is False


def test_verify_password(tmp_path, monkeypatch):
    monkeypatch.setattr(mac_veil, "CONFIG", tmp_path / "veil-config.json")
    mac_veil.set_password("secret")
    cfg = mac_veil.load_config()
    assert mac_veil.verify_password("secret", cfg) is True
    assert mac_veil.verify_password("wrong", cfg) is False


def test_verify_password_no_config():
    assert mac_veil.verify_password("x", {}) is False
    assert mac_veil.verify_password("x", {"pwd_hash": "h"}) is False  # missing salt
