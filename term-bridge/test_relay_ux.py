"""UX-pass tests for the Telegram relay command surface.

Covers the verified findings from the usability pass:
  (a) /help is generated from MENU_COMMANDS (can't drift / drop commands)
  (b) an unmatched routing prefix is refused and never injects
  (c) /sel accepts a bare integer and confirms with the tab label
  (d) _iterm_inject_enabled() defaults ON and is False only for explicit off

All terminal injection is mocked — no real terminal is ever driven.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "term-bridge"))
sys.path.insert(0, str(ROOT / "tg-relay"))

from iterm_route import RouteResult  # noqa: E402
from iterm_target import ItermTarget  # noqa: E402
from tg_menu import MENU_COMMANDS  # noqa: E402


def _load_base_relay() -> ModuleType:
    """Load tg-relay.py as a fresh, isolated module object."""
    spec = importlib.util.spec_from_file_location(
        "tg_relay_ux_mod", ROOT / "tg-relay" / "tg-relay.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def patches_mod() -> Iterator[ModuleType]:
    """Import the patches module fresh so monkeypatching it is isolated."""
    import tg_relay_patches

    importlib.reload(tg_relay_patches)
    yield tg_relay_patches
    importlib.reload(tg_relay_patches)


# --------------------------------------------------------------------------- #
# (a) /help is generated from MENU_COMMANDS
# --------------------------------------------------------------------------- #
def test_help_lists_every_menu_command(patches_mod: ModuleType) -> None:
    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_command("/help")
    for name, _desc in MENU_COMMANDS:
        assert f"/{name} —" in out, f"/help omits /{name}"


def test_help_under_telegram_limit(patches_mod: ModuleType) -> None:
    mod = _load_base_relay()
    patches_mod.apply(mod)
    assert len(mod._handle_command("/help")) <= 4096


def test_start_equals_help(patches_mod: ModuleType) -> None:
    mod = _load_base_relay()
    patches_mod.apply(mod)
    assert mod._handle_command("/start") == mod._handle_command("/help")


def test_help_keeps_prefix_examples(patches_mod: ModuleType) -> None:
    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_command("/help")
    assert "[t2]" in out  # natural-language prefix footer is preserved


# --------------------------------------------------------------------------- #
# (b) unmatched prefix → refusal, never inject
# --------------------------------------------------------------------------- #
def test_unmatched_prefix_refuses_and_does_not_inject(
    patches_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    injected: list[tuple] = []
    monkeypatch.setattr(
        patches_mod,
        "_inject_iterm",
        lambda *a, **k: injected.append((a, k)) or (0, ""),
    )
    monkeypatch.setattr(
        patches_mod,
        "route_message",
        lambda text: RouteResult(ItermTarget(1, 1), "do thing", None, "ghost"),
    )
    monkeypatch.setattr(
        patches_mod, "format_tabs_message", lambda: "• tab 1 (w1/t1): work"
    )
    monkeypatch.setenv("TG_RELAY_ITERM_INJECT", "1")

    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_natural_language(0, "[ghost] do thing")

    assert injected == [], "unmatched prefix must NOT inject"
    assert "ghost" in out
    assert "未注入" in out
    assert "tab 1" in out  # available tabs are listed


def test_no_prefix_still_injects(
    patches_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    injected: list[tuple] = []
    monkeypatch.setattr(
        patches_mod,
        "_inject_iterm",
        lambda *a, **k: injected.append((a, k)) or (0, ""),
    )
    monkeypatch.setattr(
        patches_mod,
        "route_message",
        lambda text: RouteResult(ItermTarget(1, 3), text, None, None),
    )
    monkeypatch.setattr(patches_mod, "_schedule_iterm_monitor_poll", lambda **k: None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("TG_RELAY_ITERM_INJECT", "1")

    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_natural_language(0, "hello world")

    assert len(injected) == 1, "a clean message must inject exactly once"
    assert out.startswith("✓ 已注入")


def test_injection_disabled_notice(
    patches_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        patches_mod,
        "route_message",
        lambda text: RouteResult(ItermTarget(1, 1), text, None, None),
    )
    monkeypatch.setenv("TG_RELAY_ITERM_INJECT", "0")

    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_natural_language(0, "hello")
    assert "注入已关闭" in out
    assert "TG_RELAY_ITERM_INJECT=1" in out


# --------------------------------------------------------------------------- #
# (c) /sel bare integer → resolves a target + confirms with tab label
# --------------------------------------------------------------------------- #
def test_sel_bare_integer_resolves_and_labels(
    patches_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple] = []
    monkeypatch.setattr(
        patches_mod,
        "_inject_iterm",
        lambda text, target=None: seen.append((text, target)) or (0, ""),
    )
    monkeypatch.setattr(
        patches_mod,
        "route_message",
        lambda text: RouteResult(ItermTarget(window=1, tab=5), text, None, None),
    )
    monkeypatch.setattr(
        patches_mod,
        "list_tabs",
        lambda: (0, [_FakeTab(window=1, tab=5, name="mobile-agent (-zsh)")]),
    )
    monkeypatch.setattr(sys, "platform", "darwin")

    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_command("/sel 2")

    assert len(seen) == 1
    text, target = seen[0]
    assert text == "2"
    assert target.window == 1 and target.tab == 5
    assert out.startswith("✓ 已向")
    assert "mobile-agent" in out  # confirmation names the tab
    assert "第 2 项" in out


def test_sel_wtn_form_still_works_and_labels(
    patches_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple] = []
    monkeypatch.setattr(
        patches_mod,
        "_inject_iterm",
        lambda text, target=None: seen.append((text, target)) or (0, ""),
    )
    monkeypatch.setattr(
        patches_mod,
        "list_tabs",
        lambda: (0, [_FakeTab(window=2, tab=3, name="api-server")]),
    )
    monkeypatch.setattr(sys, "platform", "darwin")

    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_command("/sel 2:3:4")

    assert len(seen) == 1
    text, target = seen[0]
    assert text == "4"
    assert target.window == 2 and target.tab == 3
    assert "api-server" in out
    assert "第 4 项" in out


def test_sel_garbage_is_usage(
    patches_mod: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_base_relay()
    patches_mod.apply(mod)
    out = mod._handle_command("/sel banana")
    assert "无法解析选择" in out


# --------------------------------------------------------------------------- #
# (d) _iterm_inject_enabled(): default ON; False only for explicit off values
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["0", "false", "no", "off", "OFF", "  Off  "])
def test_inject_disabled_for_explicit_off(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    mod = _load_base_relay()
    monkeypatch.setenv("TG_RELAY_ITERM_INJECT", value)
    assert mod._iterm_inject_enabled() is False


@pytest.mark.parametrize("value", ["", "1", "true", "yes", "on", "anything"])
def test_inject_enabled_when_unset_or_truthy(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    mod = _load_base_relay()
    if value == "":
        monkeypatch.delenv("TG_RELAY_ITERM_INJECT", raising=False)
    else:
        monkeypatch.setenv("TG_RELAY_ITERM_INJECT", value)
    assert mod._iterm_inject_enabled() is True


def test_inject_enabled_when_var_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_base_relay()
    monkeypatch.delenv("TG_RELAY_ITERM_INJECT", raising=False)
    assert mod._iterm_inject_enabled() is True


def test_injection_banner_reports_state(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_base_relay()
    monkeypatch.delenv("TG_RELAY_ITERM_INJECT", raising=False)
    assert mod._injection_banner().startswith("inject=ON backend=")
    monkeypatch.setenv("TG_RELAY_ITERM_INJECT", "off")
    assert mod._injection_banner().startswith("inject=OFF backend=")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
class _FakeTab:
    """Minimal stand-in for iterm_route.TabInfo used by /sel label lookup."""

    def __init__(self, window: int, tab: int, name: str) -> None:
        self.window = window
        self.tab = tab
        self.name = name
