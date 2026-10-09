"""用例卫生门禁：静态检查用例层有没有绕过业务封装层。

规则全部来自实测踩过的坑（见 docs/实施记录.md 的"业务封装层试点"与"shop 域补齐"两节）。
豁免粒度是（文件名, 用例 ID）对，只允许减少：每迁完一个业务域，就从名单里删掉对应条目。

    python -m gameqa.hygiene                              # 列出名单外违规与全部欠账
    python -m gameqa.hygiene --report docs/原语需求.md    # 生成欠账清单
"""

import argparse
import ast
import builtins
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "cases"
DESIGN_DOCS = (ROOT / "docs/功能用例目录.md", ROOT / "docs/Shardy验证结果.md")

# 受控词表：game 来自 config.example.toml 的 games 段；kind 来自 gameqa run --kind 的 choices；
# module 来自 2026-10-08 实测 39 条用例的取值——Stendhal 五个（shop/quest/combat/inventory/growth）
# 加 Shardy 两个（core/known_defects）。新增业务域时必须同步这一行，否则门禁会拦住它。
GAMES = {"stendhal", "shardy"}
KINDS = {"api", "ui"}
MODULES = {"shop", "quest", "combat", "inventory", "growth", "minigame", "craft", "pet", "core", "known_defects"}

DESIGN_ID = re.compile(r"S[TH]-[A-Z]+-[A-Z]+-\d+")
BASE_ID = re.compile(r"^(S[TH]-[A-Z]+-[A-Z]+-\d+)")

# 规则 9（取消/拒绝场景不得用 buy_and_confirm）故意不在这里：靠函数命名在调用点暴露。
# 机械近似检查（"buy 不得与 confirm/stock 同现"）会误伤"买完再查商品列表"这类合法写法，
# 而一条会误伤的规则比没有规则更糟。见 src/gameqa/shop.py 里 buy_and_confirm 的说明。

# 每条违规对应的补齐办法，用于自动生成 docs/原语需求.md。
FIX = {
    "词表外game/module/kind": "改用受控取值；新业务域需同时更新 GAMES/KINDS/MODULES",
    "id不在设计资料": "在设计文档里登记该编号，或改用已有的基础编号",
    "import名字不存在": "改从该名字实际所在的模块导入（违规信息里已给出），或修正名字",
    "引用未定义的名字": "补上导入或定义（这类错误只在运行时炸，收集阶段看不见）",
    "字面https": "把 URL 移进 src/gameqa/sources.py，用例只引用常量名",
    "lambda谓词": "在封装层加等待原语（参照 stendhal.await_quantity）",
    "对话匹配外泄": "改用 stendhal.said(messages, npc, snippet)",
    "用例import airtest": "改用独立管理员读服务端状态；界面手段不能做业务断言",
    "界面定位做断言": "改用独立管理员读服务端状态；界面手段不能做业务断言",
    "用例层直调dialogue": "把发言收进业务封装层的对话原子（参照 gameqa/shop.py）",
}

# 编号、词表与 import 类的错误**不可豁免**：它们是"代码就是错的"，不是"还没迁完"的欠账。
# 只有迁移欠账（字面 URL、谓词外泄等）才进豁免名单。
HARD_RULES = {"词表外game/module/kind", "id不在设计资料", "import名字不存在", "引用未定义的名字"}


def base_rule(rule):
    """违规标签可能带动态细节（如 import名字不存在:leave→stendhal.py），取冒号前的规则名。"""
    return rule.split(":", 1)[0]


# （文件名, 用例 ID）：已知欠账，只允许减少。基线用于"只减不增"检查。
# 2026-10-08 清零：43 条用例全部达标，豁免名单为空。
# 往后再有欠账只允许临时登记，且基线跟着下调——不允许长期挂着。
# COMBAT-API-004 两条），其余 11 条在名单里。每迁完一个业务域就删掉对应条目，基线同步下调。
EXEMPT_BASELINE = 0
EXEMPT = set()


def design_ids():
    """设计文档里出现过的编号；宽松口径，允许基础编号继承（ST-X-007 覆盖 -heal/-cap）。"""
    found = set()
    for path in DESIGN_DOCS:
        if path.exists():
            found |= set(DESIGN_ID.findall(path.read_text(encoding="utf-8")))
    return found


