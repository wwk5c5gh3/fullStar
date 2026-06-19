# TG Command Menu + Session Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the bot's commands in Telegram's `/` menu (`setMyCommands`), present inline-keyboard sub-commands for `/new`/`/format`/`/shot`/`/model`/`/think`, and add session-control commands (`/stop`/`/reset`/`/compact`/`/model`/`/think`) that inject keystrokes/commands into the active Claude Code session.

**Architecture:** Pure logic modules `tg_menu.py` (command list, sub-menus, callback parse/dispatch) and `tg_session_control.py` (command → inject-action mapping) hold all the testable behavior. The Telegram glue (`setMyCommands` via `post_init`, inline keyboards, `CallbackQueryHandler`) goes in `tg-relay.py main()`; the session-control slash commands wire into `tg_relay_patches.py`. Injection reuses `term_backend.inject_script()` (text) and its `--key {enter|esc}` mode (added in the merged auto-default feature).

**Tech Stack:** Python 3 (stdlib only for our modules; `python-telegram-bot` already a dependency), pytest, AppleScript via `osascript`.

## Global Constraints

- Python 3, stdlib only in `term-bridge/` modules; `python-telegram-bot` is already installed and used by `tg-relay.py`.
- Pure modules (`tg_menu`, `tg_session_control`) have no side effects and are unit-tested; the relay glue is thin.
- Callback data format `action:value` (e.g. `new:claude`, `fmt:html`, `model:opus`, `think:high`).
- Session-control assumes a **Claude Code** session. Verified semantics (2026-06-19): `/stop` → exactly ONE Esc (two = rewind); `/reset` → `/clear`; `/compact` → `/compact`; `/model <alias>` (opus|sonnet|haiku|fable); `/think <level>` → `/effort <level>` (low|medium|high|xhigh|max|auto).
- Session injects target the active tab via `iterm_target.resolve_target` (env `TG_ITERM_WINDOW`/`TG_ITERM_TAB`).
- Test files live in `term-bridge/` as `test_*.py`, run with `cd term-bridge && python -m pytest`.

---

### Task 1: Menu data + callback logic (`tg_menu.py`)

**Files:**
- Create: `term-bridge/tg_menu.py`
- Test: `term-bridge/test_tg_menu.py`

**Interfaces:**
- Produces:
  - `MENU_COMMANDS: list[tuple[str, str]]` — `(command_without_slash, description)` for `setMyCommands` (Phase 1 set; Phase 2 extends).
  - `SUBMENUS: dict[str, list[tuple[str, str]]]` — parent command (with slash) → `[(button_label, callback_data)]`.
  - `menu_for_command(text: str) -> list[tuple[str, str]] | None` — buttons if `text` is a **bare** parent command (no args), else None.
  - `parse_callback(data: str) -> tuple[str, str]` — `"new:claude"` → `("new", "claude")`; no colon → `(data, "")`.
  - `callback_to_command(action: str, value: str) -> str | None` — `("new","claude")` → `"/new claude"`; unknown action → None.
  - `dispatch_callback(data: str, handle_command) -> str` — parse → map → call `handle_command(cmd)`; unknown → `未知操作: <data>`.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_tg_menu.py
"""Tests for tg_menu — command list, sub-menus, and callback dispatch."""
from __future__ import annotations

import tg_menu as m


def test_menu_commands_includes_core():
    cmds = [c for c, _ in m.MENU_COMMANDS]
    for expected in ("new", "tabs", "shot", "format", "devices", "check", "help"):
        assert expected in cmds


def test_submenus_for_parents():
    assert ("claude", "new:claude") in m.SUBMENUS["/new"]
    assert ("codex", "new:codex") in m.SUBMENUS["/new"]
    assert ("html", "fmt:html") in m.SUBMENUS["/format"]
    assert ("android", "shot:android") in m.SUBMENUS["/shot"]


def test_menu_for_command_bare_parent_returns_buttons():
    assert m.menu_for_command("/new") == m.SUBMENUS["/new"]
    assert m.menu_for_command("/format") == m.SUBMENUS["/format"]


