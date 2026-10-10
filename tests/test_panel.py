"""面板自检：纯函数行为 + 真起一个 HTTP 服务验证路由与页面契约。"""
import importlib.util
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qa_panel", ROOT / "panel" / "panel.py")
panel = importlib.util.module_from_spec(SPEC)
sys.modules["qa_panel"] = panel
SPEC.loader.exec_module(panel)


def test_scrub_hides_secrets():
    panel.SECRETS = ["hunter2secret"]
    assert panel.scrub("pw=hunter2secret") == "pw=[redacted]"
    panel.SECRETS = []


def test_job_hint_matches_symptom_not_generic():
    def job(state, lines):
        return {"state": state, "lines": lines}

    assert panel.job_hint(job("running", [])) is None
    assert panel.job_hint(job("passed", [])) is None
    assert "会话/快照残留" in panel.job_hint(job("error", ["An active snapshot already exists"]))
    assert "持续状态或战斗" in panel.job_hint(job("error", ["R1 does not restore statuses"]))
    assert "主服" in panel.job_hint(job("error", ["Target character is not online: qaplayera"]))
    assert "清理角色状态" in panel.job_hint(job("failed", ["AssertionError: nope"]))


def test_game_run_active_follows_the_shared_lock(tmp_path, monkeypatch):
    """运行中的判定走共用文件锁：拿到锁就算在跑，放开就不算（不再依赖 pgrep 猜进程）。"""
    from gameqa.run_lock import RunLock

    monkeypatch.setattr(panel, "PROJECT", tmp_path)
    assert panel.game_run_active() is False
    lock = RunLock.acquire(tmp_path)
    try:
        assert panel.game_run_active() is True
    finally:
        lock.close()
    assert panel.game_run_active() is False


def test_count_cases_parses_collect_output(monkeypatch):
    monkeypatch.setattr(panel, "JOB_FILTERS", {"api1": ["--qa-kind", "api"]})
    monkeypatch.setattr(panel, "run", lambda argv, timeout=0: "cases/a.py::x\ncases/b.py::y\nnoise\n")
    job = {"name": "api1"}
    panel.count_cases(job)
    assert job["total"] == 2


def test_probe_reports_the_state_contract():
    state = panel.probe()
    for key in ("main", "emulator", "reverse", "health", "job", "last"):
        assert key in state, key


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), panel.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def get(port, path, timeout=60):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", "replace")


def test_http_page_and_state_endpoint():
    server = serve()
    try:
        port = server.server_address[1]
        status, page = get(port, "/")
        assert status == 200
        assert f"= {json.dumps(panel.PROJECT.name)};" in page   # 页面注入的是项目名（服务端替换）
        assert "停服前先确认没有任务在跑" in page               # 主服区块的停服须知
        status, body = get(port, "/api/state")
        assert status == 200
        assert "main" in json.loads(body)
    finally:
        server.shutdown()
        server.server_close()
