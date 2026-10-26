# Allure 接入说明（第二视图）

> 结论先说：**Allure 只做“呈现”，判定仍然只认 `case.json` / `report.json`。**
> 关掉 `--allure`，行为与接入前完全一致。

## 1. 开关

```bash
# 开
python -m gameqa run --kind api --case ST-BAG-API-001 --rounds 1 --allure

# 关（默认）：什么都不变，不产生 allure-results
python -m gameqa run --kind api --case ST-BAG-API-001 --rounds 1
```

环境变量（可选）：

| 变量 | 作用 |
| --- | --- |
| `GAMEQA_ALLURE` | `1/true/yes/on` 时启用；`--allure` 会给 pytest 子进程自动设置 |
| `GAMEQA_ALLURE_CLI` | 指定 allure 命令绝对路径；不设则查 PATH |

## 2. 依赖

```bash
# 1) pytest 插件（装在工作区的 python-env 里，不进 requirements-lock）
pip install -r requirements-allure.txt

# 2) Allure CLI（Java 实现；本机已有 JDK 21）
npm install -g allure-commandline
# 本机实际位置：/Users/Zhuanz/.local/node/v24.18.0/bin/allure
```

未装 `allure-pytest` 时传 `--allure` 只打印一行提示，**不影响测试结果和退出码**。

## 3. 产物位置

```
reports/<时间戳>/
├── round-01/allure-results/     ← pytest 原始结果（一直保留，可重新 generate）
├── allure-html/index.html       ← 生成的站点，双击可开
└── index.html                   ← 原多轮汇总页，多了一行「Allure 报告（第二视图）」入口
```

重新生成（不重跑用例）：

```bash
allure generate --clean -o reports/<时间戳>/allure-html reports/<时间戳>/round-*/allure-results
```

## 4. 映射关系

| 框架里的东西 | 在 Allure 里的呈现 |
| --- | --- |
| 用例 `id` + `title` | 用例标题（如 `ST-BAG-API-001 · 已有3个再买2个…`） |
| marker `game` / `module` / `kind` | 层级 parentSuite / suite / subSuite |
| `game` / `kind` / `covers` | 标签 `game:*`、`kind:*`、`covers:*` |
| `Evidence.action()` | 步骤 `[动作] …` |
| `Evidence.observe()` | 步骤 `[观察] …` |
| `Evidence.check()` | 步骤 `标题｜期望 X / 实际 Y` |
| `case.json` | 附件（名字里标 outcome 与是否不稳定） |
| `server.log` / 失败截图 | 附件 |

**没有搬过去的语义**（故意留在 `case.json` 里）：`unstable`（重试才过）、`A?` 未实现、快照 `restored`、`infra_retry` 明细。Allure 只有 passed/failed/broken/skipped 四种状态，表达不了这些，硬塞 tag 会丢信息。

## 5. 实现落点

| 文件 | 改动 |
| --- | --- |
| `src/gameqa/allure_report.py` | 新增。可选适配层：`active()` 判定、`step()` 上下文、附件、`generate()` 调 CLI、`summary_link()`。全部 try/except 包裹，失败不影响测试 |
| `src/gameqa/evidence.py` | `check/observe/action` 外包一层 `allure_report.step()`；关闭时是 `nullcontext`，零开销 |
| `src/gameqa/pytest_plugin.py` | setup 挂层级与标签；`pytest_runtest_call(trylast)` 设标题（必须在 allure setup 收尾之后，否则被函数名覆盖）；`pytest_runtest_makereport` 在 teardown **yield 之前**落盘并挂附件 |
| `src/gameqa/__main__.py` | `--allure` 开关、每轮传 `--alluredir`、跑完 `allure generate`、汇总页加链接 |
| `scripts/capabilities_manifest.py` | 登记 `allure_report.py` 通道为 `both`（否则自检拦下“新模块静默落进默认通道”） |
| `docs/框架能力清单.json` | 重新生成 |

## 6. 两个坑（已修，记下来免得再犯）

1. **标题被函数名覆盖**：allure 的 `pytest_runtest_setup` 是 hookwrapper，收尾时用 `allure_name(item)` 重设 `name`。标题必须在它之后设 → 放到 `pytest_runtest_call(trylast)`。
2. **附件静默丢失**：allure 在 `makereport(teardown)` 的收尾里停表，yield 之后再挂附件不会报错但也不生效。必须在 yield 之前挂。
3. **API 变更**：allure-pytest 2.16 没有 `allure.attach_file`，要用 `allure.attach.file(...)`。

## 7. 回滚

三条路，任选：

```bash
# ① 切回原分支（改动都在 allure-integration 分支上，main 未被触碰）
cd /Users/Zhuanz/Documents/Codex/2026-10-02/shi/outputs/airtest-game-qa
git switch main

# ② 用快照回滚单个文件
tar xzf ../airtest-game-qa.pre-allure-20261026.tar.gz -C . src pyproject.toml config.example.toml

# ③ 卸依赖（可选，卸载后 --allure 自动降级为提示）
pip uninstall allure-pytest allure-python-commons
npm uninstall -g allure-commandline
```

## 8. 验证记录（2026-10-26 实测）

| 项 | 结果 |
| --- | --- |
| 自检 `pytest tests -q` | 106→（接入前 109 通过/2 失败；接入后仅剩同样的 2 个 `test_ai_brief` 过期失败，与本次改动无关） |
| `ST-BAG-API-001` + `--allure` | exit=0，Repeatable=True，all passed=True |
| Allure 结果内容 | 标题带用例号、7 个步骤（4 动作 + 1 观察 + 2 断言含期望/实际）、附件 `case.json` 与 `server.log` |
| 不带 `--allure` | exit=0，不产生 `allure-results`，与原行为一致 |
| 报告站点 | `allure-html/index.html` 约 2.0M，汇总页含「Allure 报告（第二视图）」链接 |
