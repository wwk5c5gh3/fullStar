"""Tests for new_content_since — strip a previously-sent leading block from a reply.

Targets the duplicate-message symptom: a later capture repeats an earlier
(partial) send as its leading block (streaming progress sends, or a full
re-send), so the same text reaches Telegram twice.
"""
from __future__ import annotations

from iterm_extract import new_content_since


def test_no_previous_send_returns_reply_unchanged():
    assert new_content_since("hello\nworld", "") == "hello\nworld"


def test_identical_reply_returns_empty():
    assert new_content_since("done", "done") == ""


def test_streaming_continuation_returns_only_new_tail():
    last = "Working on it.\nStep 1 done."
    reply = "Working on it.\nStep 1 done.\nStep 2 done.\nAll finished."
    assert new_content_since(reply, last) == "Step 2 done.\nAll finished."


def test_unrelated_new_message_sent_in_full():
    last = "Previous answer about cats."
    reply = "A completely different answer about dogs."
    assert new_content_since(reply, last) == reply


def test_ignores_whitespace_and_blank_line_differences_in_prefix():
    last = "Line one\nLine two"
    reply = "Line   one\n\nLine two\n\nLine three"
    assert new_content_since(reply, last) == "Line three"


def test_shared_first_line_only_still_strips_repeat():
    last = "Done.\nDetails A"
    reply = "Done.\nDetails A\nDetails B"
    assert new_content_since(reply, last) == "Details B"


def test_partial_overlap_not_a_prefix_keeps_full_reply():
    # last_sent is NOT fully a leading block of reply -> send whole reply.
    last = "alpha\nbeta\nGAMMA"
    reply = "alpha\nbeta\ndelta"
    assert new_content_since(reply, last) == reply


def test_blank_previous_returns_reply():
    assert new_content_since("hello", "   \n  ") == "hello"
