#!/usr/bin/env python3
"""重写 docs/能力清单.md 里由代码决定的那段，避免能力清单与框架漂移。

    python scripts/capabilities.py           # 重写生成段
    python scripts/capabilities.py --check   # 与文件不一致则返回 1（可放进自检）
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/能力清单.md"
BEGIN, END = "<!-- generated:begin -->", "<!-- generated:end -->"


def signature(node):
    names = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    names += [a.arg for a in node.args.kwonlyargs]
    if node.args.vararg:
        names.append("*" + node.args.vararg.arg)
    if node.args.kwarg:
        names.append("**" + node.args.kwarg.arg)
    return "(" + ", ".join(names) + ")"


def primitives():
    lines = ["### A. 原语（从 `src/gameqa/*.py` 抽取；门禁与 pytest 插件除外）", ""]
    for path in sorted((ROOT / "src/gameqa").glob("*.py")):
        # 框架自身的东西不是写用例能用的词汇：门禁（hygiene）与 pytest 插件只是机制，
        # 列进"可用原语"会让读这份清单的生成者困惑。其余模块照列——用例确实会用
        # bridge/config（Shardy 第二条玩家）与 Evidence（qa.check）这些。
        if path.stem.startswith("__") or path.name in {"hygiene.py", "pytest_plugin.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [f"`{node.name}.{child.name}{signature(child)}`" for child in node.body
                           if isinstance(child, ast.FunctionDef) and not child.name.startswith("_")]
                if methods:
                    lines.append(f"- **{node.name}**（{path.name}）：" + "、".join(methods))
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith(("_", "pytest_")):
                lines.append(f"- `{node.name}{signature(node)}`（{path.name}）")
    return lines + [""]


def asset_lines():
    lines = ["### B. 模板与校准资产（扫 `assets/`）", ""]
    for folder in sorted(path for path in (ROOT / "assets").rglob("*") if path.is_dir()):
        pngs, manifests = sorted(folder.glob("*.png")), sorted(folder.glob("*.json"))
        if not pngs and not manifests:
            continue
        row = f"- `{folder.relative_to(ROOT)}/`：PNG {len(pngs)} 个"
        lines.append(row + (f"，清单 {len(manifests)} 个" if manifests else ""))
        for manifest in manifests:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            sources = sorted({item.get("source", "") for item in data.values() if isinstance(item, dict)})
            sources = [item for item in sources if item]
            lines.append(f"  - `{manifest.name}`：{len(data)} 条"
                         + (f"，来源 {', '.join(sources)}" if sources else ""))
    return lines + [""]


def case_markers(path):
    """按 AST 取 pytest.mark.case(id=...) 的 id，兼容单引号与 pytest.param(marks=...) 写法。"""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "case"
                and isinstance(func.value, ast.Attribute) and func.value.attr == "mark"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                found.append(keyword.value.value)
    return found


def case_lines():
    lines = ["### C. 已实现用例（静态解析 `cases/*.py` 的 `@pytest.mark.case`）", "",
             "> `pytest cases --collect-only` 是权威计数与筛选入口。本仓库每个参数化子例都带独立 marker",
             "> （子例后缀如 `-heal` / `-cap` / `-zero`），所以 marker 数与执行项数一致；",
             "> 若以后某条用例改成一个 marker 带多个参数，执行项数会多于此处。", ""]
    markers = distinct = 0
    for path in sorted((ROOT / "cases").glob("test_*.py")):
        ids = [item for item in dict.fromkeys(case_markers(path)) if item.startswith(("ST-", "SH-"))]
        markers += len(case_markers(path))
        distinct += len(ids)
        lines.append(f"- `{path.name}`（marker {len(case_markers(path))} 个）：" + "、".join(ids))
    lines += ["", f"marker 合计 **{markers}** 个，去重后用例 ID **{distinct}** 个。"]
    return lines


def render():
    body = "\n".join(primitives() + asset_lines() + case_lines())
    return f"{BEGIN}\n{body}\n{END}"


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
            sys.exit(f"{DOC.name} 的生成段已过期，跑 python scripts/capabilities.py 重写")
        print(f"{DOC.name} 的生成段是最新的")
        return
    DOC.write_text(updated, encoding="utf-8")
    print(f"已重写 {DOC.relative_to(ROOT)} 的生成段")


if __name__ == "__main__":
    main()
