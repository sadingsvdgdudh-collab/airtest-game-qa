import html
import json
from pathlib import Path
import time

from .bridge import TransientError, redact


class Evidence:
    def __init__(self, case_id, folder, metadata=None):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.data = {"id": case_id, "metadata": metadata or {}, "outcome": "running",
                     "unstable": False, "steps": [], "attachments": [], "diagnostics": {},
                     "started": time.time()}

    def check(self, title, actual, expected, source):
        if not source:
            raise ValueError("business assertion needs a rule source")
        passed = actual == expected
        self.data["steps"].append({"title": title, "expected": redact(expected),
                                   "actual": redact(actual), "source": source,
                                   "outcome": "passed" if passed else "failed"})
        if not passed:
            raise AssertionError(f"{title}: expected={expected!r}, actual={actual!r}; source={source}")

    def observe(self, title, operation, retries=1):
        """Retry observations only. Pass business actions to action(), never here."""
        if not 0 <= retries <= 3:
            raise ValueError("observation retries must be between 0 and 3")
        step = {"title": title, "kind": "observation", "attempts": []}
        self.data["steps"].append(step)
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                result = operation()
                step["attempts"].append({"number": attempt + 1, "outcome": "passed",
                                          "elapsed": time.monotonic() - started})
                step["outcome"] = "passed"
                return result
            except TransientError as exc:
                step["attempts"].append({"number": attempt + 1, "outcome": "failed",
                                          "error": str(exc), "elapsed": time.monotonic() - started})
                step["outcome"] = "failed"
                self.data["unstable"] = True
                if attempt == retries:
                    raise
            except Exception as exc:
                step["outcome"] = "failed"
                step["attempts"].append({"number": attempt + 1, "outcome": "failed", "error": str(exc)})
                raise

    def action(self, title, operation):
        step = {"title": title, "kind": "business_action", "outcome": "running"}
        self.data["steps"].append(step)
        try:
            result = operation()
            step["outcome"] = "passed"
            return result
        except Exception as exc:
            step.update(outcome="failed", error=str(exc))
            raise

    def attach(self, path, label):
        path = Path(path).resolve()
        if not path.is_relative_to(self.folder):
            raise ValueError("copy attachments into the case report folder first")
        self.data["attachments"].append({"label": label, "path": str(path.relative_to(self.folder))})

    def write(self):
        self.data["finished"] = time.time()
        path = self.folder / "case.json"
        path.write_text(json.dumps(redact(self.data), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def write_report(folder, records, metadata=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    payload = redact({"metadata": metadata or {}, "cases": records})
    (folder / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    esc = lambda value: html.escape(str(value))
    blocks = []
    for record in payload["cases"]:
        case_id = record["id"]
        detail = esc(json.dumps(record, ensure_ascii=False, indent=2))
        attachments = " ".join(f'<a href="{esc(case_id)}/{esc(a["path"])}">{esc(a["label"])}</a>'
                               for a in record.get("attachments", []))
        unstable = " · 不稳定" if record.get("unstable") else ""
        blocks.append(f'<article id="{esc(case_id)}"><h2>{esc(case_id)} · {esc(record["outcome"])}{unstable}</h2>'
                      f'{attachments}<details open><summary>步骤、预期、实际与证据</summary><pre>{detail}</pre></details></article>')
    page = ('<!doctype html><html lang="zh"><meta charset="utf-8"><title>Game QA report</title>'
            '<style>body{max-width:1100px;margin:32px auto;padding:0 20px;font:16px system-ui;color:#1b2838}'
            'article{border:1px solid #ccd3dc;border-radius:8px;padding:18px;margin:20px 0}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f9;padding:16px}a{margin-right:16px}</style>'
            '<h1>游戏测试执行报告</h1><p>失败、跳过和不稳定均保留；受控实验单独标识。</p>'
            f'<pre>{esc(json.dumps(payload["metadata"], ensure_ascii=False, indent=2))}</pre>' + "".join(blocks) + '</html>')
    (folder / "index.html").write_text(page, encoding="utf-8")
