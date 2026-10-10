"""快照不能在准备/恢复结果不明时自动删除，也不能把缺快照当作恢复确认。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gameqa.bridge import BridgeError, IndeterminateAction       # noqa: E402
from gameqa.stendhal import Stendhal                            # noqa: E402


class SnapshotBridge:
    def __init__(self):
        self.money, self.saved, self.calls, self.closed = 30, {}, [], False
        self.lose_prepare_response = self.lose_restore_response = False

    def call(self, op, args=None, read_only=False):
        self.calls.append(op)
        if self.closed:
            raise BridgeError("bridge is closed")
        if op in {"connect", "login"}:
            return {}
        if op == "prepare":
            if self.saved:
                raise BridgeError("An active snapshot already exists for this target; restore it first")
            self.saved["original"] = self.money
            self.money = args["money"]
            if self.lose_prepare_response:
                self.closed = True
                raise IndeterminateAction("prepare: no confirmed response; request was not resent")
            return {"snapshot_id": "original", "after": {"money": self.money}}
        if op == "restore":
            token = args["snapshot_id"]
            if token not in self.saved:
                raise BridgeError("Snapshot is missing or belongs to another character")
            self.money = self.saved.pop(token)
            if self.lose_restore_response:
                self.closed = True
                raise IndeterminateAction("restore: no confirmed response; request was not resent")
            return {"restored": True, "snapshot_id": token, "after": {"money": self.money}}
        if op == "forget":
            self.saved.clear()
            return {"forgotten": ["original"]}
        if op == "snapshots":
            return {"snapshots": [{"snapshot_id": token, "age_seconds": 120} for token in self.saved]}
        raise AssertionError(op)

    def close(self):
        self.closed = True

    def reopen(self):
        self.closed = False


class Evidence:
    def __init__(self):
        self.data = {"diagnostics": {}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GAMEQA_SNAPSHOT_TEST_PASSWORD", "test")
    config = {"target": "qaplayera", "observer": "qaobserver", "host": "127.0.0.1", "port": 1,
              "observer_password_env": "GAMEQA_SNAPSHOT_TEST_PASSWORD"}
    bridge = SnapshotBridge()
    return Stendhal(bridge, config, Evidence()), bridge


def test_applied_prepare_without_response_preserves_original_snapshot(client):
    observer, bridge = client
    bridge.lose_prepare_response = True

    with pytest.raises(IndeterminateAction, match="no confirmed response"):
        observer.prepare(money=100)

    assert bridge.money == 100
    assert bridge.saved == {"original": 30}
    assert bridge.calls.count("prepare") == 1
    assert "forget" not in bridge.calls
    assert observer.evidence.data["failure_kind"] == "preparation_error"
    assert observer.evidence.data["diagnostics"]["transient_failures"]
    assert "preparation" not in observer.evidence.data["diagnostics"]
    # 恢复仍可显式使用原快照，而不是把准备后的 100 当作基线。
    observer._reconnect("recover retained snapshot")
    assert observer.restore("original")["after"]["money"] == 30


def test_existing_snapshot_is_not_deleted_to_prepare_again(client):
    observer, bridge = client
    bridge.saved["original"] = 30
    bridge.money = 70

    with pytest.raises(BridgeError, match="An active snapshot already exists"):
        observer.prepare(money=100)

    assert bridge.saved == {"original": 30}
    assert bridge.money == 70
    assert bridge.calls.count("prepare") == 1
    assert "forget" not in bridge.calls
    assert observer.evidence.data["failure_kind"] == "preparation_error"


def test_missing_snapshot_is_a_restore_error(client):
    observer, bridge = client

    with pytest.raises(BridgeError, match="Snapshot is missing"):
        observer.restore("missing")

    assert bridge.calls.count("restore") == 1
    assert "restoration" not in observer.evidence.data["diagnostics"]


def test_missing_snapshot_after_unconfirmed_restore_is_still_an_error(client):
    observer, bridge = client
    observer.prepare(money=100)
    bridge.lose_restore_response = True

    with pytest.raises(BridgeError, match="Snapshot is missing"):
        observer.restore("original")

    assert bridge.calls.count("restore") == 2
    assert "restoration" not in observer.evidence.data["diagnostics"]
