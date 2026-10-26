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

## 3.1 面板里怎么看

面板（`panel/panel.py`）已经接上，两处：

| 位置 | 效果 |
| --- | --- |
| 「用例清单」工具栏 | 多一个 **Allure** 勾选框；勾上再执行 → 给 `gameqa run` 追加 `--allure` |
| 「结果」表格每行 | 有 Allure 产物的运行会多一个 **Allure** 链接，点开就是同一台服务器上的报告 |

报告走面板已有的 `/reports/<run>/...` 静态通道，不需要另开端口，也不用点开本地文件。
`allure-html/index.html` 用的是相对路径，挂在子路径下能正常加载 `assets/`。

**顺带处理了一件事**：Allure 2.x 生成的页面里塞了 Google Analytics（`googletagmanager`），
一打开就往外发请求。框架是离线优先的，所以生成后默认删掉那段脚本，
需要保留时设 `GAMEQA_ALLURE_KEEP_GA=1`。删的只是外链和它的初始化块，不影响页面逻辑。

## 3.2 中文界面

**Allure 2.46 自带中文**，不用逐条翻译——生成后把语言标成 `zh-CN` 就是中文。
实测概览/套件/行为/图表/时间轴/包 六个路由，中文覆盖完整，残留只有品牌词 `Allure`、语言下拉里的语言代码和数据本身。

做法（`src/gameqa/allure_i18n.py`，生成时自动执行）：

1. `index.html`：`lang="en"` → `lang="zh-CN"`，`<title>Allure Report</title>` → `<title>测试报告</title>`
2. `widgets/summary.json`：`reportName` → `测试报告`（页面大标题）

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `GAMEQA_ALLURE_I18N` | `zh` | 设为 `off` 保持英文 |
| `GAMEQA_ALLURE_TITLE` | `测试报告` | 改报告标题 |

> 走过的弯路记一下：一开始写了一套「英文→中文」字典 + MutationObserver 逐节点替换（100 多条）。
> 后来发现 Allure 本来就有中文包，只要 `<html lang>` 设对；字典方案反而把自带翻译覆盖成自己的写法。
> 所以字典整段删了，只剩 6 行补丁——**能用上游的就别自己造**。

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
| `src/gameqa/allure_report.py` | 新增。可选适配层：`active()` 判定、`step()` 上下文、附件、`generate()` 调 CLI、`strip_analytics()` 去掉 GA、`summary_link()`。全部 try/except 包裹，失败不影响测试 |
| `panel/panel.py` | 工具栏加 Allure 勾选；结果表加 Allure 链接；`child_env()` 自动定位 allure 命令（Finder 启动时 PATH 很短） |
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
| 面板内打开 | `/reports/<run>/allure-html/index.html` → 200，`assets/` 资源 200 |
| 中文覆盖 | 6 个路由渲染后中文标签 21 个，残留英文只有 `Allure`/`am`/`stendhal` |
| 报告标题 | `<title>测试报告</title>`，页面大标题「测试报告 2026/10/26」 |
| 面板勾选跑一轮 | `POST /api/run {allure:true}` → 命令带 `--allure`，job passed，产物齐全 |
| GA 已剔除 | 生成后的 `index.html` 里 `googletagmanager` 出现 0 次 |
