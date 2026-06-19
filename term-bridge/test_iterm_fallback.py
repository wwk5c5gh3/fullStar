"""Tests for should_text_fallback — the 90s text catch-up decision.

If iTerm finished but the completion marker was never recognized (so the normal
'send on complete / stable' path never fired), the latest reply can sit unsent.
Once its text has been stable for the threshold, force a text send to Telegram.
"""
from __future__ import annotations

from iterm_extract import should_text_fallback


def test_fires_when_reply_settled_past_threshold():
    assert should_text_fallback("answer", last_sent="", since_extract=95, threshold=90)


def test_not_yet_settled():
    assert not should_text_fallback("answer", last_sent="", since_extract=30, threshold=90)


def test_disabled_when_threshold_zero():
    assert not should_text_fallback("answer", last_sent="", since_extract=999, threshold=0)


def test_no_fire_when_already_sent_identically():
    assert not should_text_fallback("answer", last_sent="answer", since_extract=999, threshold=90)


def test_no_fire_on_empty_reply():
    assert not should_text_fallback("", last_sent="", since_extract=999, threshold=90)
    assert not should_text_fallback("   \n  ", last_sent="", since_extract=999, threshold=90)


def test_fires_for_changed_reply_even_if_prior_send_exists():
    assert should_text_fallback("new answer", last_sent="old answer", since_extract=120, threshold=90)


def test_exact_threshold_boundary_fires():
    assert should_text_fallback("answer", last_sent="", since_extract=90, threshold=90)
