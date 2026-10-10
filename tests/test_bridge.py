import os
import sys
import threading
import time

import pytest

from gameqa.bridge import Bridge, BridgeError, IndeterminateAction, TransientError, redact


def test_json_boundary_correlates_responses_and_hides_password():
    script = "import sys,json\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({'id':r['id'],'ok':True,'result':r['op']}),flush=True)"
    with Bridge([sys.executable, "-u", "-c", script]) as bridge:
        assert bridge.call("login", {"password": "secret"}) == "login"
        assert bridge.messages[0]["args"]["password"] == "[redacted]"


def test_mismatched_response_is_error():
    script = "import sys,json\nr=json.loads(input());print(json.dumps({'id':999,'ok':True,'result':1}),flush=True)"
    with Bridge([sys.executable, "-u", "-c", script]) as bridge:
        with pytest.raises(BridgeError, match="mismatch"):
            bridge.call("inspect", read_only=True)


def test_configured_credential_is_redacted_inside_diagnostic_text(monkeypatch):
    monkeypatch.setenv("GAMEQA_PLAYER_PASSWORD", "local-secret")
    assert redact("login args={'password':'local-secret'}") == "login args={'password':'[redacted]'}"


def test_nested_redaction_reads_environment_once_and_refreshes_between_calls(monkeypatch):
    monkeypatch.setenv("GAMEQA_BENCH_TOKEN", "first-private-token")
    reads = []
    original = os.environ.items
    monkeypatch.setattr(os.environ, "items", lambda: reads.append(1) or original())
    data = {"nested": ["first-private-token", {"PASSWORD": "hidden"}], "tuple": (1, "first-private-token")}
    assert redact(data) == {"nested": ["[redacted]", {"PASSWORD": "[redacted]"}], "tuple": [1, "[redacted]"]}
    assert data["nested"][0] == "first-private-token"
    assert len(reads) == 1
    monkeypatch.setenv("GAMEQA_BENCH_TOKEN", "second-private-token")
    assert redact("second-private-token") == "[redacted]"
    assert len(reads) == 2


def test_diagnostic_cleanup_runs_after_a_failed_scenario(monkeypatch):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "adapters/shardy_bridge/check_live.py"
    spec = importlib.util.spec_from_file_location("shardy_diagnostic", path)
    diagnostic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostic)
    operations, clients = [], []
    class Client:
        closed = False
        messages = []
        def __init__(self, command):
            self.id = len(clients)
            clients.append(self)
        def __enter__(self): return self
        def __exit__(self, *_): operations.append((self.id, "close"))
        def call(self, operation, *args, **kwargs):
            operations.append((self.id, operation))
            return {"state": {"connected": True, "game": str(self.id), "matched": self.id == 0}}
    monkeypatch.setattr(diagnostic, "Bridge", Client)
    with pytest.raises(AssertionError):
        diagnostic.scenario(["unused"], [], "win")
    assert operations[-8:] == [(1, "get_messages"), (1, "stop"), (1, "disconnect"),
                               (0, "get_messages"), (0, "exit"), (0, "disconnect"), (1, "close"), (0, "close")]


@pytest.mark.parametrize("read_only,error", [(True, TransientError), (False, IndeterminateAction)])
def test_timeout_closes_connection_and_does_not_resend(read_only, error):
    script = "import time\ninput();time.sleep(5)"
    with Bridge([sys.executable, "-u", "-c", script], timeout=0.05) as bridge:
        with pytest.raises(error):
            bridge.call("inspect" if read_only else "buy", read_only=read_only)
        assert len(bridge.messages) == 1
        assert bridge.closed


def test_read_timeout_can_open_new_process_without_losing_first_request(tmp_path):
    flag = tmp_path / "connected-once"
    script = ("import sys,json,time,pathlib\n"
              "flag=pathlib.Path(sys.argv[1]);first=not flag.exists();flag.touch()\n"
              "for line in sys.stdin:\n"
              " r=json.loads(line)\n"
              " if first: time.sleep(5)\n"
              " print(json.dumps({'id':r['id'],'ok':True,'result':'observed'}),flush=True)\n")
    with Bridge([sys.executable, "-u", "-c", script, str(flag)], timeout=0.15) as bridge:
        with pytest.raises(TransientError):
            bridge.call("inspect", read_only=True)
        bridge.reopen()
        assert bridge.call("inspect", read_only=True) == "observed"
        assert [m.get("op") for m in bridge.messages if m["direction"] == "request"] == ["inspect", "inspect"]
        assert any(m.get("event") == "reopen" for m in bridge.messages)


def wait_for_keepalive(bridge, after=0):
    deadline = time.monotonic() + 3
    while bridge.keepalive_sent <= after and time.monotonic() < deadline:
        time.sleep(0.01)
    assert bridge.keepalive_sent > after


