# `/new` TG Spawn Command — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/new claude|codex [prompt]` Telegram command that opens a new Terminal.app tab in a fresh `~/fullStar/<timestamp>` directory, auto-installs the CLI if missing, launches the agent seeded with an optional first prompt, and retargets subsequent messages to the new tab.

**Architecture:** Four small modules. `agent_cli.py` is a pure registry of agent launch/installer commands. `terminal_spawn_lib.py` is a pure builder turning `(dirname, agent, prompt)` into a chained shell line + the AppleScript that opens a tab and runs it. `terminal-spawn.py` is a thin CLI that generates the timestamp, writes the shell line to a temp script, runs the AppleScript via `osascript`, and prints `dir=`/`tab=`. `tg_new_command.py` is the pure parse+format+validate logic; `tg_relay_patches.py` wires it into the relay's `handle_command` and applies the retarget.

**Tech Stack:** Python 3 (stdlib only), pytest, AppleScript via `osascript`, macOS Terminal.app.

## Global Constraints

- macOS only for the actual spawn (`sys.platform == "darwin"`); non-macOS returns a message, never raises.
- stdlib only — no new dependencies.
- Immutable data: use `@dataclass(frozen=True)` for value objects.
- Files small and single-responsibility; mirror existing `term-bridge/` conventions (`osascript -e <script>`, `_load_env`, `(code, out)` tuples).
- Directory name format: `YYYY-MM-DD-HHMM` under `$HOME/fullStar/`.
- Agent launch commands (verbatim): claude → `claude --permission-mode bypassPermissions`; codex → `codex`.
- Installer commands (editable constants, verify against current docs during impl): claude → `curl -fsSL https://claude.ai/install.sh | bash`; codex → `npm install -g @openai/codex`.
- Retarget uses existing env keys read by `iterm_target.resolve_target`: `TG_ITERM_WINDOW` (set to `front`) and `TG_ITERM_TAB` (set to the new tab index).
- All test files live in `term-bridge/` as `test_*.py`, run with `cd term-bridge && python -m pytest`.

---

### Task 1: Agent registry (`agent_cli.py`)

**Files:**
- Create: `term-bridge/agent_cli.py`
- Test: `term-bridge/test_agent_cli.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `AgentSpec` — `@dataclass(frozen=True)` with fields `key: str`, `check: str`, `launch: str`, `installer: str`.
  - `AGENTS: dict[str, AgentSpec]` keyed by `"claude"`, `"codex"`.
  - `get_agent(key: str) -> AgentSpec | None` (case-insensitive, trims whitespace).
  - `valid_keys() -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_agent_cli.py
"""Tests for agent_cli — the claude/codex launch + installer registry."""
from __future__ import annotations

import agent_cli


def test_valid_keys():
    assert agent_cli.valid_keys() == ("claude", "codex")


def test_get_claude():
    spec = agent_cli.get_agent("claude")
    assert spec is not None
    assert spec.check == "claude"
    assert spec.launch == "claude --permission-mode bypassPermissions"
    assert "claude.ai/install.sh" in spec.installer


def test_get_codex():
    spec = agent_cli.get_agent("codex")
    assert spec is not None
    assert spec.check == "codex"
    assert spec.launch == "codex"
    assert "@openai/codex" in spec.installer


def test_get_is_case_insensitive_and_trimmed():
    assert agent_cli.get_agent("  Claude ") is agent_cli.get_agent("claude")


def test_get_unknown_returns_none():
    assert agent_cli.get_agent("kitty") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_agent_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# term-bridge/agent_cli.py
