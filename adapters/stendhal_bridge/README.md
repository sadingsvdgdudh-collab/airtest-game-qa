# Stendhal 1.49 的真实协议桥

Java 辅助进程复用官方 Marauroa 3.9.8 `ClientFramework` 和 `PerceptionHandler`。Python 通过 JSON Lines 调用，不重新实现登录握手、网络协议或感知增量合并。仅允许连接回环地址上的本地测试服。

`qaobserver` 是独立的管理员角色；UI 角色使用 `qaplayer`，接口用例使用 `qaplayera`。观察目标角色时不登录目标账号，避免挤掉界面会话。原版账号不接受数字，因此不使用 `qaplayer1`。

## 构建与启动

需要 JDK 21 和已解压的官方 `stendhal-server-1.49.zip`。源码和脚本留在项目中，官方游戏及依赖留在独立运行目录，不重复打包。

```sh
export JAVA_HOME=/absolute/path/to/jdk21
export STENDHAL_RUNTIME=/absolute/path/to/stendhal-server-1.49
export BRIDGE_BUILD_DIR=/absolute/path/to/bridge-classes
./build.sh --install-probe
./run.sh
```

当前工作区可省略这三个变量；脚本默认使用 `work/tools` 的便携 JDK 和 `work/stendhal/runtime`。自定义运行目录使用 `GAMEQA_WORK_DIR`，自定义 Java 可使用 `STENDHAL_JAVA` 指向 JDK 的 java 文件。`build.sh --install-probe` 将测试专用 `QaProbe.class`、`QaCombat.class` 及内部类放入服务端 `data/script/games/stendhal/server/script/`，按原版脚本加载机制首次调用时动态载入。先确认管理员名单 `data/conf/admins.txt` 仅授权独立 `qaobserver`。修改已经加载的 helper 前应先恢复所有活动快照、清理战斗夹具，再通过管理员 action `{"type":"script","target":"-unload QaProbe.class"}`（及 `QaCombat.class`）卸载脚本，或停服重新启动；直接复制新 class 不会替换已经加载的实例。

## JSON Lines 约定

每个输入行是一条请求，每个输出行是一条对应响应；第三方日志和异常栈全部写入 stderr。主程序顺序处理请求。

```json
{"id":1,"op":"connect","args":{"host":"127.0.0.1","port":32160}}
{"id":1,"ok":true,"result":{"connected":true,"host":"127.0.0.1","port":32160}}
```

失败返回 `{"id":1,"ok":false,"error":{"type":"...","message":"..."}}`。不会把发送成功当作业务成功。

| op | args | result |
| --- | --- | --- |
| `connect` | `host`、`port`，默认 127.0.0.1:32160 | TCP 连接状态 |
| `create_account` | `username`、`password`，可选 `email` | 服务端开户结果；应在登录前调用 |
| `login` | `username`、`password`，可选 `character` | 账号角色列表；给定角色时同时选角并等首个感知 |
| `create_character` | `character` | 已登录账号的真实创建结果 |
| `choose_character` | `character` | 选择后的自身感知；一个连接只能选一个角色 |
| `get_self_state` | 无 | 当前角色的合并感知和感知时间戳 |
| `get_world_state` | 无 | 当前角色可见区域的真实实体状态列表 |
| `send_action` | `action` 字段字典，必须含 `type` | `sent: true` 表示 SDK 已排队；随后读取状态和 NPC 回复断言 |
| `get_chat_messages` | 无 | 消费当前队列的 `{name,type,text,perception_timestamp}` 消息；含玩家普通文本及 NPC 的 `text` RPEvent |
| `get_events` | 无 | 消费 RPEvent 队列；附来源角色、类型和感知时间戳 |
| `inspect` | `target` | GM 在服务端读取指定在线测试角色的即时状态 |
| `prepare` | `target`，及下列准备字段 | `snapshot_id`、`before`、`after`、恢复字段清单 |
| `restore` | `target`、`snapshot_id` | 已核验的 `before`、`after`、`restored: true` |
| `combat_layout` | `target` | 当前地图宽高与可通行相邻格，只读 |
| `combat_prepare` | `target`，可选 `placement: near|far` | 原版 rat 副本的 `fixture_id` 与真实属性；仅限专用 UI/API 角色在 guard house 使用；默认near，far仅改变初始放置距离 |
| `combat_inspect` | `target`、`fixture_id` | rat/尸体属性、原服turn、next_to、squared_distance、近战角色range、attack_rate及target_fixture，只读 |
| `combat_cleanup` | `target`、`fixture_id` | 只移除该夹具持有的 rat/尸体实例，并核验不存在 |
| `disconnect` | 无 | 关闭连接并清空客户端状态 |

