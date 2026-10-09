# Shardy 业务断言依据

被测版本：官方 `mopsicus/shardy-tictactoe` 提交 `ed8e978917cbe5aba79009928e8c3b92a34b81cc`，Shardy 依赖锁定 `1.2.0`。测试直接连接原版服务端，两个真实 WebSocket 玩家；展示客户端是本项目编写的客户端，不代表官方 Unity 客户端覆盖。

独立井字棋规则：棋盘为 3×3；双方交替向空格落子；同一玩家的三枚棋子连成一行、一列、主对角线或反对角线即获胜；无人获胜且九格全部占满才和局。因此八枚棋子且无三子连线时必须保留棋盘并允许第九步。这些是测试预期，不从服务端的实际结果反推。

上游明确承诺匹配、落子、检测胜负与和局及保存比分，见[固定版本 README](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/README.md)。源码可用于产品特定行为：

| 行为 | 依据 |
|---|---|
| 初始比分 `[0,0]`、随机先手 | [Game.ts 83–89行](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/Game.ts#L83-L89) |
| 匹配后发 `play`，约两秒后发 `round` | [T3Service.ts](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/T3Service.ts#L176-L195) |
| 已占格、非本人轮次被忽略；合法落子向双方广播并推进轮次 | [Game.ts 137–154行](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/Game.ts#L137-L154) |
| 胜者加1分，棋盘清空，胜者为下一回合先手 | [Game.ts 188–192行](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/Game.ts#L188-L192) |

请求 ACK 不表示业务成功：[turn 命令](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/commands/turn.ts)无论 `makeTurn` 是否忽略该请求都返回 ACK。断言必须读取实际广播和两端状态。

四个正常用例（匹配、回合推进、非法落子、横排获胜与重置）归入 `core` 模块，方便统一入口一次连续跑多轮。两个原版缺陷用例位于 `known_defects`，使用正确预期并实际失败；未加 `xfail`、未修上游代码、未把缺陷的实际行为改作预期。

每例使用新的两个连接，结束时先发送原版 `exit` 删除对局，再断开；未匹配连接发送 `stop` 移出队列。API用例运行时不要同时向同一匹配队列加入第三个玩家。
