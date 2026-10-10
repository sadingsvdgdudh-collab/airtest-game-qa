# Stendhal QA 面板

本地单文件面板：看环境状态、挑用例跑、看报告与历史。它只依赖标准库，用工作区自带的 Python 跑。

```sh
# 默认 http://127.0.0.1:8787/
QA_PROJECT="$PWD" /Users/Zhuanz/Documents/Codex/2026-10-02/shi/work/python-env/bin/python panel/panel.py

# 只看状态（不开服务），适合脚本与自检
python panel/panel.py --state
```

环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `QA_PROJECT` | 本仓库根 | 用例、报告、`config.local.toml` 所在 |
| `QA_WORK` | 工作区（`.../shi/work`） | Python 环境、模拟器、Stendhal 运行时 |
| `QA_PORT` | `8787` | 监听端口 |

约定：

- 所有子进程都经 `scrub()` 清洗，密码类环境变量不会出现在日志或页面里；
- 面板自己启动的任务与命令行启动的运行**互不干扰**：`game_run_active()` 会挡掉"测试正在跑"时的健康检查，
  避免两批会话抢同一批角色（实测过一次连环失败）；
- `last.json` 是运行态记录，已 gitignore。

## 结果页

常驻显示**最近若干轮的重试率**：`重试才过 / 观测总数`，并给出一次通过条数。
重试率 **>35% 标黄提示**（不阻断）；每轮表格里也有「一次通过」与「重试才过」两列。
口径与 `summary.json` 一致：**重试才过不算一次通过**，详见 `docs/用例编写协议.md` 第六节。

## 服务按钮

面板可管三组服务：**主服 Stendhal**、**模拟器 Android**、**Shardy 井字棋**（后端 3000 + 展示页 3001）。
Shardy 用 `scripts/shardy/start.sh` / `stop.sh`；机器相关的 node 路径放在工作区 `local.env`
（`GAMEQA_NODE=/绝对路径/node`），不要写进仓库。状态灯：两个端口都在跑=绿、只起一个=黄、都没跑=灰。
