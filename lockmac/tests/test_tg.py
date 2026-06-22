"""Tests for lockmac.tg pure logic (no network)."""
from lockmac import tg


def test_parse_command_known():
    assert tg.parse_command("/lock") == "lock"
    assert tg.parse_command("/unlock") == "unlock"
    assert tg.parse_command("/status") == "status"


def test_parse_command_with_botname_suffix():
    assert tg.parse_command("/lock@MyBot") == "lock"


def test_parse_command_case_and_whitespace():
    assert tg.parse_command("  /UNLOCK  ") == "unlock"


def test_parse_command_unknown():
    assert tg.parse_command("/foo") is None
    assert tg.parse_command("hello") is None
    assert tg.parse_command("") is None


def test_extract_chat_id_latest():
    updates = {"result": [
        {"message": {"chat": {"id": 111}}},
        {"message": {"chat": {"id": 222}}},
    ]}
    assert tg.extract_chat_id(updates) == "222"


def test_extract_chat_id_empty():
    assert tg.extract_chat_id({"result": []}) is None
    assert tg.extract_chat_id({}) is None


def test_set_tg_roundtrip(tmp_path, monkeypatch):
    from lockmac import core
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    tg.set_tg("123:ABC", "999")
    cfg = core.load_config()
    assert cfg["tg_token"] == "123:ABC"
    assert cfg["tg_chat"] == "999"


def test_install_tg_agent_refuses_without_creds(tmp_path, monkeypatch):
    # KeepAlive on tg-listen with no token would crash-loop → must refuse.
    from lockmac import core
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    ok, msg = core.install_tg_agent()
    assert ok is False
    assert "tg-setup" in msg
