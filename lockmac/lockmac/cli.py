"""lockmac CLI: on | off | status | setup | passwd | boot | autostart."""
from __future__ import annotations

import getpass
import sys

from lockmac import core


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


def _tg_setup_interactive() -> tuple[bool, str]:
    from lockmac import tg

    token = input("Bot token (from @BotFather): ").strip()
    if not token:
        return False, "token required"
    input("Now send any message to your bot in Telegram, then press Enter… ")
    chat = tg.fetch_chat_id(token)
    if not chat:
        return False, "couldn't fetch chat id — message the bot first, then retry"
    tg.set_tg(token, chat)
    return True, f"✓ Telegram bound (chat {chat}). Run `lockmac tg-listen` to enable remote control."


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
    elif cmd == "tg-setup":
        ok, msg = _tg_setup_interactive()
    elif cmd == "tg-test":
        from lockmac import tg
        ok = tg.notify("lockmac: Telegram test ✓")
        msg = "✓ sent" if ok else "failed (run tg-setup first?)"
    elif cmd == "tg-listen":
        from lockmac import tg
        return tg.listen()
    elif cmd == "tg-install":
        ok, msg = core.install_tg_agent()
    elif cmd == "tg-uninstall":
        ok, msg = core.uninstall_tg_agent()
    else:
        ok, msg = False, (
            f"usage: lockmac on|off|status|setup|passwd|set-password|boot|"
            f"install-agent|uninstall-agent|tg-setup|tg-test|tg-listen|"
            f"tg-install|tg-uninstall (got {cmd!r})"
        )
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
