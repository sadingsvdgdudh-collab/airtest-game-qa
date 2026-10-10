#!/usr/bin/env python3
"""把一次命名运行归档成验收证据包 —— 生成 verification.json 并建 docs/evidence/<组名>/。

验收 = 命名 + 多轮 + 冻结来源 + 独立复核 + 归档 + 被验收清单引用。这个脚本负责其中
**可机检**的部分，并且**明确标出哪些结论必须由人或 AI 独立复核**（脚本不许伪造独立核验）。

  python scripts/archive_evidence.py --experiment stendhal-items-ui-batch3
  python scripts/archive_evidence.py --experiment <组名> --report reports/20261010T111334Z --no-add

拒绝用 custom/baseline 这类"随手跑"的名字建包；也不覆盖已存在的包（要覆盖得显式 --force）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
NOT_ACCEPTANCE = ("", "custom", "baseline")
BOUNDARY = ("index.html", "summary.json", "verification.json", "source.json", "demo-stendhal.mp4")
REVIEW_REQUIRED = ("restored_fields_independently_compared", "independent_review", "framework_self_checks",
                   "new_project_and_python_environment", "existing_local_game_android_environment", "limitations")


def load_case_files(run_dir):
    """一次运行里所有 case.json（含重试轮），每个都标上它所属的轮次。"""
    found = []
    for path in sorted(Path(run_dir).glob("round-*/*/case.json")):
        try:
            number = int(path.parent.parent.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        case["_round"] = number
        found.append(case)
    return found


def find_report(experiment, reports_dir=PROJECT / "reports"):
    """最近一次 experiment 匹配的运行目录。"""
    matches = []
    for summary_path in (reports_dir).glob("*/summary.json"):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if summary.get("experiment") == experiment:
            matches.append((summary_path.stat().st_mtime, summary_path.parent, summary))
    if not matches:
        return None, None
    _, run_dir, summary = sorted(matches)[-1]
    return run_dir, summary


def summarize_run(experiment, summary, cases):
    """只汇总报告里能直接核对的数字；判不了的一律留空并列入 review_required。"""
    observations = sum(len(case.get("steps") or []) for case in cases)
    assertions = sum(1 for case in cases for step in (case.get("steps") or [])
                     if step.get("expected") is not None)
    screenshots = sum(((case.get("diagnostics") or {}).get("ui_timing") or {}).get("screenshots") or 0
                      for case in cases)
    restorations = [(case.get("diagnostics") or {}).get("restoration") or {} for case in cases]
    retried = sum(1 for case in cases for step in (case.get("steps") or [])
                  if len(step.get("attempts") or []) > 1)
    per_round = []
    rounds = summary.get("rounds") or 0
    for number in range(1, rounds + 1):
        in_round = [case for case in cases if case.get("_round") == number]
        per_round.append({"round": number, "ids": [case["id"] for case in in_round],
                          "all_passed": bool(in_round) and all(case["outcome"] == "passed" for case in in_round),
                          "all_restored": bool(in_round) and all(
                              ((case.get("diagnostics") or {}).get("restoration") or {}).get("restored") is True
                              for case in in_round)})
    restored_fields = sorted({field for item in restorations for field in (item.get("restored_fields") or [])})
    return {
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": experiment,
        "rounds": rounds,
        "execution_ids": sorted({case["id"] for case in cases}),
        "counts": {"cases": len(cases), "observations": observations, "assertions": assertions,
                   "screenshots": screenshots,
                   "restores": sum(1 for item in restorations if item.get("restored") is True)},
        "all_passed": bool(summary.get("all_passed")),
        "phases_all_passed": all(all((case.get("phases") or {}).get(phase) == "passed"
                                     for phase in ("setup", "call", "teardown")) for case in cases),
        "unstable_cases": sorted({case["id"] for case in cases if case.get("unstable")}),
        "retried_observations": retried,
        "all_restored": bool(cases) and all(item.get("restored") is True for item in restorations),
        "permitted_location_adjustments": sum(1 for item in restorations if item.get("location_adjusted")),
        "restored_fields_from_reports": restored_fields,
        "per_round": per_round,
        # 下面是"脚本判不了"的：留给独立复核，绝不代填。
        "restored_fields_independently_compared": None,
        "independent_review": {"performed": False, "by": None,
                               "note": "必须由人或 AI 独立读取服务器状态复核后才算验收；脚本不代填"},
        "framework_self_checks": None,
        "source_hashes_match": None,
        "source_files": None,
        "source_captured_before_first_case": None,
        "new_project_and_python_environment": None,
        "existing_local_game_android_environment": None,
        "limitations": None,
        "review_required": sorted(REVIEW_REQUIRED),
    }


def source_checks(package, first_case_started):
    """有 source.json 就复查哈希，并判断冻结是否早于第一条用例。"""
    manifest_path = package / "source.json"
    if not manifest_path.exists():
        return None, None, None
    sys.path.insert(0, str(PROJECT / "scripts"))
    import freeze_source                                     # noqa: PLC0415
    changed, added, removed = freeze_source.compare(manifest_path, PROJECT)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    captured = manifest.get("captured_utc")
    before = None
    if captured and first_case_started:
        before = captured < datetime.fromtimestamp(first_case_started, timezone.utc).isoformat()
    return (not (changed or added or removed)), len(manifest["files"]), before


def credential_scan(package):
    """文本类附件里不该出现配置的凭据值。"""
    secrets = [os.environ[name] for name in ("GAMEQA_PLAYER_PASSWORD", "GAMEQA_OBSERVER_PASSWORD")
               if os.environ.get(name)]
    if not secrets:
        return "skipped: 环境里没有配置凭据变量"
    hits = []
    for path in package.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".log", ".txt", ".html", ".md"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(secret in text for secret in secrets):
                hits.append(str(path.relative_to(package)))
    return "configured credential values absent from text attachments" if not hits else f"发现凭据泄露: {hits[:5]}"


def add_boundary_files(package, project=PROJECT):
    """只把"入口 + 摘要 + 核验 + 来源"加进 git（逐轮全量证据保留本地）。"""
    wanted = [str(package.relative_to(project) / name) for name in BOUNDARY if (package / name).exists()]
    wanted += [str(path.relative_to(project)) for path in sorted(package.glob("round-*/index.html"))]
    for path in wanted:
        subprocess.run(["git", "-C", str(project), "add", "-f", path], check=False)
    return wanted


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--report", help="reports/<运行目录>；默认取最近一次同名的运行")
    parser.add_argument("--evidence", default=str(PROJECT / "docs/evidence"))
    parser.add_argument("--force", action="store_true", help="覆盖已存在的证据包（默认拒绝）")
    parser.add_argument("--no-add", action="store_true", help="不执行 git add -f")
    args = parser.parse_args(argv)

    experiment = args.experiment.strip()
    if not experiment or len(experiment) > 40 or not all(
            ch.isascii() and (ch.isalnum() or ch in "._-") for ch in experiment):
        print("拒绝：实验名只能是 1..40 个 ASCII 字母/数字/._-")
        return 2
    if experiment in NOT_ACCEPTANCE or experiment.startswith("custom"):
        print(f"拒绝：'{experiment}' 是随手跑的名字，不能建验收包。请用 --experiment 起一个有意义的组名。")
        return 2

    if args.report:
        run_dir = Path(args.report).resolve()
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    else:
        run_dir, summary = find_report(experiment)
        if run_dir is None:
            print(f"找不到 experiment='{experiment}' 的运行；先跑：python -m gameqa run --experiment {experiment} …")
            return 3

    package = Path(args.evidence).resolve() / experiment
    if package.exists():
        existing = sorted(str(p.relative_to(package)) for p in package.rglob("*") if p.is_file())
        pre_frozen = existing == ["source.json"]          # 先冻结来源、后跑用例、再归档 → 正常流程
        if pre_frozen:
            print(f"沿用预冻结的 source.json（{package}）")
        elif not args.force:
            print(f"拒绝：证据包已存在且不是预冻结状态 {package}（验收证据不覆盖；确实要重做加 --force）")
            return 4
        else:
            shutil.rmtree(package)
    manifest = package / "source.json"
    frozen = manifest.read_bytes() if manifest.exists() else None

    cases = load_case_files(run_dir)
    if not cases:
        print(f"拒绝：{run_dir} 里没有 case.json，不能作为验收证据")
        return 5

    package.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_dir, package, dirs_exist_ok=True)
    if frozen:                                            # 预冻结的清单要保住，不能被运行产物挤掉
        manifest.write_bytes(frozen)
    verification = summarize_run(experiment, summary, cases)
    first_started = min((case.get("started") or 0) for case in cases) or None
    match, files, before = source_checks(package, first_started)
    verification.update(source_hashes_match=match, source_files=files,
                        source_captured_before_first_case=before,
                        credential_scan=credential_scan(package))
    (package / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    added = [] if args.no_add else add_boundary_files(package)
    print(f"证据包：{package}")
    print(f"  轮数 {verification['rounds']}｜执行ID {verification['execution_ids']}"
          f"｜观察 {verification['counts']['observations']}｜全通过 {verification['all_passed']}"
          f"｜阶段全通过 {verification['phases_all_passed']}｜恢复全通过 {verification['all_restored']}"
          f"｜不稳定 {verification['unstable_cases']}｜重试观察 {verification['retried_observations']}")
    print(f"  来源清单：{'一致' if match else ('缺失' if match is None else '与冻结不一致！')}"
          f"（{files} 个文件；冻结早于首例：{before}）")
    print(f"  git add -f：{len(added)} 个边界文件{'（已跳过）' if args.no_add else ''}")
    print(f"  ⚠ 仍需人工/AI 独立复核：{', '.join(verification['review_required'])}")
    print(f"  验收清单可引用：见[{experiment}](evidence/{experiment}/index.html)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
