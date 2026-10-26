"""设计编号 ↔ 执行用例的别名门禁：文档说"已实现"，代码里就必须有据。

背景：`docs/功能用例目录.md` 里一条设计标了 A/U，但框架里没有同名 pytest 用例时，
证据其实来自另一条用例（共用执行 ID）。这种"别名"如果只写在文档备注里，就是文档自证——
面板也只能照抄，任何一条"已实现"都能免检。

所以别名必须在用例侧用 `pytest.mark.case(covers=[...])` 显式声明：
运行期由 gameqa.pytest_plugin 校验格式并写进证据 metadata，读期由这条门禁校验闭环。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qa_panel", ROOT / "panel" / "panel.py")
panel = importlib.util.module_from_spec(SPEC)
sys.modules["qa_panel"] = panel
SPEC.loader.exec_module(panel)

IMPLEMENTED_MARKERS = ("A", "U")


def declarations():
    return panel.case_declarations()


def declared_ids():
    return {row["id"] for row in declarations()}


def covers_map():
    found = {}
    for row in declarations():
        for cover in row["covers"]:
            found.setdefault(cover, []).append(row["id"])
    return found


def alias_designs():
    """文档标 A/U、但框架里没有独立用例的设计编号（需要 covers 声明兜住的那批）。"""
    docs = panel.documented_cases()
    ids = declared_ids()
    return {case_id: meta for case_id, meta in docs.items()
            if meta["marker"] in IMPLEMENTED_MARKERS
            and case_id not in ids
            and panel.base_of(case_id) not in {panel.base_of(i) for i in ids}}


def test_every_alias_design_has_a_covers_declaration():
    missing = sorted(set(alias_designs()) - set(covers_map()))
    assert not missing, (
        "这些设计在文档里标了已实现，但 cases/ 里没有任何 covers= 声明，等于文档自证：\n"
        + "\n".join(f"  {case_id}" for case_id in missing)
        + "\n处理方式：在真正执行它的用例 marker 上加 covers=[...]，或把文档标记改回未实现。")


def test_covers_targets_are_documented_designs():
    docs = panel.documented_cases()
    phantom = sorted(cover for cover in covers_map() if cover not in docs)
    assert not phantom, f"covers= 指向文档里没有的编号（拼写错误或编号已删）：{phantom}"


def test_covers_targets_are_marked_implemented():
    docs = panel.documented_cases()
    wrong = sorted(cover for cover in covers_map()
                   if docs.get(cover, {}).get("marker") not in IMPLEMENTED_MARKERS)
    assert not wrong, (
        f"covers= 只能指向文档标 A/U 的设计；以下目标标记不是已实现："
        f"{[(cover, docs.get(cover, {}).get('marker')) for cover in wrong]}")


def test_covers_does_not_shadow_an_existing_case():
    shadowed = sorted(set(covers_map()) & declared_ids())
    assert not shadowed, (
        f"这些编号已经有自己的 pytest 用例，不该再被别的用例 covers 声明：{shadowed}")


def test_covers_never_includes_its_own_id():
    for row in declarations():
        assert row["id"] not in row["covers"], f"{row['path']}: {row['id']} 不能 covers 自己"


def test_case_ids_are_unique_across_files():
    seen = {}
    for row in declarations():
        assert row["id"] not in seen, f"重复用例 ID：{row['id']}（{seen[row['id']]} 与 {row['path']}）"
        seen[row["id"]] = row["path"]


def test_alias_evidence_is_traceable_back_to_a_real_case():
    """面板报的别名必须能落到一个真实存在的执行用例上，而不是只落在一句备注上。"""
    ids = declared_ids()
    for case_id in alias_designs():
        owners = covers_map().get(case_id, [])
        assert owners, case_id
        for owner in owners:
            assert owner in ids, f"{case_id} 的 covers 声明来自不存在的用例 {owner}"
