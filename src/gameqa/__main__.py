import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import html
import os
from pathlib import Path
import subprocess
import sys

from . import allure_report
from .config import load_config
from .bridge import INFRA_SIGNATURES as _INFRA_SIGNATURES, redact
from .run_lock import RunBusy, RunLock


# 基础设施抖动的签名：这些不是用例判定的业务事实，可以重跑一次。
# 断言失败（failed）绝不重试——那是真结果；重试恢复的也不算完成验收（见 index.html 的说明）。
INFRA_SIGNATURES = _INFRA_SIGNATURES


def infra_failed(report):
    """挑出因基础设施抖动而失败的用例 id（只看签名，业务断言不含签名故不会被重试）。"""
    picked = []
    for case in report.get("cases", []):
        if case.get("outcome") == "passed":
            continue
        # 只看签名，不看 outcome：抖动可能落在用例体内，那样会被记成 failed；
        # 业务断言的文本里没有这些签名，所以照样不会被重试。
        text = json.dumps(case.get("phases", {}), ensure_ascii=False)
        if any(signature in text for signature in INFRA_SIGNATURES):
            picked.append(case["id"])
    return picked


def summarize(rounds):
    """每轮报告合成一份 summary。

    报告口径（不许含糊）：**"重试才过"不算一次通过**。
    - observations：case × round 的观测总数，也就是分母
    - infra_retry_count：带重试标记的观测数（不管最后过没过）
    - infra_retry_rate：上面两者相除；没有观测时为 0.0
    - first_try_passed：**没有**走重试就通过的观测数（这才是"一次通过"）
    - all_passed 要求每条观测都 passed 且没走重试 —— 有重试的轮次永远不会被判成全绿
    """
    by_case = defaultdict(list)
    for number, report in enumerate(rounds, 1):
        for case in report.get("cases", []):
            by_case[case["id"]].append({"round": number, "outcome": case["outcome"],
                                        "unstable": case.get("unstable", False),
                                        "infra_retry": bool((case.get("diagnostics") or {}).get("infra_retry"))})
    cases = []
    for case_id, observations in sorted(by_case.items()):
        outcomes = {row["outcome"] for row in observations}
        consistent = len(observations) == len(rounds) and len(outcomes) == 1
        complete = outcomes <= {"passed", "failed"}
        cases.append({"id": case_id, "observations": observations, "consistent": consistent,
                      "repeatable": consistent and complete and not any(row["unstable"] for row in observations)})
    order = [row for case in cases for row in case["observations"]]
    retried = sum(1 for row in order if row["infra_retry"])
    first_try = sum(1 for row in order if row["outcome"] == "passed" and not row["infra_retry"])
    return {"rounds": len(rounds), "cases": cases,
            "consistent": bool(cases) and all(row["repeatable"] for row in cases),
            "observations": len(order),
            "infra_retry_count": retried,
            "infra_retry_rate": round(retried / len(order), 4) if order else 0.0,
            "first_try_passed": first_try,
            "infra_retries": retried,
            "unexplained_failures": sorted(row["id"] for row in cases if any(
                obs["outcome"] != "passed" and not obs["infra_retry"] for obs in row["observations"])),
            "all_passed": bool(cases) and all(
                len(row["observations"]) == len(rounds)
                and all(obs["outcome"] == "passed" and not obs["infra_retry"] for obs in row["observations"])
                for row in cases)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="游戏测试统一入口")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="执行接口/UI用例并保存每轮证据")
    run.add_argument("--config")
    run.add_argument("--project", type=Path, default=Path.cwd())
    run.add_argument("--game", choices=["stendhal", "shardy"])
    run.add_argument("--module")
    run.add_argument("--kind", choices=["api", "ui"])
    run.add_argument("--case")
    run.add_argument("--rounds", type=int, default=1)
    run.add_argument("--retry-infra", type=int, default=1, choices=(0, 1),
                     help="基础设施抖动（掉线/超时）报错的用例重跑一次；只认这类签名，重试恢复的不计完成验收")
    run.add_argument("--report-dir", type=Path)
    run.add_argument("--experiment", default="未命名",
                     help="这次运行的用途标签（结果页会显示）；不写就是「未命名」")
    run.add_argument("--stop-after-failure", action="store_true")
    run.add_argument("--allure", action="store_true",
                     help="额外产出 Allure 报告（第二视图）；不改变判定，报告仍以 case.json/report.json 为准")
    run.add_argument("--qa-lock-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.rounds <= 20:
        parser.error("rounds must be between 1 and 20")
    project = args.project.resolve()
    if not (project / "cases").is_dir():
        parser.error("run in the project root or pass --project")
    try:
        with RunLock.acquire(project, args.qa_lock_fd) as lock:
            return execute(args, project, lock)
    except RunBusy as error:
        print(str(error), file=sys.stderr)
        return 2


def execute(args, project, lock):
    config = load_config(args.config)
    use_allure = bool(args.allure)
    if use_allure and not allure_report.available():
        print("提示：未安装 allure-pytest，本次跳过 Allure（判定与报告不受影响）；"
              "安装：pip install 'allure-pytest>=2.13,<3'", file=sys.stderr)
        use_allure = False
    child_env = {**os.environ, "GAMEQA_ALLURE": "1"} if use_allure else None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = (args.report_dir or project / "reports" / run_id).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    reports, exit_codes = [], []
    for number in range(1, args.rounds + 1):
        target = folder / f"round-{number:02d}"
        command = [sys.executable, "-m", "pytest", "-p", "gameqa.pytest_plugin", "cases",
                   "--qa-config", config["_path"], "--qa-report-dir", str(target),
                   "--qa-experiment", args.experiment, "--qa-lock-fd", str(lock.fileno())]
        for field in ("game", "module", "kind", "case"):
            value = getattr(args, field)
            if value:
                command.extend([f"--qa-{field}", value])
        if args.stop_after_failure:
            command.append("-x")
        if use_allure:
            command.extend(["--alluredir", str(target / "allure-results")])
        result = subprocess.run(command, cwd=project, text=True, encoding="utf-8",
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                pass_fds=(lock.fileno(),), env=child_env)
        target.mkdir(parents=True, exist_ok=True)
        (target / "pytest.log").write_text(redact(result.stdout), encoding="utf-8")
        print(f"Round {number}/{args.rounds}: exit={result.returncode}; {target / 'index.html'}")
        exit_codes.append(result.returncode)
        report_path = target / "report.json"
        reports.append(json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"cases": []})
        report = reports[-1]
        retried = infra_failed(report) if args.retry_infra else []
        if retried:
            retry_dir = folder / f"round-{number:02d}-retry"
            retry_command = [sys.executable, "-m", "pytest", "-p", "gameqa.pytest_plugin", "cases",
                             "--qa-config", config["_path"], "--qa-report-dir", str(retry_dir),
                             "--qa-experiment", args.experiment, "--qa-case", ",".join(retried),
                             "--qa-lock-fd", str(lock.fileno())]
            if use_allure:
                retry_command.extend(["--alluredir", str(folder / f"round-{number:02d}-retry" / "allure-results")])
            retry_result = subprocess.run(retry_command, cwd=project, text=True, encoding="utf-8",
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          pass_fds=(lock.fileno(),), env=child_env)
            retry_dir.mkdir(parents=True, exist_ok=True)
            (retry_dir / "pytest.log").write_text(redact(retry_result.stdout), encoding="utf-8")
            retry_report = (json.loads((retry_dir / "report.json").read_text(encoding="utf-8"))
                            if (retry_dir / "report.json").exists() else {"cases": []})
            by_id = {case["id"]: case for case in report["cases"]}
            recovered, still_failing = [], []
            for case in retry_report.get("cases", []):
                first = by_id.get(case["id"], {})
                case.setdefault("diagnostics", {})["infra_retry"] = {
                    "first_outcome": first.get("outcome"),
                    "first_error": json.dumps(first.get("phases", {}), ensure_ascii=False)[:400]}
                by_id[case["id"]] = case
                (recovered if case["outcome"] == "passed" else still_failing).append(case["id"])
            report["cases"] = [by_id[case["id"]] for case in report["cases"]]
            report.setdefault("metadata", {})["infra_retry"] = {
                "requested": retried, "recovered": recovered, "still_failing": still_failing}
            (target / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
            print(f"  基础设施重试：恢复 {len(recovered)} 条、仍失败 {len(still_failing)} 条（重试恢复不计完成验收）")
        if args.stop_after_failure and result.returncode != 0:
            print(f"停在第 {number}/{args.rounds} 轮：后续轮次未执行（--stop-after-failure）")
            break
    summary = {**summarize(reports), "experiment": args.experiment, "exit_codes": exit_codes}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    allure_link = ""
    if use_allure:
        results = sorted(folder.glob("round-*/allure-results"))
        html_path, problem = allure_report.generate(results, folder / "allure-html")
        if html_path:
            allure_link = allure_report.summary_link(folder, html_path)
            print(f"Allure: {html_path}")
        else:
            print(f"提示：Allure 报告未生成（{problem}）；allure-results 已保留在 {folder}", file=sys.stderr)
    esc = lambda value: html.escape(str(value))
    rows = []
    for case in summary["cases"]:
        links = " ".join(f'<a href="round-{o["round"]:02d}/index.html#{esc(case["id"])}">'
                         f'第{o["round"]}轮：{esc(o["outcome"])}{"（不稳定）" if o["unstable"] else ""}{"（重试恢复）" if o.get("infra_retry") else ""}</a>'
                         for o in case["observations"])
        rows.append(f'<tr><td>{esc(case["id"])}</td><td>{links}</td><td>{case["repeatable"]}</td></tr>')
    (folder / "index.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>Game QA rounds</title>'
        '<style>body{margin:32px;font:16px system-ui}td,th{padding:14px;border-bottom:1px solid #ddd}a{margin-right:12px}</style>'
        f'<h1>多轮执行结果</h1><p>实验：{esc(args.experiment)}；轮数：{args.rounds}；'
        f'判定一致且稳定：{summary["consistent"]}；全部通过：{summary["all_passed"]}</p>'
          # 报告口径：重试才过必须显式标注，不许当一次通过（页面和 json 里都写清楚）
          f'<p>一次通过：{summary["first_try_passed"]} / {summary["observations"]}；重试才过：{summary["infra_retry_count"]} 条（占 {summary["infra_retry_rate"]:.1%}，不计入一次通过；阈值 35% 仅供提示）</p>'
          f'<p>非基础设施失败：'
             f'{"、".join(esc(x) for x in summary["unexplained_failures"]) if summary["unexplained_failures"] else "无"}</p>'
        '<p>一致检出的缺陷仍是失败；跳过、报错、重试恢复和漏轮不能计为完成验收。</p>'
        + allure_link +
        '<table><tr><th>用例</th><th>每轮证据</th><th>可重复</th></tr>' + "".join(rows) + '</table></html>',
        encoding="utf-8")
    print(f"Repeatable: {summary['consistent']}; all passed: {summary['all_passed']}; {folder / 'summary.json'}")
    return 0 if summary["consistent"] and summary["all_passed"] and all(code == 0 for code in exit_codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
