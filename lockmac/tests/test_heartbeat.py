"""Tests for the dead-man heartbeat decision logic (pure)."""
from lockmac import tg, core


def test_heartbeat_due_when_interval_elapsed():
    assert tg.heartbeat_due(last_sent=0.0, now=100.0, interval=60) is True


def test_heartbeat_not_due_within_interval():
    assert tg.heartbeat_due(last_sent=100.0, now=130.0, interval=60) is False


def test_heartbeat_off_when_interval_zero():
    assert tg.heartbeat_due(last_sent=0.0, now=99999.0, interval=0) is False


def test_deadman_triggers_after_grace_without_ack():
    # heartbeat sent at 100, never acked (last_ack older), now 100+grace
    assert tg.deadman_triggered(last_sent=100.0, last_ack=50.0, now=400.0, grace=300) is True


def test_deadman_not_triggered_within_grace():
    assert tg.deadman_triggered(last_sent=100.0, last_ack=50.0, now=200.0, grace=300) is False


def test_deadman_not_triggered_when_acked():
    # acked after the heartbeat was sent → safe
    assert tg.deadman_triggered(last_sent=100.0, last_ack=150.0, now=999.0, grace=300) is False


def test_deadman_not_triggered_before_any_heartbeat():
    assert tg.deadman_triggered(last_sent=0.0, last_ack=0.0, now=999.0, grace=300) is False


def test_deadman_fires_even_as_heartbeats_keep_resending():
    # regression: heartbeats resend every interval (last_sent keeps advancing),
    # but with no ack the deadline must still be reached (measured from last_ack).
    # last_ack=0 (never tapped), last_sent=280 (latest beat), grace=300, now=300
    assert tg.deadman_triggered(last_sent=280.0, last_ack=0.0, now=300.0, grace=300) is True


def test_offline_triggered_after_timeout():
    assert tg.offline_triggered(last_online=100.0, now=3700.0, offline=3600) is True


def test_offline_not_triggered_within_timeout():
    assert tg.offline_triggered(last_online=100.0, now=200.0, offline=3600) is False


def test_offline_disabled_when_zero():
    assert tg.offline_triggered(last_online=0.0, now=99999.0, offline=0) is False


def test_core_heartbeat_cfg_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    iv, gr, ac, off = core.heartbeat_cfg()
    assert (iv, off) == (0, 0)  # default off
    core.set_heartbeat(1800, 600, "purge", 7200)
    assert core.heartbeat_cfg() == (1800, 600, "purge", 7200)
    core.set_heartbeat(60, 120, "bogus")  # invalid action → lock; offline defaults 0
    assert core.heartbeat_cfg()[2] == "lock"
    assert core.heartbeat_cfg()[3] == 0