"""Registry of spawnable coding-agent CLIs (launch + installer commands).

Single source of truth for `/new <agent>`. Installer strings are editable
constants — verify against current official docs when they change.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    key: str        # registry key, e.g. "claude"
    check: str      # binary name probed with `command -v`
    launch: str     # command that starts the agent
    installer: str  # command that installs it when missing


AGENTS: dict[str, AgentSpec] = {
    "claude": AgentSpec(
        key="claude",
        check="claude",
        launch="claude --permission-mode bypassPermissions",
        installer="curl -fsSL https://claude.ai/install.sh | bash",
    ),
    "codex": AgentSpec(
        key="codex",
        check="codex",
        launch="codex",
        installer="npm install -g @openai/codex",
    ),
}


def get_agent(key: str) -> AgentSpec | None:
    return AGENTS.get(key.strip().lower())


def valid_keys() -> tuple[str, ...]:
    return tuple(AGENTS.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_agent_cli.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/agent_cli.py term-bridge/test_agent_cli.py
git commit -m "feat: agent_cli registry for claude/codex launch + installer"
```

---

### Task 2: Spawn builders (`terminal_spawn_lib.py`)

**Files:**
- Create: `term-bridge/terminal_spawn_lib.py`
- Test: `term-bridge/test_terminal_spawn_lib.py`

**Interfaces:**
- Consumes: `agent_cli.AgentSpec`.
- Produces:
  - `shell_quote(s: str) -> str` — POSIX single-quote escaping.
  - `build_spawn_command(*, dirname: str, agent: AgentSpec, prompt: str) -> str` — the chained shell line.
  - `build_spawn_applescript(*, script_path: str) -> str` — AppleScript that opens a tab/window, runs `bash <script_path>`, and returns the new tab index.

Composed shell line shape (prompt non-empty):
```
mkdir -p "$HOME/fullStar/<dirname>" && cd "$HOME/fullStar/<dirname>" && (command -v claude >/dev/null 2>&1 || curl -fsSL https://claude.ai/install.sh | bash) && claude --permission-mode bypassPermissions 'prompt'
```
Empty prompt → identical but no trailing `'prompt'` argument.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_terminal_spawn_lib.py
"""Tests for terminal_spawn_lib — pure spawn command + AppleScript builders."""
from __future__ import annotations

import agent_cli
import terminal_spawn_lib as lib

CLAUDE = agent_cli.get_agent("claude")


def test_shell_quote_plain():
    assert lib.shell_quote("hello") == "'hello'"


def test_shell_quote_escapes_single_quote():
    assert lib.shell_quote("it's") == "'it'\\''s'"


def test_command_with_prompt():
    cmd = lib.build_spawn_command(dirname="2026-06-19-2230", agent=CLAUDE, prompt="fix the bug")
    assert 'mkdir -p "$HOME/fullStar/2026-06-19-2230"' in cmd
    assert 'cd "$HOME/fullStar/2026-06-19-2230"' in cmd
    assert "command -v claude >/dev/null 2>&1 || curl -fsSL https://claude.ai/install.sh | bash" in cmd
    assert cmd.rstrip().endswith("claude --permission-mode bypassPermissions 'fix the bug'")


def test_command_without_prompt_has_no_trailing_arg():
    cmd = lib.build_spawn_command(dirname="2026-06-19-2230", agent=CLAUDE, prompt="")
    assert cmd.rstrip().endswith("claude --permission-mode bypassPermissions")
    assert "''" not in cmd  # no empty-quote artifact


def test_command_prompt_quote_is_escaped():
    cmd = lib.build_spawn_command(dirname="d", agent=CLAUDE, prompt="it's")
    assert "'it'\\''s'" in cmd


def test_applescript_opens_tab_and_returns_tabcount():
    script = lib.build_spawn_applescript(script_path="/tmp/spawn-x.sh")
    assert "bash '/tmp/spawn-x.sh'" in script
    assert 'keystroke "t" using command down' in script
    assert "count of tabs of front window" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_terminal_spawn_lib.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'terminal_spawn_lib'`

- [ ] **Step 3: Write minimal implementation**

```python
# term-bridge/terminal_spawn_lib.py
"""Pure builders for spawning an agent session in a new Terminal.app tab.

