# mac-veil

A **privacy veil for macOS**: black out every display with a top-most overlay so
onlookers can't see your screen — **without locking the Mac**. Remote control,
screenshots, and automation keep working behind it.

Standalone: pure Python stdlib + a tiny Swift overlay. No Telegram, no host
project required. (mob-remote integrates it for remote on/off, but mac-veil
works entirely on its own.)

## Why "veil" not "lock"

- The overlay uses `CGShieldingWindowLevel` (above normal windows, covers the
  menu bar / Dock / all Spaces).
- `screencapture` and window-level grabs **bypass it** — so screenshots/remote
  tools still see the real content while onlookers see black.
- It is a **privacy screen, not a security lock**: Force-Quit, `ssh kill`, or a
  reboot all dismiss it. Good against shoulder-surfing, not a determined person
  at the keyboard.

## Install

```bash
pip install -e .          # needs swiftc (Xcode CLT) on macOS
```

## Use

```bash
mac-veil setup            # set a password + choose login autostart (installs LaunchAgent)
mac-veil on               # raise the veil (screen goes black; you keep working)
mac-veil on 30            # ...auto-dismiss after 30s (safety backstop)
mac-veil off              # dismiss
mac-veil status
mac-veil passwd           # change password (verifies the current one first)
mac-veil boot on|off      # toggle "veil on next login"
mac-veil install-agent    # / uninstall-agent — manage login autostart
```

## Three ways to dismiss (never get locked out)

1. **Local password** — type it into the on-screen field (salted SHA-256). Works
   with no network.
2. **SIGTERM** — `mac-veil off`, or any integrator's remote "off".
3. **`--timeout` backstop** — `mac-veil on N` auto-dismisses after N seconds.

Last resort: `ssh` in and `kill` the process.

## Files

- `mac_veil/overlay.swift` — the Swift overlay (compiled on first use to
  `~/.cache/mac-veil/mac-veil`)
- `mac_veil/core.py` — build / config / password / boot / process control
- `mac_veil/cli.py` — the `mac-veil` command
- config: `~/.config/mac-veil/config.json` (salted hash + boot flag; no plaintext)

MIT
