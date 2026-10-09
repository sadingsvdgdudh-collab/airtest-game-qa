#!/usr/bin/env python3
"""生成 docs/用例清单.md 里由代码决定的表格：编号 ↔ 中文名 ↔ py 文件 ↔ 最近运行。

    python scripts/case_table.py           # 重写生成段
    python scripts/case_table.py --check   # 与文件不一致则返回 1（可放进自检）
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/用例清单.md"
BEGIN, END = "<!-- generated:begin -->", "<!-- generated:end -->"


def case_markers(path):
    """按 AST 取 pytest.mark.case(...) 的 kwargs，兼容单引号与 pytest.param(marks=...) 写法。"""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "case"
                and isinstance(func.value, ast.Attribute) and func.value.attr == "mark"):
            continue
        meta = {kw.arg: kw.value.value for kw in node.keywords
                if kw.arg and isinstance(kw.value, ast.Constant)}
        if "id" in meta:
            found.append(meta)
    return found


def rows():
    table = []
    for path in sorted((ROOT / "cases").glob("test_*.py")):
        for meta in case_markers(path):
            table.append({"id": meta["id"], "title": meta.get("title", ""), "file": path.name})
    return sorted(table, key=lambda row: row["id"])


def render():
    table = rows()
    missing = sum(1 for row in table if not row["title"])
    lines = [BEGIN, "| 用例编号 | 中文名 | py 文件 |", "|---|---|---|"]
    for row in table:
        lines.append(f"| `{row['id']}` | {row['title'] or '（待补）'} | `{row['file']}` |")
    lines += ["", f"共 **{len(table)}** 条；中文名待补 **{missing}** 条"
                  "（在对应用例的 `@pytest.mark.case(..., title=…)` 里补）。", END]
    return "\n".join(lines)


def main():
    if not DOC.exists():
        sys.exit(f"缺少 {DOC}")
    text = DOC.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        sys.exit(f"{DOC} 里缺少 {BEGIN} / {END} 标记")
    head, rest = text.split(BEGIN, 1)
    updated = head + render() + rest.split(END, 1)[1]
    if "--check" in sys.argv:
        if updated != text:
            sys.exit(f"{DOC.name} 的生成段已过期，跑 python scripts/case_table.py 重写")
        print(f"{DOC.name} 的生成段是最新的")
        return
    DOC.write_text(updated, encoding="utf-8")
    print(f"已重写 {DOC.relative_to(ROOT)} 的生成段")


if __name__ == "__main__":
    main()
