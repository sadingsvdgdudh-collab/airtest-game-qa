# Shardy 官方后端适配

服务端来源：[mopsicus/shardy-tictactoe](https://github.com/mopsicus/shardy-tictactoe)，固定提交 `ed8e978917cbe5aba79009928e8c3b92a34b81cc`，MIT 许可。业务源码保持原版。依赖锁固定 Shardy `1.2.0`，本机验证使用 Node `24.19.0`、pnpm `11.25.0`。`prepare.sh` 只编译，不执行上游会自动改写源码的格式化任务。

## 准备与启动

需要 Node、pnpm、Git。在项目工作区根目录执行；也可以通过 `SHARDY_WORK` 指定下载和运行数据目录：

```sh
bash outputs/airtest-game-qa/adapters/shardy_bridge/prepare.sh
node outputs/airtest-game-qa/adapters/shardy_bridge/start_backend.mjs
node outputs/airtest-game-qa/integrations/shardy_client/server.mjs
```

本机使用随应用提供的工具时，设置 `SHARDY_NODE`、`SHARDY_PNPM` 后执行准备脚本。后端入口支持第一个参数指定已准备的 vendor 目录；也支持 `SHARDY_VENDOR`。后端只监听 `127.0.0.1:3000`，展示页只监听 `127.0.0.1:3001`。后台启动请分别将标准输出重定向到 `work/shardy/logs`，保留进程 PID 以便停止。

## 共用 JSONL 接口

```sh
node outputs/airtest-game-qa/adapters/shardy_bridge/bridge.mjs
```

使用上游 Shardy `Bot`、游戏 `T3Serializer` / `T3Validator` 执行真实 WebSocket 握手和业务请求。标准输入每行 `{id,op,args}`；标准输出每行 `{id,ok,result}` 或 `{id,ok:false,error:{type,message}}`。SDK 日志发到标准错误，不混入 JSONL。

| op | args | result |
|---|---|---|
| connect | host（默认 127.0.0.1）、port（默认 3000） | 连接结果、state |
| start | 无 | 官方请求确认、state |
| stop | 无 | 官方停止匹配确认、state |
| exit | 可选 game、player | 官方退出对局确认、state |
| turn | x、y；可选 game、player | 官方请求确认、state |
| get_messages | after、name（等待目标广播）、wait_ms（0..10000） | cursor、真实广播 messages、state |
| disconnect | 无 | state |

`state` 来自实际服务器广播，含 `connected/matched/game/player/turn/score/board`。棋盘是九格数组，索引 `y*3+x`，`0=X`、`1=O`、`null=空格`。首次手随机，必须读取 `round.data.t`，不能假设 X 先手。请求确认不代表落子被接受：原版会忽略重复格子或错误轮次，但仍返回确认；测试需检查真实 `turn` 广播和棋盘变化。

两个桥进程可构成两个真实玩家，第二进程也可作为 Android UI 玩家的 API 对手。`get_messages` 是读取观察结果；`turn` 不自动重发，超时后应先检查服务器广播，避免重复业务操作。

测试结束必须先发送 `exit` 删除当前对局，再 `disconnect`；未匹配连接先 `stop`。原版单纯断连接只清理匹配队列，不会删除已经创建的游戏。Python 用例的 `Shardy.close()` 执行这些真实清理请求，并记录确认消息。

## 运行验证

后端运行后，使用已安装本项目的 Python：

```sh
python outputs/airtest-game-qa/adapters/shardy_bridge/check_live.py \
  --node /absolute/path/to/node --output work/shardy/logs/rule-verification.json
```

验证真实双客户端匹配、落子、比分广播与棋盘一致性。正常横排胜利通过；原版存在两个已复现的规则失败：反对角线胜利未结算，八步时提前按和局开始下一回合。脚本分别保存正确预期、实际状态及两端消息证据，不修改服务端。脚本成功退出表示正常链路通过且已知失败被稳定复现，不代表全部业务规则通过。

源码位置：`Game.ts` 的 `field[i][ROW_MAX_COUNT-i+1]` 反对角线下标，以及 `count===Math.pow(ROW_MAX_COUNT,2)-1` 和局条件。