def base_of(case_id):
    match = BASE_ID.match(case_id)
    return match.group(1) if match else case_id


def case_calls(tree):
    """按 AST 找 pytest.mark.case(...) 调用，兼容装饰器与 pytest.param(marks=...) 两种写法。"""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "case"
                and isinstance(func.value, ast.Attribute) and func.value.attr == "mark"):
            found.append(node)
    return found


def marker_meta(call):
    meta = {}
    for keyword in call.keywords:
        if keyword.arg and isinstance(keyword.value, ast.Constant):
            meta[keyword.arg] = keyword.value.value
    return meta


def imports_airtest(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "airtest" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "airtest":
            return True
    return False


def has_literal_url(tree):
    """只看字符串常量里的 URL：文件级局部 SOURCE 常量算欠账，注释里的链接不算。"""
    return any(isinstance(node, ast.Constant) and isinstance(node.value, str)
               and "https://" in node.value for node in ast.walk(tree))


PKG = ROOT / "src" / "gameqa"


def module_names(path):
    """模块顶层能取到的名字：定义、赋值、以及再导出的名字。"""
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
    return names


def import_labels(tree):
    """用例文件里 `from gameqa.X import …` 的问题标签。

    原语会在层之间搬迁（`hello`/`leave` 从 shop 上移到 stendhal），写用例的人与 AI 都会按
    旧位置 import；`pytest --collect-only` 能发现，但那已经在跑测试了。这里静态查出来，
    并把"这个名字现在在哪个模块"直接写进标签。
    """
    labels = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("gameqa"):
            module, names = node.module, [alias.name for alias in node.names]
        elif isinstance(node, ast.Import):
            module = None
            names = [alias.name for alias in node.names if alias.name.startswith("gameqa")]
            if not names:
                continue
            for name in names:
                if not (ROOT / "src" / (name.replace(".", "/") + ".py")).exists():
                    labels.append(f"import名字不存在:{name}→该模块不存在")
            continue
        else:
            continue
        target = ROOT / "src" / (module.replace(".", "/") + ".py")
        if not target.exists():
            labels.append(f"import名字不存在:{module}→该模块不存在")
            continue
        available = module_names(target)
        for name in names:
            if name in available:
                continue
            elsewhere = sorted(p.stem + ".py" for p in PKG.glob("*.py")
                               if p != target and name in module_names(p))
            labels.append(f"import名字不存在:{name}→" +
                          ("、".join(elsewhere) if elsewhere else "任何 gameqa 模块里都没有"))
    return labels


def bound_names(node):
    """子树里出现过的**绑定**名字（参数、赋值、导入、循环变量、异常名……）。

    故意放宽：不区分作用域与先后顺序，只要出现过就算。宁可漏报也不误报——
    这条规则要抓的是"这个名字在整个文件里根本不存在"（F821 那一类），
    而这类错误只在运行时炸，收集阶段发现不了。
    """
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            names.add(child.id)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
        elif isinstance(child, ast.arg):
            names.add(child.arg)
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in child.names)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            names.add(child.name)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            names.update(child.names)
    return names


