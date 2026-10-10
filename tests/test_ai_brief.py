"""AI 简报：必须是最新的，且数字是现算的（防"手写摘要过期"重演）。"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_brief", ROOT / "scripts" / "ai_brief.py")
ai_brief = importlib.util.module_from_spec(SPEC)
sys.modules["ai_brief"] = ai_brief
SPEC.loader.exec_module(ai_brief)


def test_brief_is_fresh():
    """与 docs/AI简报.md 不一致 → 跑 --write 重写（时间戳不算差异）。"""
    assert ai_brief.OUT.exists(), "缺少 docs/AI简报.md，跑 python scripts/ai_brief.py --write"
    committed = ai_brief.body(ai_brief.OUT.read_text(encoding="utf-8"))
    assert committed == ai_brief.body(ai_brief.build()), "简报已过期，跑 --write 重写"


def test_numbers_are_measured_not_hardcoded():
    d = ai_brief.measured()
    assert d["collected"] and d["collected"] > 0, "没能测到接入用例数"
    assert d["selfchecks"] and d["selfchecks"] > 0, "没能测到自检项数"
    assert d["markers"] and d["collected"] >= d["markers"]      # 参数化只会让收集数 >= 函数数
    assert d["design_doc"] and d["unimplemented"] is not None


def test_paste_block_is_chat_friendly():
    """粘给聊天 AI 的版本不能留 markdown 表格竖线。"""
    text = ai_brief.render_paste(ai_brief.build())
    assert "|" not in text
    assert "已接入自动化用例" in text and "框架自检" in text


def test_check_mode_passes_on_fresh_file():
    assert ai_brief.main(["--check"]) == 0
