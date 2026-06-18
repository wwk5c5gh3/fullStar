#!/usr/bin/env python3
"""Format an extracted Claude Code reply into phone-friendly Telegram HTML.

Pipeline:
  raw scrollback text
    → strip_terminal_noise()  (remove ANSI, TUI borders/gutters, collapse blanks)
    → to_telegram_html()      (escape + render ```code```/`inline`/**bold** as HTML)

The output uses Telegram's HTML parse mode: only <b>, <code>, <pre> are emitted,
everything else is HTML-escaped, so arbitrary terminal output can't break the markup.
"""
from __future__ import annotations

import html
import re

# ── terminal-noise cleaning ──────────────────────────────────────────────
# CSI / escape sequences (colors, cursor moves, etc.)
_ANSI = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Box-drawing / block characters used by Claude Code's TUI chrome
_BORDER_CHARS = "─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┤┬┴┼╭╮╯╰═║╔╗╚╝╠╣╦╩╬▏▕▔▁▌▐"
_BORDER_ONLY = re.compile(r"^[\s" + re.escape(_BORDER_CHARS) + r"]*$")
_GUTTER_CHARS = "│┃┆┊▏▕"
_GUTTER_L = re.compile(r"^\s*[" + re.escape(_GUTTER_CHARS) + r"]\s?")
_GUTTER_R = re.compile(r"\s*[" + re.escape(_GUTTER_CHARS) + r"]\s*$")


def strip_terminal_noise(raw: str) -> str:
    """Remove ANSI codes, TUI border lines/gutters; normalize whitespace."""
    if not raw or not raw.strip():
        return ""
    text = _ANSI.sub("", raw)
    kept: list[str] = []
    for line in text.split("\n"):
        line = line.replace("\t", "    ").rstrip()
        if line.strip() and _BORDER_ONLY.match(line):  # only-border, keep blanks
            continue
        line = _GUTTER_L.sub("", line)
        line = _GUTTER_R.sub("", line)
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# ── markup rendering (shared core, two renderers) ────────────────────────
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_INLINE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def _tokenize_and_render(clean, escape_prose, render_token):
    """Stash code/bold spans, escape the prose, then re-render the spans.

    Tokenizing first means arbitrary terminal output in the prose can never be
    mis-parsed as markup, and code spans keep literal ``*``/``_`` etc.
    """
    tokens: list[tuple[str, str]] = []

    def stash(kind: str, content: str) -> str:
        tokens.append((kind, content))
        return f"\x00{len(tokens) - 1}\x00"

    s = _FENCE.sub(lambda m: stash("pre", m.group(1).rstrip("\n")), clean)
    s = _INLINE.sub(lambda m: stash("code", m.group(1)), s)
    s = _BOLD.sub(lambda m: stash("b", m.group(1)), s)
    s = escape_prose(s)
    return _PLACEHOLDER.sub(lambda m: render_token(*tokens[int(m.group(1))]), s)


def to_telegram_html(clean: str) -> str:
    """Render cleaned text as Telegram HTML (only <b>/<code>/<pre> emitted)."""
    def render(kind: str, content: str) -> str:
        esc = html.escape(content, quote=False)
        if kind == "pre":
            return f"<pre>{esc}</pre>"
        if kind == "code":
            return f"<code>{esc}</code>"
        return f"<b>{esc}</b>"

    return _tokenize_and_render(clean, lambda t: html.escape(t, quote=False), render)


_MDV2 = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _md_escape(t: str) -> str:
    return _MDV2.sub(r"\\\1", t)


def _md_code_escape(t: str) -> str:
    return t.replace("\\", "\\\\").replace("`", "\\`")


def to_telegram_markdown(clean: str) -> str:
    """Render cleaned text as Telegram MarkdownV2 (escaped; code/bold kept)."""
    def render(kind: str, content: str) -> str:
        if kind == "pre":
            return "```\n" + _md_code_escape(content) + "\n```"
        if kind == "code":
            return "`" + _md_code_escape(content) + "`"
        return "*" + _md_escape(content) + "*"

    return _tokenize_and_render(clean, _md_escape, render)


# Telegram parse_mode per output format
_PARSE_MODE = {"html": "HTML", "markdown": "MarkdownV2", "plain": None}


def format_reply(raw: str, fmt: str = "html", max_len: int = 3900) -> tuple[str, str | None]:
    """Clean terminal noise, render in the chosen format.

    Returns ``(body, parse_mode)``. ``fmt`` is one of html | markdown | plain
    (aliases: md/markdownv2, text/none). Truncation happens on the *cleaned*
    text before markup, so tags/entities are never split.
    """
    f = (fmt or "html").strip().lower()
    if f in ("md", "markdownv2"):
        f = "markdown"
    elif f in ("text", "none"):
        f = "plain"
    elif f not in ("html", "markdown", "plain"):
        f = "html"

    clean = strip_terminal_noise(raw)
    if not clean:
        return "", _PARSE_MODE[f]
    if len(clean) > max_len:
        clean = "…\n" + clean[-max_len:]

    if f == "markdown":
        return to_telegram_markdown(clean), "MarkdownV2"
    if f == "plain":
        return clean, None
    return to_telegram_html(clean), "HTML"


def format_reply_html(raw: str, max_len: int = 3900) -> str:
    return format_reply(raw, "html", max_len)[0]


def format_reply_markdown(raw: str, max_len: int = 3900) -> str:
    return format_reply(raw, "markdown", max_len)[0]
