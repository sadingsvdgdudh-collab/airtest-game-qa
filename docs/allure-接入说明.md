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
# 本机实际位置：<home>/.local/node/v24.18.0/bin/allure
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

## 3.3 总报告（汇总所有历史运行）

单次运行看一份报告，跨天看趋势得有一份“总报告”。已内置：

```bash
# 把所有 reports/*/round-*/allure-results 合成一份
python -m gameqa allure
# 输出：reports/_allure/index.html
```

面板「结果」页顶部也有：**打开总报告** / **重建总报告** 按钮。

合并细节（都踩过）：

| 事项 | 做法 | 为什么 |
| --- | --- | --- |
| 结果文件 | 硬链接到暂存目录再一次性 generate | 163 个文件 11 秒；APFS 硬链接零拷贝 |
| 跨轮同一条用例 | 靠 Allure 的 `historyId` 自动归并 | `fullName` + 参数一致即同一条历史 |
| 趋势点 | 先把上次的 `history/*.json` 拷进 **`results/history/` 子目录** | 平铺在 results 根目录会被忽略（实测 builds 一直是 1） |
| 没新运行时 | 记录 `.merged.json` 指纹，直接跳过重建 | 否则每点一次「重建」就多一个内容相同的趋势点 |
| 中文 | 同单份报告：`lang=zh-CN` + 标题 | 总报告也是中文 |

实测：5 条用例、163 个结果文件、重建后趋势点从 1 → 2 → 3 递增；再用同样输入重建会打印
「没有新的运行，跳过重建」。

## 3.4 总报告自动同步

带 `--allure` 的 `gameqa run` **跑完会自动刷新总报告**，不用再手动点：

```text
Round 1/1: exit=1; reports/…/round-01/index.html
Allure: reports/…/allure-html/index.html
总报告已同步（199 个结果文件）→ reports/_allure/index.html
```

| 开关 | 作用 |
| --- | --- |
| 默认 | 带 `--allure` 就跑完自动合并 |
| `--no-allure-merge` | 只出单次报告，不动总报告（大批量跑批时少 10 秒） |
| 面板 | 勾了 Allure 就等于带 `--allure`，跑完自动同步；「重建总报告」只用于补历史 |

**一个必须知道的边界**：没带 `--allure` 的运行**不会**进总报告——allure-results 是 pytest 跑的时候才产生的，
事后补不出来。合并时会提示 `另有 N 次运行没带 --allure，未包含`，看到这句就说明历史里有洞。

所以「单次报告有、总报告没有」的排查顺序：先看那次运行有没有 `allure-results/` 目录 → 再看总报告要不要重建。

## 3.5 环境未执行 vs 业务失败：分开写

同一条用例的多次尝试会进同一个「重试」表。但**"准备阶段就炸"和"断言跑完但不成立"不是一回事**：
前者其实没测。所以合并时把 broken（= 我们的 error）单独拆一份：

```
SH-TURN-UI-001 · 界面与接口双方交替落子…        passed  retries=1
【环境未执行】SH-TURN-UI-001 · 界面与接口…      broken  retries=0
```

实现（`allure_report._split_unexecuted`，只改合并时的暂存副本，不动原始结果）：

| 字段 | 处理 | 为什么 |
| --- | --- | --- |
| `fullName` | 追加 `#environment` | Allure 的树按 fullName 归并，不改会被覆盖 |
| `historyId` | `md5(fullName + "#environment")` | 重试只在同类之间统计 |
| `testCaseId` | 同上 | **漏了这个会被当同一条丢掉**（实测：改了 fullName/historyId 仍不显示） |
| `name` | 前缀 `【环境未执行】` | 列表里一眼分得开 |

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
4. **失败用例的标题会被重置**：通过用例标题正常，失败用例在收尾时 name 退回函数名
   （`test_sell_two_cheese_to_keeper`）。所以标题要在 `makereport(teardown)` 的 **yield 之前再设一次**，
   和附件同一个时机。

## 7. 回滚

三条路，任选：

```bash
# ① 切回原分支（改动都在 allure-integration 分支上，main 未被触碰）
cd <repo>
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
