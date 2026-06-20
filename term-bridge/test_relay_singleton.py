"""Tests for tg-relay single-instance guard (_parse_other_pids)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "term-bridge"))


def _load_relay():
    spec = importlib.util.spec_from_file_location(
        "tg_relay_singleton_mod", ROOT / "tg-relay" / "tg-relay.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_other_pids_excludes_self():
    mod = _load_relay()
    assert mod._parse_other_pids("100\n200\n300", me=200) == [100, 300]


def test_parse_other_pids_empty_when_only_self():
    mod = _load_relay()
    assert mod._parse_other_pids("555", me=555) == []


def test_parse_other_pids_ignores_garbage():
    mod = _load_relay()
    assert mod._parse_other_pids("", me=1) == []
    assert mod._parse_other_pids("abc\n42\n", me=1) == [42]
