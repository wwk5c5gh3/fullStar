"""mac-veil CLI: on | off | status | setup | passwd | boot | autostart."""
from __future__ import annotations

import getpass
import sys

from mac_veil import core


def _setup_interactive() -> tuple[bool, str]:
    pw1 = getpass.getpass("Set veil password: ")
    if pw1 != getpass.getpass("Repeat: "):
        return False, "passwords do not match"
    if not pw1:
        return False, "password must not be empty"
    core.set_password(pw1)
    ans = input("Auto-veil on login? [y/N]: ").strip().lower()
    core.set_boot(ans in ("y", "yes"))
    ok, msg = core.install_agent()
    if not ok:
        return False, msg
    return True, f"✓ password set + boot-default={'on' if ans in ('y','yes') else 'off'} + {msg}"


def _change_password_interactive() -> tuple[bool, str]:
    cfg = core.load_config()
    if cfg.get("pwd_hash"):  # verify current password before changing it
        if not core.verify_password(getpass.getpass("Current password: "), cfg):
            return False, "current password is wrong"
    new1 = getpass.getpass("New password: ")
    if new1 != getpass.getpass("Repeat: "):
        return False, "passwords do not match"
    if not new1:
        return False, "password must not be empty"
    core.set_password(new1)
    return True, "✓ password changed"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    rest = argv[1:]

    if cmd == "on":
        ok, msg = core.start(timeout=float(rest[0]) if rest else 0)
    elif cmd == "off":
        ok, msg = core.stop()
    elif cmd == "status":
        ok, msg = True, core.status()
    elif cmd == "setup":
        ok, msg = _setup_interactive()
    elif cmd in ("passwd", "change-password"):
        ok, msg = _change_password_interactive()
    elif cmd == "set-password":
        if not rest:
            ok, msg = False, "usage: set-password <password>"
        else:
            core.set_password(rest[0]); ok, msg = True, "✓ password set"
    elif cmd == "boot":
        if rest and rest[0] in ("on", "off"):
            core.set_boot(rest[0] == "on"); ok, msg = True, f"boot-default: {rest[0]}"
        else:
            ok, msg = False, "usage: boot on|off"
    elif cmd == "boot-start":
        ok, msg = core.boot_start()
    elif cmd in ("install-agent", "autostart-on"):
        ok, msg = core.install_agent()
    elif cmd in ("uninstall-agent", "autostart-off"):
        ok, msg = core.uninstall_agent()
    else:
        ok, msg = False, (
            f"usage: mac-veil on|off|status|setup|passwd|set-password|boot|"
            f"install-agent|uninstall-agent (got {cmd!r})"
        )
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
