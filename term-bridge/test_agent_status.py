"""Tests for agent_status — classify a terminal capture into an agent state."""
from __future__ import annotations

import agent_status as st


def test_waiting_when_select_prompt():
    text = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n↑↓ to navigate · Enter to select"
    assert "等待" in st.classify_state(text)


def test_idle_when_complete_marker():
    assert "空闲" in st.classify_state("✓ Crunched for 5s · 1.2k tokens")


def test_running_otherwise():
    assert "运行" in st.classify_state("thinking hard about the problem, editing files")


def test_empty_capture_unknown():
    assert "未知" in st.classify_state("")


def test_format_status_lists_rows():
    out = st.format_status(
        [("1", "w1/t1", "agentA", "🏃 运行中"), ("2", "w2/t1", "shell", "✅ 空闲")]
    )
    assert "w1/t1" in out and "agentA" in out and "运行中" in out
    assert "1." in out and "2." in out


def test_format_status_empty():
    assert "没有" in st.format_status([])
