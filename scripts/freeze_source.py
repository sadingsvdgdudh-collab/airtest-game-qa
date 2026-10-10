#!/usr/bin/env python3
"""冻结"公开执行源"清单 —— 验收包里的 source.json。

验收要求：**跑第一条用例之前**先冻结这次执行的源码与素材，跑完再重新算一遍哈希，
证明"验收结果对应的就是这份代码"。手工做过几次，这里把它脚本化。

  python scripts/freeze_source.py --out docs/evidence/<组名>/source.json
  python scripts/freeze_source.py --check docs/evidence/<组名>/source.json   # 跑完复查，变了就退出码 1

冻结范围（与既有验收包一致）：cases/ src/ scripts/ tests/ assets/ adapters/ integrations/ 与顶层锁定文件。
不含：docs/、reports/、.git/、__pycache__、安装生成物（egg-info）、node_modules 等。
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SCOPE_DIRS = ("cases", "src", "scripts", "tests", "assets", "adapters", "integrations")
SCOPE_FILES = ("pyproject.toml", "requirements.txt", "config.example.toml", "pnpm-lock.yaml")
EXCLUDE_PARTS = ("__pycache__", ".git", "node_modules", ".venv", "egg-info", ".pytest_cache")
SCOPE_TEXT = "公开执行源码、配置模板、锁定依赖、图像素材与框架自检；文档和安装生成物不在冻结范围"


def in_scope(path):
    if any(part in EXCLUDE_PARTS or part.endswith(".egg-info") for part in path.parts):
        return False
    if path.suffix in (".pyc", ".pyo") or path.name in (".DS_Store",):
        return False
    return True


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(project=PROJECT):
    """{相对路径: sha256}，已排序，便于比对与肉眼检查。"""
    files = {}
    for folder in SCOPE_DIRS:
        root = project / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and in_scope(path.relative_to(project)):
                files[str(path.relative_to(project))] = hash_file(path)
    for name in SCOPE_FILES:
        path = project / name
        if path.is_file():
            files[name] = hash_file(path)
    return dict(sorted(files.items()))


def write_manifest(out, project=PROJECT):
    manifest = {"captured_utc": datetime.now(timezone.utc).isoformat(),
                "formal_execution_project": str(project),
                "scope": SCOPE_TEXT,
                "files": snapshot(project)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def compare(manifest_path, project=PROJECT):
    """返回 (changed, added, removed)；manifest 里的路径相对它记录的工程目录。"""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    base = Path(manifest.get("formal_execution_project") or project)
    recorded = manifest["files"]
    current = snapshot(base if base.is_dir() else project)
    changed = sorted(k for k in recorded if k in current and current[k] != recorded[k])
    added = sorted(set(current) - set(recorded))
    removed = sorted(set(recorded) - set(current))
    return changed, added, removed


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="写出的 source.json 路径")
    parser.add_argument("--project", default=str(PROJECT))
    parser.add_argument("--check", metavar="SOURCE_JSON", help="复查模式：重新算哈希并与清单比对")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()

    if args.check:
        changed, added, removed = compare(args.check, project)
        print(f"清单 {args.check}：改动 {len(changed)}、新增 {len(added)}、删除 {len(removed)}")
        for label, items in (("改动", changed), ("新增", added), ("删除", removed)):
            for item in items[:20]:
                print(f"  {label}: {item}")
        if changed or added or removed:
            print("不一致：冻结之后执行源发生了变化，这份证据不能当作对应该清单的验收")
            return 1
        print("一致：执行源与冻结清单相同")
        return 0

    if not args.out:
        parser.error("要么给 --out 写清单，要么用 --check 复查")
    manifest = write_manifest(Path(args.out).resolve(), project)
    print(f"已冻结 {len(manifest['files'])} 个文件 → {args.out}")
    print(f"时间：{manifest['captured_utc']}（应在第一条用例之前）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
