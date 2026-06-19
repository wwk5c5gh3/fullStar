# Telegram command menu + sub-commands + session control — Design

**Date:** 2026-06-19
**Status:** Design — pending user spec review

## Goal

Make the Telegram bot easy to operate from a phone:

1. **Command menu** — register the bot's commands so Telegram shows them in the
   `/` popup (the ☰ menu), via the Bot API `setMyCommands`.
2. **Sub-command collections** — commands with discrete options present tappable
   inline-keyboard buttons instead of requiring typed arguments.
3. **Session control** — commands that drive the active Claude Code session in
   the targeted tab (`/stop`, `/reset`, `/compact`, `/model`, `/think`), by
   injecting the right keystrokes/commands.

This builds on the `/new` feature (already merged) and shares the "send a key"
inject primitive defined in the monitor auto-default spec
(`2026-06-19-monitor-auto-default-design.md`).

## Background

`tg-relay/tg-relay.py` `main()` builds the python-telegram-bot `Application`,
registers `CommandHandler`/`MessageHandler`, and runs polling. Routing logic is
monkeypatched in `tg-relay/tg_relay_patches.py` (`handle_command`,
`handle_natural_language`). Session injects go through the backend inject script
(`term_backend.inject_script()`) against the active target
(`iterm_target.resolve_target`, env `TG_ITERM_WINDOW`/`TG_ITERM_TAB`).

## Top-level command menu

Register these 7 via `setMyCommands` at startup (descriptions in Chinese):

| cmd | 描述 |
|-----|------|
| `/new` | 新 tab 启动 agent 会话 |
| `/tabs` | 列出终端标签 |
| `/shot` | 截图当前屏幕 |
| `/format` | 设置回传格式 |
| `/devices` | 列出设备 |
| `/check` | 环境检查 |
| `/help` | 显示可用命令 |

Plus the session-control commands (also in the menu):

| cmd | 描述 |
|-----|------|
| `/stop` | 停止当前运行 |
| `/reset` | 重置当前会话 (/clear) |
| `/compact` | 压缩会话上下文 |
| `/model` | 查看或切换模型 |
| `/think` | 设置思考强度 |

`setMyCommands` is called once at startup (idempotent; self-heals on restart) in
`tg-relay.py main()` via the Application `post_init` hook. The command list lives
in a pure module so it is testable and is the single source of truth.

## Sub-command inline keyboards

Parent commands with discrete options reply with an inline keyboard instead of
plain text. Tapping a button fires a Telegram `callback_query`.

| parent | buttons (label → callback_data) |
|--------|---------------------------------|
| `/new` | claude → `new:claude`, codex → `new:codex` |
| `/format` | html → `fmt:html`, markdown → `fmt:markdown`, plain → `fmt:plain`, screenshot → `fmt:screenshot` |
| `/shot` | android → `shot:android`, ios → `shot:ios` |
| `/model` | (model buttons) opus → `model:opus`, sonnet → `model:sonnet`, haiku → `model:haiku` |
| `/think` | normal → `think:normal`, think → `think:think`, think hard → `think:hard`, ultrathink → `think:ultra` |

`/new`, `/format`, `/shot` keep working with typed args too (e.g. `/new claude
fix bug`); the buttons are a convenience for the no-arg case.

### Callback handling

- A `CallbackQueryHandler` in `tg-relay.py main()` answers the query and
  dispatches by parsing `callback_data`.
- `tg_menu.parse_callback(data) -> (action, value)` (pure) splits `action:value`.
- Dispatch maps each `(action, value)` to existing logic:
  - `new:<agent>` → `handle_new([agent], ...)` (spawn; bare, no prompt).
  - `fmt:<value>` → `set_format(value)`.
  - `shot:<platform>` → the `/shot <platform>` path.
  - `model:<name>` / `think:<level>` → session-control inject (below).
- The handler edits/answers the message with the resulting reply text.

## Session control

These act on the **active target** (same tab natural-language injects go to).
They assume a **Claude Code** session (the primary agent `/new` launches); codex
mappings are a future extension and out of scope.

`tg_session_control.py` (pure) maps each command to an `InjectAction`:

```
@dataclass(frozen=True)
class InjectAction:
    kind: str          # "key" | "text"
    payload: str       # key name ("esc") or text to type ("/clear")
```

