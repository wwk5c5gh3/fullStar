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

Two levels of "lock":

| Command | Level | Remote-undo? |
|---|---|---|
| `veil` / `unveil` (= `on` / `off`) | app overlay — black out the screen, keep working | ✅ yes (password / Telegram) |
| `lock` | **real macOS system lock** (loginwindow) | ❌ no — one-way; needs the system password at the machine |

```bash
lockmac setup            # set a password + choose login autostart (installs LaunchAgent)
lockmac veil             # raise the privacy overlay (screen black; you keep working)
lockmac veil 30          # ...auto-dismiss after 30s (safety backstop)
lockmac unveil           # dismiss the overlay
lockmac lock             # REAL system lock — one-way, cannot be undone remotely
lockmac status
lockmac passwd           # change password (verifies the current one first)
lockmac setup-2fa        # enable two-step (TOTP); unlock then needs password + 6-digit code
lockmac boot on|off      # toggle "veil on next login"
lockmac install-agent    # / uninstall-agent — manage login autostart
```

### Two-step verification (TOTP, optional)

`lockmac setup-2fa` prints a secret + `otpauth://` URI — add it to an
authenticator (Google Authenticator, 1Password, …). After that the second factor
is required **both** ways:
- **Local**: the overlay shows a password field **and** a 6-digit code field.
- **Telegram**: `/unveil <6-digit-code>` (your chat is the first factor, the code
  the second).

Same RFC 6238 algorithm on both sides, so any authenticator code works
everywhere. `lockmac 2fa-off` disables it.

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
lockmac tg-listen    # long-poll in the foreground
lockmac tg-install   # …or install a KeepAlive LaunchAgent: tg-listen runs at
                     #   login and is restarted if it ever exits (tg-uninstall to remove)
```

From your chat send `/veil`, `/unveil`, `/lock`, or `/status` (only the configured
chat id is honored, fail-closed):
- `/veil` / `/unveil` — raise / dismiss the removable overlay
- `/lock` — **real system lock** (one-way; you can lock remotely but must unlock
  at the machine with the system password)

Use `tg-listen` for a foreground run, or `tg-install` to keep it always-on.

### Dead-man switch (auto-act if you don't respond / go offline)

`tg-listen` runs a local dead-man timer. **Two independent triggers** fire the
configured action (`lock` | `veil` | `purge`):

```bash
# deadman <check-in interval> <grace> <action> [offline-timeout]
lockmac deadman 1800 600 lock          # check-in every 30m, no tap in 10m → system lock
lockmac deadman 0 0 purge 3600         # no check-in; can't reach Telegram for 1h → purge dirs
lockmac deadman 1800 600 veil 7200     # check-in OR 2h offline → raise veil
lockmac deadman 0 0 lock 0             # both off
lockmac deadman                        # show current
```

- **Heartbeat trigger**: sends a **✅ 我在** button every interval; tap to reset.
  Miss the grace window → fire. (person AWOL while online)
- **Offline trigger**: can't reach Telegram for `offline-timeout` seconds → fire.
  Runs **locally**, so it works even with no network (device removed / powered off
  network). This is the true dead-man: the timer runs locally; only contact resets it.

Actions: `lock` = real system lock · `veil` = overlay · `purge` = delete the
configured directories.

### Purge list (for `action=purge`)

```bash
lockmac purge-add ~/Secret           # add a dir (rejects /, $HOME, system trees)
lockmac purge-add /Volumes/USB/data
lockmac purge-list
lockmac purge-clear
lockmac purge-now --yes              # delete now (manual; --yes required)
```

⚠️ **Destructive.** Guards: paths must be absolute and are rejected if they are
`/`, `$HOME` itself, or any system tree (`/System`, `/Library`, `/usr`, …). Only
specific directories you add are ever deleted. For real whole-disk crypto-erase
you need MDM (`EraseDevice`) — that's a later, server-backed phase.

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
