# Monitor Auto-Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a monitored terminal shows an interactive `❯ … Enter to select` prompt and nobody responds for ~60s, the monitor auto-presses Enter (selects the first option), so remotely-driven sessions self-unblock.

**Architecture:** A pure detector + decision module (`interactive_prompt.py`), a new key-only inject mode (`--key {enter|esc}`) added to both backend inject scripts, and wiring in `iterm-monitor.py`'s poll loop that fires the key after the prompt has been on-screen, unchanged, past the threshold — once per distinct prompt.

**Tech Stack:** Python 3 (stdlib only), pytest, AppleScript via `osascript`, macOS Terminal.app + iTerm2.

## Global Constraints

- Python 3, stdlib only — no new dependencies.
- macOS only for the actual `osascript` run (`sys.platform == "darwin"`); `--dry-run` works on any platform.
- Pure logic (detection, decision, AppleScript builders) has no side effects and is unit-tested; the monitor loop owns side effects (inject, notify, persist).
- Threshold env `TG_ITERM_MONITOR_AUTO_DEFAULT` default `60`; `0`/`off`/`false`/`no` disables. Mirror the existing `_screenshot_idle_seconds`/`_text_fallback_seconds` parsers.
- Auto-fire is **one-shot per distinct prompt** (keyed by the normalized stable screen) with a **fresh timer per new menu**.
- TG notice caption env `TG_ITERM_AUTO_DEFAULT_CAPTION`, default `⏱ 1 分钟未选择，已默认选择第一项`.
- Backend selected by `term_backend.inject_script()`; default backend is `terminal`.
- Test files live in `term-bridge/` as `test_*.py`, run with `cd term-bridge && python -m pytest`.

---

### Task 1: Detection + decision helpers (`interactive_prompt.py`)

