"""Tests for rate_limit — per-chat minimum interval limiter."""
from __future__ import annotations

from rate_limit import RateLimiter


def test_first_message_allowed():
    rl = RateLimiter(min_interval=1.0)
    assert rl.allow(chat_id=1, now=100.0) is True


def test_second_message_within_interval_denied():
    rl = RateLimiter(min_interval=1.0)
    assert rl.allow(1, 100.0) is True
    assert rl.allow(1, 100.5) is False


def test_message_after_interval_allowed():
    rl = RateLimiter(min_interval=1.0)
    assert rl.allow(1, 100.0) is True
    assert rl.allow(1, 101.5) is True


def test_per_chat_isolation():
    rl = RateLimiter(min_interval=1.0)
    assert rl.allow(1, 100.0) is True
    assert rl.allow(2, 100.0) is True  # different chat, not limited


def test_denied_message_does_not_push_window():
    # a burst of denied messages must not keep extending the next allowed time
    rl = RateLimiter(min_interval=1.0)
    assert rl.allow(1, 100.0) is True
    assert rl.allow(1, 100.5) is False  # denied
    assert rl.allow(1, 100.9) is False  # still denied
    assert rl.allow(1, 101.1) is True   # 1.1s after the last ALLOWED (100.0)


def test_zero_interval_disables_limit():
    rl = RateLimiter(min_interval=0)
    assert rl.allow(1, 100.0) is True
    assert rl.allow(1, 100.0) is True
    assert rl.allow(1, 100.0) is True