`build_spawn_command` composes one chained shell line (mkdir -> cd ->
install-if-missing -> launch-with-prompt). `build_spawn_applescript` returns
the AppleScript that opens a new tab (or window if none) and runs that line via
a temp bash script, returning the new tab index for retargeting. No side
effects — all timestamp/file/IO work lives in the terminal-spawn.py CLI.
"""
from __future__ import annotations

from agent_cli import AgentSpec


def shell_quote(s: str) -> str:
    """POSIX single-quote a string for safe inclusion in a shell command."""
    return "'" + s.replace("'", "'\\''") + "'"


def build_spawn_command(*, dirname: str, agent: AgentSpec, prompt: str) -> str:
    """Chained shell line: make/enter dir, install if missing, launch agent."""
    workdir = f'"$HOME/fullStar/{dirname}"'
    install = f"(command -v {agent.check} >/dev/null 2>&1 || {agent.installer})"
    launch = agent.launch
    if prompt:
        launch = f"{launch} {shell_quote(prompt)}"
    return f"mkdir -p {workdir} && cd {workdir} && {install} && {launch}"


def build_spawn_applescript(*, script_path: str) -> str:
    """AppleScript: focus Terminal, new tab (or window), run the script, return tab index."""
    runner = f"bash '{script_path}' ; rm -f '{script_path}'"
    return (
        "on run\n"
        '    tell application "Terminal"\n'
        "        set hadWindow to (count of windows) > 0\n"
        "        activate\n"
        "    end tell\n"
        '    tell application "System Events"\n'
        '        set frontmost of process "Terminal" to true\n'
        "        repeat 40 times\n"
        '            if frontmost of process "Terminal" then exit repeat\n'
        "            delay 0.05\n"
        "        end repeat\n"
        "        if hadWindow then\n"
        '            keystroke "t" using command down\n'
        "            delay 0.3\n"
        "        end if\n"
        "    end tell\n"
        '    tell application "Terminal"\n'
        "        if (count of windows) is 0 then\n"
        f'            do script "{runner}"\n'
        "        else\n"
        f'            do script "{runner}" in front window\n'
        "        end if\n"
        "        set tabIdx to (count of tabs of front window)\n"
        "    end tell\n"
        "    return tabIdx\n"
        "end run\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_terminal_spawn_lib.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/terminal_spawn_lib.py term-bridge/test_terminal_spawn_lib.py
git commit -m "feat: pure spawn shell-line + AppleScript builders"
```

---

### Task 3: Spawn CLI (`terminal-spawn.py`)

**Files:**
- Create: `term-bridge/terminal-spawn.py`
- Test: `term-bridge/test_terminal_spawn_cli.py`

**Interfaces:**
- Consumes: `agent_cli.get_agent`, `terminal_spawn_lib.build_spawn_command`, `terminal_spawn_lib.build_spawn_applescript`.
- Produces: CLI `python terminal-spawn.py --agent <key> [--prompt <text>] [--dry-run]`. On success prints two stdout lines `dir=<abs path>` and `tab=<int>` and exits 0. `--dry-run` prints `dir=`, the composed shell command, and the AppleScript without running `osascript` (exit 0, testable off-macOS). Unknown agent → stderr + exit 2.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_terminal_spawn_cli.py
"""Tests for terminal-spawn.py CLI via --dry-run (no osascript needed)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent / "terminal-spawn.py"


def _run(args):
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True, text=True, timeout=30,
    )


def test_dry_run_emits_dir_and_command():
    r = _run(["--agent", "claude", "--prompt", "do x", "--dry-run"])
    assert r.returncode == 0
    assert "dir=" in r.stdout
    assert "/fullStar/" in r.stdout
    assert "command -v claude" in r.stdout
    assert "do x" in r.stdout


