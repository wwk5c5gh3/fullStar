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