def test_menu_for_command_with_args_returns_none():
    assert m.menu_for_command("/new claude fix bug") is None


def test_menu_for_command_non_submenu_returns_none():
    assert m.menu_for_command("/help") is None


def test_parse_callback():
    assert m.parse_callback("new:claude") == ("new", "claude")
    assert m.parse_callback("nocolon") == ("nocolon", "")


def test_callback_to_command():
    assert m.callback_to_command("new", "claude") == "/new claude"
    assert m.callback_to_command("fmt", "html") == "/format html"
    assert m.callback_to_command("shot", "android") == "/shot android"
    assert m.callback_to_command("bogus", "x") is None


def test_dispatch_callback_calls_handler():
    seen = {}
    def fake_handle(cmd):
        seen["cmd"] = cmd
        return "ok"
    assert m.dispatch_callback("new:claude", fake_handle) == "ok"
    assert seen["cmd"] == "/new claude"


def test_dispatch_callback_unknown():
    assert "未知操作" in m.dispatch_callback("bogus:x", lambda c: "ok")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_tg_menu.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tg_menu'`

- [ ] **Step 3: Write minimal implementation**

```python
# term-bridge/tg_menu.py
"""Telegram bot command menu + inline sub-command definitions and callback logic.

Pure single-source-of-truth for `setMyCommands`, the inline-keyboard sub-menus,
and the callback_data → slash-command mapping. The relay glue converts these to
telegram objects and calls handle_command.
"""
from __future__ import annotations

from typing import Callable

MENU_COMMANDS: list[tuple[str, str]] = [
    ("new", "新 tab 启动 agent 会话"),
    ("tabs", "列出终端标签"),
    ("shot", "截图当前屏幕"),
    ("format", "设置回传格式"),
    ("devices", "列出设备"),
    ("check", "环境检查"),
    ("help", "显示可用命令"),
]

SUBMENUS: dict[str, list[tuple[str, str]]] = {
    "/new": [("claude", "new:claude"), ("codex", "new:codex")],
    "/format": [
        ("html", "fmt:html"),
        ("markdown", "fmt:markdown"),
        ("plain", "fmt:plain"),
        ("screenshot", "fmt:screenshot"),
    ],
    "/shot": [("android", "shot:android"), ("ios", "shot:ios")],
}

# callback action prefix → slash command base
_ACTION_TO_CMD: dict[str, str] = {
    "new": "/new",
    "fmt": "/format",
    "shot": "/shot",
    "model": "/model",
    "think": "/think",
}


def menu_for_command(text: str) -> list[tuple[str, str]] | None:
    """Buttons for a bare parent command (no args), else None."""
    parts = text.strip().split()
    if len(parts) != 1:
        return None
    cmd = parts[0].lower().split("@")[0]
    return SUBMENUS.get(cmd)


def parse_callback(data: str) -> tuple[str, str]:
    action, _sep, value = data.partition(":")
    return (action, value)


def callback_to_command(action: str, value: str) -> str | None:
    base = _ACTION_TO_CMD.get(action)
    if base is None:
        return None
    return f"{base} {value}".strip() if value else base


def dispatch_callback(data: str, handle_command: Callable[[str], str]) -> str:
    action, value = parse_callback(data)
    cmd = callback_to_command(action, value)
    if cmd is None:
        return f"未知操作: {data}"
    return handle_command(cmd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_tg_menu.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/tg_menu.py term-bridge/test_tg_menu.py
git commit -m "feat: tg_menu command list + sub-menus + callback dispatch"
```

---

### Task 2: Wire menu + sub-commands into the relay (`tg-relay.py`)

**Files:**
- Modify: `tg-relay/tg-relay.py` (`main()` and module top)
- Test: `term-bridge/test_tg_relay_import.py`

**Interfaces:**
- Consumes: `tg_menu.MENU_COMMANDS`, `menu_for_command`, `dispatch_callback`; existing `_handle_command`, `_handle_natural_language`.
- Produces: `setMyCommands` registration at startup; inline-keyboard reply for bare sub-menu commands; a `CallbackQueryHandler` that runs `dispatch_callback(q.data, _handle_command)`.

