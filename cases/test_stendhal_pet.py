"""买羊（Nishiya）：首次成交得羊，重复购买被拒且不重复扣钱。

设计条目 ST-PET-API-002（来源 S-PET）。原设计把 PET 标为 R2（停服+回滚），
这里能做成 R1：前置用真实购买达成，收尾用原版 `forsake` 放走羊——
买羊会在世界里生成一只生物，而快照恢复**不含宠物**，所以不在 finally 里放走就会一直"already has a sheep"。
"""
import pytest

from gameqa.pet import NPC, buy, forsake
from gameqa.sources import FORSAKE, SHEEP_PET, SHEEP_SELLER
from gameqa.stendhal import confirm, hello, leave, said


@pytest.mark.case(id="ST-PET-API-002", game="stendhal", module="pet", kind="api",
                  title="买羊：首次扣30得羊、重复购买被拒且不重复扣钱")
def test_second_sheep_purchase_is_refused_and_not_charged(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "只覆盖「重复购买被拒 + 不重复扣钱」这条边界；羊的喂养增重、跟随与跨区属 ST-PET-UI-001，"
        "不在本用例范围。探针只暴露一个家畜位，「仍只有1只」由 has_sheep 为真（原版上限即 1 只，"
        "见 SheepSellerNPC）加「没有第二笔扣款」共同支撑。"
    )
    before = prepare(money=130, near_npc=NPC)
    qa.check("前置：130 金币且当前没有羊",
             [before["money"], before["pet"]["has_sheep"]], [130, False],
             "测试夹具：money=130；" + SHEEP_PET)
    assert before["pet"]["animal"] is None, "前置失败：开始就有一只羊，用例无法构造重复购买场景"

    asked = hello(api_player, NPC) + buy(api_player)
    qa.check("NPC 实际报价：一只羊 30 金币",
             said(asked, NPC, "A sheep will cost 30. Do you want to buy it?"), True, SHEEP_SELLER)
    bought = confirm(api_player, "yes")
    qa.check("成交时 NPC 实际交出羊", said(bought, NPC, "Here you go"), True, SHEEP_SELLER)
    after_buy = observer.inspect()
    qa.check("首次购买扣 30：130→100", after_buy["money"], 100, SHEEP_SELLER)
    qa.check("首次购买后角色有且只有一只羊",
             [after_buy["pet"]["has_sheep"], after_buy["pet"]["has_pet"]], [True, False], SHEEP_PET)
    animal = after_buy["pet"]["animal"]
    qa.check("羊的归属是当前角色", [animal["type"], animal["owner"]], ["Sheep", qa.data.get("name", "qaplayera")],
             SHEEP_PET)

    again = buy(api_player) + confirm(api_player, "yes")
    qa.check("重复购买被明确拒绝",
             said(again, NPC, "look after that sheep you already have first"), True, SHEEP_SELLER)
    after_again = observer.inspect()
    qa.check("重复购买不扣钱：仍 100", after_again["money"], 100, SHEEP_SELLER)
    qa.check("重复购买后仍只有一只羊",
             [after_again["pet"]["has_sheep"], after_again["pet"]["has_pet"]], [True, False], SHEEP_PET)
    same = after_again["pet"]["animal"]
    qa.check("羊还是同一只（类型/归属/名字未变）",
             [same["type"], same["owner"], same["name"]], [animal["type"], animal["owner"], animal["name"]],
             SHEEP_PET)

    # 收尾：放走羊（快照恢复不含宠物，不放走会污染后续用例）
    forsake(api_player, after_again)
    import time
    time.sleep(1.5)
    cleaned = observer.inspect()
    qa.check("用例自行放走羊：收尾后没有羊", cleaned["pet"]["has_sheep"], False, FORSAKE)
    leave(api_player)
