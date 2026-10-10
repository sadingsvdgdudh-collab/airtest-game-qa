"""面板页面里的那段 JS 必须真的能解析。

来由：一次改 `JSON.stringify({...})` 时把对象拆行弄坏了，整段 `<script>` 解析失败，
`refreshState()` 永不执行 —— 页面就永远停在「读取状态…」，而后端一切正常。
这类错误 `py_compile` 和 grep 都看不出来，只有 JS 语法检查能拦。
"""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("qa_panel_script", ROOT / "panel" / "panel.py")
panel = importlib.util.module_from_spec(SPEC)
sys.modules["qa_panel_script"] = panel
SPEC.loader.exec_module(panel)

SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
# 只钉"页面必须存在"的关键函数：状态轮询、渲染、用例清单、结果页（名字取自实际脚本，别猜）
CORE = ("refreshState", "render", "loadReports", "loadCases", "pollJob", "beginJob")


def page_script():
    scripts = SCRIPT.findall(panel.HTML)
    assert scripts, "面板页面里找不到 <script>"
    return "\n".join(scripts)


def node_binary():
    found = shutil.which("node")
    if found:
        return found
    bundled = Path("/Users/Zhuanz/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node")
    return str(bundled) if bundled.exists() else None


def test_page_script_defines_the_core_functions():
    script = page_script()
    for name in CORE:
        assert f"function {name}" in script or f"async function {name}" in script, f"页面脚本里没有 {name}"




def test_page_has_the_shardy_service_controls():
    for element in ("b-shardy-start", "b-shardy-stop", "d-shardy", "shardy-note"):
        assert f'id="{element}"' in panel.HTML, f"面板页面里缺少 Shardy 元素 {element}"
    assert "state.shardy" in page_script(), "状态灯没有读 state.shardy"


def test_page_script_parses_as_javascript(tmp_path):
    node = node_binary()
    if node is None:
        pytest.skip("没有可用的 node，跳过 JS 语法检查")
    target = tmp_path / "panel.js"
    target.write_text(page_script(), encoding="utf-8")
    done = subprocess.run([node, "--check", str(target)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, f"面板页面 JS 语法错误：\n{done.stderr[:800]}"
