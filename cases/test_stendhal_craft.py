"""磨面（Jenny）材料不足：明确拒绝、不扣材料、不建订单。

设计条目 ST-CRAFT-API-002（来源 S-MILL、S-PRODUCE）。只覆盖负向路径；
正向（≥5 grain 磨出 1 袋 flour、订单 120 秒完成）属 ST-CRAFT-API-001。
"""
import pytest

from gameqa.craft import NPC, ORDER, mill
from gameqa.sources import SOURCE
from gameqa.stendhal import confirm, hello, leave, quantity, quest_phase, said

MILL = SOURCE + "src/games/stendhal/server/maps/semos/plains/MillerNPC.java#L63-L68 (requiredResources grain=5；ProducerBehaviour('jenny_mill_flour','mill','flour',…,2*60))"
PRODUCE = SOURCE + "src/games/stendhal/server/entity/npc/behaviour/impl/ProducerBehaviour.java (生产行为：按 requiredResources 校验并写订单槽)"


def ground_of(state, name):
    return sum(1 for item in state.get("ground_items", []) if item["name"] == name)


@pytest.mark.case(id="ST-CRAFT-API-002", game="stendhal", module="craft", kind="api",
                  title="磨面材料不足：明确拒绝、不扣材料、不建订单")
def test_mill_is_refused_when_grain_is_insufficient(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "只覆盖材料不足这条负向路径；正向（≥5 grain 磨出 flour、订单 120 秒完成、完成后领取）"
        "属 ST-CRAFT-API-001。实测：材料不足时 Jenny 在 mill 这一步就拒绝，不进入 yes/no 提问，"
        "所以设计动作里那一步 yes 不应有任何效果——本用例把这一点也断言了。"
    )
    before = prepare(items={"grain": 4, "flour": 0}, near_npc=NPC)
    qa.check("前置：4 份 grain、没有 flour、没有订单",
             [quantity(before, "grain"), quantity(before, "flour"), quest_phase(before, ORDER)],
             [4, 0, ""], "测试夹具：grain=4、flour=0、无 jenny_mill_flour 订单")

    asked = hello(api_player, NPC) + mill(api_player)
    qa.check("NPC 明确说明一袋需要 5 份 grain", said(asked, NPC, "bring me 5"), True, MILL)

    # 设计动作里含 yes；实测这一步不提问，所以 yes 必须无效（防止"多喊一句 yes 就把订单建起来"）
    ignored = confirm(api_player, "yes")
    after = observer.inspect()
    qa.check("材料不足时不进入确认提问（yes 没有任何 NPC 回应）",
             [m["text"] for m in ignored if m.get("type") == "npc"], [], MILL)

    qa.check("材料不足不扣 grain", quantity(after, "grain"), 4, MILL)
    qa.check("材料不足不产出 flour", quantity(after, "flour"), 0, MILL)
    qa.check("材料不足不建订单", quest_phase(after, ORDER), "", PRODUCE)
    qa.check("材料不足不在地面生成产物",
             [ground_of(after, "flour"), ground_of(after, "grain")],
             [ground_of(before, "flour"), ground_of(before, "grain")], PRODUCE)
    leave(api_player)
