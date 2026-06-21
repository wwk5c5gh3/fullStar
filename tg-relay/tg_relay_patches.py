"""Apply iTerm tab routing patches to tg-relay module."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "term-bridge"))

import term_backend
from iterm_route import (
    RouteResult,
    format_tabs_message,
    list_tabs,
    route_message,
)
from iterm_target import ItermTarget, apply_target_env, resolve_target
from tg_format_config import VALID as _FORMATS, get_format, set_format
from tg_menu import MENU_COMMANDS
from tg_new_command import SpawnResult, retarget_env

# Natural-language routing examples appended below the generated command list.
# The command list itself is generated from MENU_COMMANDS so /help can't drift.
_NL_HELP_FOOTER = (
    "\n自然语言 -> 终端 + inbox\n"
    "  前缀示例:\n"
    "  [t2] 问题 — tab 2\n"
    "  [mobile-agent] 问题 — 匹配目录名\n"
    "  @t3: 问题 — tab 3\n"
    "  (无前缀 = .env 默认 TG_ITERM_TAB)"
)

# Telegram hard-caps a message at 4096 chars.
_TELEGRAM_LIMIT = 4096


def _build_help_text() -> str:
    """Render /help (and /start) from MENU_COMMANDS so it never drifts.

    Lists every ("name", "desc") as "/name — desc", then appends the
    natural-language prefix examples. Truncated to stay under Telegram's limit.
    """
    header = "mobile-agent bot\n"
    cmd_lines = "\n".join(f"/{name} — {desc}" for name, desc in MENU_COMMANDS)
    text = f"{header}\n{cmd_lines}\n{_NL_HELP_FOOTER}"
    return text[:_TELEGRAM_LIMIT]


def _is_slash_command(text: str) -> bool:
    """Slash commands need Return twice — the TUI's autocomplete menu eats the first."""
    return text.lstrip().startswith("/")


def _inject_iterm(text: str, target=None, enter_twice: bool | None = None) -> tuple[int, str]:
    t = target or resolve_target()
    if enter_twice is None:
        enter_twice = _is_slash_command(text)
    cmd = [sys.executable, str(term_backend.inject_script())]
    if t.window is None:
        cmd.append("--front-window")
    else:
        cmd.extend(["--window", str(t.window)])
    cmd.extend(["--tab", str(t.tab)])
    if t.session is not None:
        cmd.extend(["--session", str(t.session)])
    if enter_twice:
        # slash commands: clear any leftover input first (no concatenation),
        # and press Return twice (autocomplete eats the first).
        cmd.append("--enter-twice")
        cmd.append("--clear-line")
    cmd.append(text)
    try:
        r = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            env=apply_target_env(t),
            stdin=subprocess.DEVNULL,  # daemon fd0 may be closed → child Python would crash
        )
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, str(e)


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


# Secrets that must never land in a child's argv or be inherited by children
# that don't need them. Children that DO need the token (iterm-monitor) re-read
# it from .env via their own _load_env(), so dropping it here is safe.
_SECRET_ENV_KEYS = ("TELEGRAM_BOT_TOKEN",)


def _sanitized_env(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of env with secret keys removed (see _SECRET_ENV_KEYS)."""
    return {k: v for k, v in env.items() if k not in _SECRET_ENV_KEYS}


def _schedule_iterm_monitor_poll(target=None) -> None:
    delay = os.environ.get("TG_ITERM_MONITOR_AFTER", "").strip()
    if not delay or delay.lower() in ("0", "false", "no", "off"):
        return
    try:
        secs = max(5, int(delay))
    except ValueError:
        secs = 30
    monitor = str(ROOT / "term-bridge" / "iterm-monitor.py")
    t = target or resolve_target()
    # Drop the token from the env: it must not appear in argv (it never did via
    # -c now) nor in this child's environment. iterm-monitor re-reads it from
    # .env. The grandchild inherits this sanitized env (no env= passed below).
    env = _sanitized_env(apply_target_env(t))
    env["ITERM_MONITOR_SUFFIX"] = t.log_suffix()
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                # NOTE: no --force — the running monitor daemon already streams
                # replies and tracks "already sent". --force here bypassed that
                # dedup and could re-send a reply the daemon just delivered.
                "import time, subprocess, sys; "
                f"time.sleep({secs}); "
                f"subprocess.run([sys.executable, {monitor!r}, '--once'])"
            ),
        ],
        env=env,
        stdin=subprocess.DEVNULL,  # detached child Python needs a valid fd0
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _schedule_confirm_enter(target=None, delay: float | None = None) -> None:
    """Press Enter once after a short delay to accept a confirmation dialog.

    Some slash commands (notably /model) pop a "Switch model? 1.Yes 2.No" prompt
    with Yes highlighted; the in-line double-Return fires before the dialog renders,
    so this delayed Enter lands on the dialog and accepts the default.
    Delay via TG_MODEL_CONFIRM_DELAY (seconds, default 1.3).
    """
    if delay is None:
        try:
            delay = float(os.environ.get("TG_MODEL_CONFIRM_DELAY", "1.3"))
        except ValueError:
            delay = 1.3
    t = target or resolve_target()
    # Pressing Enter needs no token; strip it and let the child inherit the env.
    env = _sanitized_env(apply_target_env(t))
    cmd = [str(term_backend.inject_script())]
    if t.window is None:
        cmd.append("--front-window")
    else:
        cmd.extend(["--window", str(t.window)])
    cmd.extend(["--tab", str(t.tab), "--key", "enter"])
    subprocess.Popen(
        [
            sys.executable, "-c",
            "import time, subprocess, sys; "
            f"time.sleep({float(delay)}); "
            f"subprocess.run([sys.executable] + {cmd!r}, stdin=subprocess.DEVNULL)",
        ],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _parse_spawn_output(code: int, stdout: str, stderr: str) -> SpawnResult:
    tab = None
    workdir = ""
    m = re.search(r"^tab=(\d+)$", stdout or "", re.M)
    if m:
        tab = int(m.group(1))
    d = re.search(r"^dir=(.+)$", stdout or "", re.M)
    if d:
        workdir = d.group(1).strip()
    raw = ((stdout or "") + (stderr or "")).strip()
    return SpawnResult(code=code, tab=tab, workdir=workdir, raw=raw)


def _backend_name() -> str:
    """Human-facing name of the active terminal backend."""
    return "iTerm" if term_backend.resolve_backend() == "iterm" else "Terminal"


def _health_header() -> str:
    """Pipeline health summary (relay/monitor alive, inject, backend), best-effort.

    Prepended to /status so the user sees at a glance whether the pipeline is
    alive before the per-tab list. Any failure degrades to a one-line note.
    """
    try:
        import pipeline_doctor

        return pipeline_doctor.health_summary()
    except Exception as e:  # never let the doctor crash /status
        return f"健康检查失败: {e}"


def _monitor_poll_armed() -> bool:
    """True when TG_ITERM_MONITOR_AFTER is set to a real delay (not an off value)."""
    raw = os.environ.get("TG_ITERM_MONITOR_AFTER", "").strip().lower()
    return raw not in ("", "0", "false", "no", "off")


def _reply_chat_configured() -> bool:
    """True when a positive-integer chat-id is set so AI replies can come back.

    Mirrors pipeline_doctor._check_chat_id: a reply is only deliverable when
    TELEGRAM_CHAT_ID (or the monitor's TG_ITERM_MONITOR_CHAT_ID) is a positive
    integer. Empty / non-integer / non-positive means no reply path.
    """
    for key in ("TELEGRAM_CHAT_ID", "TG_ITERM_MONITOR_CHAT_ID"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        try:
            if int(raw) > 0:
                return True
        except ValueError:
            continue
    return False


def _reply_promise() -> str:
    """Trailing note about whether/when an AI reply will be relayed back.

    - No reply chat configured → warn the user replies won't arrive.
    - Reply chat configured AND a delayed poll is armed → promise the relay.
    - Otherwise → no note (a live monitor daemon may still stream replies).
    """
    if not _reply_chat_configured():
        return "\n(⚠️ 回传未配置：设置 TELEGRAM_CHAT_ID 才能收到 AI 回复)"
    if _monitor_poll_armed():
        return "\n(output -> TG after delay)"
    return ""


def _unmatched_prefix_reply(prefix: str) -> str:
    """Refusal shown when a routing prefix matched no open tab (no injection)."""
    try:
        tabs_block = format_tabs_message()
    except Exception:  # tab enumeration must never crash the refusal
        tabs_block = "(无法读取标签列表)"
    return (
        f"⚠️ 没找到匹配 [{prefix}] 的标签，已忽略未注入。\n"
        f"当前可用:\n{tabs_block}"
    )


def _label_for_target(target: ItermTarget) -> str:
    """Friendly label for a target: 'wN/tN (name)' when the tab is found, else 'wN/tN'.

    Best-effort: tab enumeration may be unavailable (non-macOS / closed window),
    in which case we fall back to the positional label so /sel always confirms.
    """
    try:
        code, tabs = list_tabs()
    except Exception:
        code, tabs = 1, []
    if code == 0:
        for t in tabs:
            if t.window == target.window and t.tab == target.tab:
                return f"{target.label()} ({t.name[:40]})"
    return target.label()


def _resolve_sel(arg: str) -> tuple[ItermTarget, int] | None:
    """Parse a /sel argument into (target, choice_number).

    Accepts two forms:
      - "w:t:n" (callback form) → inject n into window w / tab t.
      - bare "n" (human-typed)  → inject n into the current default/active tab.
    Returns None when the argument is neither form.
    """
    m = re.match(r"^(\d+):(\d+):(\d+)$", arg)
    if m:
        w, t, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return ItermTarget(window=w, tab=t), n
    if re.match(r"^\d+$", arg):
        # Same sticky/default target the relay uses for unprefixed messages.
        return route_message("").target, int(arg)
    return None


def _inject_receipt(result: RouteResult, backend_name: str, body: str) -> str:
    """Success receipt: '✓ 已注入 <backend> <tab_label>' + preview + notes."""
    tab_label = (
        f"tab {result.hit.tab} ({result.hit.name[:40]})"
        if result.hit
        else result.target.label()
    )
    preview = body[:80] + ("…" if len(body) > 80 else "")
    return (
        f"✓ 已注入 {backend_name} {tab_label}\n"
        f"{preview}\n(+ inbox backup)"
        f"{_reply_promise()}"
    )


def _spawn_session(agent_key: str, prompt: str) -> SpawnResult:
    cmd = [sys.executable, str(ROOT / "term-bridge" / "terminal-spawn.py"), "--agent", agent_key]
    if prompt:
        cmd.extend(["--prompt", prompt])
    try:
        r = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return _parse_spawn_output(1, "", str(e))
    return _parse_spawn_output(r.returncode, r.stdout or "", r.stderr or "")


def apply(mod: ModuleType) -> None:
    def handle_natural_language(chat_id: int, text: str) -> str:
        result = route_message(text)
        # Wrong-session footgun guard: a prefix was typed but matched no open
        # tab — refuse instead of silently injecting into the default tab.
        if result.unmatched_prefix is not None:
            return _unmatched_prefix_reply(result.unmatched_prefix)
        target, body = result.target, result.body
        mod._append_inbox(chat_id, f"[{target.label()}] {body}")
        if mod._iterm_inject_enabled():
            if sys.platform != "darwin":
                return "saved to inbox (iTerm inject needs macOS)"
            backend_name = _backend_name()
            code, out = _inject_iterm(body, target=target)
            if code == 0:
                _schedule_iterm_monitor_poll(target=target)
                return _inject_receipt(result, backend_name, body)
            return f"inbox saved; {backend_name} failed:\n{out[:800]}"
        return mod.INJECT_DISABLED_NOTICE

    orig_cmd = mod._handle_command

    def handle_command(text: str) -> str:
        text = text.strip()
        if not text:
            return "empty message"
        if not text.startswith("/"):
            return handle_natural_language(0, text)
        parts = text.split()
        cmd = parts[0].lower().split("@")[0]
        if cmd in ("/start", "/help"):
            return _build_help_text()
        if cmd == "/tabs":
            return format_tabs_message()[:4000]
        if cmd.startswith("/format") or cmd.startswith("/fmt"):
            prefix = "/format" if cmd.startswith("/format") else "/fmt"
            glued = cmd[len(prefix):].lstrip("-_:")  # /format-html → html
            value = glued or (parts[1] if len(parts) > 1 else "")
            if not value:
                return (
                    f"当前回传格式: {get_format()}\n"
                    f"可选: {' | '.join(_FORMATS)}\n"
                    "用法: /format html  （也可 /format-markdown）"
                )
            norm = set_format(value)
            if norm is None:
                return f"未知格式: {value}\n可选: {' | '.join(_FORMATS)}"
            return f"✓ 回传格式已设为 {norm}（立即生效，无需重启）"
        if cmd == "/new":
            from tg_new_command import handle_new
            reply, new_tab = handle_new(
                parts[1:], is_macos=(sys.platform == "darwin"), spawn=_spawn_session
            )
            os.environ.update(retarget_env(new_tab))
            return reply
        if cmd == "/tab":
            from tg_tab_command import resolve_tab_command
            from target_default import write_default, clear_default
            return resolve_tab_command(
                parts[1:], list_tabs, write_default, clear_default
            )
        if cmd == "/approve":
            from agent_cli import read_approve_mode, set_approve_mode
            arg = (parts[1].strip().lower() if len(parts) > 1 else "")
            if arg in ("on", "1", "yes"):
                set_approve_mode(True)
                return "✅ 审批模式已开启：新开的 agent 会逐个询问权限，提示会以按钮发到这里点批准/拒绝"
            if arg in ("off", "0", "no"):
                set_approve_mode(False)
                return "审批模式已关闭：新开的 agent 自动放行（bypassPermissions）"
            state = "开启" if read_approve_mode() else "关闭"
            return f"审批模式当前: {state}\n用法: /approve on|off（仅影响之后 /new 的会话）"
        if cmd == "/sel":
            # interactive-prompt option button (w:t:n) OR a bare typed number
            # (-> current default tab). Inject the chosen option number.
            arg = parts[1] if len(parts) > 1 else ""
            resolved = _resolve_sel(arg)
            if resolved is None:
                return f"无法解析选择: {arg}\n用法: /sel 2 或 /sel w:t:n"
            sel_target, n = resolved
            if sys.platform != "darwin":
                return "需要 macOS"
            code, out = _inject_iterm(str(n), target=sel_target)
            if code == 0:
                return f"✓ 已向 {_label_for_target(sel_target)} 选择第 {n} 项"
            return f"选择失败:\n{out[:600]}"
        if cmd == "/status":
            from agent_status import classify_state, format_status
            header = _health_header()
            code, tabs = list_tabs()
            if code != 0 or not tabs:
                return f"{header}\n\n没有打开的终端窗口"
            rows = []
            for i, t in enumerate(tabs, 1):
                target = ItermTarget(window=t.window, tab=t.tab)
                try:
                    cap = subprocess.run(
                        [sys.executable, str(term_backend.capture_script())],
                        env=apply_target_env(target), capture_output=True, text=True,
                        timeout=20, stdin=subprocess.DEVNULL,
                    ).stdout
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    cap = ""
                rows.append((str(i), t.label, t.name, classify_state(cap)))
            return f"{header}\n\n{format_status(rows)}"
        if cmd == "/diff":
            from git_diff_report import format_diff_reply
            d = parts[1] if len(parts) > 1 else str(ROOT)
            try:
                stat = subprocess.run(
                    ["git", "-C", d, "diff", "--stat"],
                    capture_output=True, text=True, timeout=15,
                ).stdout
                body = subprocess.run(
                    ["git", "-C", d, "diff"],
                    capture_output=True, text=True, timeout=15,
                ).stdout
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                return f"git diff 失败: {e}"
            return format_diff_reply(stat, body)
        if cmd == "/p":
            from quick_prompts import load, save_prompt, delete_prompt, resolve_p_command
            reply, inject_text = resolve_p_command(
                parts[1:], load(), save_prompt, delete_prompt
            )
            if inject_text is not None:
                return handle_natural_language(0, inject_text)
            return reply
        if cmd in ("/stop", "/interrupt", "/reset", "/compact", "/model", "/think"):
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
                # /model pops a "Switch model?" confirmation — auto-accept default (Yes)
                if code == 0 and cmd == "/model":
                    _schedule_confirm_enter(target=resolve_target())
            if code == 0:
                return f"✓ 已发送 {cmd} → {action.payload}"
            return f"会话控制失败:\n{out[:800]}"
        return orig_cmd(text)

    mod._handle_natural_language = handle_natural_language
    mod._handle_command = handle_command

    orig_main = mod.main

    def main() -> int:
        import argparse

        parser = argparse.ArgumentParser(description="mobile-agent Telegram relay")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("message", nargs="?")
        args = parser.parse_args()

        mod._load_env()
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            print("TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
            return 1

        if args.dry_run:
            msg = (args.message or "/help").strip()
            if msg.startswith("/"):
                print(handle_command(msg))
            else:
                result = route_message(msg)
                if result.unmatched_prefix is not None:
                    print(_unmatched_prefix_reply(result.unmatched_prefix))
                else:
                    tab = f" ({result.hit.name})" if result.hit else ""
                    print(
                        f"[dry-run] would inject to iTerm "
                        f"{result.target.label()}{tab} + inbox:\n{result.body}"
                    )
            return 0

        return orig_main()

    mod.main = main
