"""Resolve /tab subcommands to a reply string (pure; no telegram, no AppleScript I/O).

Forms: `/tab` (list), `/tab N`, `/tab W:T`, `/tab off`. list_tabs_fn returns the
(code, [TabInfo]) tuple; write_fn(window, tab) persists; clear_fn() removes the default.
"""
from __future__ import annotations

from typing import Callable


def _label(t) -> str:
    return f"w{t.window}/t{t.tab}"


def resolve_tab_command(
    args: list[str],
    list_tabs_fn: Callable[[], tuple[int, list]],
    write_fn: Callable[[int | None, int], object],
    clear_fn: Callable[[], None],
) -> str:
    code, tabs = list_tabs_fn()
    if not args:
        if code != 0 or not tabs:
            return "没有打开的 iTerm 窗口"
        lines = ["当前 tab（点 /tab 菜单按钮或发 /tab N 设为默认）:"]
        for t in tabs:
            lines.append(f"• {_label(t)} · {t.name.replace(chr(10), ' ')[:40]}")
        lines.append("用法: /tab 3  或  /tab off（清除）")
        return "\n".join(lines)

    arg = args[0].strip().lower()
    if arg == "off":
        clear_fn()
        return "已清除默认目标，回退 .env 默认"

    window: int | None = None
    tab: int | None = None
    if ":" in arg:
        w_str, _, t_str = arg.partition(":")
        try:
            window, tab = int(w_str), int(t_str)
        except ValueError:
            return f"无法解析: {args[0]}（用法 /tab 3 或 /tab 1:3）"
    else:
        try:
            tab = int(arg)
        except ValueError:
            return f"无法解析: {args[0]}（用法 /tab 3 或 /tab 1:3）"

    if code != 0 or not tabs:
        return "无法读取 iTerm 标签列表"
    matches = [t for t in tabs if t.tab == tab and (window is None or t.window == window)]
    if not matches:
        avail = ", ".join(_label(t) for t in tabs)
        return f"tab {args[0]} 不存在，当前有: {avail}"
    hit = matches[0]
    write_fn(hit.window, hit.tab)
    return f"✓ 默认目标已设为 {_label(hit)} ({hit.name.replace(chr(10), ' ')[:40]})"
