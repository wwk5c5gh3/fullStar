#!/usr/bin/env python3
"""Extract Claude Code assistant reply from raw iTerm scrollback (strip UI chrome)."""
from __future__ import annotations

import re

# Claude Code footer / chrome — not part of the assistant answer
_FOOTER_START = re.compile(
    r"^\s*(?:"
    r"[🐢🌳📊⏵🐵🌕🤡]"
    r"|Opus\s+\d"
    r"|📁"
    r"|⏵⏵"
    r")"
)
_USER_PROMPT = re.compile(r"^❯\s*(.*)$")
_SEPARATOR = re.compile(r"^─{12,}$")
_BANNER = re.compile(r"^╭[──]+ Claude Code")
_COMPLETE = re.compile(
    r"(?:[✻*✓]\s*)?(?:Crunched|Baked|Finished|Thought|Ran)\s+for\s+\d",
    re.I,
)
_SKIP_LINE = re.compile(
    r"(?:"
    r"bypass permissions on"
    r"|ctrl\+End"
    r"|new message \(ctrl"
    r"|^Run /init to create"
    r"|^/release-notes for more"
    r"|setup issues:"
    r"|Welcome back "
    r")",
    re.I,
)


def _strip_assistant_prefix(line: str) -> str:
    return re.sub(r"^[⏺✻*]\s*", "", line.strip())


def _is_boundary_line(line: str) -> bool:
    """Boundaries when scanning after a user prompt (streaming / ⏺ mode)."""
    stripped = line.strip()
    if not stripped:
        return False
    if _FOOTER_START.match(line) or _FOOTER_START.match(stripped):
        return True
    if _SEPARATOR.match(stripped):
        return True
    if stripped.startswith("❯"):
        return True
    if _BANNER.match(stripped):
        return True
    if re.match(r"^╭[─\s]", stripped):
        return True
    if _SKIP_LINE.search(line) or _SKIP_LINE.search(stripped):
        return True
    return False


def _is_turn_boundary(line: str) -> bool:
    """Only a previous completed turn ends the scan."""
    return bool(_COMPLETE.search(line))


def _strip_leading_noise(body: list[str]) -> list[str]:
    while body:
        s = body[0].strip()
        if not s:
            body.pop(0)
            continue
        if re.match(r"^[╭╰]", s) or s.startswith("❯") or re.match(r"^─{8,}$", s):
            body.pop(0)
            continue
        if "bypass permissions" in s:
            body.pop(0)
            continue
        if s.startswith("│") and any(
            k in s for k in ("What's new", "Tips for", "Welcome back", "release-notes", "Organization", "▐▛", "▝▜")
        ):
            body.pop(0)
            continue
        break
    return body


def _is_scrollback_junk(line: str) -> bool:
  stripped = line.strip()
  if not stripped:
    return True
  if _FOOTER_START.match(line):
    return True
  if re.match(r"^\s*⏵⏵ bypass", line):
    return True
  if _BANNER.match(stripped) or "Claude Code v" in stripped:
    return True
  if re.match(r"^❯\s*$", stripped) or stripped in ("❯", "❯\xa0"):
    return True
  if re.match(r"^❯\s*/clear", stripped):
    return True
  if re.match(r"^╭[─\s]", stripped):
    return True
  if "Welcome back" in stripped or "Tips for getting started" in stripped:
    return True
  if "What's new" in stripped and stripped.startswith("│"):
    return True
  if _SEPARATOR.match(stripped):
    return True
  return False


def _find_crunch_start(lines: list[str], crunch_idx: int, *, max_lines: int = 250, max_junk_gap: int = 12) -> int:
    pos = crunch_idx - 1
    while pos >= 0 and _is_scrollback_junk(lines[pos]):
        pos -= 1
    if pos < 0:
        return 0

    start = pos
    content_lines = 0
    while start >= 0:
        if _COMPLETE.search(lines[start]) and start < crunch_idx - 3:
            return start + 1
        if "Welcome back" in lines[start] or "Tips for getting started" in lines[start]:
            return start + 1
        if _is_scrollback_junk(lines[start]):
            j = start
            gap = 0
            while j >= 0 and _is_scrollback_junk(lines[j]) and gap < max_junk_gap:
                j -= 1
                gap += 1
            if j >= 0 and not _COMPLETE.search(lines[j]) and gap < max_junk_gap:
                start = j
                continue
            return start + 1
        content_lines += 1
        if content_lines >= max_lines:
            return start
        start -= 1
    return 0


def is_reply_complete(text: str) -> bool:
    """True when Claude Code finished the latest turn (e.g. Baked/Crunched for Ns)."""
    return bool(_COMPLETE.search(text))


def normalize_for_stable_compare(text: str) -> str:
    """Drop volatile footer lines so idle detection works after output ends."""
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _FOOTER_START.match(line) or _FOOTER_START.match(stripped):
            continue
        if re.search(r"\|\s*🌕\s+\d", line):
            continue
        if "bypass permissions" in line:
            continue
        kept.append(line)
    return "\n".join(kept)


def _norm_line(line: str) -> str:
    """Collapse internal whitespace so terminal re-wrapping doesn't defeat compare."""
    return re.sub(r"\s+", " ", line.strip())


