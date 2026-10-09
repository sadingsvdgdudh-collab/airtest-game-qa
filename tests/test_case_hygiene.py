"""用例卫生门禁：名单外零违规、豁免只减不增、名单里不留已达标条目。"""
import ast

from gameqa import hygiene


def test_undefined_name_rule_catches_a_body_reference():
    """用例体里引用了文件没导入的名字：收集阶段看不见（只在运行时 NameError），必须静态报出来。"""
    tree = ast.parse("import pytest\n\n\ndef case():\n    return SOURCE + 'x'\n")
    assert hygiene.undefined_names(tree, hygiene.bound_names(tree)) == ["引用未定义的名字:SOURCE"]


def test_undefined_name_rule_has_no_false_positive():
    tree = ast.parse("import pytest\nfrom gameqa.sources import SOURCE\n\n\n"
                     "CONST = 1\n\n\ndef case(tmp_path, qa):\n"
                     "    rows = [row for row in []]\n"
                     "    return SOURCE, CONST, len(rows), str(tmp_path), qa, pytest\n")
    assert hygiene.undefined_names(tree, hygiene.bound_names(tree)) == []


def test_import_rule_names_the_module_that_has_the_name():
    """原语会在层之间搬迁，这条规则要能指出名字现在在哪个模块，并且不管跨用例文件引用。"""
    labels = hygiene.import_labels(ast.parse(
        "from gameqa.shop import leave\n"
        "from gameqa.stendhal import quanity\n"
        "from cases.test_stendhal_combat import equip\n"))
    assert "import名字不存在:leave→stendhal.py" in labels
    assert any("quanity" in label and "都没有" in label for label in labels)
    assert not any("equip" in label for label in labels), "跨用例文件引用不归这条规则管"
    assert hygiene.base_rule("import名字不存在:leave→stendhal.py") == "import名字不存在"


def test_no_unexempted_violations():
    outside, _, _ = hygiene.report_rows()
    detail = "；".join(f"{name}::{case_id} → {'、'.join(rules)}"
                      for (name, case_id), rules in sorted(outside.items()))
    assert outside == {}, f"用例卫生门禁未通过（{len(outside)} 条）：{detail}"


def test_exemption_only_shrinks():
    assert len(hygiene.EXEMPT) <= hygiene.EXEMPT_BASELINE, (
        f"豁免条目从基线 {hygiene.EXEMPT_BASELINE} 涨到 {len(hygiene.EXEMPT)}："
        "豁免只允许减少；新增欠账请先修用例，不要加名单")


def test_exemption_has_no_paid_entries():
    _, stale, _ = hygiene.report_rows()
    assert stale == [], ("这些条目已经达标，请从 hygiene.EXEMPT 删除并下调 EXEMPT_BASELINE："
                         + "、".join(f"{name}::{case_id}" for name, case_id in stale))
