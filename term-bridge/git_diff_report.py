"""Format a git diff for a Telegram reply: stat summary + truncated body.

Pure formatter (unit-tested). The relay runs `git -C <dir> diff --stat` and
`git -C <dir> diff` and passes the outputs here. Telegram caps messages near
4096 chars, so the raw diff is truncated to fit after the stat summary.
"""
from __future__ import annotations


def format_diff_reply(stat: str, body: str, max_chars: int = 3500) -> str:
    stat = (stat or "").rstrip()
    body = (body or "").rstrip()
    if not stat and not body:
        return "工作区无改动（git diff 为空）"
    out = "📝 git diff --stat:\n" + (stat or "(无 stat)")
    budget = max_chars - len(out) - 30
    if body and budget > 200:
        if len(body) <= budget:
            out += "\n\n" + body
        else:
            out += "\n\n" + body[:budget] + "\n…（diff 太长，已截断）"
    return out
