# 新增功能清单 / Feature Changelog

本批次（2026-06-19 ~ 06-20）围绕「用 Telegram 远程驱动 Mac 上的 Claude Code / Codex」一路补强：
从「能注入」到「能开新会话、能控会话、卡住能自愈、谁能用都受控」。下表为新增功能总览，
配置项见 [`.env.example`](../.env.example)，命令表见 [README.md](../README.md)。

## 1. 手机一句话开新会话 — `/new`

- `/new claude|codex [prompt]`：新建终端标签页（无窗口则新建窗口）→ `mkdir` 带时间戳的工作目录
  → 缺对应 CLI 时自动安装 → 启动 agent（`claude --permission-mode bypassPermissions` / `codex`），
  并把首句作为第一个 prompt。开完后续普通消息自动注入该新标签页。
- 实现：`term-bridge/tg_new_command.py`、`terminal-spawn` CLI、`agent_cli` 注册表。

## 2. Telegram 命令菜单 + inline 子菜单

- Bot 启动时 `setMyCommands` 注册命令，输入框「/」菜单可点选。
- 带候选项的命令（`/new` `/format` `/shot` `/model` `/think`）发裸命令弹出 **inline 按钮子菜单**，
  点一下即执行，手机端无需手打参数。
- 实现：`term-bridge/tg_menu.py`（命令清单 / 子菜单 / callback 映射的单一真源）。

## 3. 会话控制命令（直接作用于目标 AI 会话）

| 命令 | 注入动作 |
|------|----------|
| `/stop` | 向目标会话发一次 **Esc** |
| `/reset` | 键入 `/clear` |
| `/compact` | 键入 `/compact` |
| `/model opus\|sonnet\|haiku\|fable` | 键入 `/model <alias>` |
| `/think low\|medium\|high\|xhigh\|max\|auto` | 键入 `/effort <level>` |

- 命令与参数大小写不敏感，载荷统一小写。实现：`term-bridge/tg_session_control.py`。

## 4. 注入后端 `--key enter/esc` 模式

- Terminal.app 与 iTerm2 两套注入后端都支持单独发送按键（Enter / Esc），
  供会话控制（`/stop`）与卡住自动兜底复用。由 `term_backend.py` 统一切换。

## 5. 卡住自动兜底（auto-default Enter）

- 当 Claude Code / Codex 停在选择型提示（`❯ 1. Yes …`）超过
  `TG_ITERM_MONITOR_AUTO_DEFAULT` 秒（默认 60）无人选择时，monitor 自动按 Enter 选第一项并回传提示，
  避免会话整夜卡死。设 `0/off` 关闭，提示文案见 `TG_ITERM_AUTO_DEFAULT_CAPTION`。
- 实现：`interactive_prompt.py`（`detect_select_prompt` / `should_auto_default`）+ `iterm-monitor.py`。

## 6. 截图去重（≥95% 相似跳过）

- 截图兜底时对比 32×32 灰度指纹，新帧与上次已发 ≥95% 相似则跳过，避免光标闪烁/重绘刷屏。
- 仅在发送成功后才写指纹，发送失败会重试。实现：`term-bridge/screenshot_dedup.py`。
- 配合：截图改为**捕获目标 tab**，而非永远抓最前窗口。

## 7. chat-id 白名单（fail-closed 安全）

- 会话控制命令会键入你的实时终端，故 relay 内置 chat-id 白名单，只放行授权会话：
  - `TG_RELAY_ALLOWED_CHAT_IDS`（逗号/分号分隔）；留空则默认仅放行机主 `TELEGRAM_CHAT_ID`。
  - 白名单与 `TELEGRAM_CHAT_ID` **都为空 → relay 拒绝启动**（fail-closed）。无"放行所有会话"开关。
  - 注入护栏：剥离 C0 控制字符 + 单条上限 `TG_RELAY_MAX_INJECT_CHARS`（默认 2000）。
  - 速率限制：每 chat 最小间隔 `TG_RELAY_MIN_INTERVAL_SECS`（默认 1s，设 0 关闭）。
- 实现：`term-bridge/chat_allowlist.py`、`message_guard.py`、`rate_limit.py`。

## 8. Terminal.app 双向后端

- 新增系统自带 Terminal.app 的注入/捕获后端，`TG_TERM_BACKEND=terminal`（默认）/ `iterm` 切换。

## 9. 持久转发目标 — `/tab`

- `/tab`（无参）列出当前所有终端并弹按钮；`/tab 2` = 选**第 2 个**（扁平序号，对多窗口各一 tab 的系统 Terminal.app 也适用）；`/tab 1:1` = 指定窗口:标签；`/tab off` 清除。
- 选中后持久化到 `inbox/target-default.json`，后续无前缀消息的**注入 + 回传 + 卡住自动按 Enter + 空闲截图**都跟随该终端，重启不丢。
- 终端枚举按 `TG_TERM_BACKEND` 自动切换：`terminal`(默认) 查系统 Terminal.app、`iterm` 查 iTerm2（`terminal_tabs.py` / `iterm_tabs.py`，由 `iterm_route._list_targets_for_backend` 选择）。
- 路由优先级：单条前缀 `[t3]` > `/tab` 默认 > `.env` 默认。
- 实现：`term-bridge/target_default.py`（`current_target()` 单一真源）+ `iterm_route.py` + `tg_tab_command.py` + `iterm-monitor.py`。

---

> 设计与实现细节见 `docs/superpowers/specs/` 与 `docs/superpowers/plans/`（2026-06-19 各 spec / plan）。
> 全部功能均有 pytest 覆盖：`term-bridge/test_*.py`。