def test_dry_run_unknown_agent_exits_2():
    r = _run(["--agent", "kitty", "--dry-run"])
    assert r.returncode == 2
    assert "kitty" in (r.stderr + r.stdout)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_terminal_spawn_cli.py -v`
Expected: FAIL (CLI file does not exist → nonzero / FileNotFound)

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""Spawn an agent session in a new Terminal.app tab under ~/fullStar/<timestamp>.

Generates the timestamped dir name, composes the chained shell line, writes it
to a temp bash script, and runs the AppleScript via osascript. Prints `dir=`
and `tab=` on success for the relay to retarget injection to the new tab.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "term-bridge"))
from agent_cli import get_agent, valid_keys  # noqa: E402
from terminal_spawn_lib import build_spawn_applescript, build_spawn_command  # noqa: E402


def _dirname() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M")


def main() -> int:
    parser = argparse.ArgumentParser(description="Spawn an agent session in a new Terminal.app tab")
    parser.add_argument("--agent", required=True, help="Agent key: " + " | ".join(valid_keys()))
    parser.add_argument("--prompt", default="", help="Initial prompt passed to the agent")
    parser.add_argument("--dry-run", action="store_true", help="Print command + AppleScript, do not run")
    args = parser.parse_args()

    spec = get_agent(args.agent)
    if spec is None:
        print(f"unknown agent: {args.agent} (valid: {', '.join(valid_keys())})", file=sys.stderr)
        return 2

    dirname = _dirname()
    workdir = str(Path(os.path.expanduser("~")) / "fullStar" / dirname)
    command = build_spawn_command(dirname=dirname, agent=spec, prompt=args.prompt)

    if args.dry_run:
        print(f"dir={workdir}")
        print(command)
        print(build_spawn_applescript(script_path="/tmp/spawn-DRYRUN.sh"))
        return 0

    if sys.platform != "darwin":
        print("spawn requires macOS", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".sh") as f:
        f.write("#!/usr/bin/env bash\n" + command + "\n")
        script_path = f.name

    script = build_spawn_applescript(script_path=script_path)
    r = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        print(out or "osascript failed", file=sys.stderr)
        return r.returncode
    print(f"dir={workdir}")
    print(f"tab={(r.stdout or '').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_terminal_spawn_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/terminal-spawn.py term-bridge/test_terminal_spawn_cli.py
git commit -m "feat: terminal-spawn CLI (new tab + agent launch)"
```

---

### Task 4: `/new` command logic (`tg_new_command.py`)

**Files:**
- Create: `term-bridge/tg_new_command.py`
- Test: `term-bridge/test_tg_new_command.py`

**Interfaces:**
- Consumes: `agent_cli.get_agent`, `agent_cli.valid_keys`.
- Produces:
  - `SpawnResult` — `@dataclass(frozen=True)` `code: int`, `tab: int | None`, `workdir: str`, `raw: str`.
  - `parse_new(args: list[str]) -> tuple[str | None, str]` — returns `(agent_key_or_None, prompt)`.
  - `handle_new(args: list[str], *, is_macos: bool, spawn: Callable[[str, str], SpawnResult]) -> tuple[str, int | None]` — returns `(reply_text, new_tab_or_None)`. `spawn(agent_key, prompt)` is injected so the logic is testable without a terminal.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_tg_new_command.py
"""Tests for tg_new_command — pure /new parse + validate + reply formatting."""
from __future__ import annotations

import tg_new_command as nc
from tg_new_command import SpawnResult


def _ok(key, prompt):
    return SpawnResult(code=0, tab=3, workdir="/Users/x/fullStar/2026-06-19-2230", raw="tab=3")


def _fail(key, prompt):
    return SpawnResult(code=1, tab=None, workdir="", raw="osascript boom")


def test_parse_bare_returns_none_key():
    assert nc.parse_new([]) == (None, "")


def test_parse_agent_and_prompt():
    assert nc.parse_new(["Claude", "fix", "it"]) == ("claude", "fix it")


def test_bare_new_gives_usage_no_tab():
    reply, tab = nc.handle_new([], is_macos=True, spawn=_ok)
    assert tab is None
    assert "claude" in reply and "codex" in reply


def test_unknown_agent_lists_valid():
    reply, tab = nc.handle_new(["kitty"], is_macos=True, spawn=_ok)
    assert tab is None
    assert "kitty" in reply
    assert "claude" in reply


def test_non_macos_message():
    reply, tab = nc.handle_new(["claude"], is_macos=False, spawn=_ok)
    assert tab is None
    assert "macOS" in reply


