"""Allure 可选适配层（默认关闭，缺失依赖时全部退化为 no-op）。

设计约束（重要）：
1. **判定仍然只认 case.json / report.json**，Allure 只是第二视图，不参与任何断言。
2. 未安装 allure-pytest 或未开启时，这里的每个函数都不改变原有行为。
3. 任何反常都不许影响测试结果：附件失败只记录，不抛。
"""

from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from . import allure_i18n


TRUE_VALUES = {"1", "true", "yes", "on"}
ATTACH_MAX_BYTES = 4 * 1024 * 1024  # 单个附件上限，避免把几十 G 的日志塞进报告
ATTACH_SUFFIXES = {".png", ".jpg", ".jpeg", ".json", ".log", ".txt", ".webm", ".html"}


def enabled():
    """是否显式开启（环境变量）；`gameqa run --allure` 会给子进程设这个变量。"""
    return os.environ.get("GAMEQA_ALLURE", "").strip().lower() in TRUE_VALUES


def available():
    try:
        import allure  # noqa: F401
    except Exception:
        return False
    return True


def active():
    return enabled() and available()


def _allure():
    import allure
    return allure


def step(title, kind=None):
    """把一段业务动作变成 Allure 步骤。关闭时返回 nullcontext，零开销。"""
    if not active():
        return nullcontext()
    return _allure().step(str(title))


def attach_file(path, label=None):
    """挂一个附件；失败不抛。"""
    if not active():
        return False
    path = Path(path).resolve()
    try:
        if not path.is_file() or path.stat().st_size > ATTACH_MAX_BYTES:
            return False
        suffix = path.suffix.lower()
        attachment_type = None
        if suffix in {".png", ".jpg", ".jpeg"}:
            attachment_type = _allure().attachment_type.PNG
        _allure().attach.file(path, name=label or path.name, attachment_type=attachment_type)
        return True
    except Exception:
        return False


def attach_text(body, label):
    if not active():
        return False
    try:
        _allure().attach(str(body), name=str(label), attachment_type=_allure().attachment_type.TEXT)
        return True
    except Exception:
        return False


def _short(value, limit=80):
    text = repr(value)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def check_label(title, expected, actual):
    """断言步的显示名：标题 + 期望/实际（超长截断），仅用于呈现。"""
    return f"{title}｜期望 {_short(expected)} / 实际 {_short(actual)}"


def set_title(case_id, title=None):
    """标题单独设置：allure 的 setup 收尾会用函数名覆盖 name，必须在之后调用。"""
    if not active():
        return
    try:
        label = f"{case_id} · {title}" if title else case_id
        _allure().dynamic.title(label)
    except Exception:
        pass


def set_identity(case_id, meta, experiment=None):
    """给当前用例挂标题、层级和标签（失败不抛）。"""
    if not active():
        return
    try:
        allure = _allure()
        title = meta.get("title") or ""
        allure.dynamic.title(f"{case_id} · {title}" if title else case_id)
        allure.dynamic.parent_suite(meta.get("game") or "gameqa")
        allure.dynamic.suite(meta.get("module") or "module")
        allure.dynamic.sub_suite(meta.get("kind") or "case")
        allure.dynamic.tag(f"game:{meta.get('game')}")
        allure.dynamic.tag(f"kind:{meta.get('kind')}")
        for cover in meta.get("covers", ()) or ():
            allure.dynamic.tag(f"covers:{cover}")
        if experiment:
            allure.dynamic.parameter("experiment", experiment)
        allure.dynamic.parameter("case_id", case_id)
    except Exception:
        pass


def attach_case_folder(folder, outcome=None, unstable=False):
    """把一个用例的证据目录整体挂上去：case.json、截图、服务端日志。"""
    if not active():
        return 0
    folder = Path(folder).resolve()
    if not folder.is_dir():
        return 0
    count = 0
    priority = {"case.json": 0, "server.log": 1}
    for path in sorted(folder.iterdir(), key=lambda p: (priority.get(p.name, 9), p.name)):
        if path.is_file() and path.suffix.lower() in ATTACH_SUFFIXES:
            label = path.name
            if path.name == "case.json" and outcome:
                label = f"case.json（{outcome}{'·不稳定' if unstable else ''}）"
            count += int(attach_file(path, label))
    return count


GA_SCRIPT = re.compile(r"\s*<script async src=\"https://www\.googletagmanager\.com/gtag/js[^\"]*\"></script>")
GA_INLINE = re.compile(r"\s*<script>\s*window\.dataLayer[\s\S]*?</script>")


def strip_analytics(index_path):
    """Allure 2.x 会在报告里塞 Google Analytics。

    这个框架是离线优先的：报告一打开就向外发请求，不合适。默认删掉，
    `GAMEQA_ALLURE_KEEP_GA=1` 可保留。删的是外链和它的初始化块，不影响页面逻辑。
    """
    if os.environ.get("GAMEQA_ALLURE_KEEP_GA", "").strip().lower() in TRUE_VALUES:
        return False
    index_path = Path(index_path)
    try:
        text = index_path.read_text(encoding="utf-8")
        cleaned = GA_INLINE.sub("", GA_SCRIPT.sub("", text))
        if cleaned != text:
            index_path.write_text(cleaned, encoding="utf-8")
            return True
    except OSError:
        return False
    return False


def cli():
    """定位 allure 命令：先看环境变量，再找 PATH。"""
    explicit = os.environ.get("GAMEQA_ALLURE_CLI", "").strip()
    if explicit:
        return explicit if Path(explicit).exists() else None
    return shutil.which("allure")


def generate(results_dirs, out_dir, timeout=300):
    """调用 allure generate；返回 (index.html 路径, 失败原因)，二选一为 None。"""
    dirs = [Path(d) for d in results_dirs if Path(d).is_dir()]
    if not dirs:
        return None, "没有任何 allure-results 目录"
    command_path = cli()
    if not command_path:
        return None, "找不到 allure 命令（npm i -g allure-commandline，或设 GAMEQA_ALLURE_CLI）"
    out = Path(out_dir).resolve()
    if out.exists():
        shutil.rmtree(out)
    command = [command_path, "generate", "--clean", "-o", str(out), *[str(d) for d in dirs]]
    try:
        result = subprocess.run(command, text=True, encoding="utf-8", timeout=timeout,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"allure generate 执行失败：{error}"
    if result.returncode != 0 or not (out / "index.html").exists():
        tail = (result.stdout or "").strip().splitlines()[-5:]
        return None, "allure generate 退出码 %s：%s" % (result.returncode, " / ".join(tail))
    strip_analytics(out / "index.html")
    allure_i18n.localize(out)
    return out / "index.html", None


def summary_link(folder, html_path):
    """给多轮汇总页补一行入口；纯字符串，不改页面结构。"""
    try:
        rel = Path(html_path).resolve().relative_to(Path(folder).resolve())
    except Exception:
        return ""
    return f'<p><a href="{rel}">Allure 报告（第二视图）</a></p>'
