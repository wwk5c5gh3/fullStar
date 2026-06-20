"""Classify a terminal capture into an agent state, for the /status dashboard.

Reuses the same detectors the monitor uses: a select-prompt means the agent is
waiting for the operator, a completion marker means it finished the turn, and
anything else is treated as still running. classify_state and format_status are
pure; the relay captures each tab's scrollback and feeds it in.
"""
from __future__ import annotations

from interactive_prompt import detect_select_prompt
from iterm_extract import is_reply_complete


def classify_state(capture: str) -> str:
    if not capture or not capture.strip():
        return "❔ 未知"
    if detect_select_prompt(capture):
        return "⏳ 等待输入"
    if is_reply_complete(capture):
        return "✅ 空闲/完成"
    return "🏃 运行中"


def format_status(rows: list[tuple[str, str, str, str]]) -> str:
    """rows = [(index, label, name, state)] → a Telegram status list."""
    if not rows:
        return "没有打开的终端"
    lines = ["📊 终端状态:"]
    for idx, label, name, state in rows:
        short = name.replace("\n", " ")[:30]
        lines.append(f"{idx}. {label} · {state} · {short}")
    lines.append("发 /tab <序号> 切换默认目标")
    return "\n".join(lines)
