"""Instant potion consumption, with independently restored boundary variants."""
import pytest

from gameqa.stendhal import await_exact_quantity, quantity, use
from gameqa.sources import SOURCE


POTION = SOURCE + "data/conf/items/drinks.xml#L517-L538"
FEEDER = SOURCE + "src/games/stendhal/server/entity/item/consumption/FeederFactory.java#L27-L35; " + SOURCE + "src/games/stendhal/server/entity/item/consumption/Stuffer.java#L18-L25"
HEAL = SOURCE + "src/games/stendhal/server/entity/RPEntity.java#L397-L420"
USE = SOURCE + "src/games/stendhal/server/actions/UseAction.java#L77-L117"


@pytest.mark.parametrize("missing_hp", [
    pytest.param(60, id="heal-50", marks=pytest.mark.case(
        id="ST-BAG-API-007-heal", game="stendhal", module="inventory", kind="api", title="缺60血时喝即时药水：一次一瓶、回复50且不超出上限")),
    pytest.param(10, id="cap-at-max", marks=pytest.mark.case(
        id="ST-BAG-API-007-cap", game="stendhal", module="inventory", kind="api", title="只缺10血时喝即时药水：回复按最大HP封顶（不溢出）")),
])
def test_minor_potion_heals_once_without_exceeding_maximum(qa, api_player, observer, prepare, missing_hp):
    original = observer.inspect()
    maximum = original["base_hp"]
    # This batch does not prepare or restore persistent status effects.
    if original["statuses"] or original["attributes"].get("target") or maximum <= missing_hp:
        qa.data["failure_kind"] = "preparation_error"
        raise ValueError("Potion fixture needs a living character with enough maximum HP, no combat and no active status")
    before = prepare(items={"minor potion": 2}, hp=maximum - missing_hp,
                     zone="int_semos_guard_house", x=12, y=12)
    qa.check("前置：没有持续状态或主动战斗", [before["statuses"], before["attributes"].get("target")],
             [[], None], "独立安全地图前置；helper 不恢复持续状态")
    qa.check("前置：两瓶药水与指定血量", [quantity(before, "minor potion"), before["hp"]],
             [2, maximum - missing_hp], "测试数据：minor potion=2；HP=最大HP减缺失量")
    use(api_player, before, "minor potion")
    after = await_exact_quantity(observer, "minor potion", 1)
    qa.check("一次使用只消耗一瓶", quantity(after, "minor potion"), 1, FEEDER)
    qa.check("药水回复50HP并受最大HP限制", after["hp"],
             min(maximum, before["hp"] + 50), POTION + "; " + FEEDER + "; " + HEAL)
    qa.check("使用没有改变最大HP、XP、金币", [after[key] for key in ("base_hp", "xp", "money")],
             [before[key] for key in ("base_hp", "xp", "money")], USE + "; " + HEAL)
    qa.check("即时药水不创建食物持续回复状态", after["statuses"], [], FEEDER)
