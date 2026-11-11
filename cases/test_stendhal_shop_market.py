"""Xin Blanca 收购与 Harold 寄售费用。

两条实测得来的前提，写用例前必须先满足：
1. `buy_items.xml` 的 `type="buy"` 是 NPC 收购方向——向 Xin Blanca 说 `buy sword` 会被拒
   （"I don't sell swords."），要拿 60 money 必须用 `sell sword`。
2. Harold 有等级门槛：0 级说 sell 会被拒（"only accept offers from people who have a good
   reputation"）。等级表 xp[6]=1700，因此寄售用例统一 prepare(xp=1700)。
"""
import pytest

from gameqa.shop import HAROLD as HAROLD_NPC, clear_offers, confirm, post_offer, sell
from gameqa.sources import BUY_ITEMS_XIN, PREPARE_OFFER, SHOP_TRADE_REPLIES, TRADING_FEE
from gameqa.stendhal import confirm as answer, hello, quantity, said

XIN = "Xin Blanca"
HAROLD = "Harold"
MARKET_LEVEL_XP = 1700


@pytest.mark.case(id="ST-SHOP-API-010", game="stendhal", module="shop", kind="api",
                  title="向Xin Blanca出售sword得60金币")
def test_sell_sword_to_xin_blanca(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"sword": 1}, xp=0, near_npc=XIN)
    qa.check("准备后持有一把sword", quantity(before, "sword"), 1, BUY_ITEMS_XIN)

    quotation = hello(api_player, XIN) + sell(api_player, "sword")
    qa.check("Xin Blanca实际报出60金币收购价", said(quotation, XIN, "60"), True, BUY_ITEMS_XIN)

    deal = confirm(api_player, "yes")
    qa.check("Xin Blanca实际确认收购", said(deal, XIN, "Thanks! Here is your money."), True,
             SHOP_TRADE_REPLIES)
    after = observer.inspect()
    qa.check("收购后金币为160", after["money"], 160, BUY_ITEMS_XIN)
    qa.check("收购后sword已交出", quantity(after, "sword"), 0, BUY_ITEMS_XIN)


def prepare_clean(player, prepare, **fields):
    """先清掉残留寄售，再重置状态。

    寄售不随 prepare 的快照恢复，而且撤单会把物品退回背包、污染本条用例的数量预期，
    所以必须"先清寄售、再 prepare"，最后重新建立与 Harold 的会话。
    """
    hello(player, HAROLD)
    clear_offers(player)
    state = prepare(**fields)
    hello(player, HAROLD)
    return state


@pytest.mark.case(id="ST-SHOP-API-011", game="stendhal", module="shop", kind="api",
                  title="寄售费用为总价的1%：总价1000收10")
def test_market_fee_is_one_percent(qa, api_player, observer, prepare):
    before = prepare_clean(api_player, prepare, xp=MARKET_LEVEL_XP, money=200, items={"flask": 2}, near_npc=HAROLD)
    qa.check("准备后达到寄售所需等级", before["level"] >= 6, True, PREPARE_OFFER)

    quotation = post_offer(api_player, "flask", 1000)
    qa.check("Harold实际报出10金币交易费", said(quotation, HAROLD, "It would cost you 10 money."),
             True, TRADING_FEE)

    posted = confirm(api_player, "yes")
    qa.check("Harold实际确认上架并扣费", said(posted, HAROLD, "took the fee of 10"), True, TRADING_FEE)
    after = observer.inspect()
    qa.check("上架后金币为190", after["money"], 190, TRADING_FEE)
    qa.check("上架后交出一瓶flask", quantity(after, "flask"), 1, TRADING_FEE)


@pytest.mark.case(id="ST-SHOP-API-013", game="stendhal", module="shop", kind="api",
                  title="交易费不足时拒绝上架且不改动状态")
def test_market_fee_shortage_rejects_listing(qa, api_player, observer, prepare):
    before = prepare_clean(api_player, prepare, xp=MARKET_LEVEL_XP, money=9, items={"flask": 1}, near_npc=HAROLD)
    qa.check("准备后金币不足以支付10金币交易费", before["money"], 9, TRADING_FEE)

    quotation = post_offer(api_player, "flask", 1000)
    qa.check("报价阶段未直接完成上架", said(quotation, HAROLD, "took the fee"), False, TRADING_FEE)

    confirm(api_player, "yes")
    after = observer.inspect()
    qa.check("费用不足时金币仍为9", after["money"], 9, TRADING_FEE)
    qa.check("费用不足时flask未被移交", quantity(after, "flask"), 1, TRADING_FEE)
