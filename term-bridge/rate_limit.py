"""Per-chat rate limiting for the Telegram relay.

Each inbound message spawns an osascript injection; without a limit an
authorized (or compromised) account could flood the bot and the terminal.
This enforces a minimum interval between accepted messages per chat_id.

Single-process asyncio relay → no locking needed. Time is injected (`now`)
so the limiter is deterministically testable.
"""
from __future__ import annotations

import os


def min_interval_secs() -> float:
    """Minimum seconds between messages per chat (TG_RELAY_MIN_INTERVAL_SECS).

    Default 1.0; set to 0 (or negative) to disable rate limiting.
    """
    raw = os.environ.get("TG_RELAY_MIN_INTERVAL_SECS", "").strip()
    if not raw:
        return 1.0
    try:
        return float(raw)
    except ValueError:
        return 1.0


class RateLimiter:
    """Fixed minimum-interval limiter keyed by chat_id."""

    def __init__(self, min_interval: float | None = None) -> None:
        self._min = min_interval if min_interval is not None else min_interval_secs()
        self._last: dict[int, float] = {}

    @property
    def min_interval(self) -> float:
        return self._min

    def allow(self, chat_id: int, now: float) -> bool:
        """True if a message from chat_id is allowed at time `now`.

        Records the timestamp only when allowed, so a burst of denied messages
        doesn't keep pushing the next allowed time forward.
        """
        if self._min <= 0:
            return True
        last = self._last.get(chat_id)
        if last is not None and (now - last) < self._min:
            return False
        self._last[chat_id] = now
        return True
