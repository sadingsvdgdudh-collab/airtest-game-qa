"""能力清单 JSON 必须与代码一致，且符合 requirements-testing 技能读取的契约。

清单是技能侧核对"自动化建议"的依据（编号存在、文件摘要、函数符号、通道一致）。
它由 scripts/capabilities_manifest.py 生成——手工抄写会漂移，所以这里挂进自检：
清单过期、字段不合契约、或新模块静默落进默认通道，都在本文件拦下。
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "capabilities_manifest", PROJECT / "scripts/capabilities_manifest.py")
generator = importlib.util.module_from_spec(SPEC)
sys.modules["capabilities_manifest"] = generator
SPEC.loader.exec_module(generator)


def test_manifest_is_fresh_and_matches_code():
    """代码改了没重生成 → 这里失败（不能靠"上次生成时是对的"）。"""
    current = generator.OUT.read_text(encoding="utf-8")
    rebuilt = generator.dumps(generator.build(json.loads(current)))
    assert rebuilt == current, (
        "docs/框架能力清单.json 已过期，跑 python scripts/capabilities_manifest.py 重写")


def test_manifest_satisfies_skill_contract():
    data = json.loads(generator.OUT.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.1"
    assert Path(data["framework_root"]).is_absolute()
    assert data["reviewer"] and data["checked_at"]
    capabilities = data["capabilities"]
    assert capabilities, "能力清单为空"
    ids = [cap["id"] for cap in capabilities]
    assert len(ids) == len(set(ids)), "能力编号重复"
    for cap in capabilities:
        assert cap["kind"] in {"function", "asset"}, cap["id"]
        assert cap["channel"] in {"api", "ui", "both"}, cap["id"]
        assert cap["notes"], cap["id"]
        path = PROJECT / cap["file"]
        assert path.is_file(), f"{cap['id']} 引用的文件不存在：{cap['file']}"
        assert cap["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest(), (
            f"{cap['id']} 的文件摘要与磁盘不一致")
        if cap["kind"] == "function":
            assert cap.get("symbol"), f"{cap['id']} 缺 symbol"


def test_no_module_silently_falls_into_default_channel():
    """新模块必须显式登记通道：静默按 api 处理会把 UI 能力说成 api。"""
    scanned = {path.name for path in (PROJECT / "src/gameqa").glob("*.py")
               if not path.stem.startswith("__") and path.name not in generator.EXCLUDED_MODULES}
    undeclared = sorted(scanned - set(generator.CHANNEL_BY_MODULE))
    assert not undeclared, f"这些模块未在 CHANNEL_BY_MODULE 里声明通道：{undeclared}"
