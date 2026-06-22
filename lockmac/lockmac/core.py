"""lockmac core: build the Swift overlay, control it, manage password & boot.

Self-contained — no dependency on any host project. Paths follow XDG:
  overlay source : packaged alongside this module (overlay.swift)
  compiled binary: ~/.cache/lockmac/lockmac
  config         : ~/.config/lockmac/config.json   (salted SHA-256 hash + boot flag)
  pidfile        : ~/.cache/lockmac/lockmac.pid

Three dismissal paths so you can never get locked out:
  1. Local password (break-glass) — works with no network.
  2. SIGTERM (e.g. an integrator's remote "off").
  3. Optional --timeout backstop.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


def _xdg(var: str, default: Path) -> Path:
    raw = os.environ.get(var, "").strip()
    return Path(raw) if raw else default


HOME = Path.home()
CACHE_DIR = _xdg("XDG_CACHE_HOME", HOME / ".cache") / "lockmac"
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", HOME / ".config") / "lockmac"

SRC = Path(__file__).resolve().parent / "overlay.swift"
BIN = CACHE_DIR / "lockmac"
PIDFILE = CACHE_DIR / "lockmac.pid"
CONFIG = CONFIG_DIR / "config.json"

AGENT_LABEL = "com.lockmac"
AGENT_PLIST = HOME / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"

TG_AGENT_LABEL = "com.lockmac.tglisten"
TG_AGENT_PLIST = HOME / "Library" / "LaunchAgents" / f"{TG_AGENT_LABEL}.plist"


# ───────────────────────── build ─────────────────────────
def needs_build(src_mtime: float, bin_exists: bool, bin_mtime: float) -> bool:
    """True if the binary is missing or older than the source (pure, testable)."""
    if not bin_exists:
        return True
    return bin_mtime < src_mtime


def ensure_built() -> Path:
    src_m = SRC.stat().st_mtime
    bin_exists = BIN.exists()
    bin_m = BIN.stat().st_mtime if bin_exists else 0.0
    if needs_build(src_m, bin_exists, bin_m):
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", str(SRC), "-o", str(BIN)], check=True)
    return BIN


def build_argv(binary: Path, message: str | None, timeout: float) -> list[str]:
    """Construct the veil command line (pure, testable)."""
    cmd = [str(binary)]
    if timeout and timeout > 0:
        cmd += ["--timeout", str(timeout)]
    if message:
        cmd += ["--message", message]
    return cmd


# ───────────────────────── config / password ─────────────────────────
def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG)


def hash_password(password: str, salt: str) -> str:
    """Salted SHA-256 hex — MUST match the Swift side: sha256(salt + password)."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def set_password(password: str) -> None:
    if not password:
        raise ValueError("password must not be empty")
    salt = os.urandom(8).hex()
    cfg = load_config()
    cfg["salt"] = salt
    cfg["pwd_hash"] = hash_password(password, salt)
    save_config(cfg)


def verify_password(attempt: str, cfg: dict) -> bool:
    """True if attempt matches the stored salted hash (pure, testable)."""
    stored, salt = cfg.get("pwd_hash"), cfg.get("salt")
    if not stored or not salt:
        return False
    return hash_password(attempt, salt) == stored


def set_boot(enabled: bool) -> None:
    cfg = load_config()
    cfg["enable_on_boot"] = bool(enabled)
    save_config(cfg)


def _password_env() -> dict:
    cfg = load_config()
    env = dict(os.environ)
    if cfg.get("pwd_hash") and cfg.get("salt"):
        env["LOCKMAC_PWHASH"] = cfg["pwd_hash"]
        env["LOCKMAC_SALT"] = cfg["salt"]
    return env


# ───────────────────────── process control ─────────────────────────
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
    msg = message or os.environ.get("LOCKMAC_MESSAGE") or None
    proc = subprocess.Popen(
        build_argv(binary, msg, timeout),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=_password_env(),
    )
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(str(proc.pid))
    has_pw = bool(load_config().get("pwd_hash"))
    note = "" if has_pw else "（⚠ 未设本地密码，断网/无远程时只能 SSH/kill 解除——建议 lockmac setup）"
    return True, f"veil up (pid {proc.pid}){note}"


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
    cfg = load_config()
    up = f"up (pid {pid})" if pid else "off"
    pw = "set" if cfg.get("pwd_hash") else "unset"
    boot = "on" if cfg.get("enable_on_boot") else "off"
    agent = "installed" if AGENT_PLIST.exists() else "not installed"
    tg = "bound" if (cfg.get("tg_token") and cfg.get("tg_chat")) else "unbound"
    tg_svc = "on" if TG_AGENT_PLIST.exists() else "off"
    return (
        f"lockMac: {up} · password: {pw} · boot-default: {boot} · autostart: {agent}"
        f" · telegram: {tg} · tg-listen-svc: {tg_svc}"
    )


# ───────────────────────── LaunchAgent (boot autostart) ─────────────────────────
def _cli_path() -> list[str]:
    """How the LaunchAgent should invoke us: prefer the installed `lockmac`."""
    found = shutil.which("lockmac")
    if found:
        return [found]
    return [sys.executable, "-m", "lockmac.cli"]


def _plist_xml() -> str:
    prog = _cli_path() + ["boot-start"]
    items = "".join(f"    <string>{p}</string>\n" for p in prog)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"  <key>Label</key><string>{AGENT_LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n  <array>\n"
        f"{items}"
        "  </array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "</dict>\n</plist>\n"
    )


def install_agent() -> tuple[bool, str]:
    AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PLIST.write_text(_plist_xml(), encoding="utf-8")
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(AGENT_PLIST)],
                   capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(AGENT_PLIST)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"launchctl bootstrap failed: {(r.stderr or r.stdout).strip()}"
    return True, f"autostart installed: {AGENT_PLIST}"


def uninstall_agent() -> tuple[bool, str]:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(AGENT_PLIST)],
                   capture_output=True)
    AGENT_PLIST.unlink(missing_ok=True)
    return True, "autostart uninstalled"


def boot_start() -> tuple[bool, str]:
    """Invoked by the LaunchAgent at login: veil up only if enabled in config."""
    if load_config().get("enable_on_boot"):
        return start()
    return True, "boot-start: enable_on_boot=false, no veil"


# ───────────────────────── TG-listen autostart (KeepAlive) ─────────────────────────
def _tg_plist_xml() -> str:
    prog = _cli_path() + ["tg-listen"]
    items = "".join(f"    <string>{p}</string>\n" for p in prog)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"  <key>Label</key><string>{TG_AGENT_LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n  <array>\n"
        f"{items}"
        "  </array>\n"
        "  <key>RunAtLoad</key><true/>\n"
        "  <key>KeepAlive</key><true/>\n"  # restart the listener if it ever exits
        "</dict>\n</plist>\n"
    )


def install_tg_agent() -> tuple[bool, str]:
    cfg = load_config()
    if not cfg.get("tg_token") or not cfg.get("tg_chat"):
        return False, "run `lockmac tg-setup` first (no token/chat configured)"
    TG_AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    TG_AGENT_PLIST.write_text(_tg_plist_xml(), encoding="utf-8")
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(TG_AGENT_PLIST)],
                   capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(TG_AGENT_PLIST)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"launchctl bootstrap failed: {(r.stderr or r.stdout).strip()}"
    return True, f"tg-listen autostart installed: {TG_AGENT_PLIST}"


def uninstall_tg_agent() -> tuple[bool, str]:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(TG_AGENT_PLIST)],
                   capture_output=True)
    TG_AGENT_PLIST.unlink(missing_ok=True)
    return True, "tg-listen autostart uninstalled"
