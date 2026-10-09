# Shardy 第二游戏真实接口验证

本轮使用官方提交 `ed8e978917cbe5aba79009928e8c3b92a34b81cc`、锁定 Shardy `1.2.0`，业务源码未修改。[源码快照、校验和及版本](evidence/shardy-source/source.json)随证据保存。实际连接两个官方 Shardy Bot WebSocket 客户端，匹配与落子均经过官方业务流程；不是框架单元测试或内存模拟。

| 稳定用例ID | 业务 | 模块 | 真实多轮结果 |
|---|---|---|---|
| SH-MATCH-API-001 | 双玩家匹配、身份互补、空棋盘与初始比分 | core | 5/5 passed |
| SH-TURN-API-001 | 合法落子广播、双方棋盘一致、轮次推进 | core | 5/5 passed |
| SH-ILLEGAL-API-001 | 非本人轮次与已占格请求不改变状态 | core | 5/5 passed |
| SH-WIN-API-001 | 横排获胜、加分、清空、保留比分与下一回合落子 | core | 5/5 passed |
| SH-DEFECT-API-001 | 反对角线三子应结算胜利 | known_defects | 5/5 failed（原版缺陷） |
| SH-DEFECT-API-002 | 无胜者时八枚棋子应保留等待第九步 | known_defects | 5/5 failed（原版缺陷） |

两组均判定一致，无不稳定、跳过或执行错误。正常组20次业务用例通过，返回码每轮为0；原版缺陷组10次真实业务断言失败，返回码每轮为1。原版缺陷与受控注入实验分开，没有对缺陷使用 `xfail`。

共用能力是 `gameqa.bridge`、配置、pytest case标识与筛选、Evidence步骤和断言、接口消息脱敏、服务端日志及统一HTML/JSON报告。`gameqa.shardy.Shardy` 只实现本游戏的真实命令和广播观察。每个断言记录独立预期及来源，请求ACK不作为业务结果；先等待真实广播再比较双方棋盘、轮次与比分。

每例创建两个新连接，结束通过官方 `exit` 移除对局、未匹配连接通过 `stop` 移出队列，最后 `disconnect`。服务端日志显示每例删除自己的game ID后现有对局计数恒定，无本组新增残留；进程早先的 smoke/check_live 已有4个旧游戏对象，并非本组测试创建。API测试运行时不要同时在同一匹配队列加入第三位玩家。

可公开保留的实际报告：

- [正常多轮报告](evidence/shardy-api-baseline/index.html)及[摘要JSON](evidence/shardy-api-baseline/summary.json)
- [原版缺陷多轮报告](evidence/shardy-known-defects/index.html)及[摘要JSON](evidence/shardy-known-defects/summary.json)
- [反对角线缺陷报告](缺陷/Shardy-001-反对角线未结算.md)与[八步提前和局缺陷报告](缺陷/Shardy-002-八步提前和局.md)
- [业务规则与产品特定来源](Shardy规则.md)

报告按用例和轮次保存首次失败、真实消息、服务端日志、步骤、预期/实际及单独重跑命令。没有将后端HTTP可达或纯协议smoke计入业务用例结果。正常组最初版本的匹配来源行号误写为T3Service.ts 203–229行，已在代码和规则文档纠正为176–195行；原始执行报告按原样保留，未事后改写。

复现入口（配置含 `games.shardy.bridge_command/bridge_cwd/host/port/server_log`）：

```sh
python -m gameqa run --config /path/to/config.local.toml --game shardy \
  --module core --kind api --rounds 5
python -m gameqa run --config /path/to/config.local.toml --game shardy \
  --module known_defects --kind api --rounds 5
```

Android/Airtest另有 SH-TURN-UI-001 连续多轮passed、零重试：界面玩家和API对手各实际落一子，以原服广播、完整棋盘和指定格子的固定X/O图像分别校验双向互通，见[UI多轮报告](evidence/shardy-ui-baseline/index.html)。Android界面是本项目编写的浏览器展示客户端，不是官方Unity客户端；没有把这条UI用例计入上述20次API通过。