**Note for implementer:** read the current `tg-relay.py main()` (it builds `Application`, adds `CommandHandler`/`MessageHandler`, runs polling). Make minimal additive edits. `python-telegram-bot` is installed.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_tg_relay_import.py
"""Smoke test: tg-relay imports with the menu wiring (catches glue/import breakage)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_relay_module_imports_and_has_menu():
    # term-bridge must be importable for the relay's `from tg_menu import ...`
    import sys
    sys.path.insert(0, str(ROOT / "term-bridge"))
    spec = importlib.util.spec_from_file_location("tg_relay_mod", ROOT / "tg-relay" / "tg-relay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    # the menu is imported at module scope and usable
    from tg_menu import MENU_COMMANDS
    assert len(MENU_COMMANDS) >= 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_tg_relay_import.py -v`
Expected: FAIL — at this point `tg-relay.py` does not yet `import tg_menu`; if the import line is added before term-bridge is on `sys.path` the exec fails. (If it already passes trivially, proceed — the real verification is Step 4 after the edits.)

- [ ] **Step 3: Write minimal implementation**

Near the top of `tg-relay/tg-relay.py`, after `ROOT = ...`, add term-bridge to the path and import the menu:

```python
sys.path.insert(0, str(ROOT / "term-bridge"))
from tg_menu import MENU_COMMANDS, dispatch_callback, menu_for_command  # noqa: E402
```

In `main()`, replace the telegram import + handler setup with the menu-aware version:

```python
    try:
        from telegram import (
            BotCommand,
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            Update,
        )
        from telegram.ext import (
            Application,
            CallbackQueryHandler,
            CommandHandler,
            MessageHandler,
            filters,
        )
    except ImportError:
        print("pip install python-telegram-bot", file=sys.stderr)
        return 1

    def _keyboard(rows):
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(label, callback_data=data)] for label, data in rows]
        )

    async def on_message(update: Update, context) -> None:
        if not update.message or not update.message.text:
            return
        text = update.message.text.strip()
        chat_id = update.effective_chat.id or 0
        if text.startswith("/"):
            sub = menu_for_command(text)
            if sub:
                await update.message.reply_text("请选择：", reply_markup=_keyboard(sub))
                return
            reply = _handle_command(text)
        else:
            reply = _handle_natural_language(chat_id, text)
        await update.message.reply_text(reply[:4000])

    async def on_callback(update: Update, context) -> None:
        q = update.callback_query
        if not q:
            return
        await q.answer()
        reply = dispatch_callback(q.data or "", _handle_command)
        await q.edit_message_text(reply[:4000])

    async def start_cmd(update: Update, context) -> None:
        await update.message.reply_text(_handle_command("/help"))

    async def post_init(app) -> None:
        try:
            await app.bot.set_my_commands([BotCommand(c, d) for c, d in MENU_COMMANDS])
        except Exception as e:  # menu is a convenience; never block startup
            print(f"set_my_commands failed: {e}", file=sys.stderr)

    app = Application.builder().token(token).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(filters.COMMAND, on_message))
    print(f"mobile-agent tg-relay listening (root={ROOT})")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0
```

(Keep the existing `--dry-run` block above this unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_tg_relay_import.py -v`
Expected: PASS (1 passed) — the module imports cleanly with the menu wiring.

- [ ] **Step 5: Dry-run smoke check**

Run: `cd /Users/maxwell/Documents/aiTrees/fullStar && python tg-relay/run_tg_relay.py --dry-run "/help"`
Expected: prints the `/help` text (confirms patched dispatch still works; the menu/callback glue is additive).

- [ ] **Step 6: Run the full suite + commit**

```bash
cd term-bridge && python -m pytest -q
```
Expected: all pass.

```bash
git add tg-relay/tg-relay.py term-bridge/test_tg_relay_import.py
git commit -m "feat: register setMyCommands + inline sub-menus + callback handler"
```

---

### Task 3: Session-control mapping (`tg_session_control.py`)

**Files:**
- Create: `term-bridge/tg_session_control.py`
- Test: `term-bridge/test_tg_session_control.py`

**Interfaces:**
- Produces:
  - `InjectAction` — `@dataclass(frozen=True)` `kind: str` (`"key"`|`"text"`), `payload: str`.
  - `MODELS: tuple[str, ...]` = `("opus", "sonnet", "haiku", "fable")`.
  - `EFFORT_LEVELS: tuple[str, ...]` = `("low", "medium", "high", "xhigh", "max", "auto")`.
  - `resolve_session_command(cmd: str, arg: str = "") -> InjectAction | None` — maps a session command (+optional arg) to an action; returns None when an arg is required but missing/invalid (caller shows buttons/usage).
  - `session_usage(cmd: str) -> str` — usage hint listing valid args for `/model`/`/think`.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_tg_session_control.py
"""Tests for tg_session_control — session command → inject action mapping."""
from __future__ import annotations

import tg_session_control as sc


def test_stop_is_single_esc_key():
    a = sc.resolve_session_command("/stop")
    assert a == sc.InjectAction(kind="key", payload="esc")


def test_reset_clears():
    assert sc.resolve_session_command("/reset") == sc.InjectAction(kind="text", payload="/clear")


def test_compact():
    assert sc.resolve_session_command("/compact") == sc.InjectAction(kind="text", payload="/compact")


def test_model_with_valid_alias():
    assert sc.resolve_session_command("/model", "opus") == sc.InjectAction(kind="text", payload="/model opus")


def test_model_without_arg_returns_none():
    assert sc.resolve_session_command("/model") is None


def test_model_invalid_alias_returns_none():
    assert sc.resolve_session_command("/model", "gpt9") is None


def test_think_maps_to_effort():
    assert sc.resolve_session_command("/think", "high") == sc.InjectAction(kind="text", payload="/effort high")


def test_think_without_arg_returns_none():
    assert sc.resolve_session_command("/think") is None


def test_think_invalid_level_returns_none():
    assert sc.resolve_session_command("/think", "turbo") is None


def test_unknown_command_returns_none():
    assert sc.resolve_session_command("/bogus") is None


def test_session_usage_lists_models():
    u = sc.session_usage("/model")
    assert "opus" in u and "sonnet" in u


def test_session_usage_lists_effort_levels():
    u = sc.session_usage("/think")
    assert "high" in u and "max" in u
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_tg_session_control.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tg_session_control'`

- [ ] **Step 3: Write minimal implementation**

```python
# term-bridge/tg_session_control.py
"""Map session-control commands to inject actions for the active Claude Code tab.

