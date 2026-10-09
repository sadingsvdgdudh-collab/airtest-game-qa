import json
from pathlib import Path
import subprocess
import sys
import os


def test_plugin_keeps_business_failure_and_teardown_error(tmp_path):
    project = Path(__file__).resolve().parents[1]
    test_file = tmp_path / "test_sample.py"
    test_file.write_text('''import pytest
@pytest.fixture
def broken_cleanup():
    yield
    raise RuntimeError("restore failed")
@pytest.mark.case(id="SHOP-001",game="sample",module="shop",kind="api")
def test_business_failure(qa):
    qa.check("money",20,10,"documented price")
@pytest.mark.case(id="SHOP-002",game="sample",module="shop",kind="api")
def test_cleanup_error(qa,broken_cleanup):
    qa.check("item",1,1,"documented quantity")
''', encoding="utf-8")
    report = tmp_path / "report"
    result = subprocess.run([sys.executable, "-m", "pytest", "-c", str(project / "pyproject.toml"),
                             "-p", "gameqa.pytest_plugin", str(test_file), "--qa-report-dir", str(report), "-q"],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 1, result.stdout
    records = json.loads((report / "report.json").read_text())["cases"]
    assert {row["id"]: row["outcome"] for row in records} == {"SHOP-001": "failed", "SHOP-002": "error"}
    assert "restore failed" in records[1]["phases"]["teardown_detail"]


def test_plain_server_log_attachment_cannot_publish_environment_secret(tmp_path):
    project = Path(__file__).resolve().parents[1]
    secret = "fixture-secret-do-not-publish"
    (tmp_path / "conftest.py").write_text('''import os
from pathlib import Path
import pytest
import gameqa.pytest_plugin as plugin
class FakeBridge:
    def __init__(self,*args,**kwargs):
        self.messages=[]; self.stderr=""
    def close(self):
        Path(os.environ["FAKE_SERVER_LOG"]).write_text("input="+os.environ["GAMEQA_PLAYER_PASSWORD"])
@pytest.fixture(autouse=True)
def substitute_bridge(monkeypatch):
    monkeypatch.setattr(plugin,"Bridge",FakeBridge)
''')
    (tmp_path / "test_sample.py").write_text('''import pytest
@pytest.mark.case(id="LOG-001",game="sample",module="diagnostics",kind="api")
def test_read_log(qa,bridge):
    qa.check("sample",1,1,"fixture")
''')
    log = tmp_path / "server.log"
    config = tmp_path / "config.toml"
    config.write_text('[games.sample]\nbridge_command=["unused"]\nserver_log="server.log"\n')
    report = tmp_path / "report"
    result = subprocess.run([sys.executable, "-m", "pytest", "-c", str(project / "pyproject.toml"),
                             "-p", "gameqa.pytest_plugin", str(tmp_path / "test_sample.py"),
                             "--qa-config", str(config), "--qa-report-dir", str(report), "-q"],
                            env={**os.environ, "GAMEQA_PLAYER_PASSWORD": secret, "FAKE_SERVER_LOG": str(log)},
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, result.stdout
    attachment = report / "LOG-001/server.log"
    assert attachment.read_text() == "input=[redacted]"
    for path in report.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(), path
