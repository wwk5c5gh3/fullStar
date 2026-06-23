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

    if cmd in ("on", "veil"):
        ok, msg = core.start(timeout=float(rest[0]) if rest else 0)
    elif cmd in ("off", "unveil"):
        ok, msg = core.stop()
    elif cmd == "lock":
        ok, msg = core.system_lock()  # real system lock (one-way)
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
    elif cmd in ("setup-2fa", "2fa-setup"):
        from lockmac import totp
        secret = totp.generate_secret()
        core.set_totp_secret(secret)
        uri = totp.provisioning_uri(secret)
        ok, msg = True, (
            "✓ 二步验证已启用（解除遮罩需 密码 + 6位码）\n"
            f"密钥(手输): {secret}\n"
            f"或扫码/粘贴到 authenticator:\n{uri}"
        )
    elif cmd == "2fa-off":
        core.set_totp_secret(""); ok, msg = True, "二步验证已关闭"
    elif cmd in ("heartbeat", "deadman"):
        # heartbeat <interval_s> <grace_s> <action> [offline_s]
        #   interval=0 → no active check-in; offline=0 → no lost-contact trigger
        #   action: lock | veil | purge
        if not rest:
            iv, gr, ac, off = core.heartbeat_cfg()
            ok, msg = True, (
                f"心跳: {'关' if iv<=0 else f'每{iv}s/宽限{gr}s'}"
                f" · 失联超时: {'关' if off<=0 else f'{off}s'}"
                f" · 动作: {ac}\n"
                "用法: lockmac deadman <签到间隔秒> <宽限秒> <lock|veil|purge> [失联超时秒]\n"
                "  例: lockmac deadman 0 0 purge 3600   # 连不上TG满1小时→删目录\n"
                "  例: lockmac deadman 1800 600 lock 7200  # 30min签到/10min不点，或失联2h→锁"
            )
        else:
            try:
                iv = int(rest[0])
                gr = int(rest[1]) if len(rest) > 1 else 300
                ac = rest[2] if len(rest) > 2 else "lock"
                off = int(rest[3]) if len(rest) > 3 else 0
                core.set_heartbeat(iv, gr, ac, off)
                _, _, ac2, _ = core.heartbeat_cfg()
                ok, msg = True, (
                    f"✓ dead-man 已设：动作={ac2}"
                    f"{f'，每{iv}s签到/{gr}s不点触发' if iv>0 else ''}"
                    f"{f'，失联{off}s触发' if off>0 else ''}"
                    + ("" if (iv > 0 or off > 0) else "（两个触发都关=不会自动执行）")
                )
            except ValueError:
                ok, msg = False, "用法: lockmac deadman <签到间隔秒> <宽限秒> <lock|veil|purge> [失联超时秒]"
    elif cmd == "purge-add":
        if not rest:
            ok, msg = False, "用法: lockmac purge-add <绝对路径>"
        elif not core.is_safe_purge_path(rest[0]):
            ok, msg = False, f"拒绝：{rest[0]} 是危险/系统路径，不允许"
        else:
            dirs = core.get_purge_dirs()
            if rest[0] not in dirs:
                dirs.append(rest[0]); core.set_purge_dirs(dirs)
            ok, msg = True, f"✓ 已加入删除清单：{rest[0]}\n当前：{core.get_purge_dirs()}"
    elif cmd == "purge-list":
        ok, msg = True, f"删除清单：{core.get_purge_dirs() or '(空)'}"
    elif cmd == "purge-clear":
        core.set_purge_dirs([]); ok, msg = True, "✓ 删除清单已清空"
    elif cmd == "purge-now":
        if "--yes" not in rest:
            ok, msg = False, (f"⚠️ 将删除：{core.get_purge_dirs() or '(未配置)'}\n"
                              "确认请加 --yes： lockmac purge-now --yes")
        else:
            ok, msg = core.purge_dirs_now()
    elif cmd == "tg-install":
        ok, msg = core.install_tg_agent()
    elif cmd == "tg-uninstall":
        ok, msg = core.uninstall_tg_agent()
    else:
        ok, msg = False, (
            f"usage: lockmac veil|unveil|lock|status|setup|passwd|set-password|boot|"
            f"setup-2fa|2fa-off|deadman|purge-add|purge-list|purge-clear|purge-now|"
            f"install-agent|uninstall-agent|tg-setup|tg-test|tg-listen|tg-install|"
            f"tg-uninstall (got {cmd!r})\n"
            f"  veil/unveil = removable privacy overlay; lock = real system lock (one-way)"
        )
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
