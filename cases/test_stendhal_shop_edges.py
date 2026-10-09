"""Margaret purchases: cancellation, duplicate confirmation and quantity boundaries."""

import pytest

from gameqa.shop import NPC, confirm, offer, stock
from gameqa.sources import (NORMAL_PRICE, PARSER_EXPRESSION, PARSER_SENTENCE, PREFIX_MANAGER,
                            SELLER_ADDER, SELLER_BEHAVIOUR, SELL_ITEMS_PRICES)
from gameqa.stendhal import await_quantity, hello, leave, quantity, said


@pytest.mark.case(id="ST-SHOP-API-004", game="stendhal", module="shop", kind="api", title="报价后取消→重新报价→成交→重复yes不重复扣款")
def test_cancel_then_purchase_and_repeat_confirmation(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 0}, near_npc=NPC)
    if "last_player_kill_time" in before["attributes"]:
        qa.data["failure_kind"] = "preparation_error"
        raise ValueError("普通价格测试需要无 last_player_kill_time 标记的角色")
    qa.check("普通价格前置：角色没有玩家击杀加价标记",
             "last_player_kill_time" in before["attributes"], False, NORMAL_PRICE)
    quotation = hello(api_player, NPC) + offer(api_player, "cheese", 2)
    qa.check("NPC实际报出2件共40金币的报价", said(quotation, NPC, "will cost 40."),
             True, SELL_ITEMS_PRICES + "; " + SELLER_ADDER + "#L156-L175")
    cancellation = confirm(api_player, "no")
    qa.check("NPC实际确认取消", said(cancellation, NPC, "Ok, how else may I help you?"),
             True, SELLER_ADDER + "#L203-L209")
    cancelled = observer.inspect()
    qa.check("取消报价不扣金币", cancelled["money"], 100, SELLER_ADDER + "#L203-L209")
    qa.check("取消报价不发道具", quantity(cancelled, "cheese"), 0, SELLER_ADDER + "#L203-L209")

    quotation = offer(api_player, "cheese", 2)
    qa.check("取消后可重新获得同一报价", said(quotation, NPC, "will cost 40."),
             True, SELLER_ADDER + "#L156-L175")
    purchase = confirm(api_player)
    qa.check("NPC实际确认第一次成交", said(purchase, NPC, "Congratulations!"),
             True, SELLER_BEHAVIOUR + " (transactAgreedDeal)")
    purchased = await_quantity(observer, "cheese", 2)
    qa.check("一次成交后金币为60", purchased["money"], 60, SELL_ITEMS_PRICES)
    qa.check("一次成交后cheese为2", quantity(purchased, "cheese"), 2, SELLER_BEHAVIOUR)

    repeated = confirm(api_player, "yes") + stock(api_player)
    qa.check("重复确认后NPC仍可回答商品列表", said(repeated, NPC, "I sell "),
             True, SELLER_ADDER + "#L80-L90")
    qa.check("重复确认没有第二次成交回复", said(repeated, NPC, "Congratulations!"),
             False, SELLER_ADDER + "#L182-L200 (yes仅在BUY_PRICE_OFFERED成交并返回ATTENDING)")
    after = observer.inspect()
    qa.check("重复yes不再次扣款", after["money"], 60, SELLER_ADDER + "#L182-L200")
    qa.check("重复yes不再次发货", quantity(after, "cheese"), 2, SELLER_ADDER + "#L182-L200")
    leave(api_player)


@pytest.mark.parametrize(
    "request_amount,money,reply_fragment,expected_quantity,expected_money,rule",
    [
        pytest.param("0", 100, "how many pieces of cheese", 0, 100,
                     SELLER_ADDER + "#L176-L178; " + PREFIX_MANAGER,
                     id="zero", marks=pytest.mark.case(
                         id="ST-SHOP-API-005-zero", game="stendhal", module="shop", kind="api", title="数量输入0：NPC反问数量、不扣款不发货")),
        pytest.param("-1", 100, "negative amount: -1", 0, 100, PARSER_SENTENCE,
                     id="negative", marks=pytest.mark.case(
                         id="ST-SHOP-API-005-negative", game="stendhal", module="shop", kind="api", title="数量输入-1：NPC拒绝负数量、不扣款不发货")),
        pytest.param("1.5", 100, "will cost 40.", 2, 60, PARSER_EXPRESSION,
                     id="fraction", marks=pytest.mark.case(
                         id="ST-SHOP-API-005-fraction", game="stendhal", module="shop", kind="api", title="数量输入1.5：按2件报价40、成交后金币60")),
        pytest.param("1000", 20000, "will cost 20000.", 1000, 0, SELLER_ADDER + "#L129-L175",
                     id="maximum", marks=pytest.mark.case(
                         id="ST-SHOP-API-005-maximum", game="stendhal", module="shop", kind="api", title="数量输入1000（上限）：报价20000、成交后金币0")),
        pytest.param("1001", 20000, "which I can sell at once is 1000.", 0, 20000,
                     SELLER_ADDER + "#L129-L139", id="over-maximum", marks=pytest.mark.case(
                         id="ST-SHOP-API-005-over-maximum", game="stendhal", module="shop", kind="api", title="数量输入1001（超上限）：提示单次上限1000、不成交")),
    ],
)
def test_purchase_quantity_parsing_and_limit(
        qa, api_player, observer, prepare, request_amount, money,
        reply_fragment, expected_quantity, expected_money, rule):
    before = prepare(money=money, items={"cheese": 0}, near_npc=NPC)
    if "last_player_kill_time" in before["attributes"]:
        qa.data["failure_kind"] = "preparation_error"
        raise ValueError("普通价格测试需要无 last_player_kill_time 标记的角色")
    qa.check("普通价格前置：角色没有玩家击杀加价标记",
             "last_player_kill_time" in before["attributes"], False, NORMAL_PRICE)
    response = hello(api_player, NPC) + offer(api_player, "cheese", request_amount)
    qa.check("NPC实际给出本数量输入的报价或拒绝理由",
             said(response, NPC, reply_fragment), True, rule + "; " + SELL_ITEMS_PRICES)
    quoted = observer.inspect()
    qa.check("报价或拒绝阶段尚未扣款", quoted["money"], money, SELLER_ADDER + "#L125-L179")
    qa.check("报价或拒绝阶段尚未发货", quantity(quoted, "cheese"), 0, SELLER_ADDER + "#L125-L179")

    # Confirm once even after rejection, to prove it cannot commit a rejected request.
    confirmation = confirm(api_player)
    if expected_quantity:
        qa.check("有效数量的确认确实成交", said(confirmation, NPC, "Congratulations!"),
                 True, SELLER_BEHAVIOUR + " (transactAgreedDeal)")
        after = await_quantity(observer, "cheese", expected_quantity)
    else:
        qa.check("拒绝的数量没有成交回复", said(confirmation, NPC, "Congratulations!"),
                 False, SELLER_ADDER + "#L129-L178")
        # The offer response is positive evidence that the conversation remains active.
        stock_reply = stock(api_player)
        qa.check("拒绝和yes后NPC仍可回答商品列表", said(stock_reply, NPC, "I sell "),
                 True, SELLER_ADDER + "#L80-L90")
        after = observer.inspect()
    qa.check("确认后金币符合规则", after["money"], expected_money, SELL_ITEMS_PRICES + "; " + rule)
    qa.check("确认后道具数量符合规则", quantity(after, "cheese"), expected_quantity,
             SELLER_BEHAVIOUR + "; " + rule)
    leave(api_player)