def undefined_names(tree, module_level):
    """返回"引用了但文件里没有"的名字标签（含 `import *` 的文件直接跳过，避免误报）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        local = module_level | bound_names(node) | set(dir(builtins))
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load) and child.id not in local:
                label = f"引用未定义的名字:{child.id}"
                if label not in found:
                    found.append(label)
    return found


def violations():
    """返回 {(文件名, 用例 ID): [违规规则]}。"""
    known = design_ids()
    found = {}
    for path in sorted(CASES.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        file_airtest = imports_airtest(tree)
        file_url = has_literal_url(tree)
        # 模块级名字集合：用于"引用了但文件里没有"这条规则（用例体与顶层函数都查）
        file_undefined = undefined_names(tree, bound_names(tree))
        file_imports = import_labels(tree)
        for call in case_calls(tree):
            meta = marker_meta(call)
            if "id" not in meta:
                continue
            owner = next((node for node in ast.walk(tree)
                          if isinstance(node, ast.FunctionDef)
                          and any(call is inner for decor in node.decorator_list
                                  for inner in ast.walk(decor))), None)
            body = ast.get_source_segment(text, owner) if owner else text
            bad = []
            bad.extend(file_imports)
            bad.extend(file_undefined)
            if meta.get("game") not in GAMES or meta.get("kind") not in KINDS \
                    or meta.get("module") not in MODULES:
                bad.append("词表外game/module/kind")
            if meta["id"] not in known and base_of(meta["id"]) not in known:
                bad.append("id不在设计资料")
            if file_url:
                bad.append("字面https")
            if "await_state(lambda" in body:
                bad.append("lambda谓词")
            if re.search(r"for \w+ in messages", body):
                bad.append("对话匹配外泄")
            if file_airtest:
                bad.append("用例import airtest")
            if re.search(r"locate_image\(|touch_image\(", body):
                bad.append("界面定位做断言")
            if re.search(r"(?<![\w.])dialogue\(", body):
                bad.append("用例层直调dialogue")
            if bad:
                found[(path.name, meta["id"])] = bad
    return found


def report_rows():
    rows = violations()
    outside = {key: value for key, value in rows.items()
               if key not in EXEMPT or any(base_rule(r) in HARD_RULES for r in value)}
    stale = sorted(key for key in EXEMPT if key not in rows)
    debt = sorted(rows.items())
    return outside, stale, debt


def write_report(path):
    outside, stale, debt = report_rows()
    lines = ["# 原语需求（自动生成）", "",
             "生成：`python -m gameqa.hygiene --report docs/原语需求.md`。**不要手改**。", "",
             f"当前豁免（已知欠账）**{len(EXEMPT)}** 条，基线 **{EXEMPT_BASELINE}** 条（只减不增）；"
             f"名单外违规 **{len(outside)}** 条。", "",
             "## 一、名单外违规（门禁会失败，必须先修）", ""]
    if outside:
        lines += ["| 用例 | 文件 | 违规 | 补齐办法 |", "|---|---|---|---|"]
        for (name, case_id), rules in sorted(outside.items()):
            lines.append(f"| `{case_id}` | `{name}` | {'、'.join(rules)} | "
                         + "；".join(FIX.get(base_rule(r), "") for r in rules) + " |")
    else:
        lines.append("无。")
    lines += ["", "## 二、豁免中的欠账（迁到封装层要补的能力）", ""]
    if debt:
        lines += ["| 用例 | 文件 | 违规 | 补齐办法 |", "|---|---|---|---|"]
        for (name, case_id), rules in debt:
            lines.append(f"| `{case_id}` | `{name}` | {'、'.join(rules)} | "
                         + "；".join(FIX.get(base_rule(r), "") for r in rules) + " |")
    else:
        lines.append("无。")
    if stale:
        lines += ["", "## 三、可以移出豁免名单的条目（已达标）", ""]
        lines += [f"- `{name}` / `{case_id}`" for name, case_id in stale]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(outside), len(EXEMPT), len(stale)


def main():
    parser = argparse.ArgumentParser(description="用例卫生门禁")
    parser.add_argument("--report", help="把欠账清单写到该路径")
    parser.add_argument("--json", action="store_true",
                        help="给机器读的结果（面板等消费者用，不解析人看的文本）")
    args = parser.parse_args()
    if args.report:
        outside, exempt, stale = write_report(args.report)
        print(f"已写 {args.report}：名单外违规 {outside} 条、豁免 {exempt} 条、可移出 {stale} 条")
        return 0
    outside, stale, debt = report_rows()
    if args.json:
        print(json.dumps({
            "exempt": len(EXEMPT), "baseline": EXEMPT_BASELINE, "stale": len(stale),
            "outside": [{"file": name, "id": case_id, "rules": rules}
                        for (name, case_id), rules in sorted(outside.items())],
            "debt": [{"file": name, "id": case_id, "rules": rules} for (name, case_id), rules in debt],
        }, ensure_ascii=False))
        return 1 if outside else 0
    for (name, case_id), rules in sorted(outside.items()):
        print(f"违规 {name}::{case_id}: {'、'.join(rules)}")
    print(f"名单外违规 {len(outside)} 条；豁免 {len(EXEMPT)} 条（基线 {EXEMPT_BASELINE}）；"
          f"欠账条目 {len(debt)} 条；可移出名单 {len(stale)} 条")
    return 1 if outside else 0


if __name__ == "__main__":
    sys.exit(main())
