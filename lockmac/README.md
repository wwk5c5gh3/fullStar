# lockmac

A **privacy veil for macOS**: black out every display with a top-most overlay so
onlookers can't see your screen — **without locking the Mac**. Remote control,
screenshots, and automation keep working behind it.

Standalone: pure Python stdlib + a tiny Swift overlay. No Telegram, no host
project required. (mob-remote integrates it for remote on/off, but lockmac
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
lockmac setup            # set a password + choose login autostart (installs LaunchAgent)
lockmac on               # raise the veil (screen goes black; you keep working)
lockmac on 30            # ...auto-dismiss after 30s (safety backstop)
lockmac off              # dismiss
lockmac status
lockmac passwd           # change password (verifies the current one first)
lockmac boot on|off      # toggle "veil on next login"
lockmac install-agent    # / uninstall-agent — manage login autostart
```

## Three ways to dismiss (never get locked out)

1. **Local password** — type it into the on-screen field (salted SHA-256). Works
   with no network.
2. **SIGTERM** — `lockmac off`, or any integrator's remote "off".
3. **`--timeout` backstop** — `lockmac on N` auto-dismisses after N seconds.

Last resort: `ssh` in and `kill` the process.

## Telegram remote control (optional, self-contained)

lockmac can be driven from Telegram on its own — no other project needed:

```bash
lockmac tg-setup     # paste bot token, message the bot once → chat id auto-saved
lockmac tg-test      # send a test message
lockmac tg-listen    # long-poll; /lock /unlock /status from your chat control it
```

From your chat send `/lock`, `/unlock`, `/status`. Only the configured chat id is
honored (fail-closed). `tg-listen` runs in the foreground — keep it alive with
`nohup`, `tmux`, or a LaunchAgent.

> One bot, one poller: getUpdates allows a single consumer per token. If
> something else already polls that bot (e.g. another relay), give lockmac its
> own bot — otherwise they conflict (Telegram 409).

## Files

- `lockmac/overlay.swift` — the Swift overlay (compiled on first use to
  `~/.cache/lockmac/lockmac`)
- `lockmac/core.py` — build / config / password / boot / process control
- `lockmac/cli.py` — the `lockmac` command
- config: `~/.config/lockmac/config.json` (salted hash + boot flag; no plaintext)

MIT
