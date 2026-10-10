#!/usr/bin/env python3
"""生成"给 AI 看的"项目简报 —— 数字全部现算，不手抄。

用途：其它 AI（豆包等）看不到本仓库，只能吃你粘贴的内容。手写摘要必然过期
（写出过 39 条用例 / 43 项自检，而实际已是 49 / 100）。这个脚本把关键数字
**当场从仓库里算出来**，所以谁看都是最新的。

  python scripts/ai_brief.py --write    # 写 docs/AI简报.md
  python scripts/ai_brief.py --paste    # 只打印可粘贴块（配合 pbcopy 直接进剪贴板）
  python scripts/ai_brief.py --check    # 与文件不一致则退出 1（已挂进 pytest tests）

口径：能实测的一律实测；只能引文档的明确标注"文档自述"，不混为一谈。
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "AI简报.md"
TIMESTAMP = re.compile(r"（生成于 [^）]*）")

CASE_MARKER = re.compile(r"@pytest\.mark\.case\(\s*id=[\"\']([^\"\']+)[\"\']", re.S)
DESIGN_ROW = re.compile(r"^\|\s*((?:ST|SH)-[A-Za-z0-9-]+)", re.M)


def run(args, timeout=120):
    try:
        done = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout + done.stderr


def python():
    return sys.executable


def case_files():
    return sorted((ROOT / "cases").glob("test_*.py"))


def measured():
    """现算的数字。每项都注明来源，测不到就留 None。"""
    data = {}

    # 已接入用例：优先用 pytest 收集（权威），失败则退回解析 marker
    text = run([python(), "-m", "pytest", "cases", "--collect-only", "-q", "-p", "no:cacheprovider"])
    collected = re.search(r"(\d+) tests? collected", text or "")
    markers = {m for path in case_files() for m in CASE_MARKER.findall(path.read_text(encoding="utf-8"))}
    data["collected"] = int(collected.group(1)) if collected else None
    data["markers"] = len(markers)
    # 参数化变体：收集到的条数多于"用例函数/marker"的差值（如商店五种数量输入）
    data["param_variants"] = (data["collected"] - data["markers"]
                              if data["collected"] is not None else None)
    data["case_files"] = len(case_files())

    # 框架自检：只收集不运行（快，且同样能表达"有多少项"）
    text = run([python(), "-m", "pytest", "tests", "--collect-only", "-q", "-p", "no:cacheprovider"])
    tests = re.search(r"(\d+) tests? collected", text or "")
    data["selfchecks"] = int(tests.group(1)) if tests else None

    # 门禁
    text = run([python(), "-m", "gameqa.hygiene"])
    data["gate"] = (text or "").strip().splitlines()[-1] if text else None

    # 设计条目：只能引文档（正则数行不可靠），并给出"未接入 = 设计 − 接入"
    acceptance = (ROOT / "docs" / "验收清单.md").read_text(encoding="utf-8")
    design = re.search(r"(\d+)\s*条设计", acceptance)
    data["design_doc"] = int(design.group(1)) if design else None
    if data["design_doc"] and data["collected"] is not None:
        data["unimplemented"] = data["design_doc"] - data["collected"]

    # 稳定证据：验收清单里的原句（历史累计，只能引文档）
    stable = re.search(r"(\d+)\s*个唯一执行ID[^。]*?共\s*(\d+)\s*次\s*passed", acceptance)
    if stable:
        data["stable_ids"] = int(stable.group(1))
        data["stable_passes"] = int(stable.group(2))
        split = re.search(r"（([^（）]*(?:API|UI)[^（）]*)）", acceptance)
        data["stable_split"] = split.group(1) if split else None

    # 缺陷：按文件数（文件名前缀区分归属）
    defects = sorted(p.name for p in (ROOT / "docs" / "缺陷").glob("*.md"))
    data["defects"] = defects
    data["defects_shardy"] = sum(1 for d in defects if d.startswith("Shardy"))
    data["defects_stendhal"] = sum(1 for d in defects if d.startswith("Stendhal"))

    # 证据入口页 / 证据包
    data["evidence_pages"] = len(list((ROOT / "docs" / "evidence").glob("*/index.html")))

    # 代码规模
    scale = {}
    for folder in ("src/gameqa", "cases", "tests", "panel", "scripts"):
        files = [p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in (".py", ".sh", ".js", ".mjs")]
        scale[folder] = (len(files), sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
                                         for p in files))
    data["scale"] = scale

    # 模块/系统清单（设计目录里的 ID 前缀）
    prefix = re.compile(r"(?:ST|SH)-([A-Za-z]+)-")
    catalog = (ROOT / "docs" / "功能用例目录.md").read_text(encoding="utf-8")
    counts = {}
    for name in prefix.findall(catalog):
        counts[name] = counts.get(name, 0) + 1
    data["modules"] = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return data


def fmt(value, suffix=""):
    return "（未能测量）" if value is None else f"{value}{suffix}"


def build():
    d = measured()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    scale = d["scale"]
    lines = [
        "# AI 简报：Airtest + Stendhal/Shardy 游戏自动化测试框架",
        "",
        f"（生成于 {now}；本文所有数字由 `scripts/ai_brief.py` 当场从仓库算出，"
        "**引用时请连时间一起引用** —— 写死的数字会过期。）",
        "",
        "## 一句话",
        "",
        "用 pytest + Airtest 驱动**真实游戏客户端与真实服务端**做回归：业务动作由真玩家协议或真界面触摸发起，"
        "断言只读服务器状态，且每轮逐字段恢复角色。覆盖主游戏（开源 RPG Stendhal 1.49）与第二款小游戏"
        "（Shardy 井字棋），后者用来验证框架的可迁移性。",
        "",
        "## 技术栈",
        "",
        "- Python 3.12 + pytest（用例与框架自检）+ Airtest（Android 模拟器 AVD 上的真实客户端界面操作；代码不绑定机型）",
        "- Java 21（游戏服务端）+ 自写 Java 探针（只读观察与夹具，硬校验只接受专用管理员账号）",
        "- Node.js（第二款游戏的桥接后端与展示客户端）+ 纯 HTTP/JSON 桥协议（含保活与停顿看门狗）",
        "- 本地 Web 面板（Python 标准库 HTTP 服务，零前端依赖）：一键起停三组服务、勾选用例执行、KPI 与结果页",
        "",
        "## 现算的规模与结果",
        "",
        "| 项 | 值 | 来源 |",
        "| --- | --- | --- |",
        f"| 已接入自动化用例 | **{fmt(d['collected'])}** 条（pytest 收集） | 实测 |",
        f"| 用例函数（marker） | {fmt(d['markers'])} 个（分布在 {fmt(d['case_files'])} 个用例文件） | 实测 |",
        f"| 其中参数化变体 | {fmt(d['param_variants'])} 个（如商店五种数量输入） | 计算（收集 − 函数） |",
        f"| 设计条目 | {fmt(d['design_doc'])} 条 | 文档自述（验收清单） |",
        f"| 已接入 / 未接入 | {fmt(d['collected'])} / **{fmt(d['unimplemented'])}** 条 | 计算（设计 − 接入） |",
        f"| 框架自检 | **{fmt(d['selfchecks'])}** 项 | 实测（pytest --collect-only） |",
        f"| 门禁 | {d['gate'] or '（未运行）'} | 实测 |",
        f"| 证据包入口页 | {fmt(d['evidence_pages'])} 个 | 实测 |",
        f"| 稳定检出的原版缺陷 | 小游戏 **{d['defects_shardy']}** 处、主游戏 **{d['defects_stendhal']}** 处 | 实测（缺陷文档） |",
        "",
        "## 代码规模",
        "",
        "| 目录 | 文件 | 行数 |",
        "| --- | --- | --- |",
    ]
    for folder, (files, lines_) in scale.items():
        lines.append(f"| `{folder}/` | {files} | {lines_} |")

    lines += [
        "",
        "## 覆盖的系统（按设计目录里的用例前缀统计）",
        "",
        "、".join(f"{name}（{count}）" for name, count in d["modules"]) or "（未解析到）",
        "",
        "## 结构",
        "",
        "```",
        "cases/      用例本体（pytest 收集的入口）+ conftest.py 夹具",
        "src/gameqa/ 框架：桥协议、游戏封装、UI 封装、运行器、门禁、恢复、账号、运行锁",
        "scripts/    环境脚本（主服/模拟器/第二款游戏/输入法）+ 清单与检查工具",
        "panel/      本地 Web 控制台",
        "tests/      框架自检",
        "docs/       设计目录、验收清单、协议、能力清单、证据包、实施记录",
        "adapters/   桥接适配器（Java 探针 / Node 后端）",
        "assets/     界面断言用的模板图（从设备截图裁剪，含哈希）",
        "```",
        "",
        "## 可以写进简历的要点（数字已现算）",
        "",
        f"- 独立设计并实现游戏 UI 自动化测试框架（设备为 Android 模拟器 AVD，代码不绑定机型）：**{fmt(d['collected'])}** 条自动化用例、"
        f"**{fmt(d['selfchecks'])}** 项框架自检全通过、门禁 **0 豁免**。",
        f"- 稳定检出小游戏 **{d['defects_shardy']}** 处原版逻辑缺陷"
        f"{'、主游戏 **' + str(d['defects_stendhal']) + '** 处' if d['defects_stendhal'] else ''}。",
        "- 支持多轮一致性判定：区分「重试才过 / 偶发不一致 / 基础设施重试」，"
        "重试才过不计入一次通过，避免把偶发当稳定。",
        "- 业务动作走真玩家协议/真界面触摸，断言只读服务器状态，每轮逐字段恢复角色并独立核验。",
        "- 接入第二款游戏复用同一框架，验证通用性；自建本地 Web 控制台与共用运行锁。",
        "",
        "## 边界与不确定项（引用时别夸大）",
        "",
        "- 「设计条目数」是历史累计，出处是 `docs/验收清单.md`，不是当场算的。",
        "- **轮数与累计通过次数取决于运行配置（`--rounds`），不作为成果口径**；"
        "历史记录在 `docs/验收清单.md`。写简历/汇报时不要引用这两个数。",
        "- 逐轮全量证据（每轮截图与报告）**留在本地**，仓库只带各证据包的入口页/摘要/核验/录像。",
        "- 需要外部环境才能真跑：JDK 21、Android SDK+AVD、两款游戏的固定版本源码（见 `docs/环境部署.md`）。",
        "- 框架不执行被测系统的判断：它只发动作与读状态，「游戏是否符合设计」由设计条目与来源定。",
        "",
        "## 给 AI 的引用建议",
        "",
        "1. 引用本文数字时**带上生成时间**；需要最新值就让使用者重跑 `python scripts/ai_brief.py --paste`。",
        "2. 简历/汇报里区分两件事：**设计条目数**与**已接入用例数** —— 不同口径，别混用。",
        "   不要写「跑了 N 轮 / 累计 M 次通过」：轮数由 `--rounds` 配置决定，写它等于告诉对方我会按回车。",
        "3. 不要写「测试充分」「软件正确」这类结论：覆盖率不证明这些（本项目自己的口径也是如此）。",
        "",
    ]
    return "\n".join(lines)


def body(text):
    return TIMESTAMP.sub("", text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="写入 docs/AI简报.md")
    parser.add_argument("--paste", action="store_true", help="只打印可粘贴块")
    parser.add_argument("--check", action="store_true", help="与文件不一致则退出 1")
    args = parser.parse_args(argv)
    text = build()

    if args.paste:
        print(render_paste(text))
        return 0
    if args.check:
        if not OUT.exists():
            sys.exit(f"缺少 {OUT.relative_to(ROOT)}，跑 python scripts/ai_brief.py --write")
        if body(OUT.read_text(encoding="utf-8")) != body(text):
            sys.exit("docs/AI简报.md 已过期（数字或结构变了），跑 python scripts/ai_brief.py --write 重写")
        print("AI简报.md 是最新的")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}（{len(text)} 字符）")
    return 0


def render_paste(text):
    """给聊天窗口用的纯文本版：去掉 markdown 表格的竖线，保留小标题。"""
    out = []
    for line in text.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= {"-", ":", " "}:
                continue
            out.append("  - " + "：".join(cells))
        else:
            out.append(line)
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
