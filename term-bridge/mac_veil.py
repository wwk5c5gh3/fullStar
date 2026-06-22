"""Control the mac-veil privacy overlay: build-once, start/stop, password, boot.

Three dismissal paths so you can never get locked out:
  1. Local password (break-glass) — works even if Telegram is down.
  2. Telegram /veil off — SIGTERM.
  3. Optional --timeout backstop.

Config (inbox/veil-config.json, gitignored): salted SHA-256 password hash +
enable_on_boot flag. The hash/salt are passed to the Swift veil via env
(MAC_VEIL_PWHASH / MAC_VEIL_SALT), never on argv. Boot autostart is a per-user
LaunchAgent that runs `mac_veil.py boot-start` at login.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "term-bridge" / "mac-veil.swift"
BIN = ROOT / "term-bridge" / ".bin" / "mac-veil"
PIDFILE = ROOT / "inbox" / "mac-veil.pid"
CONFIG = ROOT / "inbox" / "veil-config.json"

AGENT_LABEL = "com.mobremote.veil"
AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"


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
    """Env carrying the password hash/salt to the Swift veil (not on argv)."""
    cfg = load_config()
    env = dict(os.environ)
    if cfg.get("pwd_hash") and cfg.get("salt"):
        env["MAC_VEIL_PWHASH"] = cfg["pwd_hash"]
        env["MAC_VEIL_SALT"] = cfg["salt"]
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
    msg = message or os.environ.get("MAC_VEIL_MESSAGE") or None
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
    note = "" if has_pw else "（⚠ 未设本地密码，TG 不可用时只能 SSH/kill 解除——建议 ./mob veil setup）"
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
    pw = "已设" if cfg.get("pwd_hash") else "未设"
    boot = "开" if cfg.get("enable_on_boot") else "关"
    agent = "已装" if AGENT_PLIST.exists() else "未装"
    return f"veil: {up} · 本地密码: {pw} · 开机默认: {boot} · 自启服务: {agent}"


# ───────────────────────── LaunchAgent (boot autostart) ─────────────────────────
def _plist_xml() -> str:
    py = sys.executable
    script = str(ROOT / "term-bridge" / "mac_veil.py")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{py}</string>
    <string>{script}</string>
    <string>boot-start</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
"""


def install_agent() -> tuple[bool, str]:
    AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PLIST.write_text(_plist_xml(), encoding="utf-8")
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(AGENT_PLIST)],
                   capture_output=True)  # ignore if not loaded
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(AGENT_PLIST)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"launchctl bootstrap failed: {(r.stderr or r.stdout).strip()}"
    return True, f"自启服务已安装：{AGENT_PLIST}"


def uninstall_agent() -> tuple[bool, str]:
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(AGENT_PLIST)],
                   capture_output=True)
    AGENT_PLIST.unlink(missing_ok=True)
    return True, "自启服务已卸载"


def boot_start() -> tuple[bool, str]:
    """Invoked by the LaunchAgent at login: veil up only if enabled in config."""
    if load_config().get("enable_on_boot"):
        return start()
    return True, "boot-start: enable_on_boot=false, 不遮挡"


# ───────────────────────── CLI ─────────────────────────
def _setup_interactive() -> tuple[bool, str]:
    import getpass

    pw1 = getpass.getpass("设置遮罩解除密码: ")
    pw2 = getpass.getpass("再输一次: ")
    if pw1 != pw2:
        return False, "两次密码不一致"
    if not pw1:
        return False, "密码不能为空"
    set_password(pw1)
    ans = input("开机默认自动遮挡? [y/N]: ").strip().lower()
    set_boot(ans in ("y", "yes"))
    ok, msg = install_agent()
    if not ok:
        return False, msg
    return True, f"✓ 已设密码 + 开机默认={'开' if ans in ('y','yes') else '关'} + {msg}"


def _change_password_interactive() -> tuple[bool, str]:
    import getpass

    cfg = load_config()
    if cfg.get("pwd_hash"):  # verify current password before allowing a change
        if not verify_password(getpass.getpass("当前密码: "), cfg):
            return False, "当前密码错误"
    new1 = getpass.getpass("新密码: ")
    if new1 != getpass.getpass("再输一次: "):
        return False, "两次密码不一致"
    if not new1:
        return False, "密码不能为空"
    set_password(new1)
    return True, "✓ 密码已更改"


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    rest = argv[1:]
    if cmd == "on":
        ok, msg = start(timeout=float(rest[0]) if rest else 0)
    elif cmd == "off":
        ok, msg = stop()
    elif cmd == "status":
        ok, msg = True, status()
    elif cmd == "setup":
        ok, msg = _setup_interactive()
    elif cmd in ("passwd", "change-password"):
        ok, msg = _change_password_interactive()
    elif cmd == "set-password":
        if not rest:
            ok, msg = False, "用法: set-password <密码>"
        else:
            set_password(rest[0]); ok, msg = True, "✓ 密码已设置"
    elif cmd == "boot":
        if rest and rest[0] in ("on", "off"):
            set_boot(rest[0] == "on"); ok, msg = True, f"开机默认遮挡: {rest[0]}"
        else:
            ok, msg = False, "用法: boot on|off"
    elif cmd == "boot-start":
        ok, msg = boot_start()
    elif cmd == "install-agent":
        ok, msg = install_agent()
    elif cmd == "uninstall-agent":
        ok, msg = uninstall_agent()
    else:
        ok, msg = False, f"用法: mac_veil.py on|off|status|setup|passwd|set-password|boot|install-agent|uninstall-agent (got {cmd!r})"
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
