#!/usr/bin/env python3
"""生成 docs/框架能力清单.json —— 供 requirements-testing 技能机械核对"自动化建议"。

为什么要有这个文件：技能侧已经能按「框架能力清单.json」核对用例引用的能力是否真实
（编号存在、文件摘要一致、函数确实定义在该文件里）。但那份清单此前靠人工/AI 从
docs/能力清单.md 转录，两个表示之间会漂移。本脚本直接从代码生成同一份结构化清单，
把"转录"这一步去掉。

    python scripts/capabilities_manifest.py           # 写出/更新 docs/框架能力清单.json
    python scripts/capabilities_manifest.py --check   # 与文件不一致则返回 1（可放进自检）

清单契约（技能侧 modules/testcase-builder/scripts/automation_evidence.py）：
    schema_version  "1.1"（1.1 起每条能力必须带 channel）
    framework_root  本仓库路径（技能侧可用环境变量 QA_FRAMEWORK_ROOT 覆盖）；
                    等值检查（--check / 自检）**忽略它的位置差异**，重生成时刷新为本机路径
    reviewer        生成者标识（本脚本为 auto:…）
    checked_at      ISO 时间；能力集合未变化时保留原值，因此 --check 是等值比较
    capabilities[]  {id, kind, channel, file, sha256, symbol?, notes}

channel 取值：
    api   经协议桥驱动游戏（stendhal/shardy/shop/quest/pet/…）
    ui    Airtest 驱动真实客户端（stendhal_ui/shardy_ui/device）与全部视觉资产
    both  两条通道都会用到的中立能力（evidence/config/sources/run_lock/accounts/recovery）

只做静态抽取：不导入、不执行框架代码。
"""
import ast
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/框架能力清单.json"
SCHEMA = "1.1"
REVIEWER = "auto:scripts/capabilities_manifest.py"

# 框架机制不是"写用例能用的词汇"，与 docs/能力清单.md 的口径保持一致
EXCLUDED_MODULES = {"hygiene.py", "pytest_plugin.py"}

CHANNEL_BY_MODULE = {
    "stendhal_ui.py": "ui",
    "shardy_ui.py": "ui",
    "device.py": "ui",
    "evidence.py": "both",
    "config.py": "both",
    "sources.py": "both",
    "run_lock.py": "both",
    "accounts.py": "both",
    "recovery.py": "both",
    # 经协议桥驱动游戏：显式登记，避免以后新增模块静默落进默认通道
    "stendhal.py": "api",
    "shardy.py": "api",
    "bridge.py": "api",
    "shop.py": "api",
    "quest.py": "api",
    "pet.py": "api",
    "craft.py": "api",
    "minigame.py": "api",
}
DEFAULT_CHANNEL = "api"


def signature(node):
    names = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    names += [a.arg for a in node.args.kwonlyargs]
    if node.args.vararg:
        names.append("*" + node.args.vararg.arg)
    if node.args.kwarg:
        names.append("**" + node.args.kwarg.arg)
    return "(" + ", ".join(names) + ")"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_entries():
    entries = []
    modules = sorted((ROOT / "src/gameqa").glob("*.py"))
    for path in modules:
        if path.stem.startswith("__") or path.name in EXCLUDED_MODULES:
            continue
        channel = CHANNEL_BY_MODULE.get(path.name, DEFAULT_CHANNEL)
        relative = path.relative_to(ROOT).as_posix()
        sha = digest(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, ast.FunctionDef) and not child.name.startswith("_"):
                        symbol = f"{node.name}.{child.name}"
                        entries.append({
                            "id": f"{path.stem}.{symbol}",
                            "kind": "function",
                            "channel": channel,
                            "file": relative,
                            "sha256": sha,
                            "symbol": symbol,
                            "notes": f"自动生成；签名 {signature(child)}",
                        })
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith(("_", "pytest_")):
                entries.append({
                    "id": f"{path.stem}.{node.name}",
                    "kind": "function",
                    "channel": channel,
                    "file": relative,
                    "sha256": sha,
                    "symbol": node.name,
                    "notes": f"自动生成；签名 {signature(node)}",
                })
    return entries


def asset_entries():
    """视觉资产按 PNG 计（校准 JSON 通过其 PNG 被引用，不单独登记）。"""
    entries = []
    for path in sorted((ROOT / "assets").rglob("*.png")):
        relative = path.relative_to(ROOT).as_posix()
        entries.append({
            "id": f"asset:{relative}",
            "kind": "asset",
            "channel": "ui",
            "file": relative,
            "sha256": digest(path),
            "notes": "自动生成；Airtest 视觉模板（UI 通道）",
        })
    return entries


def build(previous: dict | None = None) -> dict:
    capabilities = function_entries() + asset_entries()
    capabilities.sort(key=lambda item: (item["kind"], item["id"]))
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if previous and previous.get("capabilities") == capabilities:
        # 能力集合没变就不刷新时间戳：让 checked_at 表达"证据最后变化的时刻"，
        # 也让 --check 退化成一次等值比较。
        checked_at = previous.get("checked_at", checked_at)
    return {
        "schema_version": SCHEMA,
        # 保留原值：framework_root 是本机绝对路径，位置变了不该让 --check 判"过期"
        # （重生成时会刷新成本机路径，见 main()）。
        "framework_root": previous.get("framework_root", str(ROOT)),
        "reviewer": REVIEWER,
        "checked_at": checked_at,
        "counts": {
            "function": sum(1 for c in capabilities if c["kind"] == "function"),
            "asset": sum(1 for c in capabilities if c["kind"] == "asset"),
        },
        "capabilities": capabilities,
    }


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def main():
    previous = None
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"{OUT.relative_to(ROOT)} 不是合法 JSON：{exc}")

    text = dumps(build(previous))
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"{OUT.name} 已过期，跑 python scripts/capabilities_manifest.py 重写")
        print(f"{OUT.name} 是最新的")
        return
    text = dumps({**json.loads(text), "framework_root": str(ROOT)})   # 写出时刷新为本机路径
    OUT.write_text(text, encoding="utf-8")
    data = json.loads(text)
    print(f"已写出 {OUT.relative_to(ROOT)}：能力 {len(data['capabilities'])} 条"
          f"（函数 {data['counts']['function']} / 资产 {data['counts']['asset']}）")


if __name__ == "__main__":
    main()
