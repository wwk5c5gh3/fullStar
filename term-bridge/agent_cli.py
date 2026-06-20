"""Registry of spawnable coding-agent CLIs (launch + installer commands).

Single source of truth for `/new <agent>`. Installer strings are editable
constants — verify against current official docs when they change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Flags that make an agent auto-approve every tool call. Approval mode strips
# these so the agent prompts instead — those prompts surface as Telegram option
# buttons (interactive-prompt feature), letting the operator approve/deny by tap.
_BYPASS_FLAGS = (
    "--permission-mode bypassPermissions",
    "--dangerously-skip-permissions",
)


def _approve_mode_path() -> Path:
    return ROOT / "inbox" / "approve-mode"


def read_approve_mode() -> bool:
    if os.environ.get("TG_AGENT_APPROVE", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return _approve_mode_path().is_file()


def set_approve_mode(on: bool) -> None:
    p = _approve_mode_path()
    if on:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("1", encoding="utf-8")
    else:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def approval_launch(launch: str) -> str:
    """Strip auto-approve flags so the agent prompts on each tool call."""
    out = launch
    for flag in _BYPASS_FLAGS:
        out = out.replace(flag, "")
    return " ".join(out.split())


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
    """Return the agent spec, with its launch command overridable via .env.

    Set `AGENT_<KEY>_LAUNCH` to fully customize how the agent starts. The value
    has spaces, so it MUST be quoted in .env (it is sourced by the daemon):
      AGENT_CLAUDE_LAUNCH="claude --permission-mode bypassPermissions --model opus"
      AGENT_CODEX_LAUNCH="codex --model gpt-5"
    """
    spec = AGENTS.get(key.strip().lower())
    if spec is None:
        return None
    override = os.environ.get(f"AGENT_{spec.key.upper()}_LAUNCH", "").strip()
    result = replace(spec, launch=override) if override else spec
    if read_approve_mode():
        result = replace(result, launch=approval_launch(result.launch))
    return result


def valid_keys() -> tuple[str, ...]:
    return tuple(AGENTS.keys())