| command | InjectAction | notes |
|---------|--------------|-------|
| `/stop` | key `esc` | interrupt current run — exactly ONE Esc (two = rewind); uses `--key esc` |
| `/reset` | text `/clear` | Claude Code clear-conversation command |
| `/compact` | text `/compact` | Claude Code compact command |
| `/model <name>` | text `/model <name>` | from button or typed arg; bare `/model` shows buttons |
| `/think <level>` | text `/effort <level>` | session thinking-intensity (see below) |

`/think` semantics (verified 2026-06-19 via claude-code-guide): Claude Code has
no `/think` slash command, and "think"/"think hard" are NOT recognized keywords.
Session-level reasoning depth is set by **`/effort <level>`** where level ∈
`low | medium | high | xhigh | max | auto`. So our `/think <level>` command
injects `/effort <level>` directly (no relay-side prefix state). Bare `/think`
shows the level buttons. (The only per-turn keyword is `ultrathink`, out of
scope here.)

The relay executes a text `InjectAction` via the existing inject path
(`term_backend.inject_script()` with the text + Enter) and a key `InjectAction`
via the new `--key` mode. Replies confirm what was sent (e.g. `已发送 Esc 中断当前
运行`).

**Verification during implementation:** confirm the exact Claude Code commands
(`/clear`, `/compact`, `/model <name>`, Esc-to-interrupt, thinking keywords)
against current Claude Code behavior (claude-code-guide) before finalizing the
mapping constants. The mapping lives in one module as editable constants.

## New / changed files

- `term-bridge/tg_menu.py` (new, pure): `MENU_COMMANDS` (list of
  `(command, description)`), `SUBMENUS` (parent → list of `(label,
  callback_data)`), `parse_callback(data) -> (str, str)`. Single source of truth
  for the menu + buttons.
- `term-bridge/tg_session_control.py` (new, pure): `InjectAction`,
  `SESSION_COMMANDS`, `resolve_session_command(cmd, arg) -> InjectAction | None`,
  and the `/think` prefix mapping. Stateless mapping; the prefix *state* reuses
  the existing format-style state file mechanism.
- `tg-relay/tg-relay.py` `main()` (modify): add `post_init` calling
  `set_my_commands` from `tg_menu.MENU_COMMANDS`; add a `CallbackQueryHandler`;
  have `on_message` attach an inline keyboard when a parent command is sent
  bare.
- `tg-relay/tg_relay_patches.py` `handle_command` (modify): add `/stop`,
  `/reset`, `/compact`, `/model`, `/think` branches that resolve to an
  `InjectAction` (or buttons for bare `/model`/`/think`) and execute the inject.
- Backend inject scripts `--key {enter|esc}` mode — **defined in the monitor
  auto-default spec**; this feature consumes it (don't duplicate).

## Error handling

- `set_my_commands` failure at startup → log and continue (menu is a
  convenience, not critical).
- Unknown `callback_data` → answer the query with a "未知操作" notice.
- Session-control inject failure / non-macOS → reply with the error (truncated),
  consistent with existing inject reply style.
- Session control assumes the target is a Claude Code session; if it is not, the
  injected `/clear` etc. is simply typed into whatever is there — documented
  limitation, not guarded.

## Testing

pytest in `term-bridge/`:

- `tg_menu`: `MENU_COMMANDS` shape and contents; `SUBMENUS` entries for
  `/new`/`/format`/`/shot`/`/model`/`/think`; `parse_callback` for valid
  `action:value`, missing colon, empty.
- `tg_session_control`: `resolve_session_command` returns the right
  `InjectAction` for each command (key vs text, payload); `/model <name>` builds
  `/model <name>`; `/think <level>` prefix mapping; unknown command → None.
- The `--key enter|esc` inject mode is tested in the auto-default feature.
- Relay/patches wiring: command parsing for the new slash commands (covered by
  pure dispatch tests; telegram callback glue is thin and smoke-tested).

## Phasing (for the implementation plan)

- **Phase 1:** `tg_menu` + `setMyCommands` registration + inline-keyboard
  sub-menus for `/new`/`/format`/`/shot` + callback dispatch.
- **Phase 2:** `--key` inject mode + `tg_session_control` + `/stop`/`/reset`/
  `/compact`/`/model`/`/think` + their buttons.

## Non-goals

- No codex-specific session-control mappings (Claude Code only for now).
- No multi-step conversational flows (e.g. `/new` → choose agent → then prompt);
  buttons launch bare, prompts come as normal messages.
- No persistent per-chat menu customization; one global command set.