**Files:**
- Create: `term-bridge/interactive_prompt.py`
- Test: `term-bridge/test_interactive_prompt.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `detect_select_prompt(capture: str) -> bool`
  - `should_auto_default(*, is_prompt: bool, stable_elapsed: float, threshold: float, stable_key: str, last_fired_key: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_interactive_prompt.py
"""Tests for interactive_prompt — detect arrow-select menus + auto-default decision."""
from __future__ import annotations

import interactive_prompt as ip

MENU = (
    "? Project location\n"
    "❯ 1. Point me to the path\n"
    "  2. It's a different repo\n"
    "  3. Describe the bug first\n"
    "  4. Type something.\n"
    "Enter to select · ↑/↓ to navigate · Esc to cancel\n"
)

PLAIN = "Listed 1 directory\nThe working directory is empty.\nDone.\n"


def test_detects_select_menu():
    assert ip.detect_select_prompt(MENU) is True


def test_plain_output_is_not_a_prompt():
    assert ip.detect_select_prompt(PLAIN) is False


def test_footer_without_cursor_is_not_a_prompt():
    # Footer text present but no ❯ cursor → not a live menu
    assert ip.detect_select_prompt("Enter to select · ↑/↓ to navigate\n") is False


def test_empty_is_not_a_prompt():
    assert ip.detect_select_prompt("") is False


def test_should_default_disabled_when_threshold_zero():
    assert ip.should_auto_default(
        is_prompt=True, stable_elapsed=999, threshold=0, stable_key="a", last_fired_key=""
    ) is False


def test_should_default_false_when_not_prompt():
    assert ip.should_auto_default(
        is_prompt=False, stable_elapsed=999, threshold=60, stable_key="a", last_fired_key=""
    ) is False


def test_should_default_false_before_threshold():
    assert ip.should_auto_default(
        is_prompt=True, stable_elapsed=30, threshold=60, stable_key="a", last_fired_key=""
    ) is False


def test_should_default_true_after_threshold_new_prompt():
    assert ip.should_auto_default(
        is_prompt=True, stable_elapsed=61, threshold=60, stable_key="a", last_fired_key="b"
    ) is True


def test_should_default_false_when_already_fired_for_this_prompt():
    assert ip.should_auto_default(
        is_prompt=True, stable_elapsed=61, threshold=60, stable_key="a", last_fired_key="a"
    ) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_interactive_prompt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interactive_prompt'`

- [ ] **Step 3: Write minimal implementation**

```python
# term-bridge/interactive_prompt.py
"""Detect interactive arrow-select prompts and decide when to auto-default.

Pure helpers for iterm-monitor: detect Claude Code's AskUserQuestion / yes-no
widget (a `❯ … Enter to select` list) and decide when a stuck menu should be
auto-resolved by pressing Enter. The monitor loop owns the side effects.
"""
from __future__ import annotations

_CURSOR = "❯"


def detect_select_prompt(capture: str) -> bool:
    """True when the capture shows an arrow-select menu awaiting a choice."""
    if not capture:
        return False
    low = capture.lower()
    has_footer = "enter to select" in low and (
        "to navigate" in low or "↑" in capture or "↓" in capture
    )
    return has_footer and _CURSOR in capture


def should_auto_default(
    *,
    is_prompt: bool,
    stable_elapsed: float,
    threshold: float,
    stable_key: str,
    last_fired_key: str,
) -> bool:
    """Fire iff enabled, a prompt is shown, it has been stable past the
    threshold, and we have not already fired for this exact screen."""
    if threshold <= 0 or not is_prompt:
        return False
    if stable_elapsed < threshold:
        return False
    return stable_key != last_fired_key
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_interactive_prompt.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/interactive_prompt.py term-bridge/test_interactive_prompt.py
git commit -m "feat: interactive_prompt detection + auto-default decision"
```

---

### Task 2: `--key {enter|esc}` mode — Terminal.app backend

**Files:**
- Modify: `term-bridge/terminal_inject_lib.py` (add `build_key_script`)
- Modify: `term-bridge/terminal-inject.py` (add `inject_key` + `--key` flag)
- Test: `term-bridge/test_terminal_key.py`

**Interfaces:**
- Consumes: `terminal_inject_lib._window_ref` (existing internal helper).
- Produces:
  - `terminal_inject_lib.build_key_script(*, window: int | None, tab: int, key: str) -> str`
  - `terminal-inject.py` CLI flag `--key {enter,esc}` (mutually exclusive with pasting text); `--dry-run` prints `would press <key> to Terminal (<label>)`.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_terminal_key.py
"""Tests for the --key (enter/esc) mode of the Terminal.app inject backend."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import terminal_inject_lib as lib

CLI = Path(__file__).resolve().parent / "terminal-inject.py"


def test_key_script_enter_uses_keystroke_return():
    s = lib.build_key_script(window=1, tab=2, key="enter")
    assert "keystroke return" in s
    assert "tab 2" in s


def test_key_script_esc_uses_key_code_53():
    s = lib.build_key_script(window=None, tab=1, key="esc")
    assert "key code 53" in s


def test_cli_dry_run_key_enter():
    r = subprocess.run(
        [sys.executable, str(CLI), "--key", "enter", "--tab", "3", "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    assert "would press enter" in r.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_terminal_key.py -v`
Expected: FAIL with `AttributeError: module 'terminal_inject_lib' has no attribute 'build_key_script'`

- [ ] **Step 3: Write minimal implementation**

Add to `term-bridge/terminal_inject_lib.py`:

```python
_KEY_ACTIONS = {"enter": "keystroke return", "esc": "key code 53"}


def build_key_script(*, window: int | None, tab: int, key: str) -> str:
    """`on run` AppleScript that focuses the target Terminal tab and presses one key."""
    if key not in _KEY_ACTIONS:
        raise ValueError(f"unknown key: {key!r}")
    win = _window_ref(window)
    action = _KEY_ACTIONS[key]
    focus_window = (
        f"    try\n"
        f"        set index of {win} to 1\n"
        f"    end try\n"
        f"    try\n"
        f"        set selected of tab {int(tab)} of {win} to true\n"
        f"    end try\n"
    )
    return (
        "on run\n"
        '    if application "Terminal" is not running then error "No Terminal running"\n'
        '    tell application "Terminal"\n'
        f"{focus_window}"
        "    end tell\n"
        '    tell application "System Events"\n'
        '        set frontmost of process "Terminal" to true\n'
        "        repeat 40 times\n"
        '            if frontmost of process "Terminal" then exit repeat\n'
        "            delay 0.05\n"
        "        end repeat\n"
        f"        {action}\n"
        "    end tell\n"
        "end run\n"
    )
```

Add to `term-bridge/terminal-inject.py` — a key-inject function (after `inject`):

```python
from terminal_inject_lib import build_inject_script, build_key_script  # noqa: E402 (update existing import)


def inject_key(key: str, *, target: ItermTarget | None = None) -> tuple[int, str]:
    if sys.platform != "darwin":
        return 1, "Terminal inject requires macOS"
    _load_env()
    t = target or resolve_target()
    script = build_key_script(window=t.window, tab=t.tab, key=key)
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        if _needs_access_hint(out):
            out += _ACCESS_HINT
        return r.returncode, out or "osascript failed"
    return 0, out or "ok"
```

In `main()`, add the flag and branch (place `--key` parsing with the other args; branch before the text path):

```python
    parser.add_argument("--key", choices=("enter", "esc"), help="Press a single key instead of typing text")
    ...
    if args.key:
        if args.dry_run:
            print(f"would press {args.key} to Terminal ({target.label()})")
            return 0
        code, out = inject_key(args.key, target=target)
        if code != 0:
            print(out, file=sys.stderr)
            return code
        print(f"{out} [{target.label()}]")
        return 0
```

(The existing `text`/`stdin` reading must not run when `--key` is set — guard the `text = args.text if ...` line with `if not args.key:` or place the `--key` branch before it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_terminal_key.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite**

Run: `cd term-bridge && python -m pytest -q`
Expected: all pass (no regression in existing terminal-inject tests).

- [ ] **Step 6: Commit**

```bash
git add term-bridge/terminal_inject_lib.py term-bridge/terminal-inject.py term-bridge/test_terminal_key.py
git commit -m "feat: --key enter/esc mode for Terminal.app inject backend"
```

---

### Task 3: `--key {enter|esc}` mode — iTerm backend

**Files:**
- Modify: `term-bridge/iterm-inject.py` (add `_key_applescript`, `inject_key`, `--key` flag)
- Test: `term-bridge/test_iterm_key.py`

**Interfaces:**
- Consumes: `iterm_target.applescript_session_block`, `applescript_session_close`, `apply_target_env`, `resolve_target` (existing).
- Produces: `iterm-inject.py` CLI flag `--key {enter,esc}`; `--dry-run` prints `would press <key> to iTerm (<label>)`. Enter → `write text ""` (iTerm appends a newline = Return); Esc → `write text (character id 27) without newline`.

**Note for implementer:** read `iterm_target.applescript_session_block()` / `applescript_session_close()` first to match the exact indentation of the `write text` line (the existing `APPLESCRIPT` indents it 20 spaces).

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_iterm_key.py
"""Tests for the --key (enter/esc) mode of the iTerm inject backend."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import importlib.util

_CLI = Path(__file__).resolve().parent / "iterm-inject.py"
_spec = importlib.util.spec_from_file_location("iterm_inject_mod", _CLI)
iterm_inject_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iterm_inject_mod)


