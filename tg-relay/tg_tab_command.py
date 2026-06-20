"""Resolve /tab subcommands to a reply string (pure; no telegram, no AppleScript I/O).

Forms:
- `/tab`        — list open terminals with a flat 1-based index
- `/tab N`      — pick the N-th terminal in that list (flat index; works whether the
                  backend lays terminals out as one-window-many-tabs or many-windows)
- `/tab W:T`    — pick an explicit window:tab
- `/tab off`    — clear the default

list_tabs_fn returns the (code, [TabInfo]) tuple; write_fn(window, tab) persists;
clear_fn() removes the default.
"""
from __future__ import annotations

from typing import Callable

_USAGE = "（用法 /tab 1 选第几个，或 /tab 1:1 指定窗口:标签）"


def _label(t) -> str:
    return f"w{t.window}/t{t.tab}"


def _name(t) -> str:
    return t.name.replace(chr(10), " ")[:40]


def resolve_tab_command(
    args: list[str],
    list_tabs_fn: Callable[[], tuple[int, list]],
    write_fn: Callable[[int | None, int, str | None], object],
    clear_fn: Callable[[], None],
) -> str:
    code, tabs = list_tabs_fn()
    if not args:
        if code != 0 or not tabs:
            return "没有打开的终端窗口"
        lines = ["当前终端（发 /tab <序号> 设为默认，或点按钮）:"]
        for i, t in enumerate(tabs, 1):
            lines.append(f"{i}. {_label(t)} · {_name(t)}")
        lines.append("用法: /tab 1  或  /tab off（清除）")
        return "\n".join(lines)

    arg = args[0].strip().lower()
    if arg == "off":
        clear_fn()
        return "已清除默认目标，回退 .env 默认"

    if code != 0 or not tabs:
        return "无法读取终端标签列表"

    if ":" in arg:  # explicit window:tab
        w_str, _, t_str = arg.partition(":")
        try:
            window, tab = int(w_str), int(t_str)
        except ValueError:
            return f"无法解析: {args[0]}{_USAGE}"
        matches = [t for t in tabs if t.window == window and t.tab == tab]
        if not matches:
            avail = ", ".join(_label(t) for t in tabs)
            return f"{args[0]} 不存在，当前有: {avail}"
        hit = matches[0]
    else:  # flat 1-based index into the enumerated list
        try:
            n = int(arg)
        except ValueError:
            return f"无法解析: {args[0]}{_USAGE}"
        if n < 1 or n > len(tabs):
            avail = ", ".join(f"{i}.{_label(t)}" for i, t in enumerate(tabs, 1))
            return f"序号 {n} 不存在，当前共 {len(tabs)} 个: {avail}"
        hit = tabs[n - 1]

    write_fn(hit.window, hit.tab, getattr(hit, "session_id", None))
    return f"✓ 默认目标已设为 {_label(hit)} ({_name(hit)})"
