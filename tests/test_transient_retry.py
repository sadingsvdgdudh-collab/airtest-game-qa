"""瞬时断连的重试策略：只读重连后重试一次；准备和业务动作不重放。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gameqa.bridge import IndeterminateAction, TransientError     # noqa: E402
from gameqa.stendhal import Stendhal                             # noqa: E402

TRACKED = {"prepare", "restore", "forget", "snapshots", "action", "chat"}


class FakeBridge:
    """只让指定操作失败若干次；connect/login 永远成功（否则测的就不是被测操作了）。"""

    def __init__(self, failing=None):
        self.failing, self.calls, self.closed, self.reopens = dict(failing or {}), [], False, 0

    def call(self, op, args=None, read_only=False):
        self.calls.append(op)
        if self.failing.get(op, 0) > 0:
            self.failing[op] -= 1
            self.closed = True
            raise (TransientError if read_only else IndeterminateAction)(f"{op}: boom")
        return {"snapshots": [], "forgot": []}

    def close(self):
        self.closed = True

    def reopen(self):
        self.reopens += 1
        self.closed = False


class FakeEvidence:
    def __init__(self):
        self.data = {"diagnostics": {}}

    def observe(self, title, function, retries=0):
        return function()


def client(failing=None):
    config = {"target": "qaplayera", "observer": "qaobserver", "host": "127.0.0.1", "port": 1,
              "observer_password_env": "X", "player_password_env": "X"}
    os.environ["X"] = "secret"
    bridge = FakeBridge(failing)
    stendhal = Stendhal.__new__(Stendhal)                    # 不走 __init__（避免真的登录）
    stendhal.bridge, stendhal.config, stendhal.evidence = bridge, config, FakeEvidence()
    stendhal.observer, stendhal.username, stendhal.password_env = True, "qaobserver", "X"
    return stendhal, bridge


def tracked(bridge):
    return [op for op in bridge.calls if op in TRACKED]


def test_read_only_op_retries_once_after_reconnect():
    stendhal, bridge = client({"snapshots": 1})
    stendhal._guarded("snapshots", read_only=True)
    assert bridge.reopens == 1
    assert tracked(bridge) == ["snapshots", "snapshots"], tracked(bridge)
    assert "connect" in bridge.calls and "login" in bridge.calls        # 重连时确实重登了
    assert stendhal.evidence.data["diagnostics"]["transient_retries"]


def test_second_failure_is_not_retried_again():
    stendhal, bridge = client({"snapshots": 5})
    try:
        stendhal._guarded("snapshots", read_only=True)
        raise AssertionError("应当抛出")
    except TransientError:
        pass
    assert tracked(bridge) == ["snapshots", "snapshots"], tracked(bridge)
    assert stendhal.evidence.data["diagnostics"]["transient_failures"]


def test_business_actions_never_go_through_guarded():
    """业务动作不经过 _guarded（一次都不得重试）：源码里它们仍直接调 bridge.call。"""
    source = open(os.path.join(os.path.dirname(__file__), "..", "src", "gameqa", "stendhal.py"),
                  encoding="utf-8").read()
    assert 'self.bridge.call("send_action"' in source
    assert '_guarded("send_action"' not in source
    # chat 也是业务动作：它走 action({"type": "chat"})，同样不经过 _guarded
    assert 'return self.action({"type": "chat", "text": text}' in source
