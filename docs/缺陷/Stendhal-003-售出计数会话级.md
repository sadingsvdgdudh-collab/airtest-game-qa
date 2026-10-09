# Stendhal-003：售出计数是"会话级"的，且持久化的 sold.* 被错装进 bought

类型：原版真实缺陷（未注入）。状态：已复现，未修复（对用例的影响已绕开）。严重程度：次要。
自动化回归：无（本缺陷由 `ST-SHOP-API-007/008/009` 的"计数增量"断言暴露，用例改为读持久映射后为绿）。

版本：Stendhal `1.49`（源码提交 `cbe0825e9b46f2a8adf9adce8c5747ece13b17a0`）。

**缺陷一：构造器把 `sold.*` 装进了 `bought`。**
`src/games/stendhal/server/entity/player/PlayerLootedItemsHandler.java` 构造器按前缀把持久化的
`looted_items` 映射装回 8 个计数 map：`produced./obtained./mined./harvested./bought.` 都装进各自的 map，
但第 78 行是 `if (item.contains("sold.")) bought.put(item.replace("sold.", ""), ...)`——**sold 装进了 bought**，
而 `sold` 这个 map **从不被加载**。

**缺陷二：因此 `Player.getQuantityOfSoldItems()` 是会话级的。**
它读的是 `sold` map（`itemCounter.getQuantityOfSoldItems`，即上面那个从不加载的 map），
所以每次登录都从 0 开始。凡是依赖它的地方（例如 COMMERCE 类成就里按售出数量判定的条件
`achievement/condition/SoldNumberOfCondition.java`）都会在重登后从零计。

**实测证据**（`ST-SHOP-API-007` 的只读探针，卖 2 个 cheese 给 Siandra）：

| 时刻 | `item_counter_cache.sold`（会话级字段） | `commerce.looted_items["sold.cheese"]`（持久真值） |
|---|---|---|
| 卖前 | `{}` | `3` |
| 卖 2 件后 | `{"cheese": 5}` | `5` |

持久值正确地 +2（3→5）；而字段从"空"跳到 5——用它算增量会得到 3（卖 2 件）或 2（卖 1 件），
即**每次都多 1**。这也解释了为什么按字段写的断言会在真机上稳定多 1。

**对测试的影响与处置**：`gameqa.stendhal.sold_count` 改为读
`commerce.looted_items["sold.<item>"]`（持久真值），并在断言出处里注明原因；
`ST-SHOP-API-007/008/009` 的计数增量因此恢复正常（007 增量 2、009 增量 1，各 2 轮验证）。

**未做**：没有改原版源码（本项目的原则是不动上游业务逻辑）；本缺陷不影响"买卖是否成交/金币是否正确"，
只影响售出计数的持久性与成就判定。
