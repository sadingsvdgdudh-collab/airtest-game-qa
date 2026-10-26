# Stendhal-003：售出计数是"会话级"的，且持久化的 sold.* 被错装进 bought

类型：原版真实缺陷（未注入）。状态：已复现，未修复，**用例保留红**。严重程度：次要。
自动化回归：`ST-SHOP-API-007`、`ST-SHOP-API-009` 各多一条断言，稳定 failed；`ST-SHOP-API-008` 不涉及成交，仍为绿。
口径：同一用例里两条断言并存——持久计数必须对（已绿），游戏自认的会话字段必须对（红）。
**不许**再把红的那条删掉或改成读持久映射来消红。

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

**对测试的影响与处置（2026-10-26 修订）**：

- `gameqa.stendhal.sold_count` 读 `commerce.looted_items["sold.<item>"]`（持久真值）——保留，断言数据没坏。
- 新增 `gameqa.stendhal.sold_count_session` 读 `item_counter_cache.sold`——这就是
  `Player.getQuantityOfSoldItems()` 的来源，成就判定用的正是它。
- `ST-SHOP-API-007/009` 各加一条会话字段的增量断言，**预期红**：

| 用例 | 断言 | 期望 | 实测 |
|---|---|---|---|
| ST-SHOP-API-007 | 游戏自认的售出计数增量 | 2 | **6** |
| ST-SHOP-API-009 | 游戏自认的售出计数增量 | 1 | **5** |

（007 的持久计数同轮为 2，正确；说明写坏的不是数据，是读取路径。）
`ST-SHOP-API-008`（数量不足被拒）两条都是 0，仍为绿——它守的是"没成交就不记账"。
上游修好构造器后，这两条会自己变绿，不需要改用例。

**未做**：没有改原版源码（本项目的原则是不动上游业务逻辑）；本缺陷不影响"买卖是否成交/金币是否正确"，
只影响售出计数的持久性与成就判定。
