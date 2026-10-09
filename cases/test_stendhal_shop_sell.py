"""ST-SHOP-API-007/008：把 cheese 卖给 Siandra（Ados 酒吧 keeper）的正常与数量不足分支。"""
import pytest

from gameqa.shop import NPC, SIANDRA, buy_and_confirm, confirm, sell
from gameqa.sources import FOOD_ITEMS, SELL_ITEMS_PRICES, SELL_TO_KEEPER_PRICES, SHOP_TRADE_REPLIES
from gameqa.stendhal import (await_exact_quantity, await_quantity, hello, leave, quantity, said,
                             sold_count, use)

TAVERN = "int_semos_tavern_0"      # Margaret 所在的 Semos 酒馆


def bought_two_cheese_with_money_deducted(state):
    """买入 2 个 cheese 的完成态：到货 2 个且金币被扣到 60。

    到货与扣款是两次属性更新，只等数量会读到"东西到手但钱还没扣"的中间态（实测踩到）。
    """
    return quantity(state, "cheese") == 2 and state["money"] == 60      # Margaret 所在的 Semos 酒馆


@pytest.mark.case(id="ST-SHOP-API-007", game="stendhal", module="shop", kind="api",
                  title="出售2个cheese给Siandra：单价5、金币20→30、售出计数+2")
def test_sell_two_cheese_to_keeper(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "NPC 报价台词含物品名（动态拼接），只断言其中的价格部分；价格 10 来自设计条目与 "
        "buy_items.xml 的 cheese=5，台词模板本身来自 2026-10-08 实测观测。"
    )
    before = prepare(money=20, items={"cheese": 3}, near_npc=SIANDRA)
    qa.check("出售前金币20", before["money"], 20, "测试夹具：money=20")
    qa.check("出售前有3个cheese", quantity(before, "cheese", "bag"), 3, "测试夹具：cheese=3")
    try:
        messages = hello(api_player, SIANDRA) + sell(api_player, "cheese", 2) + confirm(api_player)
        after = observer.inspect()
        qa.check("NPC实际报出2件收购价10",
                 said(messages, SIANDRA, "are worth 10. Do you want to sell them?"),
                 True, SELL_TO_KEEPER_PRICES)
        qa.check("NPC实际确认收款", said(messages, SIANDRA, "Thanks! Here is your money."),
                 True, SELL_TO_KEEPER_PRICES)
        qa.check("出售2件后cheese剩1", quantity(after, "cheese", "bag"), 1, SELL_TO_KEEPER_PRICES)
        qa.check("出售2件收入10：金币20→30", after["money"], 30, SELL_TO_KEEPER_PRICES)
        qa.check("售出计数增量恰好2",
                 sold_count(after, "cheese") - sold_count(before, "cheese"), 2,
                 SELL_TO_KEEPER_PRICES + "; commerce.looted_items[sold.cheese]（持久计数；sold 字段有 1.49 构造器 bug）")
    finally:
        leave(api_player)


@pytest.mark.case(id="ST-SHOP-API-008", game="stendhal", module="shop", kind="api",
                  title="出售数量不足（只有1个却卖2个）：NPC拒绝、金币与计数都不变")
def test_sell_more_than_held_is_refused(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "拒绝台词的出处：设计条目标记 S-BUYER，但本检出不含该行为类（behaviour/ 只有 journal 子目录），"
        "无法引用官方行号。断言取自 2026-10-08 实测观测，且只取稳定片段（台词含物品名，属动态拼接）。"
        "这条断言的权威性弱于状态断言——它锁的是当前实现，不是设计意图。"
        "另实测：数量不足在报价阶段不校验，报价照旧发出，只有确认之后才拒绝（所以动作序列含 yes）。"
    )
    before = prepare(money=20, items={"cheese": 1}, near_npc=SIANDRA)
    try:
        messages = hello(api_player, SIANDRA) + sell(api_player, "cheese", 2) + confirm(api_player)
        after = observer.inspect()
        qa.check("NPC实际拒绝数量不足",
                 said(messages, SIANDRA, "Sorry! You don't have that many pieces of"),
                 True, SELL_TO_KEEPER_PRICES + "; 实测观测")
        qa.check("拒绝后cheese仍为1", quantity(after, "cheese", "bag"), 1, SELL_TO_KEEPER_PRICES)
        qa.check("拒绝后金币仍为20", after["money"], 20, SELL_TO_KEEPER_PRICES)
        qa.check("拒绝后售出计数无增量",
                 sold_count(after, "cheese") - sold_count(before, "cheese"), 0,
                 SELL_TO_KEEPER_PRICES + "; commerce.looted_items[sold.cheese]（持久计数；sold 字段有 1.49 构造器 bug）")
    finally:
        leave(api_player)


@pytest.mark.case(id="ST-SHOP-API-009", game="stendhal", module="shop", kind="api",
                  title="跨区买卖与消耗：Margaret买2个→Siandra卖1个→吃掉剩下的1个")