Verified Claude Code semantics (2026-06-19): /stop = one Esc, /reset = /clear,
/compact = /compact, /model <alias>, /think <level> = /effort <level>. The relay
executes a `text` action by typing it (+Enter) and a `key` action via the
backend `--key` mode.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InjectAction:
    kind: str     # "key" | "text"
    payload: str  # key name ("esc") or text to type ("/clear")


MODELS: tuple[str, ...] = ("opus", "sonnet", "haiku", "fable")
EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max", "auto")


def resolve_session_command(cmd: str, arg: str = "") -> InjectAction | None:
    cmd = cmd.strip().lower()
    arg = arg.strip().lower()
    if cmd == "/stop":
        return InjectAction(kind="key", payload="esc")
    if cmd == "/reset":
        return InjectAction(kind="text", payload="/clear")
    if cmd == "/compact":
        return InjectAction(kind="text", payload="/compact")
    if cmd == "/model":
        return InjectAction(kind="text", payload=f"/model {arg}") if arg in MODELS else None
    if cmd == "/think":
        return InjectAction(kind="text", payload=f"/effort {arg}") if arg in EFFORT_LEVELS else None
    return None


def session_usage(cmd: str) -> str:
    cmd = cmd.strip().lower()
    if cmd == "/model":
        return "用法: /model " + "|".join(MODELS) + "（或点按钮选择）"
    if cmd == "/think":
        return "用法: /think " + "|".join(EFFORT_LEVELS) + "（设置思考强度，等价 /effort）"
    return f"未知会话命令: {cmd}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_tg_session_control.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/tg_session_control.py term-bridge/test_tg_session_control.py
