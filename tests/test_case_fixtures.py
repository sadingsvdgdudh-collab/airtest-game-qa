"""准备夹具的掉线握手与恢复失败不能破坏原快照。"""
from types import SimpleNamespace

import pytest

from cases import conftest as fixtures
from gameqa.evidence import Evidence


def prepare_fixture(tmp_path, monkeypatch, *, offline_once=False, restoration_error=False):
    qa, calls = Evidence("fixture", tmp_path), []
    online = not offline_once
    monkeypatch.setattr(fixtures, "time", SimpleNamespace(sleep=lambda seconds: calls.append(("sleep", seconds))))

    def inspect(*args, **kwargs):
        nonlocal online
        calls.append("inspect")
        if not online:
            online = True
            raise RuntimeError("Target character is not online: qaplayera")

    def prepare(**fields):
        calls.append("prepare")
        return {"snapshot_id": "original", "after": {"money": 100}}

    def restore(token):
        calls.append(("restore", token))
        if restoration_error:
            raise RuntimeError("restore unavailable")

    observer = SimpleNamespace(evidence=qa, _guarded=inspect, prepare=prepare, restore=restore,
                               forget=lambda **kwargs: pytest.fail("原快照不能被自动删除"))
    player = SimpleNamespace(_reconnect=lambda reason: calls.append("reconnect"))
    request = SimpleNamespace(node=SimpleNamespace(_qa_meta={"kind": "api"}),
                              getfixturevalue=lambda name: player)
    fixture = fixtures.prepare.__wrapped__(observer, qa, request)
    return fixture, next(fixture), qa, calls


def test_offline_handshake_reconnects_waits_and_then_prepares(tmp_path, monkeypatch):
    fixture, start, qa, calls = prepare_fixture(tmp_path, monkeypatch, offline_once=True)
    assert start(money=100) == {"money": 100}
    with pytest.raises(StopIteration):
        next(fixture)
    assert calls == ["inspect", "reconnect", ("sleep", 1.5), "inspect", "prepare", ("restore", "original")]
    assert qa.data["diagnostics"]["login_handshake"]


def test_business_failure_restores_original_without_factory_reset(tmp_path, monkeypatch):
    fixture, start, qa, calls = prepare_fixture(tmp_path, monkeypatch)
    start(money=100)
    qa.data["steps"].append({"outcome": "failed"})
    from gameqa import recovery
    monkeypatch.setattr(recovery, "reset_character", lambda *args: pytest.fail("应先恢复原始状态"))
    with pytest.raises(StopIteration):
        next(fixture)
    assert calls[-1] == ("restore", "original")


def test_failed_restore_keeps_snapshot_and_reports_error(tmp_path, monkeypatch):
    fixture, start, qa, calls = prepare_fixture(tmp_path, monkeypatch, restoration_error=True)
    start(money=100)
    with pytest.raises(RuntimeError, match="restore unavailable"):
        next(fixture)
    assert qa.data["diagnostics"]["pending_snapshots"] == ["original"]
    assert calls[-1] == ("restore", "original")


def test_failed_segment_restore_does_not_lose_token_before_teardown(tmp_path, monkeypatch):
    fixture, start, qa, calls = prepare_fixture(tmp_path, monkeypatch, restoration_error=True)
    start(money=100)
    with pytest.raises(RuntimeError, match="restore unavailable"):
        start(money=200)
    with pytest.raises(RuntimeError, match="restore unavailable"):
        next(fixture)
    assert calls.count("prepare") == 1
    assert calls[-2:] == [("restore", "original"), ("restore", "original")]
    assert qa.data["diagnostics"]["pending_snapshots"] == ["original"]
