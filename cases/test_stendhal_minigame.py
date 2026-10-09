"""赌桌（Ricardo）下注：余额不足与取消都不扣钱、不发骰子。

设计条目 ST-MINIGAME-API-001（来源 S-DICE）：两个子例都是负向路径，
正向分支（扣 100 金币、发骰子）不在本用例范围内。
"""
import pytest

from gameqa.minigame import NPC, play
from gameqa.sources import SOURCE
from gameqa.stendhal import confirm, hello, leave, quantity, said

DICE = SOURCE + "src/games/stendhal/server/maps/quests/DiceGambling.java"
STAKE = DICE + "#L37 (STAKE=100)"
QUESTION = DICE + "#L75-L78 (play → 报价)"
INSUFFICIENT = DICE + "#L96-L100 (余额不足：拒绝且无动作)"
CANCEL = DICE + "#L102-L107 (no：取消且无动作)"
DICE_ITEM = SOURCE + "data/conf/items/miscs.xml#L85-L87 (dice)"


def dice_on_ground(state):
    return sum(1 for item in state.get("ground_items", []) if item["name"] == "dice")


@pytest.mark.case(id="ST-MINIGAME-API-001", game="stendhal", module="minigame", kind="api",
                  title="赌桌下注：余额不足与取消都不扣钱不发骰子")
def test_dice_stake_is_not_charged_when_refused_or_cancelled(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "两个子例都是负向路径（钱不够时接受、钱够时拒绝），所以不断言 DiceGambling#L80-L95 的"
        "正向分支（扣 100 金币并发骰子）。'不发骰子'在三处查：背包、地面 ground_items、金币增量。"
    )

    # 子例一：钱不够（99 < 100）时接受下注
    low = prepare(money=99, items={"dice": 0}, near_npc=NPC)
    qa.check("前置：金币99、没有骰子", [low["money"], quantity(low, "dice")], [99, 0],
             "测试夹具：money=99、dice=0")
    asked = hello(api_player, NPC) + play(api_player)
    qa.check("NPC实际报价：下注100金币", said(asked, NPC, "stake 100 gold. Do you want to pay?"),
             True, QUESTION)
    refused = confirm(api_player, "yes")
    after_low = observer.inspect()
    qa.check("余额不足时明确拒绝", said(refused, NPC, "You don't have enough money"),
             True, INSUFFICIENT)
    qa.check("拒绝不扣金币", after_low["money"], 99, INSUFFICIENT)
    qa.check("拒绝不发骰子（背包）", quantity(after_low, "dice"), 0, DICE_ITEM)
    qa.check("拒绝不发骰子（地面）", dice_on_ground(after_low), 0, DICE_ITEM)
    leave(api_player)

    # 子例二：钱刚好够（100）时取消
    rich = prepare(money=100, items={"dice": 0}, near_npc=NPC)
    qa.check("前置：金币恰好100、没有骰子", [rich["money"], quantity(rich, "dice")], [100, 0],
             STAKE + "; 测试夹具：money=100、dice=0")
    asked_again = hello(api_player, NPC) + play(api_player)
    qa.check("NPC实际报价（同一口径）", said(asked_again, NPC, "stake 100 gold. Do you want to pay?"),
             True, QUESTION)
    cancelled = confirm(api_player, "no")
    after_rich = observer.inspect()
    qa.check("取消时明确回应", said(cancelled, NPC, "risk nothing?"), True, CANCEL)
    qa.check("取消不扣金币", after_rich["money"], 100, CANCEL)
    qa.check("取消不发骰子（背包）", quantity(after_rich, "dice"), 0, DICE_ITEM)
    qa.check("取消不发骰子（地面）", dice_on_ground(after_rich), 0, DICE_ITEM)
    leave(api_player)
