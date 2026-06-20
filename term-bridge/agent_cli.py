"""Registry of spawnable coding-agent CLIs (launch + installer commands).

Single source of truth for `/new <agent>`. Installer strings are editable
constants — verify against current official docs when they change.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace


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
    return replace(spec, launch=override) if override else spec


def valid_keys() -> tuple[str, ...]:
    return tuple(AGENTS.keys())