def new_content_since(reply: str, last_sent: str) -> str:
    """Return only the part of `reply` not already covered by `last_sent`.

    Guards against duplicate Telegram messages where a later capture repeats an
    earlier (partial) send as its leading block — e.g. a mid-stream send followed
    by the completed turn, or a verbatim re-send. Comparison is line-based on
    normalized non-blank lines, so whitespace/wrapping differences don't matter.

    Only strips when `last_sent` is fully a leading block of `reply` (the precise
    "repeats the previous message" case); an otherwise-different reply is returned
    unchanged. Returns "" when `reply` adds nothing beyond `last_sent`.
    """
    if not last_sent.strip() or not reply.strip():
        return reply

    prev = [_norm_line(l) for l in last_sent.splitlines() if l.strip()]
    if not prev:
        return reply

    cur_raw = reply.splitlines()
    cur_norm = [_norm_line(l) for l in cur_raw if l.strip()]
    n = len(prev)
    if len(cur_norm) < n or cur_norm[:n] != prev:
        return reply  # not a continuation of the previous send → keep full reply

    # Drop the first n non-blank lines (the repeated block) from the original text.
    seen = 0
    idx = 0
    while idx < len(cur_raw) and seen < n:
        if cur_raw[idx].strip():
            seen += 1
        idx += 1
    tail = cur_raw[idx:]
    while tail and not tail[0].strip():
        tail.pop(0)
    while tail and not tail[-1].strip():
        tail.pop()
    return "\n".join(tail).strip()


def should_text_fallback(
    reply: str, last_sent: str, since_extract: float, threshold: float
) -> bool:
    """Whether to force-send `reply` as a 90s text catch-up.

    Fires when the completion marker was missed but the extracted reply has been
    stable (`since_extract`) for at least `threshold` seconds and still differs
    from what was last sent, so a finished answer never sits unsent. A
    non-positive threshold disables the fallback.
    """
    if threshold <= 0:
        return False
    if not reply or not reply.strip():
        return False
    if reply == last_sent:
        return False
    return since_extract >= threshold


def _extract_after_crunched(lines: list[str]) -> str:
    crunch_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if _COMPLETE.search(lines[i]):
            crunch_idx = i
            break
    if crunch_idx < 0:
        return ""

    end = crunch_idx
    start = _find_crunch_start(lines, crunch_idx)

    body: list[str] = []
    for i in range(max(0, start), end):
        raw = lines[i]
        stripped = raw.strip()
        if _BANNER.match(stripped):
            continue
        if _FOOTER_START.match(raw) or _FOOTER_START.match(stripped):
            continue
        if re.match(r"^\s*⏵⏵ bypass permissions", raw):
            continue
        if _SKIP_LINE.search(raw) or _SKIP_LINE.search(stripped):
            continue
        if i == max(0, start):
            cleaned = _strip_assistant_prefix(raw)
            if cleaned:
                body.append(cleaned)
        else:
            body.append(raw.rstrip())

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    body = _strip_leading_noise(body)

    out = "\n".join(body).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def _extract_after_user_prompt(lines: list[str]) -> str:
    last_user = -1
    for i, line in enumerate(lines):
        m = _USER_PROMPT.match(line.strip())
        if m and m.group(1).strip() and not m.group(1).strip().startswith("/clear"):
            last_user = i

    if last_user < 0:
        return ""

    start = -1
    for i in range(last_user + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith(("⏺", "✻")):
            start = i
            break

    if start < 0:
        return ""

    body: list[str] = []
    for i in range(start, len(lines)):
        raw = lines[i]
        stripped = raw.strip()

        if i > start:
            if _is_boundary_line(raw):
                break
            if _COMPLETE.search(raw):
                break

        if _BANNER.match(stripped):
            continue
        if _SKIP_LINE.search(raw) or _SKIP_LINE.search(stripped):
            continue

        if i == start:
            cleaned = _strip_assistant_prefix(raw)
            if cleaned:
                body.append(cleaned)
        else:
            body.append(raw.rstrip())

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    out = "\n".join(body).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out



def _extract_before_footer(lines: list[str]) -> str:
    """Fallback: last content block before the bottom Claude Code footer."""
    end = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if _FOOTER_START.match(lines[i]):
            end = i
            continue
        if _SEPARATOR.match(lines[i].strip()) and i < len(lines) - 3:
            end = i
            break
        if lines[i].strip().startswith("❯"):
            end = i
            break
        if _COMPLETE.search(lines[i]):
            end = i
            break
        if lines[i].strip():
            break

    start = end - 1
    while start >= 0 and _is_scrollback_junk(lines[start]):
        start -= 1
    start += 1

    body: list[str] = []
    for i in range(max(0, start), max(0, end)):
        raw = lines[i]
        stripped = raw.strip()
        if _BANNER.match(stripped):
            continue
        if _FOOTER_START.match(raw):
            continue
        if _COMPLETE.search(raw):
            continue
        if _is_scrollback_junk(raw) and not re.match(r"^\s{2,}\S", raw):
            continue
        body.append(raw.rstrip())

    body = _strip_leading_noise(body)
    out = "\n".join(body).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    if len(out) < 40:
        return ""
    return out


def extract_latest_reply(text: str) -> str:
    """Return the latest assistant message body, or empty string."""
    if not text or not text.strip():
        return ""

    lines = text.splitlines()

    reply = _extract_after_crunched(lines)
    if reply:
        return reply

    reply = _extract_after_user_prompt(lines)
    if reply:
        return reply

    return _extract_before_footer(lines)


def main() -> int:
    import argparse
    import subprocess
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Extract assistant reply from iTerm scrollback")
    parser.add_argument("--tail", type=int, default=0)
    parser.add_argument("--text", help="Read from string instead of iTerm")
    args = parser.parse_args()

    if args.text is not None:
        text = args.text
    else:
        root = Path(__file__).resolve().parent
        r = subprocess.run(
            [sys.executable, str(root / "iterm-capture.py"), "--tail", str(args.tail)],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if r.returncode != 0:
            print(r.stderr or r.stdout, file=sys.stderr)
            return r.returncode
        text = r.stdout or ""

    reply = extract_latest_reply(text)
    if reply:
        sys.stdout.write(reply)
        if not reply.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
