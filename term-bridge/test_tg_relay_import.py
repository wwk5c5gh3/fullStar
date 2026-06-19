"""Smoke test: tg-relay imports with the menu wiring (catches glue/import breakage)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_relay_module_imports_and_has_menu():
    # term-bridge must be importable for the relay's `from tg_menu import ...`
    import sys
    sys.path.insert(0, str(ROOT / "term-bridge"))
    spec = importlib.util.spec_from_file_location("tg_relay_mod", ROOT / "tg-relay" / "tg-relay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    # the menu is imported at module scope and usable
    from tg_menu import MENU_COMMANDS
    assert len(MENU_COMMANDS) >= 7
