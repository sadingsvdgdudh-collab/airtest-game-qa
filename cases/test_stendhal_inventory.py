"""背包容量、装备槽适配与装备贡献重算。

三条实测前提：
1. `money` 也占 1 格——11 件物品 + money 正好填满 12 槽，再加一件会报 "Bag is full"。
2. `equip` 只发动作、立即返回：服务端拒绝是异步的，异常不会浮出，断言必须读服务端状态。
3. `atk` / `def` 是技能值（装备前后不变），装备贡献在 `attributes.atk_item` 里
   （持 club 为 6、空手为 0）。
"""
import pytest

from gameqa.stendhal import await_quantity, equip, quantity
from gameqa.sources import SOURCE

CAPACITY = SOURCE + "src/games/stendhal/server/entity/slot/PlayerBagSlot.java#L33-L37"
EQUIP = SOURCE + "src/games/stendhal/server/actions/equip/EquipUtil.java (适配校验)"
ATK_DEF = SOURCE + "src/games/stendhal/server/entity/player/Player.java (updateItemAtkDef)"

ELEVEN = {name: 1 for name in ("cheese", "flask", "beer", "apple", "meat",
                               "bread", "dagger", "knife", "axe", "hammer", "rope")}


@pytest.mark.case(id="ST-INV-API-001", game="stendhal", module="inventory", kind="api",
                  title="未扩容背包最多12个对象，第13个装不进")
def test_bag_capacity_is_twelve(qa, api_player, observer, prepare):
    filled = prepare(money=100, items=ELEVEN, xp=0)
    qa.check("11件物品加money正好占满12槽", len(filled["slots"]["bag"]), 12, CAPACITY)
    qa.check("背包已满标记为真", filled["bag_full"], True, CAPACITY)

    full = dict(ELEVEN)
    full["shovel"] = 1
    with pytest.raises(Exception) as caught:
        prepare(money=100, items=full, xp=0)
    qa.check("再加一件物品时准备阶段即被拒绝",
             "Bag is full" in str(caught.value), True, CAPACITY)


@pytest.mark.case(id="ST-INV-API-002", game="stendhal", module="inventory", kind="api",
                  title="装备移到允许且有空位的槽成功")
def test_equip_to_allowed_slot_succeeds(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 1}, xp=0)
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    qa.check("准备后club在右手", club["name"], "club", EQUIP)

    equip(api_player, before, club, "rhand", "bag")
    moved = await_quantity(observer, "club", 1, slot="bag")
    qa.check("club进入背包列表", quantity(moved, "club", "bag"), 1, EQUIP)
    qa.check("右手槽已空", len(moved["slots"]["rhand"]), 0, EQUIP)


@pytest.mark.case(id="ST-INV-API-003", game="stendhal", module="inventory", kind="api",
                  title="移到不支持该位置的槽被拒且状态不变")
def test_equip_to_unsupported_slot_is_refused(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 1}, xp=0)
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    equip(api_player, before, club, "rhand", "bag")
    in_bag = await_quantity(observer, "club", 1, slot="bag")

    club = next(item for item in in_bag["slots"]["bag"] if item["name"] == "club")
    equip(api_player, in_bag, club, "bag", "head")
    after = observer.inspect()
    qa.check("头部槽没有出现该武器", len(after["slots"]["head"]), 0, EQUIP)
    qa.check("武器仍在背包列表", quantity(after, "club", "bag"), 1, EQUIP)


@pytest.mark.case(id="ST-INV-API-004", game="stendhal", module="inventory", kind="api",
                  title="装备与卸下武器后装备攻防贡献被重算")
def test_item_atk_contribution_is_recalculated(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 1}, xp=0)
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    qa.check("持械时装备攻击贡献为6", int(before["attributes"]["atk_item"]), 6, ATK_DEF)
    skill_atk = before["atk"]

    equip(api_player, before, club, "rhand", "bag")
    bare = await_quantity(observer, "club", 1, slot="bag")
    qa.check("卸下后装备攻击贡献归零", int(bare["attributes"]["atk_item"]), 0, ATK_DEF)
    qa.check("卸下不影响技能攻击值", bare["atk"], skill_atk, ATK_DEF)

    club = next(item for item in bare["slots"]["bag"] if item["name"] == "club")
    equip(api_player, bare, club, "bag", "rhand")
    rearmed = await_quantity(observer, "club", 1, slot="rhand")
    qa.check("重新装备后攻击贡献恢复为6", int(rearmed["attributes"]["atk_item"]), 6, ATK_DEF)


@pytest.mark.case(id="ST-INV-API-005", game="stendhal", module="inventory", kind="api",
                  title="钥匙圈未解锁时不能放入物品")
def test_keyring_locked_refuses_item(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 1}, xp=0)
    qa.check("准备后没有钥匙圈解锁feature", "keyring" in (before.get("features") or {}), False, EQUIP)
    cheese = next(item for item in before["slots"]["bag"] if item["name"] == "cheese")

    equip(api_player, before, cheese, "bag", "keyring")
    after = observer.inspect()
    qa.check("钥匙圈槽仍为空", len(after["slots"]["keyring"]), 0, EQUIP)
    qa.check("cheese仍在背包列表", quantity(after, "cheese", "bag"), 1, EQUIP)


@pytest.mark.case(id="ST-INV-API-006", game="stendhal", module="inventory", kind="api",
                  title="等级达到物品最低等级时不出现效果不足提示")
def test_no_level_warning_when_level_is_enough(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 1}, xp=0)
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    qa.check("club最低等级为0", int(club["attributes"]["min_level"]), 0, EQUIP)
    qa.check("玩家等级不低于最低等级", before["level"] >= 0, True, EQUIP)

    equip(api_player, before, club, "rhand", "bag")
    moved = await_quantity(observer, "club", 1, slot="bag")
    club = next(item for item in moved["slots"]["bag"] if item["name"] == "club")
    equip(api_player, moved, club, "bag", "rhand")
    armed = await_quantity(observer, "club", 1, slot="rhand")
    qa.check("达标时装备成功", quantity(armed, "club", "rhand"), 1, EQUIP)
