import pytest

from gameqa.quest import NPC as QUEST_NPC, accept_quest, hand_over
from gameqa.shop import NPC, buy_and_confirm
from gameqa.sources import (BEER_QUEST_REWARD, LEVEL_RULES, LEVEL_UPDATE, SELLER_BEHAVIOUR,
                            SELL_ITEMS_PRICES, SOURCE)
from gameqa.stendhal import (await_field, await_phase, await_quantity, hello, quantity,
                             quest_phase, said)


@pytest.mark.case(id="ST-SHOP-API-001", game="stendhal", module="shop", kind="api", title="买两个奶酪：金币100→60、背包+2")
def test_buy_two_cheese(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"cheese": 0}, near_npc=NPC)
    qa.check("准备初始金币", before["money"], 100, "测试夹具：100 gold")
    buy_and_confirm(api_player, "cheese", 2)
    after = await_quantity(observer, "cheese", 2)
    qa.check("金币扣除2×20", after["money"], 60, SELL_ITEMS_PRICES)
    qa.check("背包获得2个cheese", quantity(after, "cheese"), 2, SELL_ITEMS_PRICES)


@pytest.mark.case(id="ST-SHOP-API-002", game="stendhal", module="shop", kind="api", title="金币不足（19）：NPC拒绝、不扣款不发货")
def test_insufficient_money_changes_neither_money_nor_inventory(qa, api_player, observer, prepare):
    prepare(money=19, items={"cheese": 0}, near_npc=NPC)
    messages = buy_and_confirm(api_player, "cheese")
    after = observer.inspect()
    qa.check("NPC实际拒绝金币不足的购买", said(messages, NPC, "enough money"),
             True, SELLER_BEHAVIOUR)
    qa.check("金币不足时不扣款", after["money"], 19, SELL_ITEMS_PRICES + "; " + SELLER_BEHAVIOUR)
    qa.check("金币不足时不发货", quantity(after, "cheese"), 0, SELLER_BEHAVIOUR)


@pytest.mark.case(id="ST-SHOP-API-003", game="stendhal", module="shop", kind="api", title="恰好够付20金币：金币归零、获得1个奶酪")
def test_exact_money_purchases_one_item(qa, api_player, observer, prepare):
    prepare(money=20, items={"cheese": 0}, near_npc=NPC)
    buy_and_confirm(api_player, "cheese")
    after = await_quantity(observer, "cheese", 1)
    qa.check("恰好够付后金币为0", after["money"], 0, SELL_ITEMS_PRICES)
    qa.check("恰好够付可获得道具", quantity(after, "cheese"), 1, SELLER_BEHAVIOUR)


@pytest.mark.case(id="ST-BAG-API-001", game="stendhal", module="inventory", kind="api", title="已有3个再买2个：合并为5、只占一个背包槽")
def test_purchased_stack_merges_with_existing_stack(qa, api_player, observer, prepare):
    prepare(money=100, items={"cheese": 3}, near_npc=NPC)
    buy_and_confirm(api_player, "cheese", 2)
    after = await_quantity(observer, "cheese", 5)
    stacks = [item for item in after["inventory"] if item["slot"] == "bag" and item["name"] == "cheese"]
    qa.check("已有3个加新购2个", quantity(after, "cheese", "bag"), 5,
             SOURCE + "src/games/stendhal/server/entity/item/StackableItem.java")
    qa.check("同类可堆叠道具保持一个背包槽", len(stacks), 1,
             SOURCE + "src/games/stendhal/server/entity/RPEntity.java (equipToInventoryOnly)")


@pytest.mark.case(id="ST-QUEST-API-001", game="stendhal", module="quest", kind="api", title="交付啤酒只发一次奖励：重复询问不再发奖")
def test_beer_reward_is_granted_once(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 1}, quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=0, karma=20, near_npc=QUEST_NPC)
    messages = hello(api_player, QUEST_NPC) + hand_over(api_player)
    after = await_phase(observer, "beer_hayunn", "done")
    qa.check("任务完成主状态", quest_phase(after, "beer_hayunn"), "done",
             BEER_QUEST_REWARD + "; BringItemTask phase;timestamp;count")
    qa.check("任务消耗1个beer", quantity(after, "beer"), 0, BEER_QUEST_REWARD)
    qa.check("任务奖励20金币", after["money"], 120, BEER_QUEST_REWARD)
    qa.check("任务奖励50经验", after["xp"], 50, BEER_QUEST_REWARD)
    qa.check("任务奖励10karma", after["karma"], before["karma"] + 10, BEER_QUEST_REWARD)
    repeat_messages = hello(api_player, QUEST_NPC) + accept_quest(api_player)
    repeated = observer.inspect()
    qa.check("NPC实际回应不可重复任务", said(repeat_messages, QUEST_NPC, "Thanks all the same"),
             True, BEER_QUEST_REWARD)
    qa.check("重复对话不重复发金币", repeated["money"], 120, BEER_QUEST_REWARD)
    qa.check("重复对话不重复发经验", repeated["xp"], 50, BEER_QUEST_REWARD)
    qa.check("重复对话不重复发karma", repeated["karma"], after["karma"], BEER_QUEST_REWARD)


@pytest.mark.case(id="ST-GROWTH-API-001", game="stendhal", module="growth", kind="api", title="任务奖励50经验恰好达到1级")
def test_actual_quest_reward_crosses_level_one_threshold(qa, api_player, observer, prepare):
    before = prepare(money=0, items={"beer": 1}, quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=0, near_npc=QUEST_NPC)
    hello(api_player, QUEST_NPC) + hand_over(api_player)
    after = await_field(observer, "xp", 50)
    qa.check("真实任务奖励为50经验", after["xp"], 50, BEER_QUEST_REWARD)
    qa.check("升级来自已完成的任务", quest_phase(after, "beer_hayunn"), "done", BEER_QUEST_REWARD)
    qa.check("奖励前处于0级", int(before["attributes"]["level"]), 0, "测试夹具：0 XP / 0 level")
    qa.check("50经验达到1级", int(after["attributes"]["level"]), 1, LEVEL_RULES)
    qa.check("升级增加10最大生命值", int(after["attributes"]["base_hp"]),
             int(before["attributes"]["base_hp"]) + 10, LEVEL_UPDATE)
