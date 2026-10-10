#!/usr/bin/env python3
"""Stendhal QA 面板：CLI 的薄壳。只绑 127.0.0.1，只用标准库，不复制运行逻辑。

启动:
    /Users/Zhuanz/Documents/Codex/2026-10-02/shi/work/python-env/bin/python panel.py
自检（只打印状态探测结果，不起服务）:
    python panel.py --state
"""
import json
import mimetypes
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT = Path(os.environ.get("QA_PROJECT", "/Users/Zhuanz/Documents/Codex/2026-10-02/shi/outputs/airtest-game-qa"))
sys.path.insert(0, str(PROJECT / "src"))
from gameqa.run_lock import RunBusy, RunLock, run_active

WORK = Path(os.environ.get("QA_WORK", "/Users/Zhuanz/Documents/Codex/2026-10-02/shi/work"))
PY = WORK / "python-env/bin/python"
ADB = WORK / "android/sdk/platform-tools/adb"
PORT = int(os.environ.get("QA_PORT", "8787"))
EMULATOR = "emulator-5554"


def child_env():
    env = dict(os.environ, GAMEQA_WORK_DIR=str(WORK))
    for line in (WORK / "local.env").read_text(encoding="utf-8").splitlines():
        parts = shlex.split(line)
        if len(parts) == 2 and parts[0] == "export" and "=" in parts[1]:
            key, value = parts[1].split("=", 1)
            env[key] = value
    return env


ENV = child_env()
SECRETS = [value for key, value in ENV.items() if "PASSWORD" in key and len(value) > 3]


def scrub(text):
    for secret in SECRETS:
        text = text.replace(secret, "[redacted]")
    return text


def run(argv, timeout=15):
    try:
        done = subprocess.run(argv, cwd=PROJECT, env=ENV, capture_output=True, text=True, timeout=timeout)
        return done.stdout or ""
    except Exception:
        return ""


def adb(*args):
    return run([str(ADB), *args])