`inspect` 结果包含：

```text
name, attributes, slots, inventory, quests,
money, xp, hp, level, base_hp, karma, commerce,
atk_xp, def_xp, atk, def, keyed, item_counter_cache,
features, trade_state, bag_full, ground_items
```

`attributes` 保留服务端原始字符串；`slots` 递归保留槽位和对象；`inventory` 是所有槽位中的 Item 摘要，统计背包时需筛选 `slot == "bag"`。`money` 使用原版 `getNumberOfEquipped("money")`，不把银行金额算作可携带金币。

无储位购买用例只读`features`扩容状态、`trade_state`、原版bag是否满及目标所在区的全部地面Item树（`ground_items`），避免只看GM自己视野。这些字段不新增恢复范围；地面查询不枚举尸体内容或银行。关闭trade且没有content容器、双手占用、默认12槽满、无cheese堆时，才满足本例的无可用储位前置。

probe 限定 `qaobserver` 且管理员级别至少 1000，目标必须匹配 `qaplayer` 或带小写字母后缀的测试角色。目标在线且与观察角色不同。每个 probe 请求携带独立 UUID，响应身份再次匹配 `target`。

## 数据准备与恢复

`prepare` 支持：

- `money`：将背包中的金币设为指定数量。
- `items: {"cheese": 0, "beer": 1}`：设定指定背包物品的数量；零代表清除。非堆叠物品只支持数量 1。
- `quests: {"beer_hayunn": "start", "meet_hayunn": "done"}`：设定任务槽状态；null 清除指定任务。
- `xp`、`hp`、`karma`：准备测试需要的字段；原版 `setXP` 不触发升级，因此夹具按官方 `Level.getLevel(xp)` 同时准备等级，并按原版每级 10 HP 的规则校准基础 HP；显式 `hp` 最后应用。该步骤只准备一致前置状态，业务升级仍由真实任务奖励或击杀触发。
- `zone`、`x`、`y`：一起提供目标位置；或使用 `near_npc` 查找实际 NPC 并选择无障碍的相邻格。两种定位方式互斥。

示例：

```json
{"id":2,"op":"prepare","args":{"target":"qaplayera","money":100,"items":{"cheese":0},"near_npc":"Margaret"}}
```

辅助能力只负责准备、读取和恢复；购买走目标玩家的原版 `{"type":"chat","text":"hi"}`、`buy cheese`、`yes`。Margaret 的 cheese 单价是 20 gold。

快照恢复并核验：完整背包与八个装备槽物品字段（不比较重新生成的对象 ID）、所有任务状态、经验、HP、等级、基础 HP、karma、原地图位置攻击/防御技能等级与经验、`!kills`/`!tutorial`/`!visited`/`skills` 键值以及 `npc_purchases`/`npc_sales`/`looted_items` 的键值。若原位置被移动 NPC 或其他角色占用，仅接受同地图内曼哈顿距离不超过 1 的可通行相邻格，并明确返回 `location_adjusted`、原/实际坐标、最大距离和原因；其他数据仍精确匹配，超出边界拒绝恢复成功。经验升级会修改等级和基础 HP，因此这些字段分别保存并通过官方 setter 恢复。Marauroa 3.9.8 的 `removeMap` 不实际删除存储且 `getMap` 返回拷贝，commerce 使用 `remove(map,key)`/`put(map,key,value)` 恢复，并将不存在的 map 和空 map 统一表示为 `{}`。`PlayerLootedItemsHandler` 缓存八类物品统计；测试 GM helper 通过反射保存、恢复这些 Map 原值并单独核验，避免下次真实购买写回旧累计值，不修改业务实现。

目前不恢复银行、状态效果、成就、数据库审计/击杀日志、血迹或其他世界实体。不会声称整个角色或整个世界已恢复。快照仅在服务端进程内保存；每个目标只能存在一个活动快照，重启或卸载 probe 后旧快照无效。嵌套背包/装备和需要修改背包以外同名物品的准备会被明确拒绝。异常准备尝试回滚，失败核验保留快照并返回真实错误。

