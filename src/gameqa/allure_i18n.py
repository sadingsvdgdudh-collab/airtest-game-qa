"""Allure 报告汉化。

结论先说：**Allure 2.46 自带中文**，不需要逐条翻译，只要在生成后把语言标成 `zh-CN`。
验证过 6 个路由（概览/套件/行为/图表/时间轴/包），中文覆盖完整；
剩下没翻译的只有品牌词 “Allure”、报告名和语言下拉里的语言代码。

开关：`GAMEQA_ALLURE_I18N=off` 关闭；`GAMEQA_ALLURE_TITLE` 改报告标题（默认「测试报告」）。
"""

import json
import os
from pathlib import Path

OFF_VALUES = {"0", "false", "no", "off"}
DEFAULT_TITLE = "测试报告"


def enabled():
    return os.environ.get("GAMEQA_ALLURE_I18N", "zh").strip().lower() not in OFF_VALUES


def title():
    return os.environ.get("GAMEQA_ALLURE_TITLE", DEFAULT_TITLE).strip() or DEFAULT_TITLE


def _patch_language(index_path):
    try:
        page = index_path.read_text(encoding="utf-8")
    except OSError:
        return False
    import re
    cleaned = re.sub(r'<html dir="ltr" lang="[^"]*">', '<html dir="ltr" lang="zh-CN">', page, count=1)
    cleaned = cleaned.replace("<title>Allure Report</title>", "<title>测试报告</title>", 1)
    if cleaned == page:
        return False
    index_path.write_text(cleaned, encoding="utf-8")
    return True


def _patch_title(summary_path, report_title):
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if data.get("reportName") == report_title:
        return False
    data["reportName"] = report_title
    summary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def localize(report_dir, report_title=None):
    """把一个已生成的 Allure 报告目录切成中文。返回做了哪些改动。"""
    if not enabled():
        return []
    report_dir = Path(report_dir)
    changed = []
    if _patch_language(report_dir / "index.html"):
        changed.append("lang=zh-CN")
    if _patch_title(report_dir / "widgets" / "summary.json", report_title or title()):
        changed.append("reportName")
    return changed
