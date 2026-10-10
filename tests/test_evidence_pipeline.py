"""验收流水线的两个脚本：冻结来源（freeze_source）与归档证据（archive_evidence）。

这里只用临时目录里的合成运行记录，不碰真机、不写 docs/evidence。
"""
import importlib.util
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, PROJECT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


freeze = load("freeze_source", "scripts/freeze_source.py")
archive = load("archive_evidence", "scripts/archive_evidence.py")


def mini_project(root):
    (root / "src").mkdir(parents=True)
    (root / "cases").mkdir()
    (root / "src/a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "cases/t.py").write_text("x = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("name = 'm'\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/ignored.md").write_text("不在冻结范围\n", encoding="utf-8")
    return root


def test_freeze_records_scope_hashes_and_check_detects_changes(tmp_path):
    project = mini_project(tmp_path / "proj")
    manifest_path = tmp_path / "source.json"
    manifest = freeze.write_manifest(manifest_path, project)
    assert set(manifest) == {"captured_utc", "formal_execution_project", "scope", "files"}
    assert set(manifest["files"]) == {"src/a.py", "cases/t.py", "pyproject.toml"}   # docs/ 不在范围
    assert len(manifest["files"]["src/a.py"]) == 64                                # sha256
    assert freeze.compare(manifest_path, project) == ([], [], [])                  # 没变
    (project / "src/a.py").write_text("print(2)\n", encoding="utf-8")
    (project / "src/b.py").write_text("new\n", encoding="utf-8")
    changed, added, removed = freeze.compare(manifest_path, project)
    assert changed == ["src/a.py"] and added == ["src/b.py"] and removed == []


def fake_run(root, experiment="items-ui-batch3", rounds=2):
    run = root / "reports" / "20261010T111334.109876Z"
    (run / "round-01").mkdir(parents=True)
    (run / "round-02").mkdir(parents=True)
    summary = {"experiment": experiment, "rounds": rounds, "all_passed": True}
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run / "index.html").write_text("report", encoding="utf-8")
    for number in (1, 2):
        case_dir = run / f"round-0{number}" / "ST-SHOP-API-001"
        case_dir.mkdir()
        case = {
            "id": "ST-SHOP-API-001", "outcome": "passed", "unstable": number == 2,
            "phases": {"setup": "passed", "call": "passed", "teardown": "passed"},
            "started": 1000 + number,
            "steps": [{"title": "买两个", "outcome": "passed", "expected": 60, "attempts": [{"number": 1}]},
                      {"title": "到位", "outcome": "passed", "attempts": [{"number": 1}, {"number": 2}]}],
            "diagnostics": {"restoration": {"restored": True, "location_adjusted": number == 2,
                                            "restored_fields": ["money", "bag"]},
                            "ui_timing": {"screenshots": 3}},
        }
        (case_dir / "case.json").write_text(json.dumps(case), encoding="utf-8")
        (run / f"round-0{number}" / "index.html").write_text("round", encoding="utf-8")
    return run


def test_archive_builds_package_and_keeps_pre_frozen_manifest(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    run = fake_run(root)
    evidence = root / "docs/evidence"
    pre_frozen = evidence / "items-ui-batch3" / "source.json"     # 先冻结、后跑、再归档
    pre_frozen.parent.mkdir(parents=True)
    pre_frozen.write_text(json.dumps({"captured_utc": "2026-10-10T00:00:00+00:00",
                                      "formal_execution_project": str(root),
                                      "scope": "s", "files": {}}), encoding="utf-8")

    code = archive.main(["--experiment", "items-ui-batch3", "--report", str(run),
                         "--evidence", str(evidence), "--no-add"])
    assert code == 0
    package = evidence / "items-ui-batch3"
    assert pre_frozen.exists()                                     # 预冻结的清单没被挤掉
    assert (package / "index.html").exists() and (package / "round-02/index.html").exists()
    report = json.loads((package / "verification.json").read_text(encoding="utf-8"))
    assert report["experiment"] == "items-ui-batch3" and report["rounds"] == 2
    assert report["execution_ids"] == ["ST-SHOP-API-001"]
    assert report["counts"] == {"cases": 2, "observations": 4, "assertions": 2, "screenshots": 6, "restores": 2}
    assert report["all_passed"] is True and report["phases_all_passed"] is True
    assert report["unstable_cases"] == ["ST-SHOP-API-001"]
    assert report["retried_observations"] == 2                     # 两轮各有一条观察重试过
    assert report["all_restored"] is True and report["permitted_location_adjustments"] == 1
    assert report["per_round"][0] == {"round": 1, "ids": ["ST-SHOP-API-001"],
                                      "all_passed": True, "all_restored": True}
    assert report["independent_review"]["performed"] is False      # 脚本不许代填独立复核
    assert "independent_review" in report["review_required"]
    assert report["source_hashes_match"] is True                   # 空清单 → 与当前一致


def test_archive_refuses_throwaway_or_unsafe_names(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    fake_run(root, experiment="custom")
    evidence = root / "docs/evidence"
    for name, expected in (("custom", 2), ("baseline", 2), ("中文名", 2), ("", 2)):
        assert archive.main(["--experiment", name, "--evidence", str(evidence), "--no-add"]) == expected
    assert not evidence.exists()


def test_archive_refuses_missing_run_and_existing_package(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    evidence = root / "docs/evidence"
    assert archive.main(["--experiment", "no-such-group", "--evidence", str(evidence), "--no-add"]) == 3
    run = fake_run(root, "grp-1")
    (evidence / "grp-1").mkdir(parents=True)
    (evidence / "grp-1" / "index.html").write_text("旧的", encoding="utf-8")
    assert archive.main(["--experiment", "grp-1", "--report", str(run),
                         "--evidence", str(evidence), "--no-add"]) == 4
    assert (evidence / "grp-1" / "index.html").read_text(encoding="utf-8") == "旧的"   # 没被覆盖
