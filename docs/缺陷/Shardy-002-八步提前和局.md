# Shardy-002：第八步无人获胜时提前清空棋盘

类型：原版真实缺陷，未注入。状态：已复现，未修复。严重程度：主要（第九步无法进行，错误结束尚未完成的回合）。自动化回归：`SH-DEFECT-API-002`，模块 `known_defects`。

版本与连接：[固定提交、依赖及源码校验](../evidence/shardy-source/source.json)。两个真实 Shardy Bot 玩家连接官方后端 `127.0.0.1:3000`，全部落子走原版业务命令，业务源码未改。

前置：双方真实匹配并收到 `round`，棋盘九格全空、比分 `[0,0]`；读取广播中的随机先手身份。

复现步骤（x列/y行，均从0开始）：依次交替落子 `(0,0)`、`(1,0)`、`(2,0)`、`(1,1)`、`(0,1)`、`(2,1)`、`(1,2)`、`(0,2)`。每步等待双方 `turn` 广播。此排列的行、列和两条对角线都没有三枚同方棋子。

预期：八枚棋子保留，只有 `(2,2)` 一格为空；比分不变，轮到初始先手走第九步。无胜者且九格全满才和局，见[独立业务规则](../Shardy规则.md)。

实际：第1轮先手为O（`1`），对局 `lIMVVyQrKZ`。第八步双方先收到 `{"t":0,"x":0,"y":2}`，紧接着收到新的 `round`，比分 `[0,0]`、轮次 `0`、棋盘九格全空。失败断言预期 `[1,0,1,1,0,0,0,1,null]`，实际 `[null,null,null,null,null,null,null,null,null]`。第九步所需的原棋盘已经丢失。

原因：[Game.ts 第193行](https://github.com/mopsicus/shardy-tictactoe/blob/ed8e978917cbe5aba79009928e8c3b92a34b81cc/src/Game.ts#L193)使用 `count === Math.pow(ROW_MAX_COUNT,2)-1`，3×3棋盘阈值被计算为8；第八次合法落子即进入清空和发新回合分支。第八步日志于 `2026-10-02T16:37:45.175Z` 记录落子，下一毫秒已向双方发送 `round`。建议和局阈值改为9，继续在和局前检查胜利，并覆盖“第九步获胜”和“第九步真正和局”；本交付保留原版代码。

证据：

- [证据入口（各轮步骤/预期/实际、两端接口消息与服务端日志）](../evidence/shardy-known-defects/index.html)
- [被测 Game.ts 源码快照](../evidence/shardy-source/src-Game.ts.txt)

统一入口复现：

```sh
python -m gameqa run --config /path/to/config.local.toml --game shardy \
  --case SH-DEFECT-API-002 --rounds 1
```

当前原版预期退出码为1。自动化不吞掉失败，不使用 `xfail`，不把提前清空作为预期。每例结束通过原版 `exit` 删除对局再断开；正确修复后同一回归用例应通过。