def test_cross_area_buy_sell_then_eat(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "两段准备：第一段在 Semos 酒馆向 Margaret 买 2 个，第二段传送到 Ados 酒吧向 Siandra 卖 1 个并吃掉剩下的 1 个。"
        "分段准备的效果不跨段保留，所以第二段的前置显式写出第一段的实测结果（money=60、cheese=2）。"
        "实测异常：真实买过之后，第一次向另一个 NPC 确认会被忽略（报价正常、yes 无任何回应），"
        "因此第二段的卖出会先 bye 重开一次会话再确认；该异常已登记进 docs/能力清单.md 的已知脆弱点。"
        "另实测：吃掉 cheese 不产生持续状态（statuses 仍为空），故只断言消耗本身，不断言状态效果。"
    )
    # 第一段：Semos 酒馆，向 Margaret 买 2 个
    tavern = prepare(money=100, items={"cheese": 0}, zone=TAVERN, x=15, y=7)
    qa.check("前置：酒馆里100金币、没有cheese", [tavern["money"], quantity(tavern, "cheese")],
             [100, 0], "测试夹具：money=100、cheese=0")
    messages = hello(api_player, NPC) + buy_and_confirm(api_player, "cheese", 2)
    # 到货和扣款是两次属性更新：只等"数量到 2"会读到还没扣款的状态（实测金币仍 100）。
    # 等"数量到 2 且金币 60"这个组合状态出现，再做断言，避免用例自己制造竞态。
    bought = await_quantity(observer, "cheese", 2)
    if bought["money"] != 60:
        bought = observer.await_state(bought_two_cheese_with_money_deducted, "等待买入 2 件扣款到账", timeout=5)
    qa.check("NPC实际报出2件价40", said(messages, NPC, "will cost 40. Do you want to buy them?"),
             True, SELL_ITEMS_PRICES)
    # 成交回话是"这次动作真的生效了"的直接证据。实测有过一次丢动作：报价和 yes 都在，
    # 但没有任何成交回话、金币也没扣——只断言金币会把"动作丢失"伪装成金额不符。
    qa.check("NPC实际回话确认交付", said(messages, NPC, "Congratulations! Here are your pieces of cheese!"),
             True, SHOP_TRADE_REPLIES)
    qa.check("买入2件花费40：金币100→60", bought["money"], 60, SELL_ITEMS_PRICES)
    qa.check("买入后背包有2个cheese", quantity(bought, "cheese"), 2, SELL_ITEMS_PRICES)
    leave(api_player)

    # 第二段：Ados 酒吧，把第一段的结果显式带过来
    bar = prepare(money=60, items={"cheese": 2}, near_npc=SIANDRA)
    qa.check("前置：第一段的实测结果被显式带进第二段",
             [bar["money"], quantity(bar, "cheese")], [60, 2], "测试夹具：延续第一段结果 60/2")
    quoted = hello(api_player, SIANDRA) + sell(api_player, "cheese", 1) + confirm(api_player)
    qa.check("NPC实际报出1件价5", said(quoted, SIANDRA, "is worth 5. Do you want to sell it?"),
             True, SELL_TO_KEEPER_PRICES)
    # 实测：买过之后第一次确认会被吞；重开会话再卖一次即可（见 coverage_limit）
    leave(api_player)
    retried = hello(api_player, SIANDRA) + sell(api_player, "cheese", 1) + confirm(api_player)
    qa.check("第二次出售得到成交回话", said(retried, SIANDRA, "Thanks! Here is your money."),
             True, SHOP_TRADE_REPLIES)
    sold = await_exact_quantity(observer, "cheese", 1)
    qa.check("重开会话后成交：金币60→65", sold["money"], 65, SELL_TO_KEEPER_PRICES)
    qa.check("卖出1件后cheese剩1", quantity(sold, "cheese"), 1, SELL_TO_KEEPER_PRICES)
    qa.check("售出计数增量恰好1", sold_count(sold, "cheese") - sold_count(bar, "cheese"), 1,
             SELL_TO_KEEPER_PRICES + "; commerce.looted_items[sold.cheese]（持久计数；sold 字段有 1.49 构造器 bug）")

    # 吃掉剩下的 1 个
    use(api_player, sold, "cheese")
    eaten = await_exact_quantity(observer, "cheese", 0)
    qa.check("吃掉最后1个：cheese归零", quantity(eaten, "cheese"), 0, FOOD_ITEMS)
    qa.check("消耗不影响金币：仍65", eaten["money"], 65, FOOD_ITEMS + "; " + SELL_TO_KEEPER_PRICES)
    # cheese 是食物：真机消耗会回血（实测 95→96），所以只断言没有被扣血
    qa.check("消耗不会降低生命值", eaten["hp"] >= sold["hp"], True, FOOD_ITEMS)
    leave(api_player)
