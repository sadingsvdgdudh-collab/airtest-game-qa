# Shardy-001：反对角线三子连线后未结算胜利

类型：原版真实缺陷，未注入。状态：已复现，未修复。严重程度：主要（合法获胜不计分，不能进入下一回合）。自动化回归：`SH-DEFECT-API-001`，模块 `known_defects`。

版本：`mopsicus/shardy-tictactoe@ed8e978917cbe5aba79009928e8c3b92a34b81cc`；Shardy `1.2.0`；本机 Node `24.19.0` / Python `3.12.14`。两个真实 WebSocket 玩家连接 `127.0.0.1:3000`，调用原版匹配和落子命令，无状态直改。上游业务源码未修改，见[版本和源码校验](../evidence/shardy-source/source.json)。

前置：双方 `connect/start`，收到 `round`，棋盘为空、比分 `[0,0]`；读取 `round.data.t` 决定先手，不能假设 X 先手。

复现步骤（坐标从0开始，x为列、y为行）：先手 `(0,2)`；后手 `(0,0)`；先手 `(1,1)`；后手 `(1,0)`；先手 `(2,0)`。每步等待双方真实 `turn` 广播后继续。

预期：先手反对角线三子连线，先手比分加1，棋盘清空，开始下一回合。依据：[独立业务规则](../Shardy规则.md)及上游承诺检测胜负。不能用有缺陷的索引表达式作为测试预期。

实际：第1轮先手为X（`0`），对局 `m7oVQtZo9P`。第五步的双方广播均确认 `{"t":0,"x":2,"y":0}`；棋盘为 `[1,1,0,null,0,null,0,null,null]`，比分仍 `[0,0]`，轮到O（`1`），没有胜后 `round` 广播。失败断言：预期比分 `[1,0]`，实际 `[0,0]`。

原因：[Game.ts 第180行](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/Game.ts#L180)使用 `field[i][ROW_MAX_COUNT-i+1]`。当棋盘边长为3，实际检查的是 `[0][4]`、`[1][3]`、`[2][2]`，其中前两格越界，反对角线计数永远不能到3。应检查 `[0][2]`、`[1][1]`、`[2][0]`，即第二维 `ROW_MAX_COUNT-1-i`。第五步服务端日志实际记录 `row: 1, column: 1, diagonal: 1, diagonal2: 0`，与三子反对角线状态吻合。建议修复该共享判定索引并补两个先手方向的回归；本交付保留原版代码。

证据：

- [证据入口（各轮步骤/预期/实际、两端接口消息与服务端日志）](../evidence/shardy-known-defects/index.html)
- [被测 Game.ts 源码快照](../evidence/shardy-source/src-Game.ts.txt)

统一入口复现：

```sh
python -m gameqa run --config /path/to/config.local.toml --game shardy \
  --case SH-DEFECT-API-001 --rounds 1
```

当前原版预期退出码为1，表示正确业务预期被真实结果违反；没有 `xfail` 或把错误结果改成预期。每例结束先发送原版 `exit` 删除对局，再断开两个连接。修复后同一用例应通过，并检查横排获胜用例 `SH-WIN-API-001` 没有退化。
