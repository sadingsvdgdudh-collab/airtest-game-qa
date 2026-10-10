"""证据链接检查挂进自检：文档引用的证据必须存在且已入库（克隆后不断链）。"""
import importlib.util
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_evidence_links", PROJECT / "scripts/check_evidence_links.py")
checker = importlib.util.module_from_spec(SPEC)
sys.modules["check_evidence_links"] = checker
SPEC.loader.exec_module(checker)


def test_every_documented_evidence_reference_is_on_disk_and_tracked():
    problems = checker.check(PROJECT)
    assert problems == [], "克隆后会断链：\n" + "\n".join(
        f"{path} <- {who} ({why})" for path, who, why in problems)


def test_checker_flags_missing_file_and_directory_without_entry(tmp_path):
    docs = tmp_path / "docs"
    (docs / "evidence" / "pkg").mkdir(parents=True)
    (docs / "a.md").write_text("见 [证据](evidence/nope/index.html)\n", encoding="utf-8")
    assert any("磁盘上不存在" in why for _, _, why in checker.check(tmp_path))
    (docs / "b.md").write_text("见 [证据](evidence/pkg)\n", encoding="utf-8")
    assert any("目录没有 index.html" in why for _, _, why in checker.check(tmp_path))
    (docs / "evidence" / "pkg" / "index.html").write_text("ok\n", encoding="utf-8")
    problems = checker.check(tmp_path)
    assert not [p for p in problems if p[0].endswith("pkg")]      # 有入口页就放行


def test_references_ignore_fenced_commands_and_external_links(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "c.md").write_text(
        "```bash\npython x.py --source-dir docs/evidence/whatever/src\n```\n"
        "[外链](https://example.com/evidence/x)\n", encoding="utf-8")
    assert checker.references(tmp_path) == {}