def test_keepalive_timeout_closes_old_process_and_restarts_after_login(tmp_path, monkeypatch):
    monkeypatch.setattr(Bridge, "_dump_stall", lambda *args, **kwargs: None)
    flag = tmp_path / "connected-once"
    script = ("import sys,json,time,pathlib\n"
              "flag=pathlib.Path(sys.argv[1]);first=not flag.exists();flag.touch()\n"
              "for line in sys.stdin:\n"
              " r=json.loads(line)\n"
              " if first and r['op']=='ping': time.sleep(5)\n"
              " print(json.dumps({'id':r['id'],'ok':True,'result':r['op']}),flush=True)\n")
    with Bridge([sys.executable, "-u", "-c", script, str(flag)], timeout=0.2,
                min_interval=0, keepalive_op="ping", keepalive_interval=0) as bridge:
        assert bridge.call("login") == "login"
        old_process, old_thread = bridge.process, bridge._keepalive_thread
        old_thread.join(timeout=3)
        assert not old_thread.is_alive()
        assert bridge.closed
        assert old_process.poll() is not None
        assert len(bridge.keepalive_errors) == 1
        assert bridge.keepalive_errors[0].startswith("TransientError:")
        bridge.reopen()
        assert bridge.call("login") == "login"
        assert bridge.call("inspect", read_only=True) == "inspect"
        wait_for_keepalive(bridge)
        assert bridge._keepalive_thread is not old_thread
        assert not bridge.closed
        requests = [m for m in bridge.messages if m["direction"] == "request"]
        assert [m["id"] for m in requests] == list(range(1, len(requests) + 1))
        assert [m["op"] for m in requests[:4]] == ["login", "ping", "login", "inspect"]


def test_keepalive_continues_after_normal_close_and_reopen():
    """close → reopen → 重新登录之后，保活必须继续发（跨多个 tick，不靠一次巧合）。

    这条对应一个真实的坑：close() 会 set 保活用的 Event，如果重连时没有换新的，
    新线程一进循环就退出、保活静默失效。_start() 每次重建该 Event，这里把它钉住。

    真机复验（自检里不睡 40 秒，避免拖慢；需要时手动跑）：
      观察者连接 keepalive_op="inspect" 静默 45 秒后仍可调用 inspect——
      不带保活时同一条连接约 15 秒就会被服务端关掉（实测）。
    """
    script = ("import sys,json\nfor line in sys.stdin:\n"
              " r=json.loads(line);print(json.dumps({'id':r['id'],'ok':True,'result':r['op']}),flush=True)")
    with Bridge([sys.executable, "-u", "-c", script], min_interval=0,
                keepalive_op="ping", keepalive_interval=0) as bridge:
        bridge.call("login")
        wait_for_keepalive(bridge)
        old_thread, old_stop, sent = bridge._keepalive_thread, bridge._keepalive_stop, bridge.keepalive_sent
        bridge.close()
        old_thread.join(timeout=1)
        assert not old_thread.is_alive()
        assert old_stop.is_set()                      # close() 会把旧 Event 置位
        bridge.reopen()
        assert bridge._keepalive_stop is not old_stop  # 重连必须换一个干净的 Event
        bridge.call("login")
        wait_for_keepalive(bridge, after=sent)
        wait_for_keepalive(bridge, after=bridge.keepalive_sent)   # 连续两个 tick 都在发
        assert bridge._keepalive_thread.is_alive()
        assert bridge.keepalive_errors == []
        assert bridge.call("inspect", read_only=True) == "inspect"   # 连接仍可用


def test_close_does_not_wait_for_keepalive_queued_on_call_lock(monkeypatch):
    script = ("import sys,json\nfor line in sys.stdin:\n"
              " r=json.loads(line);print(json.dumps({'id':r['id'],'ok':True,'result':r['op']}),flush=True)")
    with Bridge([sys.executable, "-u", "-c", script], min_interval=0,
                keepalive_op="ping", keepalive_interval=0) as bridge:
        ready = threading.Event()
        old_stop = bridge._keepalive_stop
        original_wait = old_stop.wait
        def ready_to_call(timeout):
            stopped = original_wait(0.01)
            ready.set()
            return stopped
        monkeypatch.setattr(old_stop, "wait", ready_to_call)
        ping_threads = []
        original_call = bridge._call
        def track_call(op, *args, **kwargs):
            if op == "ping":
                ping_threads.append(threading.current_thread())
            return original_call(op, *args, **kwargs)
        monkeypatch.setattr(bridge, "_call", track_call)
        with bridge._lock:
            bridge.call("login")
            old_thread = bridge._keepalive_thread
            assert ready.wait(1)
            started = time.monotonic()
            bridge.close()
            assert time.monotonic() - started < 1
            bridge.reopen()
            bridge.call("login")
        old_thread.join(timeout=1)
        assert not old_thread.is_alive()
        wait_for_keepalive(bridge)
        assert old_thread not in ping_threads
        assert bridge.keepalive_errors == []