第一批药水边界用例需要无持续状态的前置，`inspect` 因此额外返回原版 `getStatusList().getStatuses()` 的名称列表 `statuses`。此字段只观察，不清除或恢复状态；药水子例发现持续状态、主动战斗或不足的最大HP时以准备错误结束，不把环境问题计为业务失败。

战斗夹具保留原版 rat 属性、掉落、AI 和死亡流程，派生类只记录死亡流程生成的尸体引用用于精确清理；不直接扣血或制造成功。玩家通过原版 `equip`、`attack`、`moveto` action 完成业务。夹具拒绝接近其他玩家的放置点，并要求既有 rat 击杀数低于 9，避免本次击杀跨越 rat 成就门槛。测试不领取随机掉落，普通 rat 无毒。rat 的 XML 配置经验为 5；`CreaturesXMLLoader.java:206` 加载时乘 20 得到内部 XP=100，`RPEntity.rewardKillers` 再乘 0.05，单人击杀的实际预期为 +5 XP。最少 1 XP 的分支只在分摊奖励取整为零时应用，不能跳过加载器直接从 XML 值计算。

`ST-COMBAT-UI-001`通过原版Android界面实际卸下木棍、装备短剑、长按rat并选择一次Attack；GM只观察击杀/经验/尸体。清理前先确认目标在线，意外离线时重新登录后再清理专用rat和尸体，然后由R1恢复角色，最后关闭浏览器。尸体窗口可能随随机掉落自动出现，不能把窗口必现或固定战斗秒数当作通过条件。

远距/取消异常走原版玩家协议：远距仍可设置target，非邻接且没有远程武器时不产生攻击伤害；取消必须发送`{"type":"stop","attack":""}`。按原服回合观察至少两倍实际attack_rate，逐次记录目标生命与玩家来源事件；取消后rat仍可反击。far在本基准从(17,5)放到(17,15)，保持AI与属性，避开(8,12)的GM。

## 已运行的最小检查

```sh
python3 check_live.py \
  --credentials /absolute/path/to/private/credentials.json \
  --evidence /absolute/path/to/check-evidence
```

私有凭据文件格式为 `{"qaobserver":{"username":"qaobserver","password":"...","character":"qaobserver"},"qaplayera":{...}}`，不要提交到公开仓库。

该检查在真实本地 Stendhal 1.49 服务端上运行，验证独立观察账号、100 → 80 gold、cheese +1、Margaret 的询价及成功回复、目标会话保持有效和核验后的数据恢复。它不替代 Airtest UI 用例，也不把协议操作称为界面自动化。原始请求响应证据省略密码，stderr 单独保存。

追加 `--occupy-original-tile` 会让管理员暂占原位置，验证相邻格恢复被明确标记且位移在允许范围内；最后恢复管理员位置。

## 官方依据

- [Marauroa ClientFramework](https://github.com/arianne/marauroa/blob/master/src/marauroa/client/ClientFramework.java)：开户、登录、选角和业务 action；编译以发行包内 3.9.8 jars 的实际签名为准。
- [Marauroa PerceptionHandler](https://github.com/arianne/marauroa/blob/master/src/marauroa/client/net/PerceptionHandler.java)：官方感知增量合并。
- [Stendhal v1.49 ScriptInJava](https://github.com/arianne/stendhal/blob/v1.49/src/games/stendhal/server/core/scripting/ScriptInJava.java)：动态加载本地测试服 Java 脚本。
- [DeepInspect](https://github.com/arianne/stendhal/blob/v1.49/src/games/stendhal/server/script/DeepInspect.java)：独立管理员读取在线角色的原版示例。
- [NPC 文本事件](https://github.com/arianne/stendhal/blob/v1.49/src/games/stendhal/server/entity/npc/NPC.java)、[事件名称](https://github.com/arianne/stendhal/blob/v1.49/src/games/stendhal/common/constants/Events.java)：NPC 回复使用名为 `text` 的 RPEvent。
- [商店定价](https://github.com/arianne/stendhal/blob/v1.49/data/conf/shops/sell_items.xml)：Margaret cheese 20、beer 10。
- [BeerForHayunn](https://github.com/arianne/stendhal/blob/v1.49/src/games/stendhal/server/maps/quests/BeerForHayunn.java)：非重复任务，交付一瓶 beer，奖励 20 gold、50 XP、10 karma。

官方游戏和 Marauroa 是 GPL 软件；使用和分发时保留官方许可证，不把第三方代码或其许可归为项目原创成果。