def test_key_applescript_enter_writes_empty_line():
    s = iterm_inject_mod._key_applescript("enter")
    assert 'write text ""' in s


def test_key_applescript_esc_writes_escape_char():
    s = iterm_inject_mod._key_applescript("esc")
    assert "character id 27" in s


def test_cli_dry_run_key_enter():
    r = subprocess.run(
        [sys.executable, str(_CLI), "--key", "enter", "--tab", "2", "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    assert "would press enter" in r.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_iterm_key.py -v`
Expected: FAIL with `AttributeError: ... has no attribute '_key_applescript'`

- [ ] **Step 3: Write minimal implementation**

Add to `term-bridge/iterm-inject.py` (after the `APPLESCRIPT` constant):

```python
def _key_applescript(key: str) -> str:
    """AppleScript that sends a single key to the target iTerm session.

    enter → write an empty line (iTerm appends newline = Return).
    esc   → write the ESC byte without a trailing newline.
    """
    if key == "enter":
        action = '                    write text ""'
    elif key == "esc":
        action = "                    write text (character id 27) without newline"
    else:
        raise ValueError(f"unknown key: {key!r}")
    return (
        "on run\n"
        + applescript_session_block()
        + "\n" + action + "\n"
        + applescript_session_close(extra_close=0)
        + '\n    tell application "iTerm" to activate\nend run\n'
    )


def inject_key(key: str, *, target: ItermTarget | None = None) -> tuple[int, str]:
    if sys.platform != "darwin":
        return 1, "iTerm inject requires macOS"
    _load_env()
    t = target or resolve_target()
    env = apply_target_env(t)
    r = subprocess.run(
        ["osascript", "-e", _key_applescript(key)],
        env=env, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode, out or ("ok" if r.returncode == 0 else "osascript failed")
```

In `main()`, add the flag and branch (before the `text = args.text ...` line):

```python
    parser.add_argument("--key", choices=("enter", "esc"), help="Press a single key instead of typing text")
    ...
    if args.key:
        if args.dry_run:
            print(f"would press {args.key} to iTerm ({target.label()})")
            return 0
        code, out = inject_key(args.key, target=target)
        if code != 0:
            print(out, file=sys.stderr)
            return code
        print(f"{out} [{target.label()}]")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_iterm_key.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/iterm-inject.py term-bridge/test_iterm_key.py
git commit -m "feat: --key enter/esc mode for iTerm inject backend"
```

---

### Task 4: Wire auto-default into `iterm-monitor.py`

**Files:**
- Modify: `term-bridge/iterm-monitor.py`
- Test: `term-bridge/test_monitor_auto_default.py`

**Interfaces:**
- Consumes: `interactive_prompt.detect_select_prompt`, `interactive_prompt.should_auto_default`, `term_backend.inject_script`, the existing `_send_tg`, `_monitor_file`, `normalize_for_stable_compare`.
- Produces: `_auto_default_seconds() -> float` env parser; `_auto_default_caption() -> str`; `_read_auto_default_mark()/_write_auto_default_mark(key)`; `_inject_key(key) -> tuple[int,str]`; auto-default firing inside `run_loop`.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_monitor_auto_default.py
"""Tests for the monitor's auto-default env parsing + key inject command build."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MON = Path(__file__).resolve().parent / "iterm-monitor.py"
_spec = importlib.util.spec_from_file_location("iterm_monitor_mod", _MON)
mon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mon)


def test_auto_default_seconds_default(monkeypatch):
    monkeypatch.delenv("TG_ITERM_MONITOR_AUTO_DEFAULT", raising=False)
    assert mon._auto_default_seconds() == 60.0


def test_auto_default_seconds_off(monkeypatch):
    monkeypatch.setenv("TG_ITERM_MONITOR_AUTO_DEFAULT", "off")
    assert mon._auto_default_seconds() == 0.0


def test_auto_default_seconds_custom(monkeypatch):
    monkeypatch.setenv("TG_ITERM_MONITOR_AUTO_DEFAULT", "30")
    assert mon._auto_default_seconds() == 30.0


def test_auto_default_caption_default(monkeypatch):
    monkeypatch.delenv("TG_ITERM_AUTO_DEFAULT_CAPTION", raising=False)
    assert "默认" in mon._auto_default_caption()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_monitor_auto_default.py -v`
Expected: FAIL with `AttributeError: ... has no attribute '_auto_default_seconds'`

- [ ] **Step 3: Write minimal implementation**

Add imports near the top of `iterm-monitor.py` (with the other `from ... import`):

```python
from interactive_prompt import detect_select_prompt, should_auto_default  # noqa: E402
```

Add helpers (near `_screenshot_idle_seconds`/`_text_fallback_seconds`):

```python
def _auto_default_seconds() -> float:
    """Auto-press Enter on a stuck select-prompt after this long. Env
    TG_ITERM_MONITOR_AUTO_DEFAULT (default 60, 0/off disables)."""
    raw = os.environ.get("TG_ITERM_MONITOR_AUTO_DEFAULT", "60").strip()
    if raw.lower() in ("", "0", "false", "no", "off"):
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 60.0


def _auto_default_caption() -> str:
    return os.environ.get(
        "TG_ITERM_AUTO_DEFAULT_CAPTION", "⏱ 1 分钟未选择，已默认选择第一项"
    ).strip() or "⏱ 已默认选择第一项"


def _read_auto_default_mark() -> str:
    p = _monitor_file("auto-default-mark")
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _write_auto_default_mark(key: str) -> None:
    p = _monitor_file("auto-default-mark")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key, encoding="utf-8")


def _inject_key(key: str) -> tuple[int, str]:
    cmd = [sys.executable, str(term_backend.inject_script()), "--key", key]
    t = resolve_target()
    if t.window is None:
        cmd.append("--front-window")
    else:
        cmd.extend(["--window", str(t.window)])
    cmd.extend(["--tab", str(t.tab)])
    r = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=30,
        env=os.environ.copy(), stdin=subprocess.DEVNULL,
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
```

In `run_loop`, after `screenshot_idle = _screenshot_idle_seconds()` etc., add:

```python
    auto_default = _auto_default_seconds()
```

Track when the current stable screen began. Initialise before the loop:

```python
    stable_since = time.time()
```

In the block that runs when `stable_key != last_stable` (the screen changed), set:

```python
            stable_since = time.time()
```

Add the auto-default check inside the loop (after the screenshot-idle block, before `if once:`):

```python
        if auto_default > 0:
            is_prompt = detect_select_prompt(current)
            if should_auto_default(
                is_prompt=is_prompt,
                stable_elapsed=time.time() - stable_since,
                threshold=auto_default,
                stable_key=stable_key,
                last_fired_key=_read_auto_default_mark(),
            ):
                k_code, k_msg = _inject_key("enter")
                if k_code == 0:
                    _write_auto_default_mark(stable_key)
                    _send_tg(_auto_default_caption(), "plain")
                    print(f"[{ts}] auto-default: pressed enter ({k_msg})", flush=True)
                else:
                    print(f"[{ts}] auto-default error: {k_msg}", flush=True)
```

Also add `auto-default-mark` to the `--reset` cleanup list in `main()`:

```python
        for kind in ("state", "last-sent", "last-sent-at", "screenshot-mark", "auto-default-mark"):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_monitor_auto_default.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full suite**

Run: `cd term-bridge && python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add term-bridge/iterm-monitor.py term-bridge/test_monitor_auto_default.py
git commit -m "feat: auto-default Enter on stuck select-prompts in monitor loop"
```

---

## Self-Review

**Spec coverage:**
- Detection of `❯ … Enter to select` widget → Task 1 `detect_select_prompt`. ✓
- One-shot-per-prompt / fresh-timer decision → Task 1 `should_auto_default` + Task 4 mark file keyed by `stable_key`. ✓
- `--key enter|esc` on Terminal backend → Task 2; iTerm backend → Task 3. ✓
- Threshold env (default 60, off disables) → Task 4 `_auto_default_seconds`. ✓
- Fire Enter via backend inject + TG notice + persist mark → Task 4. ✓
- `--reset` clears the new mark → Task 4 Step 3. ✓
- Testing per module → all tasks ship tests. ✓

**Placeholder scan:** No TBD/TODO; all code steps complete. The implementer note in Task 3 (read `applescript_session_block` for indentation) points at existing code, not a placeholder.

**Type consistency:** `should_auto_default(*, is_prompt, stable_elapsed, threshold, stable_key, last_fired_key)` defined in Task 1 and called identically in Task 4. `build_key_script(*, window, tab, key)` (Task 2) and `_key_applescript(key)` (Task 3) match their callers. `_inject_key(key)` builds the CLI added in Tasks 2/3 (`--key`, `--window/--front-window`, `--tab`). `_monitor_file(kind)` usage matches existing signature.
