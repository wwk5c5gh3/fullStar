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
