import pytest

from gameqa.stendhal import await_quantity, quantity
from gameqa.sources import SELL_ITEMS_PRICES




@pytest.mark.case(id="ST-SHOP-UI-001", game="stendhal", module="shop", kind="ui", title="界面购买2个cheese：扣40金币、背包+2")
def test_android_purchase_has_correct_money_and_inventory(qa, stendhal_ui, observer, prepare):
    # The patrol's whole x11..18/y3..4 route stays within chat range from (15,7).
    before = prepare(money=100, items={"cheese": 0}, zone='int_semos_tavern_0', x=15, y=7)
    qa.check("独立管理员读取的是UI角色", before["name"], "qaplayer", "本地隔离UI账户配置")
    stendhal_ui.android.screenshot("准备完成：金币100、cheese0、Margaret商店")
    stendhal_ui.dialogue("bye", "hi Margaret", "buy 2 cheese", "yes")
    after = await_quantity(observer, "cheese", 2)
    qa.check("UI购买2个cheese扣除40金币", after["money"], 60, SELL_ITEMS_PRICES)
    qa.check("UI购买使背包获得2个cheese", quantity(after, "cheese"), 2, SELL_ITEMS_PRICES)
    stendhal_ui.android.screenshot("购买结果：界面与服务器数据同时留证")
