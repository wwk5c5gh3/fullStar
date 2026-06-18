"""Tests for tg_format — phone-friendly Telegram HTML formatting of iTerm replies."""
from __future__ import annotations

from tg_format import (
    format_reply,
    format_reply_html,
    format_reply_markdown,
    strip_terminal_noise,
    to_telegram_html,
    to_telegram_markdown,
)


# ── strip_terminal_noise ──

def test_strips_ansi_escape_codes():
    assert strip_terminal_noise("\x1b[31mred\x1b[0m text") == "red text"


def test_drops_pure_border_lines():
    raw = "╭──────────╮\nhello world\n╰──────────╯"
    assert strip_terminal_noise(raw) == "hello world"


def test_strips_left_and_right_box_gutters():
    assert strip_terminal_noise("│ inside the box │") == "inside the box"


def test_expands_tabs_and_trims_trailing_space():
    assert strip_terminal_noise("a\tb   ") == "a    b"


def test_collapses_three_or_more_blank_lines():
    assert strip_terminal_noise("a\n\n\n\n\nb") == "a\n\nb"


def test_empty_input_returns_empty():
    assert strip_terminal_noise("") == ""
    assert strip_terminal_noise("   \n  \n") == ""


# ── to_telegram_html ──

def test_html_escapes_special_chars():
    assert to_telegram_html("<a> & b") == "&lt;a&gt; &amp; b"


def test_inline_code_becomes_code_tag_with_escaping():
    assert to_telegram_html("run `x<y`") == "run <code>x&lt;y</code>"


def test_fenced_block_becomes_pre_tag():
    assert to_telegram_html("```\ncode<>\n```") == "<pre>code&lt;&gt;</pre>"


def test_double_star_becomes_bold():
    assert to_telegram_html("**Done** now") == "<b>Done</b> now"


def test_code_content_not_treated_as_bold():
    # ** inside code must stay literal, not become <b>
    assert to_telegram_html("`a**b`") == "<code>a**b</code>"


# ── to_telegram_markdown (MarkdownV2) ──

def test_markdown_escapes_special_chars():
    # . - ! are MarkdownV2 specials and must be backslash-escaped
    assert to_telegram_markdown("a.b-c!") == r"a\.b\-c\!"


def test_markdown_inline_code():
    assert to_telegram_markdown("run `auth.py`") == "run `auth.py`"


def test_markdown_fenced_block():
    assert to_telegram_markdown("```\nx=1\n```") == "```\nx=1\n```"


def test_markdown_bold_is_single_star():
    assert to_telegram_markdown("**Done**") == r"*Done*"


# ── format_reply dispatcher ──

def test_dispatcher_html():
    body, mode = format_reply("**hi** there.")
    assert mode == "HTML" and body == "<b>hi</b> there."


def test_dispatcher_markdown():
    body, mode = format_reply("**hi** there.", fmt="markdown")
    assert mode == "MarkdownV2" and body == r"*hi* there\."


def test_dispatcher_plain_has_no_parse_mode():
    body, mode = format_reply("│ hello │", fmt="plain")
    assert mode is None and body == "hello"


def test_dispatcher_unknown_defaults_to_html():
    _, mode = format_reply("x", fmt="weird")
    assert mode == "HTML"


def test_format_reply_markdown_helper():
    assert format_reply_markdown("**Fixed** `a.py`") == "*Fixed* `a.py`"


# ── format_reply_html (integration) ──

def test_format_cleans_then_renders_html():
    raw = "\x1b[1m╭────╮\n│ **Fixed** the bug in `auth.py` │\n╰────╯"
    out = format_reply_html(raw)
    assert out == "<b>Fixed</b> the bug in <code>auth.py</code>"


def test_format_truncates_long_text_without_breaking_tags():
    raw = "x" * 5000
    out = format_reply_html(raw, max_len=100)
    assert out.startswith("…")
    assert len(out) <= 120  # cleaned tail + ellipsis, escaped
    assert "<" not in out.replace("…", "")  # no dangling partial tags


def test_format_empty_returns_empty():
    assert format_reply_html("   \n ") == ""


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
