# 本项目 Shardy 测试展示客户端

这是本项目编写的最小浏览器客户端，不是官方 Unity 客户端，也不能代表官方客户端的测试覆盖。

客户端通过真实 Shardy WebSocket 协议连接官方服务端：四字节消息头、自定义握手、确认及心跳。棋盘和比分仅根据官方广播更新；客户端不自行计算胜负、不替换服务端规则。`window.shardyState` / `window.shardyMessages` 仅保留接收状态供诊断，预期结果仍应来自独立测试规则。

启动：

```sh
node outputs/airtest-game-qa/integrations/shardy_client/server.mjs
```

Android 模拟器中使用内置 Chrome，先设置两个本地反向端口：

```sh
adb -s emulator-5554 reverse tcp:3000 tcp:3000
adb -s emulator-5554 reverse tcp:3001 tcp:3001
adb -s emulator-5554 shell am start -a android.intent.action.VIEW \
  -d http://127.0.0.1:3001/ -p com.android.chrome
```

点击“连接”、再点“开始匹配”；API 对手使用 JSONL 桥的 `connect/start`。服务端约一秒匹配、再延迟两秒开始回合。读取广播中的实际玩家编号和当前轮次后落子。按钮 ID 为 `connect/start/disconnect/cell-0` 到 `cell-8`；比分为 `score-x/score-o`。

已验证 HTTP 返回、语法及双 API 玩家协议链路，也已用 Airtest 完成 Android 真实落子与棋子图像断言，连续多轮通过。见[界面验收证据](../../docs/evidence/shardy-ui-baseline/index.html)；该结果只覆盖本项目展示客户端。
