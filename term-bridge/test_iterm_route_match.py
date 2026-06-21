# term-bridge/test_iterm_route_match.py
"""Tests for route_message's unmatched_prefix contract.

route_message must let callers distinguish "no prefix → default" from "prefix
given but unmatched" (a wrong-session footgun), while keeping the legacy
parse_routed_message 3-tuple identical.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import iterm_route as ir
from iterm_route import TabInfo
from iterm_target import ItermTarget


def _tabs(*pairs):
    return 0, [TabInfo(window=w, tab=t, name=f"dir{t}") for w, t in pairs]


def _named_tabs(*triples):
    # (window, tab, name)
    return 0, [TabInfo(window=w, tab=t, name=n) for w, t, n in triples]


def test_no_prefix_unmatched_is_none(monkeypatch):
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=3))
    monkeypatch.setattr(ir, "list_tabs", lambda: _tabs((1, 1), (1, 3)))
    r = ir.route_message("现在项目状态如何")
    assert r.unmatched_prefix is None
    assert r.hit is None
    assert (r.target.window, r.target.tab) == (1, 3)
    assert r.body == "现在项目状态如何"


def test_tab_prefix_no_such_tab_sets_unmatched_key(monkeypatch):
    # [t9] but only t1 is open -> caller must learn the prefix was unmatched.
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=1))
    monkeypatch.setattr(ir, "list_tabs", lambda: _tabs((1, 1)))
    r = ir.route_message("[t9] deploy")
    assert r.unmatched_prefix == "9"
    assert r.hit is None
    assert (r.target.window, r.target.tab) == (1, 1)
    assert r.body == "deploy"


def test_matching_tab_prefix_unmatched_is_none(monkeypatch):
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=3))
    monkeypatch.setattr(ir, "list_tabs", lambda: _tabs((1, 1), (1, 2), (1, 3)))
    r = ir.route_message("[t2] 列目录")
    assert r.unmatched_prefix is None
    assert r.hit is not None
    assert r.target.tab == 2
    assert r.body == "列目录"


def test_unmatched_alias_sets_unmatched_key(monkeypatch):
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=1))
    monkeypatch.setattr(ir, "list_tabs", lambda: _named_tabs((1, 1, "mobile-agent")))
    r = ir.route_message("[nope] do thing")
    assert r.unmatched_prefix == "nope"
    assert r.hit is None
    assert (r.target.window, r.target.tab) == (1, 1)
    assert r.body == "do thing"


def test_prefix_with_empty_rest_unmatched_is_none(monkeypatch):
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=3))
    monkeypatch.setattr(ir, "list_tabs", lambda: _tabs((1, 1), (1, 3)))
    r = ir.route_message("[t9]")
    assert r.unmatched_prefix is None
    assert r.hit is None
    # body keeps the original text when there's nothing after the prefix.
    assert r.body == "[t9]"


def test_tabs_not_enumerable_does_not_falsely_reject(monkeypatch):
    # list_tabs failing (non-macOS/test) must NOT set unmatched_prefix; we
    # genuinely can't tell the prefix is wrong.
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=1))
    monkeypatch.setattr(ir, "list_tabs", lambda: (1, []))
    r = ir.route_message("[t9] deploy")
    assert r.unmatched_prefix is None
    assert r.hit is None
    assert r.body == "deploy"


def test_matching_alias_unmatched_is_none(monkeypatch):
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=1))
    monkeypatch.setattr(
        ir, "list_tabs", lambda: _named_tabs((1, 1, "shell"), (1, 2, "mobile-agent"))
    )
    r = ir.route_message("[mobile-agent] git status")
    assert r.unmatched_prefix is None
    assert r.hit is not None
    assert r.target.tab == 2
    assert r.body == "git status"


def test_parse_routed_message_wrapper_matches_route_message(monkeypatch):
    # The legacy 3-tuple must stay byte-for-byte identical to route_message.
    monkeypatch.setattr(ir, "read_default", lambda: ItermTarget(window=1, tab=1))
    monkeypatch.setattr(ir, "list_tabs", lambda: _tabs((1, 1)))
    r = ir.route_message("[t9] deploy")
    target, body, hit = ir.parse_routed_message("[t9] deploy")
    assert (target.window, target.tab) == (r.target.window, r.target.tab)
    assert body == r.body
    assert hit is r.hit
