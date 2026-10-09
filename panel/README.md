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