def listening(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def http_code(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status
    except Exception:
        return None


HEALTH = {"at": 0.0, "data": None, "checking": False}
HEALTH_TTL = 45.0


def game_run_active():
    """检测共用文件锁，包括命令行、清理和另一面板的角色检查。"""
    return run_active(PROJECT)


def character_health(force=False):
    """角色残留检查：跑 cleanup_characters.py --dry-run --json（只读，约 10 秒）。

    会短暂把两个角色拉上线再登出，所以**有任务在跑时绝不刷新**——只在空闲时做，
    结果缓存起来给 /api/state 读，避免拖慢 1.5 秒一次的轮询。
    """
    with LOCK:
        now = time.monotonic()
        if not force and HEALTH["data"] and now - HEALTH["at"] < HEALTH_TTL:
            return HEALTH["data"]
        if running_job() or HEALTH["checking"]:
            return HEALTH["data"] or {"characters": [], "note": "有任务或检查在进行，暂不检查"}
        try:
            lock = RunLock.acquire(PROJECT)
        except RunBusy:
            return HEALTH["data"] or {"characters": [], "note": "有运行在进行，暂不检查"}
        HEALTH["checking"] = True
    try:
        done = subprocess.run([str(PY), "scripts/cleanup_characters.py", "--dry-run", "--json",
                               "--qa-lock-fd", str(lock.fileno())],
                              cwd=PROJECT, env=ENV, capture_output=True, text=True, timeout=120,
                              pass_fds=(lock.fileno(),))
        try:
            data = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            data = {"characters": [], "error": (done.stderr or done.stdout or "检查失败")[-200:]}
        data["at"] = time.strftime("%H:%M:%S")
        with LOCK:
            HEALTH.update({"at": now, "data": data})
        return data
    finally:
        with LOCK:
            lock.close()
            HEALTH["checking"] = False


def health_loop():
    """空闲时定期刷新角色健康；有任务在跑就跳过。启动后先等几秒再查一次，别让面板空着。"""
    time.sleep(5)
    while True:
        try:
            character_health(force=True)
        except Exception:
            pass
        time.sleep(HEALTH_TTL)


def job_hint(job):
    """任务没跑成时给一句可执行的处置建议（按日志里的症状给，不是泛泛一句）。"""
    if job["state"] in ("running", "passed"):
        return None
    text = "\n".join(job["lines"][-80:])
    if "An active snapshot already exists" in text or "bridge is closed" in text:
        return "症状像会话/快照残留：点主服「停止」再「启动」，然后重跑。"
    if "needs no active status or combat" in text or "R1 does not restore statuses" in text:
        return "症状像角色带着持续状态或战斗：点「清理角色状态」，然后重跑。"
    if "Target character is not online" in text:
        return "角色不在线（可能被别的会话占用）：点主服「停止」再「启动」最稳。"
    if job["state"] == "failed":
        return "环境可能脏了：先点「清理角色状态」；若仍失败，点主服的「停止」再「启动」。"
    return None


def probe():
    emulator = re.search(rf"^{EMULATOR}\s+device", adb("devices"), re.M) is not None
    booted = emulator and adb("-s", EMULATOR, "shell", "getprop", "sys.boot_completed").strip() == "1"
    reverse = adb("-s", EMULATOR, "reverse", "--list") if emulator else ""
    return {
        "main": {"listening": listening(32160), "http": http_code("http://127.0.0.1:8080/stendhal.html")},
        "emulator": {"device": emulator, "boot_completed": bool(booted)},
    "shardy": {"backend": listening(3000), "client": listening(3001)},
        "reverse": {str(p): f"tcp:{p}" in reverse for p in (8080, 3000, 3001)},
        "job": running_job(),
        "health": ({**(HEALTH["data"] or {"characters": []}), "checking": HEALTH["checking"]}
                   if HEALTH["data"] or HEALTH["checking"] else None),
        "last": LAST,
    }


JOB_CMDS = {
    "selfcheck": [str(PY), "-m", "pytest", "tests", "-q"],
    "connect": ["bash", "scripts/android/connect.sh"],
    # 用例运行不在这里：四个用例按钮和「执行所选」走同一个 start_selection，
    # 这样失败语义（--stop-after-failure + 后续未执行清单）、轮数校验、进度统计只有一份实现。
    # 防呆：中途停任务后 R1 不恢复、角色带着攻击/寻路/持续状态时用它。
    # 连背包残留一起清：脚本用 prepare 清空后 forget 撤掉快照，不需要重启主服。
    "cleanup": [str(PY), "scripts/cleanup_characters.py", "--clear-items"],
}
SERVICE_CMDS = {
    "emulator-window": {                      # 与 emulator 同物，只是开窗口（方便人看着跑）
        "start": ["env", "GAMEQA_EMULATOR_WINDOW=1", "bash", "scripts/android/start.sh"],
        "stop": [str(ADB), "-s", EMULATOR, "emu", "kill"],
        "log": WORK / "android/logs/emulator.log",
    },
    "main": {
        "start": ["sh", "scripts/stendhal/start.sh", "main"],
        "stop": ["sh", "scripts/stendhal/stop.sh", "main"],
        "log": WORK / "stendhal/runtime/panel-main.log",
    },
    "emulator": {
        "start": ["bash", "scripts/android/start.sh"],
        "stop": [str(ADB), "-s", EMULATOR, "emu", "kill"],
        "log": WORK / "android/logs/emulator.log",
    },
    "shardy": {
        "start": ["bash", "scripts/shardy/start.sh"],
        "stop": ["bash", "scripts/shardy/stop.sh"],
        "log": WORK / "shardy/logs/panel.log",
    },
}

JOBS = {}
SERVICES = {}
LOCK = threading.Lock()
NEXT_ID = [1]
LAST_PATH = Path(__file__).with_name("last.json")
try:
    LAST = json.loads(LAST_PATH.read_text(encoding="utf-8"))
except Exception:
    LAST = {}


JOB_ROUNDS = {}                                # 用例运行的轮数由界面轮次框给（走 start_selection）
JOB_FILTERS = {
    "api1": ["--qa-case", "ST-SHOP-API-001"],
    "apigroup": ["--qa-game", "stendhal", "--qa-kind", "api"],
    "uicase": ["--qa-case", "ST-SHOP-UI-001"],
    "uigroup": ["--qa-game", "stendhal", "--qa-kind", "ui"],
}
COLLECT = [str(PY), "-m", "pytest", "cases", "--collect-only", "-q",
           "-p", "gameqa.pytest_plugin", "-p", "no:cacheprovider",
           "--qa-config", ENV.get("GAMEQA_CONFIG", "")]


def count_cases(job):
    """任务启动时补一次 collect-only，拿到总数，单轮任务才有分母和 ETA。"""
    filters = JOB_FILTERS.get(job["name"])
    if not filters:
        return
    total = sum(1 for line in run(COLLECT + filters, timeout=180).splitlines() if "::" in line)
    if total:
        with LOCK:
            job["total"] = total


def job_report_dir(job):
    """本次任务新建的报告目录：开始前记下已有的，之后出现的就是它的。"""
    before = job.get("reports_before")
    if before is None:
        return None
    fresh = [p for p in (PROJECT / "reports").iterdir() if p.is_dir() and p.name not in before]
    return max(fresh, key=lambda p: p.stat().st_mtime) if fresh else None


def job_progress(job):
    """所有任务都有已运行时长；gameqa 类任务再给轮次、本轮用例数和预估剩余。"""
    info = {"elapsed": round(time.monotonic() - job["started"], 1)}
    rounds = job.get("rounds")
    total = job.get("total")
    if total:
        info["total"] = total
    folder = job_report_dir(job) if rounds else None
    if folder is None:
        return info
    dirs = sorted((d for d in folder.iterdir() if re.fullmatch(r"round-\d+", d.name)),
                  key=lambda d: d.name)
    if not dirs:
        return info
    done = [d for d in dirs if (d / "report.json").exists()]
    cases = len([x for x in dirs[-1].iterdir() if x.is_dir()])
    info["round"] = min(len(done) + 1, rounds)
    info["rounds"] = rounds
    info["cases"] = cases
    info["per_round"] = max((len([x for x in d.iterdir() if x.is_dir()]) for d in done),
                            default=0) or total or 0
    if done:                                   # 多轮：按已完成的轮平均
        info["eta"] = round(info["elapsed"] / len(done) * (rounds - len(done)))
    elif rounds == 1 and total and cases >= 2:  # 单轮：最新那个用例还在跑，按已完成条数估
        info["eta"] = round(info["elapsed"] / (cases - 1) * max(0, total - cases))
    return info


def running_job():
    for job in JOBS.values():
        if job["state"] == "running":
            return {"id": job["id"], "name": job["name"], "progress": job_progress(job)}
    return None


def drain(job):
    for line in job["proc"].stdout:
        with LOCK:
            job["lines"].append(scrub(line.rstrip("\n")))
    code = job["proc"].wait()
    with LOCK:
        if job.get("run_lock"):
            job["run_lock"].close()
        job["code"] = code
        job["state"] = "passed" if code == 0 else "failed"
        LAST[job["name"]] = {"state": job["state"], "code": code, "id": job["id"], "at": time.time(),
                             "line": job["lines"][-1] if job["lines"] else ""}
        LAST_PATH.write_text(json.dumps(LAST, ensure_ascii=False), encoding="utf-8")
        if job.get("selected"):                     # 失败即停：把没跑到的选条目列出来
            folder = job_report_dir(job)
            done = set()
            if folder and (folder / "summary.json").exists():
                try:
                    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
                    done = {case["id"] for case in summary.get("cases", [])}
                except ValueError:
                    pass
            job["unexecuted"] = [case_id for case_id in job["selected"] if case_id not in done]
    threading.Thread(target=character_health, kwargs={"force": True}, daemon=True).start()


def start_job(name, argv=None, selected=None, rounds=None):
    if argv is None and name not in JOB_CMDS:
        raise KeyError(name)
    with LOCK:
        if running_job() or HEALTH["checking"]:
            return None
        try:
            lock = RunLock.acquire(PROJECT)
        except RunBusy:
            return None
        job_id = NEXT_ID[0]
        job = {"id": job_id, "name": name, "state": "running", "code": None, "lines": [],
               "started": time.monotonic(),
               "reports_before": {p.name for p in (PROJECT / "reports").iterdir()},
               "selected": selected, "total": len(selected) if selected else None,
               "rounds": rounds or JOB_ROUNDS.get(name)}
        command = list(argv) if argv is not None else [
            part.format(rounds=job["rounds"]) if isinstance(part, str) else part
            for part in JOB_CMDS[name]]
        job["display"] = " ".join(str(part) for part in command)   # 回显给页面/接口，便于核对等价性
        owns_characters = selected is not None or name == "cleanup"
        if owns_characters:
            command += ["--qa-lock-fd", str(lock.fileno())]
            job["run_lock"] = lock
        try:
            job["proc"] = subprocess.Popen(command, cwd=PROJECT,
                                           env=dict(ENV, PYTHONUNBUFFERED="1"), text=True, bufsize=1,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           pass_fds=(lock.fileno(),) if owns_characters else ())
        except BaseException:
            lock.close()
            raise
        if not owns_characters:  # 自检和端口映射不使用角色，不给其内部的假用例继承锁。
            lock.close()
        NEXT_ID[0] += 1
        JOBS[job_id] = job
    threading.Thread(target=drain, args=(job,), daemon=True).start()
    if selected is None:
        threading.Thread(target=count_cases, args=(job,), daemon=True).start()
    return job_id


def start_selection(payload, experiment="未命名-面板"):
    """自定义选择执行：白名单、同 kind、轮次范围都在服务端校验，命令用 list 拼。"""
    cases, rounds = payload.get("cases"), payload.get("rounds", 1)
    if not isinstance(cases, list) or not cases or any(not isinstance(c, str) for c in cases):
        return "cases 必须是非空字符串数组"
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 20:
        return "rounds 必须是 1..20 的整数"
    kinds = implemented_kinds()
    unknown = [case_id for case_id in cases if case_id not in kinds]
    if unknown:
        return "不在框架清单里的用例：" + "、".join(unknown[:5])
    chosen = list(dict.fromkeys(cases))
    if len({kinds[case_id] for case_id in chosen}) > 1:
        return "不能把 api 和 ui 用例混在一次运行里（共用管理员、商店NPC和浏览器）"
    argv = [str(PY), "-m", "gameqa", "run", "--case", ",".join(chosen), "--rounds", str(rounds),
            "--experiment", experiment, "--stop-after-failure"]
    return start_job("自选-" + kinds[chosen[0]], argv, selected=chosen, rounds=rounds)


def start_service(name):
    spec = SERVICE_CMDS[name]
    if SERVICES.get(name) and SERVICES[name].poll() is None:
        return
    spec["log"].parent.mkdir(parents=True, exist_ok=True)
    handle = spec["log"].open("ab")
    # start_new_session：面板是控制器不是属主，重启面板不该带走主服和模拟器
    SERVICES[name] = subprocess.Popen(spec["start"], cwd=PROJECT, env=ENV, stdout=handle, stderr=handle,
                                      start_new_session=True)


def stop_service(name):
    spec = SERVICE_CMDS[name]
    subprocess.run(spec["stop"], cwd=PROJECT, env=ENV, capture_output=True, text=True, timeout=30)


RECONNECT_TRIED = [0.0]


def watchdog():
    """模拟器重启会丢掉 adb reverse；探测到缺失就自己跑一次 connect.sh。"""
    while True:
        time.sleep(5)
        try:
            state = probe()
            missing = state["emulator"]["device"] and state["emulator"]["boot_completed"] \
                and not state["reverse"]["8080"]
            if missing and not running_job() and time.monotonic() - RECONNECT_TRIED[0] > 30:
                RECONNECT_TRIED[0] = time.monotonic()
                start_job("connect")
        except Exception:
            pass


DOC_SOURCES = [("stendhal", PROJECT / "docs/功能用例目录.md"),
               ("shardy", PROJECT / "docs/Shardy验证结果.md")]
ID_RE = re.compile(r"(S[TH]-[A-Z]+-[A-Z]+-\d+[A-Za-z-]*)")
BASE_RE = re.compile(r"^(S[TH]-[A-Z]+-[A-Z]+-\d+)")
MARK_RE = re.compile(r"(?<![A-Za-z0-9])([AU]\?|[AU]|M\?)(?![A-Za-z0-9])")


def base_of(case_id):
    match = BASE_RE.match(case_id)
    return match.group(1) if match else case_id


def documented_cases():
    """设计文档里的用例编号 + A/U/A?/U?/M? 标记 + 来源列（标记不含量轮数，见设计文档图例）。

    一行里可能出现多个编号（正文交叉引用），全部登记为"文档里出现过"；
    只有行首那个是设计条目本身，才带标记、来源和 primary=True。
    """
    found = {}
    for game, path in DOC_SOURCES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            ids = ID_RE.findall(line)
            if not ids:
                continue
            row = line.strip().startswith("|")
            cells = [c.strip() for c in line.strip().strip("|").split("|")] if row else []
            marks = MARK_RE.findall(line)
            note = next((c for c in reversed(cells) if c), "")
            for index, case_id in enumerate(ids):
                primary = index == 0 and row
                entry = {"game": game, "doc": path.name, "primary": primary,
                         "marker": marks[-1] if primary and marks else "",
                         "source": cells[4] if primary and len(cells) > 4 else "",
                         "note": note if primary else ""}
                previous = found.get(case_id)
                if previous is None or (not previous["marker"] and entry["marker"]):
                    found[case_id] = entry
    return found


_TITLES = {}


def implemented_cases():
    """框架自报的实现清单：collect-only + 面板自带的 dumper 插件，不改框架。

    dumper 顺带打一行 TITLES（编号→中文名），这里一起收下——同一次 collect-only，
    不额外起进程；把 titles 塞进 INVENTORY 结构会破坏它的 {game:{module:{kind:[id]}}} 约定。
    """
    global _TITLES
    env = dict(ENV, PYTHONPATH=str(Path(__file__).resolve().parent))
    done = subprocess.run([str(PY), "-m", "pytest", "cases", "--collect-only", "-q",
                           "-p", "gameqa.pytest_plugin", "-p", "qa_inventory", "-p", "no:cacheprovider",
                           "--qa-config", ENV.get("GAMEQA_CONFIG", "")],
                          cwd=PROJECT, env=env, capture_output=True, text=True, timeout=180)
    payload = {}
    for row in done.stdout.splitlines():
        if row.startswith("INVENTORY "):
            payload = json.loads(row[len("INVENTORY "):])
        elif row.startswith("TITLES "):
            _TITLES = json.loads(row[len("TITLES "):])
    return payload


def case_titles():
    """编号 → 中文名。必须在 implemented_cases() 之后读（那一次 collect-only 顺带刷新它）。

    不要写成"为空才去取"的缓存：用例的中文名会不断被补上，而面板进程长期活着，
    那样第一次拿到的一批会被当成最新，后来补的名字永远不显示。
    """
    return dict(_TITLES)


def gate_status():
    """用例卫生门禁的逐条状态：达标 / 欠账（豁免中）/ 违规（名单外，必须修）。

    走 `python -m gameqa.hygiene --json` 子进程，不把框架 import 进面板进程——
    和取用例清单一样，两边环境不同也不会互相牵连。
    """
    done = subprocess.run([str(PY), "-m", "gameqa.hygiene", "--json"],
                          cwd=PROJECT, env=ENV, capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}
    out = {row["id"]: {"state": "违规", "rules": row["rules"]} for row in data.get("outside", [])}
    for row in data.get("debt", []):
        out.setdefault(row["id"], {"state": "欠账", "rules": row["rules"]})
    return out


def implemented_kinds():
    """id → kind，用来做自定义运行的白名单校验（只认框架自报的清单）。"""
    kinds = {}
    for modules in implemented_cases().values():
        for by_kind in modules.values():
            for kind, ids in by_kind.items():
                for case_id in ids:
                    kinds[case_id] = kind
    return kinds


def case_durations():
    """最近几次运行里每条用例的实测耗时，用于执行前的时长预估。"""
    out = {}
    runs = sorted((PROJECT / "reports").glob("*/round-01"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for run in runs[:8]:
        for path in run.glob("*/case.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            out.setdefault(data["id"], round(data.get("finished", 0) - data.get("started", 0), 1))
        if len(out) >= 30:
            break
    return out


def case_inventory():
    docs = documented_cases()
    durations = case_durations()
    latest = {}
    # 只看最近若干次运行就够（面板不需要全历史），但窗口太窄会让"最近40次运行"整列变成"未跑过"——
    # 探针/单例跑几次就把全组运行挤出去了。取 40 次：读 40 个 summary.json 仍是毫秒级。
    for folder in sorted((PROJECT / "reports").glob("*/summary.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
        try:
            summary = json.loads(folder.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for case in summary.get("cases", []):
            latest.setdefault(case["id"], {"run": folder.parent.name,
                                           "outcome": case["observations"][-1]["outcome"]})
    implemented = []
    inventory = implemented_cases()          # 一次 collect-only：清单 + 中文名（_TITLES）
    titles = case_titles()
    gate = gate_status()
    for game, modules in inventory.items():
        for module, kinds in modules.items():
            for kind, ids in kinds.items():
                for case_id in sorted(ids):
                    meta = docs.get(case_id) or docs.get(base_of(case_id)) or {}
                    implemented.append({"id": case_id, "game": game, "module": module, "kind": kind,
                                        "marker": meta.get("marker", ""), "source": meta.get("source", ""),
                                        "documented": bool(meta), "last": latest.get(case_id),
                                        "seconds": durations.get(case_id),
                                        "title": titles.get(case_id, ""),
                                        "gate": gate.get(case_id, {"state": "达标", "rules": []})})
    ids = {row["id"] for row in implemented}
    bases = {base_of(case_id) for case_id in ids}
    designed = [{"id": case_id, "marker": meta["marker"], "source": meta["source"],
                 "doc": meta["doc"], "note": meta["note"]}
                for case_id, meta in sorted(docs.items())
                if case_id not in ids and case_id not in bases and (meta["marker"] or meta["primary"])]
    # 文档声明"已实现"但框架里没有独立用例的：共用执行ID的别名设计，单独列，不算未实现
    aliases = [row for row in designed if row["marker"] in ("A", "U")]
    designed = [row for row in designed if row["marker"] not in ("A", "U")]
    unmatched = sorted(case_id for case_id in ids
                       if case_id not in docs and base_of(case_id) not in docs)
    data = {"implemented": implemented, "designed": designed, "aliases": aliases, "unmatched": unmatched,
            "counts": {"implemented": len(implemented), "designed": len(designed), "aliases": len(aliases),
                       "documented_total": len(docs), "unmatched": len(unmatched),
                       "undocumented_implemented": sum(1 for row in implemented if not row["documented"]),
                       "untitled": sum(1 for row in implemented if not row["title"]),
                       "gate_debt": sum(1 for row in implemented if row["gate"]["state"] != "达标")}}
    return data


RETRY_WARN_RATE = 0.35


def retry_rate(summaries):
    """最近若干轮的重试率。

    口径与 summary.json 一致：**重试才过不算一次通过**。
    observations 是 case × round 的观测总数（分母），retried 是带重试标记的观测数，
    first_try 是没走重试就通过的观测数。超过 35% 只给提示（warn=True），不阻断任何操作。
    """
    observations = retried = first_try = 0
    for summary in summaries:
        for case in summary.get("cases", []):
            for observation in case.get("observations", []):
                observations += 1
                if observation.get("infra_retry"):
                    retried += 1
                elif observation.get("outcome") == "passed":
                    first_try += 1
    rate = (retried / observations) if observations else 0.0
    return {"observations": observations, "retried": retried, "first_try": first_try,
            "rate": round(rate, 4), "warn": rate > RETRY_WARN_RATE, "threshold": RETRY_WARN_RATE}


def reports(limit=8):
    found, summaries = [], []
    for folder in sorted((PROJECT / "reports").glob("*/summary.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            summary = json.loads(folder.read_text(encoding="utf-8"))
        except ValueError:
            continue
        summaries.append(summary)
        rows = [o for case in summary.get("cases", []) for o in case.get("observations", [])]
        retried = sum(1 for o in rows if o.get("infra_retry"))
        found.append({"run": folder.parent.name, "rounds": summary.get("rounds"),
                      "report": ("index.html" if (folder.parent / "index.html").exists()
                                 else "round-01/index.html"),
                      "experiment": summary.get("experiment", ""),
                      "consistent": summary.get("consistent"), "all_passed": summary.get("all_passed"),
                      "exit_codes": summary.get("exit_codes", []),
                      "observations": len(rows),
                      "infra_retry_count": summary.get("infra_retry_count", retried),
                      "infra_retry_rate": summary.get("infra_retry_rate",
                                                      round(retried / len(rows), 4) if rows else 0.0),
                      "first_try_passed": summary.get("first_try_passed", sum(
                          1 for o in rows if o.get("outcome") == "passed" and not o.get("infra_retry"))),
                      "failed": [c["id"] for c in summary.get("cases", [])
                                 if any(o.get("outcome") != "passed" for o in c.get("observations", []))]})
        if len(found) >= limit:
            break
    return {"runs": found, "retry": retry_rate(summaries)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        if path == "/":
            # 页面里的项目名要在服务端替换：HTML 是原样发出的，前端的 PROJECT 变量并不存在
            # （曾经因此抛 ReferenceError，整段脚本中断，页面永远停在"读取状态…"）。
            page = HTML.replace("$('proj').textContent = PROJECT;",
                                f"$('proj').textContent = {json.dumps(PROJECT.name)};")
            return self.send_bytes(page.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/state":
            return self.send_json(probe())
        if path == "/api/reports":
            return self.send_json(reports())
        if path == "/api/cases":
            return self.send_json(case_inventory())
        if path.startswith("/api/job/"):
            tail = path.rsplit("/", 1)[1]
            job = JOBS.get(int(tail)) if tail.isdigit() else None
            if not job:
                return self.send_json({"error": "no such job"}, 404)
            cursor = int(query.get("cursor", ["0"])[0])
            with LOCK:
                lines, state, code = job["lines"][cursor:], job["state"], job["code"]
            return self.send_json({"name": job["name"], "state": state, "code": code,
                                   "lines": lines, "next": cursor + len(lines),
                                   "unexecuted": job.get("unexecuted"),
                                   "hint": job_hint(job) if state != "running" else None,
                                   "progress": job_progress(job) if state == "running" else None})
        if path.startswith("/reports/"):
            target = (PROJECT / path.lstrip("/")).resolve()
            if not target.is_relative_to((PROJECT / "reports").resolve()) or not target.is_file():
                return self.send_json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self.send_bytes(target.read_bytes(), ctype)
        return self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parts = urllib.parse.urlparse(self.path).path.strip("/").split("/")
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except ValueError:
            return self.send_json({"error": "请求体不是合法 JSON"}, 400)
        if urllib.parse.urlparse(self.path).path == "/api/run":
            result = start_selection(payload)
            if isinstance(result, str):
                return self.send_json({"error": result}, 400)
            job = JOBS.get(result) or {}
            return self.send_json({"job": result, "cases": len(payload.get("cases") or []),
                                   "command": job.get("display", "")} if result
                                  else {"error": "已有任务在跑"}, 200 if result else 409)
        if parts[:2] == ["api", "job"] and len(parts) == 3:
            # 全组任务的轮数由界面「轮次」框给（?rounds=N），服务端照样校验范围
            rounds = None
            raw = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("rounds", [""])[0]
            if raw:
                if not raw.isdigit() or not 1 <= int(raw) <= 20:
                    return self.send_json({"error": "轮数必须是 1..20"}, 400)
                rounds = int(raw)
            try:
                job_id = start_job(parts[2], rounds=rounds)
            except KeyError:
                return self.send_json({"error": "no such job"}, 404)
            return self.send_json({"job": job_id} if job_id else {"error": "已有任务在跑"}, 200 if job_id else 409)
        if parts == ["api", "health", "check"]:
            threading.Thread(target=character_health, kwargs={"force": True}, daemon=True).start()
            return self.send_json({"checking": True})
        if parts[:2] == ["api", "service"] and len(parts) == 4 and parts[3] in ("start", "stop"):
            if parts[2] not in SERVICE_CMDS:
                return self.send_json({"error": "no such service"}, 404)
            (start_service if parts[3] == "start" else stop_service)(parts[2])
            return self.send_json({"ok": True})
        return self.send_json({"error": "not found"}, 404)


HTML = r"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>Stendhal QA 面板</title><style>
:root{
  --bg:#f4f6f9; --card:#fff; --ink:#16202c; --muted:#5a6b7d;
  --line:#d8e0e8; --line-2:#c3ceda;
  --ok:#177a36; --ok-bg:#e8f5ec; --warn:#8a6100; --warn-bg:#fdf3d8; --bad:#b3261e; --bad-bg:#fdecea;
  --accent:#1f5fa9; --accent-ink:#fff; --ring:#2f7fd1; --ink-2:#0f1721;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
  --r1:6px; --r2:10px; --r3:14px;
  --shadow:0 1px 2px rgba(16,32,48,.06), 0 4px 12px rgba(16,32,48,.05);
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--ring);outline-offset:2px;border-radius:var(--r1)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}

header{padding:var(--s3) var(--s5);background:var(--ink-2);color:#fff;display:flex;gap:var(--s4);
  align-items:baseline;flex-wrap:wrap;border-bottom:3px solid var(--accent)}
header h1{margin:0;font-size:16px;letter-spacing:.02em}
header span{font-size:13px;opacity:.85}
header #proj{font-family:var(--mono);opacity:.7}

.pills{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--s2);padding:var(--s3) var(--s5) 0}
.kpi{display:flex;align-items:center;gap:var(--s3);border:1px solid var(--line);background:var(--card);
  border-radius:var(--r2);padding:10px var(--s3);box-shadow:var(--shadow)}
.kpi .num{font:600 20px/1.15 var(--mono);letter-spacing:-.01em}
.kpi .label{font-size:12px;color:var(--muted)}
.kpi .words{font-size:12px;color:var(--muted);margin-top:1px}
.kpi.on{border-color:#b7e0c4;background:var(--ok-bg)}
.kpi.warn{border-color:#f0d58c;background:var(--warn-bg)}
.kpi.off .num,.kpi.off .words{color:var(--muted)}

main{display:grid;grid-template-columns:repeat(12,1fr);gap:var(--s2);padding:var(--s3) var(--s5) var(--s4);align-items:start}
#sec-cases,#sec-self,#sec-char{grid-column:span 4;grid-row:1}
#sec-main,#sec-emu,#sec-shardy{grid-column:span 4;grid-row:2}
section{border:1px solid var(--line);border-radius:var(--r2);background:var(--card);padding:var(--s3) var(--s4);
  box-shadow:var(--shadow)}
section h2{margin:0 0 var(--s3);font-size:14px;letter-spacing:.01em;display:flex;gap:var(--s2);align-items:center;
  padding-bottom:var(--s2);border-bottom:1px solid var(--line)}
.dot{width:10px;height:10px;border-radius:50%;background:#bbb;display:inline-block;flex:none}
.dot.on{background:var(--ok)} .dot.off{background:#bbb} .dot.warn{background:var(--warn)} .dot.bad{background:var(--bad)}

button{font:inherit;padding:5px 12px;margin:0 var(--s2) var(--s2) 0;border:1px solid var(--line-2);border-radius:var(--r1);
  background:var(--card);color:var(--ink);cursor:pointer;transition:background .12s,border-color .12s,transform .04s}
button:hover:enabled{background:#eef2f7;border-color:var(--line-2)}
button:active:enabled{transform:translateY(1px)}
button:disabled{opacity:.5;cursor:not-allowed;background:#f2f4f7;color:var(--muted);border-color:var(--line)}
#b-run{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
#b-run:hover:enabled{background:#1a5391;border-color:#1a5391}
#b-main-start,#b-emu-start,#b-shardy-start{color:var(--accent);border-color:#b9cde6;background:#f7fafd}
#b-main-start:hover:enabled,#b-emu-start:hover:enabled,#b-shardy-start:hover:enabled{background:#eaf2fb}

.why{color:var(--bad);font-size:13px;margin:var(--s2) 0 0}
.hint{margin:var(--s3) var(--s5) 0;padding:10px 14px;border-radius:var(--r2);background:#fff8e6;
  border:1px solid #f0d9a0;font-size:14px}
#lower{margin:0 var(--s5) var(--s5)}
.tabs{display:flex;gap:var(--s2);margin:0 0 var(--s2)}
.tabs button{margin:0}
.tabs button.active{background:var(--ink-2);border-color:var(--ink-2);color:#fff}
pre{margin:0;background:var(--ink-2);color:#d7e3f2;padding:14px;border-radius:var(--r2);max-height:320px;overflow:auto;
  font:12.5px/1.5 var(--mono);white-space:pre-wrap}
pre:empty{display:none}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle;font-size:13px}
#lower > div[id^="pane-"]{background:var(--card);border:1px solid var(--line);border-radius:var(--r2);padding:var(--s3) var(--s4);box-shadow:var(--shadow)}
#rep-body td:first-child,#cases-body td:nth-child(2){font-family:var(--mono);font-size:12.5px}
.recent{display:grid;grid-template-columns:repeat(6,1fr);gap:var(--s2);margin-bottom:var(--s3)}
.recent .cell{border:1px solid var(--line);border-radius:var(--r2);padding:8px 10px;background:#fbfcfe}
.recent .cell .num{font:600 17px/1.2 var(--mono)}
.recent .cell .lbl{font-size:12px;color:var(--muted)}
thead th{position:sticky;top:0;background:var(--card);z-index:1;font-size:13px;color:var(--muted);
  border-bottom:1px solid var(--line-2)}
tbody tr:hover{background:#f7fafc}
tbody tr:nth-child(even){background:#fbfcfe}
tbody tr:nth-child(even):hover{background:#f4f8fb}
.badge{padding:1px 8px;border-radius:10px;font-size:12px;color:#fff;background:var(--ok)}
.badge.no{background:var(--bad)}
.warnbox{padding:6px 10px;border-radius:var(--r1);background:var(--warn-bg);border:1px solid #f0d58c;color:var(--warn)}
.muted{color:var(--muted);font-size:13px}
#pick-bar{position:sticky;top:0;z-index:2;background:var(--card);border-bottom:1px solid var(--line-2);
  padding:var(--s2) 0;display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap;font-size:14px}
#pick-bar input[type=number],#pick-bar input[type=text]{font:inherit;padding:4px 6px;border:1px solid var(--line-2);
  border-radius:var(--r1);background:var(--card);color:var(--ink)}
.pickgroup{color:var(--accent);cursor:pointer;font-size:13px;margin-left:var(--s2)}
.gate{font-size:12px;padding:1px 6px;border-radius:9px;white-space:nowrap}
.gate.ok{background:var(--ok-bg);color:var(--ok)}
.gate.debt{background:var(--warn-bg);color:var(--warn)}
.gate.bad{background:var(--bad-bg);color:var(--bad)}

@media (max-width:1000px){
  main{grid-template-columns:1fr;padding:var(--s3)}
  main > section{grid-column:1 / -1 !important;grid-row:auto !important}
  .pills{grid-template-columns:1fr 1fr;padding-left:var(--s3);padding-right:var(--s3)}
  #lower{padding:0}
  .hint,.pills{padding-left:var(--s3);padding-right:var(--s3);margin-left:0;margin-right:0}
  table{display:block;overflow-x:auto}
}
</style>
<header><h1>Stendhal QA 面板</h1><span id="proj"></span><span id="state-summary"></span></header>
<div class="pills" id="pills"></div>
<p class="hint" id="hint" role="status" aria-live="polite">读取状态…</p>

<main>
  <section id="sec-cases"><h2><i class="dot" id="d-case" aria-hidden="true"></i>用例</h2>
    <p class="muted">运行时到「用例清单」里勾：可以按项目/类型筛选、点「全选筛选结果」、改轮次，再点「执行所选」。
      空手跑一条时勾一条即可。</p>
    <p class="muted">UI 用例需要模拟器就绪；API 用例只需要主服。两组不要同时跑。</p>
    <p class="muted" id="case-last"></p>
    <p class="why" id="case-why"></p></section>
  <section id="sec-self"><h2><i class="dot" id="d-self" aria-hidden="true"></i>环境自检</h2>
    <button id="b-selfcheck">跑框架自检（tests/）</button>
    <p class="muted" id="self-note">不碰游戏和模拟器，约 4 秒。</p></section>
  <section id="sec-char"><h2><i class="dot" id="d-char" aria-hidden="true"></i>测试角色</h2>
    <button id="b-healthcheck">重新检查角色状态</button>
    <button id="b-cleanup" title="清测试角色的攻击目标/寻路/持续状态，并清空背包里的持久残留（prepare 清空 + forget 撤快照，不需要重启主服）。会话层的残留仍用主服的停止+启动。">清理角色状态</button>
    <p class="muted" id="char-note">检查中…（会短暂登录两个角色，约 10 秒）</p></section>

  <section id="sec-main"><h2><i class="dot" id="d-main" aria-hidden="true"></i>主服 Stendhal</h2>
    <button id="b-main-start">启动主服</button><button id="b-main-stop">停止主服</button>
    <p class="muted" id="main-note"></p>
    <p class="muted">停服前先确认没有任务在跑；停服脚本会等数据库写队列落库（未落库时强停会丢写，症状是角色再也登不进去）。</p>
    <p class="why" id="main-why"></p></section>

  <section id="sec-emu"><h2><i class="dot" id="d-emu" aria-hidden="true"></i>模拟器 Android</h2>
    <button id="b-emu-start">启动模拟器</button><button id="b-emu-stop">停止模拟器</button>
    <label class="muted" title="勾上=带窗口启动（用软件渲染，首帧慢 30-60 秒）；不勾=无窗口，适合无人值守"><input id="emu-window" type="checkbox" checked> 显示窗口</label>
    <button id="b-connect">重新连接（端口映射）</button>
    <p class="muted" id="emu-note"></p>
    <p class="why" id="emu-why"></p></section>

  <section id="sec-shardy"><h2><i class="dot" id="d-shardy" aria-hidden="true"></i>Shardy 井字棋</h2>
    <button id="b-shardy-start">启动 Shardy</button><button id="b-shardy-stop">停止 Shardy</button>
    <p class="muted" id="shardy-note"></p>
  </section>
</main>

<div id="lower">
  <div class="tabs"><button id="t-job" class="active">当前任务</button><button id="t-cases">用例清单</button><button id="t-rep">结果</button></div>
  <div id="pane-job">
      <div class="recent" id="recent"></div>
    <p class="muted" id="job-note">还没有任务。到「用例清单」勾选执行；上面只有环境与服务的按钮。</p>
    <p class="why" id="job-hint"></p>
    <pre id="job-out"></pre>
  </div>
  <div id="pane-cases" hidden>
    <p class="muted" id="cases-summary">读取中…（要跑一次 collect-only，约 0.2 秒）</p>
    <div id="pick-bar">
      <label>项目 <select id="game-filter">
        <option value="all">全部</option><option value="stendhal">stendhal</option><option value="shardy">shardy</option>
      </select></label>
      <label>类型 <select id="kind-filter">
        <option value="all">全部</option><option value="api">api</option><option value="ui">ui</option>
      </select></label>
      <button id="b-pickall">全选筛选结果</button>
      <span id="pick-count">已选 0 条</span>
      <span id="pick-eta">预计 —</span>
      <label>轮次 <input id="rounds" type="number" value="1" min="1" max="20"></label>
      <button id="b-run" disabled>执行所选</button>
      <span class="why" id="pick-why"></span>
    </div>
    <div id="cases-body"></div>
  </div>
  <div id="pane-rep" hidden>
    <p id="rep-retry" class="muted">重试率：读取中…</p>
    <p class="muted">口径：<b>重试才过不算一次通过</b>；超过 35% 只作提示，不阻断运行。</p>
    <table><thead><tr><th>运行</th><th>轮数</th><th>一次通过</th><th>重试才过</th><th>各轮一致</th><th>全部通过</th><th>失败用例</th><th></th></tr></thead>
    <tbody id="rep-body"></tbody></table>
    <p class="muted">报告目录：<span id="rep-root"></span></p>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
let state = {}, current = null, cursor = 0, timer = null;

async function api(path, method) {
  const r = await fetch(path, {method: method || 'GET'});
  return r.json();
}
function post(path) { return api(path, 'POST'); }

function say(text, kind) {
  $('job-out').textContent = text;
  $('job-note').textContent = kind || '';
  $('job-hint').textContent = '';
}

function beginJob(jobId, label) {
  current = jobId; cursor = 0; showTab('job');
  say('$ ' + label + '\n\n', '运行中…');
  if (timer) clearInterval(timer);
  timer = setInterval(pollJob, 600);
}

async function startJob(name, argvLabel, rounds) {
  const r = await post('/api/job/' + name + (rounds ? '?rounds=' + rounds : ''));
  if (r.error) { $('job-note').textContent = '没有启动：' + r.error; return; }
  beginJob(r.job, argvLabel);
}

async function pollJob() {
  if (!current) return;
  const r = await api('/api/job/' + current + '?cursor=' + cursor);
  if (r.error) { clearInterval(timer); timer = null; return; }
  if (r.lines.length) { $('job-out').textContent += r.lines.join('\n') + '\n'; cursor = r.next; $('job-out').scrollTop = 1e9; }
  if (r.state !== 'running') {
    clearInterval(timer); timer = null;
    $('job-note').textContent = r.name + ' 结束：' + r.state + '（退出码 ' + r.code + '）'
      + (r.unexecuted && r.unexecuted.length
         ? ' · 失败即停，后续未执行 ' + r.unexecuted.length + ' 条：' + r.unexecuted.join('、') : '');
    $('job-hint').textContent = r.hint || '';
    current = null; refreshState(); loadReports();
  } else {
    $('job-note').textContent = r.name + ' 运行中 · ' + progressText(r.progress);
  }
}

function showTab(which) {
  $('pane-job').hidden = which !== 'job';
  $('pane-cases').hidden = which !== 'cases';
  $('pane-rep').hidden = which !== 'rep';
  $('t-job').className = which === 'job' ? 'active' : '';
  $('t-cases').className = which === 'cases' ? 'active' : '';
  $('t-rep').className = which === 'rep' ? 'active' : '';
}

function dot(el, cls, text) { el.className = 'dot ' + cls; el.title = text || ''; }

function lastOf(names) {
  const rows = names.map((n) => state.last[n] && Object.assign({name: n}, state.last[n])).filter(Boolean);
  return rows.sort((a, b) => b.id - a.id)[0];
}
function describe(row) {
  const run = /reports\/(\d{8}T\d+Z)/.exec(row.line || '');
  const verdict = /Repeatable: (\w+); all passed: (\w+)/.exec(row.line || '');
  return row.name + '：' + row.state + '（退出码 ' + row.code + '）'
    + (run ? ' ' + run[1] : '') + (verdict ? ' 一致=' + verdict[1] + ' 全通过=' + verdict[2] : '')
    + (row.at ? ' · ' + new Date(row.at * 1000).toLocaleTimeString() : '');
}

function fmtDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}
function progressText(p) {
  if (!p) return '';
  let text = '已运行 ' + fmtDuration(p.elapsed);
  if (p.rounds) text += ' · 第 ' + p.round + '/' + p.rounds + ' 轮';
  if (p.cases !== undefined) {
    text += '（本轮 ' + p.cases + (p.per_round ? '/' + p.per_round : '') + ' 条已开始）';
  }
  if (p.eta) text += ' · 预计还需约 ' + fmtDuration(p.eta);
  return text;
}

function render() {
  const main = state.main, emu = state.emulator, rev = state.reverse, shardy = state.shardy || {};
  const uiReady = emu.device && emu.boot_completed && rev['8080'];

  dot($('d-main'), main.listening ? 'on' : 'off');
  $('main-note').textContent = main.listening
    ? ('32160 监听中，Web 入口 ' + (main.http === null ? '尚未响应（刚启动约需 7 秒，稍等）' : 'HTTP ' + main.http))
    : '未监听 32160。';
  $('b-main-start').disabled = main.listening;
  $('b-main-stop').disabled = !main.listening;
  $('main-why').textContent = main.listening && main.http !== null && main.http !== 200
    ? ('主服在监听但 Web 入口返回 ' + main.http + '，检查 work/stendhal/runtime/log/server.log。') : '';

  dot($('d-emu'), emu.device && emu.boot_completed ? (rev['8080'] ? 'on' : 'warn') : (emu.device ? 'warn' : 'off'));
  dot($('d-shardy'), state.shardy && state.shardy.backend && state.shardy.client ? 'on'
      : (state.shardy && (state.shardy.backend || state.shardy.client) ? 'warn' : 'off'));
  $('emu-note').textContent = emu.device
    ? ('设备在线，开机' + (emu.boot_completed ? '完成' : '未完成') + '；端口映射 8080 ' + (rev['8080'] ? '已建' : '缺失')
       + '（自动重连已开启）')
    : '未检测到 emulator-5554。';
  $('shardy-note').textContent = state.shardy
    ? ('后端 3000 ' + (state.shardy.backend ? '在跑' : '没跑') + ' · 展示页 3001 ' + (state.shardy.client ? '在跑' : '没跑')) : '';
  $('b-emu-start').disabled = emu.device;
  $('b-emu-stop').disabled = !emu.device;
  $('b-connect').disabled = !emu.device;
  $('emu-why').textContent = emu.device && !rev['8080'] ? '端口映射缺失：模拟器重启后会丢，点「重新连接」。' : '';

  dot($('d-case'), main.listening && uiReady ? 'on' : (main.listening ? 'warn' : 'off'));
  $('b-cleanup').disabled = !main.listening;
  $('case-why').textContent = !main.listening ? '主服未启动，用例无法运行。'
    : (!uiReady ? 'UI 用例需要模拟器开机完成且 8080 映射存在；API 用例可以先跑。' : '');
  const lastCase = lastOf(['custom-api', 'custom-ui']);
  $('case-last').textContent = lastCase ? '上次运行 ' + describe(lastCase) : '';

  const self = state.last.selfcheck;
  dot($('d-self'), !self ? 'off' : (self.state === 'passed' ? 'on' : 'bad'));
  $('self-note').textContent = self
    ? ('上次自检 ' + self.state + '（退出码 ' + self.code + '）：' + self.line)
    : '不碰游戏和模拟器，约 4 秒。';
  renderCharacterHealth(state.health);
  const kpi = (label, num, words, level) => '<div class="kpi ' + level + '">'
    + '<i class="dot ' + level + '" aria-hidden="true"></i><div><div class="num">' + num + '</div>'
    + '<div class="label">' + label + '</div><div class="words">' + words + '</div></div></div>';
  const revOk = rev['8080'] && rev['3000'] && rev['3001'];
  const shardyOk = shardy.backend && shardy.client, shardyHalf = shardy.backend || shardy.client;
  const mainOk = main.listening && main.http === 200;
  const emuOk = emu.device && emu.boot_completed;
  const job = state.job;
  $('pills').innerHTML = [
    kpi('主服 Stendhal', '32160', mainOk ? '在跑 · Web 200' : (main.listening ? '在跑 · Web ' + main.http : '没跑'),
        mainOk ? 'on' : (main.listening ? 'warn' : 'off')),
    kpi('模拟器 Android', '5554', (emuOk ? '就绪' : (emu.device ? '已连，未启动完' : '没连'))
        + ' · 端口映射' + (revOk ? '全' : '不全'), emuOk && revOk ? 'on' : (emu.device ? 'warn' : 'off')),
    kpi('Shardy 井字棋', '3000/3001', shardyOk ? '在跑' : (shardyHalf ? '只起了一半' : '没跑'),
        shardyOk ? 'on' : (shardyHalf ? 'warn' : 'off')),
    kpi('当前任务', job ? (Math.round((job.progress || {}).elapsed || 0) + 's') : '空闲',
        job ? job.name + ' 进行中' : '没有任务在跑', job ? 'warn' : 'off'),
  ].join('');
  $('state-summary').textContent = '主服 ' + (main.listening ? '✓' : '✗')
    + ' · 模拟器 ' + (emu.device ? (emu.boot_completed ? '✓' : '开机中') : '✗')
    + ' · 映射 ' + (rev['8080'] ? '✓' : '✗');

  $('hint').textContent = !main.listening ? '下一步：启动主服。'
    : !emu.device ? '下一步：到「用例清单」勾 API 用例执行（不需要模拟器）；顺带启动模拟器，为 UI 用例做准备。'
    : !emu.boot_completed ? '下一步：等模拟器开机完成（约 1–2 分钟），看 work/android/logs/emulator.log。'
    : !rev['8080'] ? '下一步：点「重新连接」建立端口映射。'
    : '下一步：到「用例清单」筛选（项目/类型）→ 全选筛选结果 → 改轮次 → 执行所选。勾一条就是冒烟。';
  const busy = state.job;
  if (busy) $('hint').textContent = '正在运行：' + busy.name + ' · ' + progressText(busy.progress)
    + '（同时只能跑一个任务）';
}

function healthItem(c) {
  if (!c.online) return c.name + ' 连不上';
  if (!c.dirty) return c.name + ' 干净';
  const bag = (c.bag || []).map(([n, q]) => n + '×' + q).join('、');
  const extra = [];
  if (bag) extra.push('背包有 ' + bag);
  if ((c.statuses || []).length) extra.push('持续状态 ' + c.statuses.length + ' 项');
  if (c.target) extra.push('攻击目标未清');
  return c.name + ' 有残留：' + extra.join('，');
}
function renderCharacterHealth(h) {
  const node = $('char-note');
  if (!h) { node.textContent = '还没检查（有任务在跑时会跳过）。'; dot($('d-char'), 'off'); return; }
  if (h.error) { node.textContent = '检查失败：' + h.error; dot($('d-char'), 'bad'); return; }
  if (!h.characters || !h.characters.length) {
    node.textContent = h.note || '暂未取得角色状态'; dot($('d-char'), 'off'); return;
  }
  const dirty = h.characters.filter((c) => c.dirty || !c.online).length;
  dot($('d-char'), dirty ? 'bad' : 'on');
  node.textContent = (h.at ? '检查于 ' + h.at + ' · ' : '') + h.characters.map(healthItem).join(' · ')
    + (dirty ? '　→ 点「清理角色状态」可以清掉（含背包残留）' : '');
}

async function refreshState() { state = await api('/api/state'); render(); }

function pct(value) { return (100 * value).toFixed(1) + '%'; }

async function loadReports() {
  const data = await api('/api/reports');
  const rows = data.runs || [];
  const retry = data.retry || {observations: 0, retried: 0, rate: 0, warn: false, first_try: 0};
  const box = $('rep-retry');
  const text = '最近 ' + rows.length + ' 轮重试率：' + pct(retry.rate)
    + '（重试才过 ' + retry.retried + ' / 观测 ' + retry.observations + '，一次通过 ' + retry.first_try + '）';
  box.textContent = retry.observations ? text : '最近 ' + rows.length + ' 轮还没有可统计的观测。';
  box.className = retry.warn ? 'warnbox' : 'muted';
  const stamp = (run) => run.slice(4, 6) + '-' + run.slice(6, 8) + ' ' + run.slice(9, 11) + ':' + run.slice(11, 13) + ' UTC';
  const last = rows[0];
  const cell = (num, lbl) => '<div class="cell"><div class="num">' + num + '</div><div class="lbl">' + lbl + '</div></div>';
  $('recent').innerHTML = last ? [
    cell(stamp(last.run), '最近一次运行'),
    cell(last.rounds, '轮数'),
    cell(last.first_try_passed + ' / ' + last.observations, '一次通过'),
    cell(last.infra_retry_count + (last.observations ? '（' + pct(last.infra_retry_rate) + '）' : ''), '重试才过'),
    cell(last.failed.length ? last.failed.length + ' 条' : '无失败', '失败用例')
      + '<div class="cell"><div class="num"><a href="/reports/' + last.run + '/' + last.report
      + '" target="_blank">打开报告</a></div><div class="lbl">多轮汇总页</div></div>',
  ].join('') : '<p class="muted">还没有运行记录。到「用例清单」勾选执行。</p>';
  $('rep-root').textContent = '项目 reports/（目录名是 UTC 时间）';
  $('rep-body').innerHTML = rows.map((r) =>
    '<tr><td>' + r.run + '</td>'
    + '<td>' + r.rounds + '</td>'
    + '<td>' + r.first_try_passed + ' / ' + r.observations + '</td>'
    + '<td' + (r.infra_retry_rate > 0.35 ? ' class="warnbox"' : '') + '>' + r.infra_retry_count
    + (r.observations ? '（' + pct(r.infra_retry_rate) + '）' : '') + '</td>'
    + '<td><span class="badge' + (r.consistent ? '' : ' no') + '">' + r.consistent + '</span></td>'
    + '<td><span class="badge' + (r.all_passed ? '' : ' no') + '">' + r.all_passed + '</span></td>'
    + '<td class="muted">' + (r.failed.join(', ') || '—') + '</td>'
    + '<td><a href="/reports/' + r.run + '/' + r.report + '" target="_blank">打开报告</a>'
    + ' <a href="/reports/' + r.run + '/summary.json" target="_blank">summary</a></td></tr>').join('')
    || '<tr><td colspan="8" class="muted">还没有运行记录。</td></tr>';
}

const MARK_TEXT = {A: '已实现 API', U: '已实现 UI', 'A?': '建议API·未实现',
                   'U?': '建议UI·未实现', 'M?': '建议手工·未实现'};
function markText(m) { return MARK_TEXT[m] || '—'; }
function table(head, rows) {
  return '<table><thead><tr>' + head.map((h) => '<th>' + h + '</th>').join('') + '</tr></thead><tbody>'
    + rows.map((r) => '<tr>' + r.map((c) => '<td>' + c + '</td>').join('') + '</tr>').join('')
    + '</tbody></table>';
}
function details(title, body, attr) {
  return '<details' + (attr || '') + '><summary>' + title + '</summary>' + body + '</details>';
}

const GATE_TEXT = {'达标': ['ok', '达标'], '欠账': ['debt', '欠账（门禁豁免中）'],
                   '违规': ['bad', '违规（门禁不允许）']};
function gateText(r) {
  const [cls, text] = GATE_TEXT[r.gate.state] || ['ok', r.gate.state];
  const rules = (r.gate.rules || []).join('、');
  return '<span class="gate ' + cls + '" title="' + (rules || '无规则违规') + '">' + text + '</span>';
}
function gameOf(id) { return id.startsWith('SH-') ? 'shardy' : 'stendhal'; }

function caseSummary() {
  const c = caseData.counts, f = $('game-filter').value;


  return '已实现 ' + c.implemented + ' 条 · 已设计未实现 ' + c.designed
    + ' 条 · 声明已实现但无独立用例 ' + c.aliases + ' 条 · 文档共 ' + c.documented_total
    + ' 条 · 实现但文档里找不到 ' + c.unmatched + ' 条 · 已实现但无文档标记 '
    + c.undocumented_implemented + ' 条 · 中文名待补 ' + c.untitled + ' 条 · 门禁欠账 ' + c.gate_debt + ' 条'
    + (f === 'all' ? ''
       : '【已筛选 ' + f + '：' + caseData.implemented.filter((r) => r.game === f).length
         + '/' + c.implemented + ' 条；文档侧条目请切回「全部」】');
}

// 筛选只隐藏别的项目的分组，不重新渲染：已勾选的用例不会因为你换个项目看就悄悄被清掉。
function applyFilter() {
  if (!caseData) return;
  const game = $('game-filter').value, kind = $('kind-filter').value;
  document.querySelectorAll('#cases-body [data-game]').forEach((el) => {
    const hideGame = game !== 'all' && el.dataset.game !== game;
    const hideKind = kind !== 'all' && el.dataset.kind !== kind && el.dataset.game !== 'doc';
    el.hidden = hideGame || hideKind;
  });
  $('cases-summary').textContent = caseSummary();
  const visible = visiblePicks().length;
  $('b-pickall').textContent = '全选筛选结果（' + visible + ' 条）';
  $('b-pickall').disabled = !visible;
  updatePick();
}

function visiblePicks() {
  return [...document.querySelectorAll('#cases-body details:not([hidden]) .pick')];
}

async function loadCases() {
  caseData = await api('/api/cases');
  const d = caseData;
  const groups = {};
  d.implemented.forEach((r) => {
    const key = r.game + ' / ' + r.module + ' / ' + r.kind;
    (groups[key] = groups[key] || []).push(r);
  });
  let html = Object.keys(groups).sort().map((key) => details(
    key + '（' + groups[key].length + ' 条）<span class="pickgroup" data-group="' + key + '">全选本组</span>',
    table(['选', '用例 ID', '中文名', '门禁', '文档标记', '最近40次运行', '文档来源'],
      groups[key].map((r) => [
        '<input type="checkbox" class="pick" value="' + r.id + '" data-kind="' + r.kind
          + '" data-group="' + key + '" data-seconds="' + (r.seconds || '') + '">',
        r.id, r.title || '<span class="muted">待补</span>', gateText(r), markText(r.marker),
        r.last ? r.last.outcome + ' · ' + r.last.run + (r.seconds ? '（' + fmtDuration(r.seconds) + '）' : '')
               : '未跑过',
        r.source || (r.documented ? '—' : '⚠ 文档里没这个编号')])),
    ' data-game="' + groups[key][0].game + '" data-kind="' + groups[key][0].kind + '"')).join('');
  html += details('已设计未实现（文档里有、框架里没有）', table(['用例 ID', '文档标记', '文档来源', '文档备注'],
    d.designed.map((r) => [r.id, markText(r.marker), r.source || '—', r.note || r.doc])),
    ' data-game="doc"');
  html += details('声明已实现但无独立用例（共用执行ID的别名）', table(['用例 ID', '文档标记', '文档备注'],
    d.aliases.map((r) => [r.id, markText(r.marker), r.note || '—'])), ' data-game="doc"');
  html += details('实现但文档里找不到（编号对不上）', table(['用例 ID'], d.unmatched.map((id) => [id])),
    ' data-game="doc"');
  $('cases-body').innerHTML = html;
  document.querySelectorAll('.pickgroup').forEach((el) => {
    el.onclick = (event) => {
      event.preventDefault(); event.stopPropagation();
      const on = el.dataset.on !== '1';
      el.dataset.on = on ? '1' : '0';
      document.querySelectorAll('.pick[data-group="' + el.dataset.group + '"]')
        .forEach((box) => { box.checked = on; });
      updatePick();
    };
  });
  updatePick();
  applyFilter();
}

const FALLBACK_SECONDS = {api: 6.4, ui: 60};
function picked() { return [...document.querySelectorAll('#cases-body .pick:checked')]; }
function roundsValue() {
  const n = parseInt($('rounds').value, 10);
  return Number.isFinite(n) ? Math.max(1, Math.min(20, n)) : 1;
}
function estimateSeconds() {
  const rounds = roundsValue();
  return picked().reduce((total, box) =>
    total + (parseFloat(box.dataset.seconds) || FALLBACK_SECONDS[box.dataset.kind] || 30) * rounds, 0);
}
function updatePick() {
  const chosen = picked();
  const seconds = estimateSeconds();
  const mixed = new Set(chosen.map((box) => box.dataset.kind)).size > 1;
  $('pick-count').textContent = '已选 ' + chosen.length + ' 条';
  $('pick-eta').textContent = chosen.length ? '预计约 ' + fmtDuration(seconds) : '预计 —';
  const uiPicked = chosen.some((box) => box.dataset.kind === 'ui');
  const uiReady = state && state.main.listening && state.emulator.device && state.emulator.boot_completed;
  $('b-run').disabled = !chosen.length || mixed || (uiPicked && !uiReady);
  $('pick-why').textContent = mixed
    ? 'API 和 UI 用例不能混在一次运行：共用管理员、商店 NPC 和浏览器，请分成两次'
    : (uiPicked && !uiReady ? '选中的 UI 用例需要主服 + 模拟器开机 + 端口映射就绪'
    : (chosen.length && seconds > 1200 ? '超过 20 分钟，点执行时会再确认' : ''));
}

$('b-selfcheck').onclick = () => startJob('selfcheck', 'python -m pytest tests -q');
// 运行入口只剩「用例清单」的「执行所选」一处：不做第二套语义

// 全组任务用界面上的「轮次」框决定跑几轮；没有"必须五轮"这回事。


$('b-cleanup').onclick = () => startJob('cleanup', 'python scripts/cleanup_characters.py');
$('b-healthcheck').onclick = async () => {
  $('char-note').textContent = '检查中…（会短暂登录两个角色，约 10 秒）';
  await post('/api/health/check');
  setTimeout(refreshState, 12000);
};

$('b-connect').onclick = () => startJob('connect', 'bash scripts/android/connect.sh');
$('b-main-start').onclick = async () => { await post('/api/service/main/start'); setTimeout(refreshState, 1500); };
$('b-main-stop').onclick = async () => { await post('/api/service/main/stop'); setTimeout(refreshState, 1200); };
$('b-emu-start').onclick = async () => {
  const service = $('emu-window').checked ? 'emulator-window' : 'emulator';
  $('emu-note').textContent = '启动中（' + (service === 'emulator-window' ? '带窗口' : '无窗口') + '，约 30–60 秒）…';
  await post('/api/service/' + service + '/start');
  setTimeout(() => { refreshState(); $('emu-note').textContent = service === 'emulator-window' ? '已发出启动：模拟器窗口应出现在桌面上' : '已发出启动（无窗口）'; }, 5000);
};
$('b-emu-stop').onclick = async () => { await post('/api/service/emulator/stop'); setTimeout(refreshState, 2000); };
$('b-shardy-start').onclick = async () => { $('shardy-note').textContent = '启动中（约 5 秒）…'; await post('/api/service/shardy/start'); setTimeout(() => { refreshState(); $('shardy-note').textContent = '已发出启动，状态灯 5 秒后刷新'; }, 5000); };
$('b-shardy-stop').onclick = async () => { $('shardy-note').textContent = '停止中…'; await post('/api/service/shardy/stop'); setTimeout(() => { refreshState(); $('shardy-note').textContent = '已停止'; }, 2000); };
$('t-job').onclick = () => showTab('job');
$('t-cases').onclick = () => { showTab('cases'); loadCases(); };
$('t-rep').onclick = () => { showTab('rep'); loadReports(); };
function pickVisible(on) {
  visiblePicks().forEach((box) => { box.checked = on; });
  updatePick();
}
$('b-pickall').onclick = () => pickVisible(true);
$('game-filter').onchange = () => { applyFilter(); };
$('kind-filter').onchange = () => { applyFilter(); };
$('cases-body').addEventListener('change', updatePick);
$('rounds').addEventListener('input', updatePick);
$('b-run').onclick = async () => {
  const cases = picked().map((box) => box.value);
  const rounds = roundsValue();
  const seconds = estimateSeconds();
  if (seconds > 1200 && !confirm('预计要跑 ' + fmtDuration(seconds) + '，确定开始？')) return;
  const r = await fetch('/api/run', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({cases: cases, rounds: rounds})}).then((response) => response.json());
  if (r.error) { $('pick-why').textContent = r.error; return; }
  beginJob(r.job, 'python -m gameqa run --case "' + cases.join(',') + '" --rounds ' + rounds
    + ' --experiment custom --stop-after-failure');
};

$('proj').textContent = PROJECT;refreshState(); loadReports();
setInterval(refreshState, 1500);
</script></html>"""


def main():
    import sys
    if "--state" in sys.argv:
        print(json.dumps(probe(), ensure_ascii=False, indent=2))
        return
    print(f"Stendhal QA 面板： http://127.0.0.1:{PORT}/  （Ctrl-C 停止）")
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=health_loop, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
