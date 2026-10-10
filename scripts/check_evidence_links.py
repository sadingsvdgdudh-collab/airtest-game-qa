#!/usr/bin/env python3
"""校验文档里的证据引用：磁盘存在，并且已被 git 跟踪。

动机：`docs/evidence/` 整树在 .gitignore 里（逐轮全量截图/报告保留本地），
只有"证据包入口 + 摘要 + 核验 + 录像"随仓库交付。如果文档链接指向未入库的文件，
克隆仓库后就是断链——这就是交付缺陷。本脚本把这条规则变成可执行检查。

规则：
- 扫描 docs/**/*.md 与 README.md 里的 markdown 链接，以及以 evidence/ 开头、**看起来像文件**的行内代码
  （行内代码里单纯提目录是散文，不算引用）；
- 指向文件：必须磁盘存在 **且** 被 git 跟踪；
- 指向目录：该目录必须存在，且它的 index.html 必须存在并被跟踪（克隆后读者要能点进去）；
- git 不可用时只做磁盘校验，并明确说明"跟踪校验已跳过"（源码包场景）。
"""
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)]+)\)")
CODE = re.compile(r"`((?:docs/)?evidence/[^`]+)`")
IGNORED_PREFIXES = ("http://", "https://", "mailto:")


FENCE = re.compile(r"^\s*(```|~~~)")


def strip_fences(text):
    """去掉围栏代码块：那里的路径是复现命令，不是文档链接。"""
    lines, inside = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return "\n".join(lines)


def normalise(target, doc_dir, project):
    """把引用解析成"相对仓库根"的路径；不是 evidence 引用或跑到仓库外就返回 None。"""
    target = target.strip().split("#", 1)[0].strip()
    if not target or target.startswith(IGNORED_PREFIXES) or "evidence/" not in target:
        return None
    base = project if target.startswith("docs/") else doc_dir
    resolved = (base / target).resolve()
    try:
        return str(resolved.relative_to(project)).rstrip("/")
    except ValueError:
        return None


def references(project=PROJECT):
    """{证据相对路径: {引用它的文档}}。"""
    found = {}
    docs = sorted(project.glob("docs/**/*.md")) + [project / "README.md"]
    for doc in docs:
        if not doc.exists():
            continue
        text = strip_fences(doc.read_text(encoding="utf-8", errors="ignore"))
        for pattern, is_code in ((LINK, False), (CODE, True)):
            for match in pattern.finditer(text):
                target = match.group(1)
                # 行内代码里提到目录（如 docs/evidence/）是散文，不算引用；只有像文件的才算。
                tail = target.rstrip("/").rsplit("/", 1)[-1]
                if is_code and ("." not in tail or set(tail) <= {".", "…"}):
                    continue
                path = normalise(target, doc.parent, project)
                if path:
                    found.setdefault(path, set()).add(str(doc.relative_to(project)))
    return found


def tracked_files(project=PROJECT):
    """git 跟踪的文件集合；git 不可用时返回 None。"""
    try:
        done = subprocess.run(["git", "-C", str(project), "ls-files"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return set(done.stdout.split()) if done.returncode == 0 else None


def check(project=PROJECT):
    """返回问题列表；空列表表示克隆后不会断链。"""
    tracked = tracked_files(project)
    problems = []
    for path, docs in sorted(references(project).items()):
        who = "、".join(sorted(docs))
        target = project / path
        if target.is_dir():
            entry = target / "index.html"
            if not entry.exists():
                problems.append((path, who, "目录没有 index.html；请指向该证据包的入口页"))
            elif tracked is not None and str(entry.relative_to(project)) not in tracked:
                problems.append((path, who, "入口页未入库（git add -f 该证据包）"))
            continue
        if not target.exists():
            problems.append((path, who, "磁盘上不存在"))
        elif tracked is not None and str(target.relative_to(project)) not in tracked:
            problems.append((path, who, "存在但未被 git 跟踪（克隆后是断链）"))
    return problems


def main():
    problems = check()
    total = len(references())
    skipped = tracked_files() is None
    print(f"证据引用 {total} 条" + ("（git 不可用，仅校验磁盘存在）" if skipped else "（校验磁盘存在 + 已跟踪）"))
    for path, who, why in problems:
        print(f"  ✗ {path}\n      引用自 {who}\n      {why}")
    if problems:
        print(f"未通过：{len(problems)} 条引用在克隆后会是断链")
        return 1
    print("通过：所有证据引用都存在且已入库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
