import os
from pathlib import Path
import re
import shlex
import time

import pytest

from .bridge import Bridge, redact
from .config import load_config, resolve_path
from .device import AndroidDevice
from .evidence import Evidence, write_report


def pytest_addoption(parser):
    group = parser.getgroup("gameqa")
    for name in ("config", "game", "module", "kind", "case", "report-dir"):
        group.addoption(f"--qa-{name}", default=None)
    group.addoption("--qa-experiment", default="baseline")


def pytest_configure(config):
    config._qa_records = {}
    config._qa_folder = Path(config.getoption("--qa-report-dir") or "reports/latest").resolve()


def pytest_collection_modifyitems(config, items):
    selected, deselected = [], []
    seen = set()
    for item in items:
        marker = item.get_closest_marker("case")
        if not marker:
            deselected.append(item)
            continue
        meta = dict(marker.kwargs)
        required, optional = {"id", "game", "module", "kind"}, {"title"}
        if not required <= set(meta) or not set(meta) <= required | optional:
            raise pytest.UsageError(f"{item.nodeid}: case marker requires id, game, module, kind"
                                    f"（可选 {', '.join(sorted(optional))}）")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", meta["id"]):
            raise pytest.UsageError(f"unsafe case id: {meta['id']}")
        if meta["id"] in seen:
            raise pytest.UsageError(f"duplicate case id: {meta['id']}")
        seen.add(meta["id"])
        wanted = all(not config.getoption(f"--qa-{field}") or
                     config.getoption(f"--qa-{field}") == meta[field]
                     for field in ("game", "module", "kind"))
        wanted_cases = (config.getoption("--qa-case") or "").split(",")
        wanted &= not config.getoption("--qa-case") or meta["id"] in wanted_cases
        if wanted:
            item._qa_meta = meta
            selected.append(item)
        else:
            deselected.append(item)
    items[:] = selected
    if deselected:
        config.hook.pytest_deselected(items=deselected)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if not hasattr(item, "_qa_meta"):
        return
    reproduce = ["python", "-m", "gameqa", "run", "--project", str(item.config.rootpath),
                 "--case", item._qa_meta["id"], "--rounds", "1",
                 "--experiment", item.config.getoption("--qa-experiment")]
    if item.config.getoption("--qa-config"):
        reproduce.extend(["--config", item.config.getoption("--qa-config")])
    meta = {**item._qa_meta, "nodeid": item.nodeid,
            "experiment": item.config.getoption("--qa-experiment"), "reproduce": shlex.join(reproduce)}
    item._qa_evidence = Evidence(meta["id"], item.config._qa_folder / meta["id"], meta)
    item.config._qa_records[meta["id"]] = item._qa_evidence


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    evidence = getattr(item, "_qa_evidence", None)
    if not evidence:
        return
    phases = evidence.data.setdefault("phases", {})
    phases[report.when] = report.outcome
    if report.failed:
        phases[f"{report.when}_detail"] = redact(str(report.longrepr))
    if report.skipped:
        evidence.data["skip_reason"] = str(report.longrepr)
    if report.when == "teardown":
        if (phases.get("setup") == "failed" or phases.get("teardown") == "failed"
                or evidence.data.get("failure_kind") == "preparation_error"):
            evidence.data["outcome"] = "error"
        elif phases.get("call") == "failed":
            evidence.data["outcome"] = "failed"
        elif "skipped" in phases.values():
            evidence.data["outcome"] = "skipped"
        else:
            evidence.data["outcome"] = "passed"
        evidence.write()


def pytest_sessionfinish(session, exitstatus):
    records = [item.data for item in session.config._qa_records.values()]
    write_report(session.config._qa_folder, records,
                 {"exit_code": int(exitstatus), "experiment": session.config.getoption("--qa-experiment"),
                  "generated": time.time(), "collected": len(records)})


@pytest.fixture
def qa(request):
    return request.node._qa_evidence


@pytest.fixture
def qa_config(request):
    return load_config(request.config.getoption("--qa-config"))


@pytest.fixture
def game_config(request, qa_config):
    game = request.node._qa_meta["game"]
    try:
        selected = dict(qa_config["games"][game])
        if request.node._qa_meta["kind"] == "api" and selected.get("api_target"):
            selected["target"] = selected["api_target"]
        return selected
    except KeyError as exc:
        pytest.fail(f"configuration has no games.{game}: {exc}")


@pytest.fixture
def bridge(qa, qa_config, game_config):
    command = [os.path.expandvars(part) for part in game_config["bridge_command"]]
    cwd = resolve_path(qa_config, game_config.get("bridge_cwd", "."))
    log = resolve_path(qa_config, game_config["server_log"]) if game_config.get("server_log") else None
    log_offset = log.stat().st_size if log and log.exists() else 0
    connection = Bridge(command, cwd=cwd, timeout=game_config.get("timeout", 20),
                        server_log=log,
                        # inspect 读的是目标的实时状态，一定是服务端往返（presence/get_chat_messages 可能由桥本地作答）
                        keepalive_op="inspect", keepalive_args={"target": game_config.get("target")})
    try:
        yield connection
    finally:
        connection.close()
        if getattr(connection, "stalls", None):
            qa.data["diagnostics"]["stall_dumps"] = connection.stalls
        qa.data["diagnostics"]["interface_messages"] = redact(connection.messages)
        qa.data["diagnostics"]["bridge_stderr"] = connection.stderr
        if log and log.exists():
            with log.open("rb") as stream:
                stream.seek(min(log_offset, log.stat().st_size))
                text = stream.read(256_000).decode("utf-8", errors="replace")
            path = qa.folder / "server.log"
            path.write_text(redact(text), encoding="utf-8")
            qa.attach(path, "本用例服务端日志")


@pytest.fixture
def android(qa, qa_config):
    device = AndroidDevice(qa_config["device"]["uri"], qa)
    qa.data["metadata"]["device"] = qa_config["device"]
    try:
        yield device
    finally:
        device.screenshot("用例结束时界面")