git commit -m "feat: tg_session_control command -> inject action mapping"
```

---

### Task 4: Wire session control + their sub-menus (`tg_relay_patches.py`, `tg_menu.py`)

**Files:**
- Modify: `tg-relay/tg_relay_patches.py` (add `_inject_key` + the session-command branch in `handle_command`; extend `/help`)
- Modify: `term-bridge/tg_menu.py` (add `/model`/`/think` to `SUBMENUS`; add the 5 session commands to `MENU_COMMANDS`)
- Test: `term-bridge/test_tg_session_wiring.py` (and extend `test_tg_menu.py`)

**Interfaces:**
- Consumes: `tg_session_control.resolve_session_command`, `session_usage`; `term_backend.inject_script`; existing `_inject_iterm`, `resolve_target`, `apply_target_env`.
- Produces: relay handling for `/stop`/`/reset`/`/compact`/`/model`/`/think`; `_inject_key(key, target=None) -> tuple[int,str]`; extended menu data.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_tg_session_wiring.py
"""Tests for the session-control menu additions + patches helper presence."""
from __future__ import annotations

import sys
from pathlib import Path

import tg_menu as m

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tg-relay"))
import tg_relay_patches as patches


def test_session_commands_in_menu():
    cmds = [c for c, _ in m.MENU_COMMANDS]
    for expected in ("stop", "reset", "compact", "model", "think"):
        assert expected in cmds


def test_model_and_think_submenus_exist():
    assert ("opus", "model:opus") in m.SUBMENUS["/model"]
    assert ("high", "think:high") in m.SUBMENUS["/think"]


def test_callback_maps_model_and_think():
    assert m.callback_to_command("model", "opus") == "/model opus"
    assert m.callback_to_command("think", "high") == "/think high"


def test_patches_exposes_inject_key():
    assert hasattr(patches, "_inject_key")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_tg_session_wiring.py -v`
Expected: FAIL — `/model` not in SUBMENUS and `patches._inject_key` missing.

- [ ] **Step 3: Write minimal implementation**

In `term-bridge/tg_menu.py`, extend the data:

```python
MENU_COMMANDS: list[tuple[str, str]] = [
    ("new", "新 tab 启动 agent 会话"),
    ("tabs", "列出终端标签"),
    ("shot", "截图当前屏幕"),
    ("format", "设置回传格式"),
    ("devices", "列出设备"),
    ("check", "环境检查"),
    ("stop", "停止当前运行"),
    ("reset", "重置当前会话"),
    ("compact", "压缩会话上下文"),
    ("model", "查看或切换模型"),
    ("think", "设置思考强度"),
    ("help", "显示可用命令"),
]
```

and add to `SUBMENUS`:

```python
    "/model": [
        ("opus", "model:opus"),
        ("sonnet", "model:sonnet"),
        ("haiku", "model:haiku"),
        ("fable", "model:fable"),
    ],
    "/think": [
        ("low", "think:low"),
        ("medium", "think:medium"),
        ("high", "think:high"),
        ("xhigh", "think:xhigh"),
        ("max", "think:max"),
        ("auto", "think:auto"),
    ],
```

In `tg-relay/tg_relay_patches.py`, add `_inject_key` (module level, near `_inject_iterm`):

```python
def _inject_key(key: str, target=None) -> tuple[int, str]:
    t = target or resolve_target()
    cmd = [sys.executable, str(term_backend.inject_script())]
    if t.window is None:
        cmd.append("--front-window")
    else:
        cmd.extend(["--window", str(t.window)])
    cmd.extend(["--tab", str(t.tab), "--key", key])
    try:
        r = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=30,
            env=apply_target_env(t), stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, str(e)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
```

