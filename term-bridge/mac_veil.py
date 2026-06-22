"""Control the mac-veil privacy overlay: build-once, start, stop, status.

The Swift source is compiled on first use into term-bridge/.bin/mac-veil
(gitignored); recompiled automatically when the source is newer. start() runs
it detached and records a pidfile; stop() sends SIGTERM (clean dismiss).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "term-bridge" / "mac-veil.swift"
BIN = ROOT / "term-bridge" / ".bin" / "mac-veil"
PIDFILE = ROOT / "inbox" / "mac-veil.pid"


def needs_build(src_mtime: float, bin_exists: bool, bin_mtime: float) -> bool:
    """True if the binary is missing or older than the source (pure, testable)."""
    if not bin_exists:
        return True
    return bin_mtime < src_mtime


def ensure_built() -> Path:
    """Compile the Swift veil if missing/stale. Returns the binary path."""
    src_m = SRC.stat().st_mtime
    bin_exists = BIN.exists()
    bin_m = BIN.stat().st_mtime if bin_exists else 0.0
    if needs_build(src_m, bin_exists, bin_m):
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", str(SRC), "-o", str(BIN)], check=True)
    return BIN


def _read_pid() -> int | None:
    try:
        pid = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def running_pid() -> int | None:
    """PID of a live veil process (pidfile first, then pgrep fallback)."""
    pid = _read_pid()
    if pid:
        return pid
    try:
        out = subprocess.run(
            ["pgrep", "-f", str(BIN)], capture_output=True, text=True, timeout=5
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    for tok in out.split():
        try:
            return int(tok)
        except ValueError:
            continue
    return None


def build_argv(binary: Path, message: str | None, timeout: float) -> list[str]:
    """Construct the veil command line (pure, testable)."""
    cmd = [str(binary)]
    if timeout and timeout > 0:
        cmd += ["--timeout", str(timeout)]
    if message:
        cmd += ["--message", message]
    return cmd


def start(message: str | None = None, timeout: float = 0) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "veil requires macOS"
    existing = running_pid()
    if existing:
        return True, f"veil already up (pid {existing})"
    try:
        binary = ensure_built()
    except (subprocess.CalledProcessError, OSError) as exc:
        return False, f"build failed: {exc}"
    msg = message or os.environ.get("MAC_VEIL_MESSAGE") or None
    proc = subprocess.Popen(
        build_argv(binary, msg, timeout),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(proc.pid))
    return True, f"veil up (pid {proc.pid})"


def stop() -> tuple[bool, str]:
    pid = running_pid()
    if not pid:
        PIDFILE.unlink(missing_ok=True)
        return True, "veil already off"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return False, f"stop failed: {exc}"
    PIDFILE.unlink(missing_ok=True)
    return True, "veil off"


def status() -> str:
    pid = running_pid()
    return f"veil: up (pid {pid})" if pid else "veil: off"


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    rest = argv[1:]
    if cmd == "on":
        timeout = float(rest[0]) if rest else 0
        ok, msg = start(timeout=timeout)
    elif cmd == "off":
        ok, msg = stop()
    elif cmd == "status":
        ok, msg = True, status()
    else:
        ok, msg = False, f"usage: mac_veil.py on|off|status (got {cmd!r})"
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
