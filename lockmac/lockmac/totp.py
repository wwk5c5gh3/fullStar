"""TOTP (RFC 6238) — second factor for lockmac, stdlib only.

Same algorithm on the Swift side (overlay.swift) so a code verifies identically
whether you unlock locally (password + code) or via Telegram (chat + code).
Defaults: HMAC-SHA1, 30s step, 6 digits — compatible with Google Authenticator,
1Password, etc.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def generate_secret(length: int = 20) -> str:
    """Random base32 secret (no padding), ready for an authenticator app."""
    return base64.b32encode(os.urandom(length)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_now(secret_b32: str, t: float | None = None, step: int = 30, digits: int = 6) -> str:
    now = int(t if t is not None else time.time())
    return _hotp(secret_b32, now // step, digits)


def verify_totp(
    secret_b32: str,
    code: str,
    t: float | None = None,
    step: int = 30,
    digits: int = 6,
    window: int = 1,
) -> bool:
    """True if `code` matches within ±window steps (clock-skew tolerance)."""
    if not secret_b32 or not code:
        return False
    code = code.strip()
    now = int(t if t is not None else time.time())
    base = now // step
    return any(_hotp(secret_b32, base + w, digits) == code for w in range(-window, window + 1))


def provisioning_uri(secret_b32: str, label: str = "veil", issuer: str = "lockmac") -> str:
    """otpauth:// URI for an authenticator app (paste/scan to enroll)."""
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(label)}"
        f"?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )
