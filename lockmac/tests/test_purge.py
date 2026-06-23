"""Tests for the guarded purge (delete configured dirs) — safety first."""
from pathlib import Path

from lockmac import core


def test_is_safe_purge_path_rejects_roots_and_system():
    for bad in ["/", "/System", "/usr", "/bin", "/Library", "/Applications",
                "/Users", "/Volumes", str(Path.home())]:
        assert core.is_safe_purge_path(bad) is False, bad


def test_is_safe_purge_path_rejects_system_subtrees():
    assert core.is_safe_purge_path("/System/Library/x") is False
    assert core.is_safe_purge_path("/Library/Foo") is False


def test_is_safe_purge_path_rejects_relative_and_empty():
    assert core.is_safe_purge_path("relative/dir") is False
    assert core.is_safe_purge_path("") is False
    assert core.is_safe_purge_path("   ") is False


def test_is_safe_purge_path_allows_specific_dirs():
    assert core.is_safe_purge_path(str(Path.home() / "Secret")) is True
    assert core.is_safe_purge_path("/Volumes/USB/data") is True


def test_purge_dirs_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    assert core.get_purge_dirs() == []
    core.set_purge_dirs([str(tmp_path / "a"), "  ", str(tmp_path / "b")])
    assert core.get_purge_dirs() == [str(tmp_path / "a"), str(tmp_path / "b")]


def test_purge_dirs_now_deletes_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    target = tmp_path / "secret"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "f.txt").write_text("x")
    # safe because it's an absolute, non-system path (under /private/var tmp on macOS,
    # but the guard only blocks /var exact + system trees, not tmp subdirs)
    monkeypatch.setattr(core, "is_safe_purge_path", lambda p: True)  # isolate deletion logic
    core.set_purge_dirs([str(target)])
    ok, msg = core.purge_dirs_now()
    assert ok is True
    assert not target.exists()
    assert "已删除 1" in msg


def test_purge_dirs_now_empty_config(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG", tmp_path / "config.json")
    ok, msg = core.purge_dirs_now()
    assert ok is False
