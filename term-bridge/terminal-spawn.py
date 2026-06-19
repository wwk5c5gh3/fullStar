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