In the nested `handle_command` (inside `apply`), add a branch before `return orig_cmd(text)`:

```python
        if cmd in ("/stop", "/reset", "/compact", "/model", "/think"):
            from tg_session_control import resolve_session_command, session_usage
            arg = parts[1] if len(parts) > 1 else ""
            action = resolve_session_command(cmd, arg)
            if action is None:
                return session_usage(cmd)
            if sys.platform != "darwin":
                return "会话控制需要 macOS"
            if action.kind == "key":
                code, out = _inject_key(action.payload)
            else:
                code, out = _inject_iterm(action.payload, target=resolve_target())
            if code == 0:
                return f"✓ 已发送 {cmd} → {action.payload}"
            return f"会话控制失败:\n{out[:800]}"
```

(`parts` is already computed as `text.split()` earlier in `handle_command`. Add a `/help` line: `"/stop /reset /compact /model /think — 控制当前会话\n"`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_tg_session_wiring.py test_tg_menu.py -v`
Expected: PASS (existing tg_menu tests still pass; new wiring tests pass).

- [ ] **Step 5: Dry-run smoke checks**

Run: `cd /Users/maxwell/Documents/aiTrees/fullStar && python tg-relay/run_tg_relay.py --dry-run "/model"`
Expected: prints the `/model` usage hint (lists opus|sonnet|haiku|fable).

Run: `python tg-relay/run_tg_relay.py --dry-run "/think bogus"`
Expected: prints the `/think` usage hint (invalid level → usage).

(Do NOT run a bare `/stop`/`/model opus` live unless you intend to inject into the active tab.)

- [ ] **Step 6: Run the full suite + commit**

```bash
cd term-bridge && python -m pytest -q
```
Expected: all pass.

```bash
git add term-bridge/tg_menu.py tg-relay/tg_relay_patches.py term-bridge/test_tg_session_wiring.py
git commit -m "feat: wire /stop /reset /compact /model /think session control + sub-menus"
```

---

## Self-Review

**Spec coverage:**
- `setMyCommands` registration of the command list → Task 2 `post_init` + Task 1/4 `MENU_COMMANDS`. ✓
- Inline-keyboard sub-menus for `/new`/`/format`/`/shot` (Task 1) and `/model`/`/think` (Task 4) → `SUBMENUS` + Task 2 keyboard reply. ✓
- Callback dispatch (`action:value` → slash command → `handle_command`) → Task 1 `dispatch_callback` + Task 2 `CallbackQueryHandler`. ✓
- Session control `/stop`(esc)/`/reset`(/clear)/`/compact`/`/model <alias>`/`/think`→`/effort <level>` → Task 3 mapping + Task 4 wiring + `_inject_key` (esc) / `_inject_iterm` (text). ✓
- Verified semantics (single Esc, /effort) → Task 3 constants + comments. ✓
- Error handling: unknown callback (`未知操作`), bare/invalid arg (`session_usage`), non-macOS, inject failure (truncated) → Tasks 1/3/4. ✓
- Testing per pure module (Tasks 1, 3) + glue smoke tests (Tasks 2, 4). ✓

**Placeholder scan:** No TBD/TODO; all code steps complete. Task 2/4 implementer notes point at existing code, not placeholders.

**Type consistency:** `InjectAction(kind, payload)` defined in Task 3, constructed/consumed identically in Task 4. `resolve_session_command(cmd, arg="")` / `session_usage(cmd)` signatures match callers. `dispatch_callback(data, handle_command)` (Task 1) matches the `CallbackQueryHandler` call (Task 2). `callback_to_command` includes `model`/`think` from Task 1 so Task 4's buttons resolve. `_inject_key(key, target=None)` mirrors the existing `_inject_iterm` signature/pattern.

**Phasing:** Phase 1 = Tasks 1–2 (menu + sub-menus, shippable alone). Phase 2 = Tasks 3–4 (session control). Task 4 extends `MENU_COMMANDS`/`SUBMENUS` so the session commands only appear in the menu once they work.
