# Stendhal 本地接入与隔离实验

固定主游戏版本：官方 `v1.49`，commit [`cbe0825e9b46f2a8adf9adce8c5747ece13b17a0`](https://github.com/arianne/stendhal/tree/cbe0825e9b46f2a8adf9adce8c5747ece13b17a0)。发行服务端使用 Marauroa 3.9.8。

`network_patch/NIONetworkConnectionManager.java` 保留官方 GPL 声明，源于官方 Marauroa commit `849cc668d727d4f62283d99bb56db5913dfdb31b`。唯一运行行为变化：把官方 TCP `bind(null)` 改为读取 `tcp_host`、默认 loopback，避免测试服务端监听局域网。

`web_patch/ItemMap.ts` 保留官方 AGPL 声明，修复新编译 Web 客户端实际启动时的循环依赖错误：模块顶层读取尚未初始化的 `SingletonRepo.singletons`，移到 `getCursor()` 内延迟执行。原始差异保存在 `lazy-config.diff`。这是客户端接入修复，不是故意注入的业务缺陷；测试报告应分别记录。

## 本地准备

Python 3.12+，Git，以及可执行 Node.js。所有下载、源码、配置、数据库和日志位于 `GAMEQA_WORK_DIR`（默认项目 `../../work`）下。没有全局安装。

```sh
python3 scripts/stendhal/setup.py --download-jdk --node /path/to/node
adapters/stendhal_bridge/build.sh --install-probe
scripts/stendhal/start.sh main
```

`--download-jdk` 只适用于 macOS arm64。其他主机提供 `--java /path/to/java`（JDK含javac）。已准备的工作目录直接复用固定版本下载，SHA256不匹配时停止；已有数据库不重置。`STENDHAL_JAVA`、`STENDHAL_NODE`、`GAMEQA_WORK_DIR` 可显式覆盖工具和目录。

主服务：TCP `127.0.0.1:32160`，HTTP/WS `127.0.0.1:8080`。命令前台保留进程；在另一个终端执行 `scripts/stendhal/stop.sh main` 停止。Android Chrome 使用 `adb reverse tcp:8080 tcp:8080`，打开 `http://127.0.0.1:8080/stendhal.html`。同源 `/ws/` 连接本地游戏服务器。

账号由协议桥创建，独立观察角色 `qaobserver`，UI目标 `qaplayer`，接口目标 `qaplayera`。本地随机凭据存 `work/stendhal/runtime/credentials.json`，禁止提交。

## 独立受控缺陷：购买 cheese 多扣 1 金币

```sh
python3 scripts/stendhal/build_fault.py
```

这一步仅构建，不启动第二个JVM。`runtime-fault/` 使用自己的全新H2数据库、配置、日志和端口（TCP32161/HTTP8081）；原版jar只读复用。`fault/classes/` 的 `SellerBehaviour.class` 仅在实验启动类路径中加载。原版源码与GPL声明保留在 `defects/overcharge/SellerBehaviour.java`，`overcharge.diff` 给出最小差异。

注入范围严格为角色名匹配 `qaplayer[a-z]*` 且购买 `cheese`，成交检查和扣款金额加 1。界面报价、原配置20金币和测试预期保持原样；多扣1金币应由实际前后状态断言检出。日志明确记录 `INJECTED_QA_DEFECT`。

主服与缺陷服有独立数据库和端口，可以并行运行。当前两服分别限制最大堆内存512MB，实验仅启动和停止缺陷服：

```sh
scripts/stendhal/start.sh fault
```

首次实验需要在TCP32161上重新创建测试账号/角色并完成fixture准备。实验测试配置切换至 `port=32161`、`url=http://127.0.0.1:8081/stendhal.html`、`server_log=../../work/stendhal/runtime-fault/log/server.log`；Android建立 `adb reverse tcp:8081 tcp:8081`。不要改变断言去接受21金币。

恢复原版：

```sh
scripts/stendhal/stop.sh fault
```

恢复测试配置到TCP32160/HTTP8080，对仍在运行的原版主服执行相同业务断言，记录回归结果。若主服原先未运行，使用 `scripts/stendhal/start.sh main` 启动。实验应在报告中明确标记为“注入缺陷检出”，不能当作原版游戏缺陷。

## 证据边界

主服务已经真实启动，TCP/HTTP均仅绑定127.0.0.1，H2创建成功；官方资源真实HTTP200。实际Android Chrome已显示登录界面，启动循环依赖修复由Airtest截图确认。账号创建、独立GM读取在线角色、fixture准备/恢复由真实协议验证。受控缺陷已经在独立缺陷服真实执行多轮，同一正确断言每轮得到预期60/实际59并判定failed，数据准备和恢复均通过；见[缺陷报告](../../docs/缺陷/注入-商店多扣金币.md)及[原始证据](../../docs/evidence/stendhal-injected/index.html)。原版回归由主服另行记录。
