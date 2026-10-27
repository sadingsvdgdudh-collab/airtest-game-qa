#!/usr/bin/env python3
"""把历史 Allure 结果里的 historyId 归一（一次性数据修复）。

背景：早期接入时把 `experiment` 当成 Allure parameter，它参与 historyId 计算，
于是同一条用例换个实验名就分成两条。代码已改成 label（新结果不会再裂），
但**旧结果的 historyId 是写死在 JSON 里的**，必须回填一次，总报告才能并成一条。

规则：historyId = md5(fullName)。同一条测试跨运行恒定，与参数无关。

用法：
    python scripts/normalize_allure_history.py --dry-run   # 只看会改多少
    python scripts/normalize_allure_history.py             # 真改（先备份）
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time

PROJECT = Path(__file__).resolve().parents[1]
RESULTS = "reports/*/round-*/allure-results/*-result.json"


def canonical(full_name):
    return hashlib.md5((full_name or "").encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="归一历史 Allure 结果的 historyId")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--project", type=Path, default=PROJECT)
    args = parser.parse_args()

    files = sorted(args.project.glob(RESULTS))
    changed, moved_labels = [], 0
    plan = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        full_name = data.get("fullName") or ""
        if not full_name:
            continue
        target = canonical(full_name)
        parameters = data.get("parameters") or []
        legacy = [p for p in parameters if p.get("name") == "experiment"]
        if data.get("historyId") == target and not legacy:
            continue
        plan.append((path, data, target, legacy))

    print(f"扫描 {len(files)} 个结果文件，需要修正 {len(plan)} 个")
    if args.dry_run:
        for path, data, target, legacy in plan[:10]:
            print(f"  {path.parent.parent.parent.name} | {data.get('name', '')[:40]} | "
                  f"{data.get('historyId', '')[:8]} → {target[:8]}"
                  f"{' | experiment=' + str(legacy[0].get('value')) if legacy else ''}")
        return 0

    if plan:
        backup = args.project / "reports" / f"allure-history-backup-{time.strftime('%Y%m%dT%H%M%S')}.tar.gz"
        with tarfile.open(backup, "w:gz") as archive:
            for path, _, _, _ in plan:
                archive.add(path, arcname=str(path.relative_to(args.project)))
        print(f"备份：{backup}")

    for path, data, target, legacy in plan:
        data["historyId"] = target
        if legacy:
            labels = data.setdefault("labels", [])
            for item in legacy:
                labels.append({"name": "experiment", "value": str(item.get("value"))})
            data["parameters"] = [p for p in data.get("parameters", []) if p.get("name") != "experiment"]
            moved_labels += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        changed.append(path)

    print(f"已改写 {len(changed)} 个文件；其中 {moved_labels} 个把 experiment 从 parameter 挪到 label")
    print("接着重建总报告：python -m gameqa allure（先删 reports/_allure/.merged.json 强制重建）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
