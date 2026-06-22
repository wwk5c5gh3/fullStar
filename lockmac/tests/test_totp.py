"""Tests for lockmac.totp — verified against RFC 6238 test vectors."""
import base64

from lockmac import totp

# RFC 6238 uses the ASCII seed "12345678901234567890" (SHA1).
_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


def test_rfc6238_vector_t59():
    # RFC 6238 Appendix B: T=59 → 94287082 (8 digits) → 6 digits = "287082"
    assert totp.totp_now(_SECRET, t=59) == "287082"


def test_rfc6238_vector_t1111111109():
    # 07081804 (8) → "081804" (6)
    assert totp.totp_now(_SECRET, t=1111111109) == "081804"


def test_verify_accepts_current():
    code = totp.totp_now(_SECRET, t=1000)
    assert totp.verify_totp(_SECRET, code, t=1000) is True


def test_verify_window_tolerance():
    code = totp.totp_now(_SECRET, t=1000)          # previous step
    assert totp.verify_totp(_SECRET, code, t=1000 + 30, window=1) is True


def test_verify_rejects_wrong():
    assert totp.verify_totp(_SECRET, "000000", t=59) is False
    assert totp.verify_totp(_SECRET, "", t=59) is False
    assert totp.verify_totp("", "287082", t=59) is False


def test_generate_secret_is_base32():
    s = totp.generate_secret()
    # decodable as base32 (with padding) → valid secret
    pad = "=" * ((8 - len(s) % 8) % 8)
    assert base64.b32decode(s + pad)


def test_provisioning_uri():
    uri = totp.provisioning_uri("ABC234", label="veil")
    assert uri.startswith("otpauth://totp/lockmac:veil?")
    assert "secret=ABC234" in uri


def test_core_totp_config_roundtrip(tmp_path, monkeypatch):
    from lockmac import core
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    assert core.totp_enabled() is False
    core.set_totp_secret("ABC234")
    assert core.totp_enabled() is True
    assert core.get_totp_secret() == "ABC234"
    core.set_totp_secret("")
    assert core.totp_enabled() is False