def test_success_returns_tab_and_mentions_dir():
    reply, tab = nc.handle_new(["claude", "fix bug"], is_macos=True, spawn=_ok)
    assert tab == 3
    assert "claude" in reply
    assert "2026-06-19-2230" in reply
    assert "fix bug" in reply


def test_failure_reports_error_no_tab():
    reply, tab = nc.handle_new(["claude"], is_macos=True, spawn=_fail)
    assert tab is None
    assert "boom" in reply
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_tg_new_command.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tg_new_command'`

- [ ] **Step 3: Write minimal implementation**

```python
# term-bridge/tg_new_command.py
"""Pure logic for the `/new <agent> [prompt]` Telegram command.

Parses the command, validates the agent against the registry, delegates the
actual terminal spawn to an injected callable, and formats the reply. Keeping
this free of subprocess/platform calls makes it unit-testable; tg_relay_patches
wires it to the real spawn and applies the retarget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_cli import get_agent, valid_keys


@dataclass(frozen=True)
class SpawnResult:
    code: int
    tab: int | None
    workdir: str
    raw: str


def _usage() -> str:
    return (
        "用法: /new claude|codex [初始提示词]\n"
        f"可用 agent: {', '.join(valid_keys())}"
    )


def parse_new(args: list[str]) -> tuple[str | None, str]:
    if not args:
        return (None, "")
    return (args[0].strip().lower(), " ".join(args[1:]).strip())


def handle_new(
    args: list[str],
    *,
    is_macos: bool,
    spawn: Callable[[str, str], SpawnResult],
) -> tuple[str, int | None]:
    key, prompt = parse_new(args)
    if key is None:
        return (_usage(), None)
    if get_agent(key) is None:
        return (f"未知 agent: {key}\n可用: {', '.join(valid_keys())}", None)
    if not is_macos:
        return ("开新会话需要 macOS", None)

    res = spawn(key, prompt)
    if res.code != 0:
        return (f"spawn 失败:\n{res.raw[:800]}", None)

    preview = (prompt[:80] + ("…" if len(prompt) > 80 else "")) if prompt else "(无初始提示)"
    where = res.workdir or f"~/fullStar/<ts>"
    tabnote = f"tab {res.tab}" if res.tab is not None else "新 tab"
    reply = (
        f"✓ 已启动 {key} @ {where} ({tabnote})\n"
        f"{preview}\n"
        "(后续消息将注入此会话)"
    )
    return (reply, res.tab)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_tg_new_command.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add term-bridge/tg_new_command.py term-bridge/test_tg_new_command.py
git commit -m "feat: /new command parse + validate + reply logic"
```

---

### Task 5: Wire `/new` into the relay (`tg_relay_patches.py`)

**Files:**
- Modify: `tg-relay/tg_relay_patches.py` (add `re` import, `_spawn_session`, `/new` branch in `handle_command`, `/help` line)
- Test: `term-bridge/test_tg_new_wiring.py`

**Interfaces:**
- Consumes: `tg_new_command.handle_new`, `tg_new_command.SpawnResult`, `terminal-spawn.py` CLI.
- Produces: relay `/new` command; on success sets `os.environ["TG_ITERM_WINDOW"]="front"` and `os.environ["TG_ITERM_TAB"]=str(tab)`. `_spawn_session(agent_key, prompt) -> SpawnResult` runs `terminal-spawn.py` and parses `dir=`/`tab=` from stdout.

- [ ] **Step 1: Write the failing test**

```python
# term-bridge/test_tg_new_wiring.py
"""Tests for the _spawn_session stdout parser used by the relay /new wiring."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tg-relay"))
import tg_relay_patches as patches


def test_parse_spawn_output_extracts_dir_and_tab():
    res = patches._parse_spawn_output(0, "dir=/Users/x/fullStar/2026-06-19-2230\ntab=4\n", "")
    assert res.code == 0
    assert res.tab == 4
    assert res.workdir == "/Users/x/fullStar/2026-06-19-2230"


def test_parse_spawn_output_failure_keeps_raw():
    res = patches._parse_spawn_output(1, "", "osascript boom")
    assert res.code == 1
    assert res.tab is None
    assert "boom" in res.raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd term-bridge && python -m pytest test_tg_new_wiring.py -v`
