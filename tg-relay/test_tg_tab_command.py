import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tg-relay"))
sys.path.insert(0, str(ROOT / "term-bridge"))

from tg_tab_command import resolve_tab_command
from iterm_route import TabInfo


def _tabs():
    return 0, [TabInfo(1, 1, "..rees/fullStar"), TabInfo(1, 3, "myapp")]


def test_no_arg_lists_tabs():
    out = resolve_tab_command([], lambda: _tabs(), lambda w, t: None, lambda: None)
    assert "w1/t1" in out and "w1/t3" in out
    assert "/tab" in out  # usage hint


def test_set_by_number_writes_default():
    written = {}
    out = resolve_tab_command(
        ["3"], lambda: _tabs(), lambda w, t: written.update(window=w, tab=t), lambda: None
    )
    assert written == {"window": 1, "tab": 3}
    assert "w1/t3" in out and "✓" in out


def test_set_by_window_colon_tab():
    written = {}
    out = resolve_tab_command(
        ["1:3"], lambda: _tabs(), lambda w, t: written.update(window=w, tab=t), lambda: None
    )
    assert written == {"window": 1, "tab": 3}


def test_unknown_number_reports_available():
    out = resolve_tab_command(["9"], lambda: _tabs(), lambda w, t: None, lambda: None)
    assert "不存在" in out and "t1" in out and "t3" in out


def test_off_clears_default():
    cleared = {"v": False}
    out = resolve_tab_command(
        ["off"], lambda: _tabs(), lambda w, t: None, lambda: cleared.__setitem__("v", True)
    )
    assert cleared["v"] is True
    assert "已清除" in out
