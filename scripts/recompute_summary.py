#!/usr/bin/env python3
"""按当前口径重算历史 summary.json（一次性数据修复）。

背景：早期 `first_try_passed` / `infra_retry_count` 只认“整条用例重跑”，
漏掉了用例内的观察重试（unstable），于是会出现
「一次通过 1/1、重试才过 0」却 `unstable=true` 的自相矛盾。

本脚本用每轮的 `report.json` 重新跑一遍 `summarize()`，保留原有的
experiment / exit_codes 等元信息，只覆盖统计字段。改前自动备份。

用法：
    python scripts/recompute_summary.py --dry-run
    python scripts/recompute_summary.py
"""
import argparse
import json
from pathlib import Path
import tarfile
import time

from gameqa.__main__ import summarize


def load_rounds(folder):
    rounds = []
    for path in sorted(folder.glob("round-*/report.json"), key=lambda p: p.name):
        if "retry" in path.parent.name:
            continue
        try:
            rounds.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return []
    return rounds


def main():
    parser = argparse.ArgumentParser(description="重算历史 summary.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()

    changed, plan = 0, []
    for summary_path in sorted(args.project.glob("reports/*/summary.json")):
        try:
            old = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rounds = load_rounds(summary_path.parent)
        if not rounds:
            continue
        fresh = summarize(rounds)
        fresh["experiment"] = old.get("experiment", "")
        fresh["exit_codes"] = old.get("exit_codes", [])
        # 只修"数字自相矛盾"的运行：有 unstable 观测却被算成一次通过。
        # 老报告缺字段（None）不在本次范围内，避免一次性改写全部历史。
        contradictory = any(obs.get("outcome") == "passed" and obs.get("unstable")
                            and not obs.get("infra_retry")
                            for case in old.get("cases", []) for obs in case.get("observations", []))
        if contradictory and old.get("first_try_passed") != fresh.get("first_try_passed"):
            plan.append((summary_path, old, fresh))

    print(f"需要重算的运行：{len(plan)}")
    for path, old, fresh in plan[:10]:
        print(f"  {path.parent.name} | 一次通过 {old.get('first_try_passed')}→{fresh.get('first_try_passed')} "
              f"| 重试 {old.get('infra_retry_count')}→{fresh.get('infra_retry_count')} "
              f"| 全通过 {old.get('all_passed')}→{fresh.get('all_passed')}")
    if args.dry_run or not plan:
        return 0

    backup = args.project / "reports" / f"summary-backup-{time.strftime('%Y%m%dT%H%M%S')}.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        for path, _, _ in plan:
            archive.add(path, arcname=str(path.relative_to(args.project)))
    print(f"备份：{backup}")

    for path, _, fresh in plan:
        path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8")
        changed += 1
    print(f"已重写 {changed} 份 summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