Expected: FAIL with `AttributeError: module 'tg_relay_patches' has no attribute '_parse_spawn_output'`

- [ ] **Step 3: Write minimal implementation**

Add `import re` near the top of `tg-relay/tg_relay_patches.py` (with the other stdlib imports), and add these module-level helpers after `_schedule_iterm_monitor_poll`:

```python
def _parse_spawn_output(code: int, stdout: str, stderr: str):
    from tg_new_command import SpawnResult
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


def _spawn_session(agent_key: str, prompt: str):
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
```

Then inside `apply(mod)`, in `handle_command`, add a `/new` branch before `return orig_cmd(text)`:

```python
        if cmd == "/new":
            from tg_new_command import handle_new
            reply, new_tab = handle_new(
                parts[1:], is_macos=(sys.platform == "darwin"), spawn=_spawn_session
            )
            if new_tab is not None:
                os.environ["TG_ITERM_WINDOW"] = "front"
                os.environ["TG_ITERM_TAB"] = str(new_tab)
            return reply
```

And add this line to the `/help` text block (after the `/tabs` line):

```python
            "/new claude|codex [prompt] — 新 tab 启动 agent 会话\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd term-bridge && python -m pytest test_tg_new_wiring.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite + a dry-run smoke check**

Run: `cd term-bridge && python -m pytest -q`
Expected: all tests pass.

Run: `cd /Users/maxwell/Documents/aiTrees/fullStar && python tg-relay/tg-relay.py --dry-run "/new claude fix the login bug"`
Expected: stdout shows the `/new` reply (`已启动 claude …`) on macOS, or the `开新会话需要 macOS` line off-macOS. (On macOS this actually opens a tab — only run if you want the live check.)

- [ ] **Step 6: Commit**

```bash
git add tg-relay/tg_relay_patches.py term-bridge/test_tg_new_wiring.py
git commit -m "feat: wire /new into tg-relay with retarget to new tab"
```

---

## Self-Review

**Spec coverage:**
- Command syntax `/new claude|codex [prompt]` → Task 4 `parse_new`/`handle_new`, Task 5 wiring. ✓
- Chained shell line (mkdir/cd/install-if-missing/launch) → Task 2 `build_spawn_command`. ✓
- Auto-install via `|| <installer>` → Task 1 registry + Task 2 builder. ✓
- First prompt as positional arg, empty → no arg → Task 2 tests. ✓
- Timestamp dir name → Task 3 `_dirname`. ✓
- New tab vs new window → Task 2 `build_spawn_applescript`. ✓
- Retarget via `TG_ITERM_WINDOW`/`TG_ITERM_TAB` → Task 5. ✓
- New files `agent_cli.py`, `terminal_spawn_lib.py`, `terminal-spawn.py` → Tasks 1–3; `/help` line + wiring → Task 5. ✓ (Spec named 3 new files; this plan adds a 4th, `tg_new_command.py`, to keep the relay-side logic unit-testable — consistent with the existing `tg_format_config` pattern.)
- Error handling: unknown agent, non-macOS, osascript failure → Task 4 tests. ✓
- Testing per module → Tasks 1–5 each ship tests. ✓
- Non-goals (no persistent routing file, no monitor retarget, no extra agents) → honored; retarget is in-process env only. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. The single `~/fullStar/<ts>` literal in `tg_new_command._usage`/fallback is intentional display text, not a placeholder.

**Type consistency:** `SpawnResult(code, tab, workdir, raw)` defined in Task 4 and constructed identically by `_parse_spawn_output` in Task 5. `handle_new` signature `(args, *, is_macos, spawn)` matches its caller in Task 5. `AgentSpec` fields (`key`, `check`, `launch`, `installer`) used consistently in Tasks 1–3. `build_spawn_command(*, dirname, agent, prompt)` and `build_spawn_applescript(*, script_path)` signatures match callers in Task 3.
