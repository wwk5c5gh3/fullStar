# Auto-default on interactive prompts (monitor) — Design

**Date:** 2026-06-19
**Status:** Design — pending user spec review

## Goal

When a monitored terminal session shows an interactive arrow-select prompt
(Claude Code's `AskUserQuestion` menu, or a yes/no confirmation — both render as
the same `❯ … Enter to select` widget) and nobody responds within ~1 minute, the
monitor auto-selects the highlighted first option by pressing Enter. This
unblocks sessions that are being driven remotely over Telegram, where the
operator cannot see or navigate the on-screen menu.

Applies to **all sessions the monitor watches** (per-monitor; each `iterm-monitor`
instance gets the behavior since it lives in the poll loop).

## Background

`term-bridge/iterm-monitor.py` `run_loop` already polls the target every
`interval` (~5s), normalizes each capture (`normalize_for_stable_compare`),
tracks screen stability (`last_stable`, `stable_count`) and idle time
(`last_extract_change_at`), and drives idle behaviors (90s text fallback, 60s
screenshot). Auto-default is one more idle behavior in the same loop.

## Detection — new pure module `term-bridge/interactive_prompt.py`

- `detect_select_prompt(capture: str) -> bool` — returns True when the capture
  contains the arrow-select widget signature. Signature = presence of the footer
  hint (`Enter to select` together with a navigation hint `↑`/`↓`, or the literal
  `to navigate`) **and** a selection cursor `❯`. Both menus and yes/no confirms
  in Claude Code use this widget, so one detector covers both.
- Pure and unit-testable against captured fixtures (positive: real menu text;
  negative: normal assistant output, free-text prompts with no footer).
- Codex's confirm style can be added later as an alternate signature; out of
  scope now.

## Action — a "send a key" primitive (shared with the command-menu spec)

The current inject path (`terminal-inject.py` / `iterm-inject.py`, selected by
`term_backend.inject_script()`) refuses empty text and always pastes. Add a
key-only mode so we can press Enter without typing text:

- New CLI flag `--key {enter|esc}` on both backend inject scripts.
  - `terminal-inject.py` (Terminal.app): focus the target window/tab, then
    `keystroke return` / `key code 53` (Esc) via System Events — reuse the
    existing focus/frontmost logic in `terminal_inject_lib`.
  - `iterm-inject.py` (iTerm): write `\n` for enter / `\x1b` for esc to the
    target session via the existing iTerm write path.
- When `--key` is given, `text` is not required and nothing is pasted.
- `term_backend.inject_script()` already returns the right script per backend.

Auto-default fires `inject --key enter` against the monitor's resolved target.

## Timing — in `run_loop`

- Read `auto_default_seconds` from env `TG_ITERM_MONITOR_AUTO_DEFAULT` (default
  `60`; `0`/`off`/`false`/`no` disables). Helper mirrors the existing
  `_screenshot_idle_seconds` / `_text_fallback_seconds` parsers.
- Track when the current stable screen first appeared. The loop already resets
  `stable_count = 0` and updates `last_stable` whenever `stable_key` changes —
  add a `stable_since` timestamp set at that same point.
- Each poll, if `auto_default_seconds > 0` and `detect_select_prompt(current)`
  and `now - stable_since >= auto_default_seconds` and this stable prompt has
  not already been auto-fired, then: fire `inject --key enter`, send a Telegram
  notice, and mark this prompt fired.
- **One-shot per prompt, fresh timer per new menu:** the fired-marker is keyed
  by the current `stable_key` (the normalized screen). A different menu produces
  a different `stable_key`, so it gets its own 60s window and its own single
  fire. Persist the marker in a monitor state file
  (`_monitor_file("auto-default-mark")`) holding the last fired `stable_key`
  hash, consistent with the existing `screenshot-mark` pattern.

## Decision helper (testable)

Extract the fire/skip decision into a pure function so timing logic is unit
tested without a terminal:

```
should_auto_default(
    *, is_prompt: bool, stable_elapsed: float, threshold: float,
    stable_key: str, last_fired_key: str
) -> bool
```
Returns True iff `threshold > 0 and is_prompt and stable_elapsed >= threshold
and stable_key != last_fired_key`. The loop owns the side effects (inject,
notify, persist marker).

## Telegram notice

After a successful fire, send (via the monitor's existing `_send_tg`) a short
notice, default `⏱ 1 分钟未选择，已默认选择第一项`, configurable via
`TG_ITERM_AUTO_DEFAULT_CAPTION`. Failures to inject are logged to the monitor
log and do not mark the prompt fired (so a transient failure can retry next
poll).

## Error handling

- Non-macOS / inject failure → log to monitor log; do not set the fired marker.
- Detection is best-effort string matching; a false negative just means no
  auto-default (safe). A false positive would press Enter on a non-menu — guard
  by requiring BOTH the footer hint and the `❯` cursor to reduce this to near
  zero on normal output.

## Testing

- `interactive_prompt.detect_select_prompt`: positive fixtures (real
  `AskUserQuestion` capture, a yes/no confirm), negatives (plain output,
  free-text prompt, empty).
- `should_auto_default`: threshold 0 disables; not-a-prompt → False; elapsed <
  threshold → False; elapsed ≥ threshold and new key → True; same key as
  last_fired → False.
- `--key enter|esc` inject mode via `--dry-run` (prints intended keystroke, no
  osascript), on any platform.

## Non-goals

- No per-option intelligence (always the highlighted/first option).
- No detection of Codex-specific prompt styles (later).
- No retarget of which session the monitor watches (separate concern).
