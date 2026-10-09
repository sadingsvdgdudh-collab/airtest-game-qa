"""Real quest dialogue and rewards; every parameter has an independent snapshot."""
import pytest

from gameqa.quest import NPC, accept_quest, decline_quest, hand_over, refuse_hand_over
from gameqa.sources import (BEER_QUEST_FLOW, BRING_ITEM_TASK, LEVEL_RULES, LEVEL_UPDATE,
                            QUEST_COMPLETE, QUEST_OFFER)
from gameqa.stendhal import await_phase, hello, quantity, quest_phase, said


@pytest.mark.case(id="ST-QUEST-API-002", game="stendhal", module="quest", kind="api", title="接取送酒任务：只进入start、不发任何奖励")
def test_accept_quest_starts_without_rewards(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 0},
                     quests={"beer_hayunn": None, "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    qa.check("准备时尚未接取送酒任务", quest_phase(before, "beer_hayunn"), "", "测试夹具：移除 beer_hayunn")
    messages = hello(api_player, NPC) + accept_quest(api_player)
    after = await_phase(observer, "beer_hayunn", "start")
    qa.check("NPC实际提出送酒任务", said(messages, NPC, "My mouth is dry"), True, BEER_QUEST_FLOW)
    qa.check("NPC实际接受接取确认", said(messages, NPC, "Thanks! I'll be right here, waiting."),
             True, BEER_QUEST_FLOW)
    qa.check("接受后任务开始", quest_phase(after, "beer_hayunn"), "start", QUEST_OFFER)
    qa.check("仅接取不发金币", after["money"], before["money"], BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    qa.check("仅接取不发经验", after["xp"], before["xp"], BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    qa.check("仅接取不发beer", quantity(after, "beer"), 0, BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    qa.check("仅接取不增加karma", after["karma"], before["karma"], QUEST_OFFER)
    # The TravelLog display is a separate UI assertion, not established by quest state.
    qa.data["diagnostics"]["coverage_limit"] = "任务日志 TravelLog 的界面显示留待 UI 用例；本例验证实际 NPC 对话、任务状态及资源。"


@pytest.mark.case(id="ST-QUEST-API-003", game="stendhal", module="quest", kind="api", title="已接任务缺beer：再次询问只提醒、不发奖励")
def test_missing_beer_keeps_active_quest_without_rewards(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 0},
                     quests={"beer_hayunn": None, "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    qa.data["diagnostics"]["coverage_limit"] = (
        "本例通过真实接取建立并保持 ATTENDING 会话，验证接取后缺材料的提醒分支。"
        "已接任务且无beer时重新问候不能建立会话的两次独立失败另存；尚不据此认定业务缺陷。"
    )
    accepted_messages = hello(api_player, NPC) + accept_quest(api_player)
    accepted = await_phase(observer, "beer_hayunn", "start")
    qa.check("NPC实际提出送酒任务", said(accepted_messages, NPC, "My mouth is dry"), True, BEER_QUEST_FLOW)
    qa.check("NPC实际接受任务并保持会话",
             said(accepted_messages, NPC, "Thanks! I'll be right here, waiting."),
             True, BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    qa.check("真实接取后任务处于start", quest_phase(accepted, "beer_hayunn"), "start", QUEST_OFFER)
    qa.check("缺材料分支开始时确实没有beer", quantity(accepted, "beer"), 0, "前置：真实接取后仍无beer")
    qa.check("真实接取前置不发奖励", [accepted[key] for key in ("money", "xp", "karma")],
             [before[key] for key in ("money", "xp", "karma")], BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    # 同一会话内再问一次并确认，触发缺材料提醒分支（与会话开启分开，观察窗口不同）。
    messages = accept_quest(api_player)
    after = observer.inspect()
    qa.check("NPC实际提醒仍需beer", said(messages, NPC, "I'm still waiting for that beer"),
             True, BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    qa.check("缺少材料时任务仍start", quest_phase(after, "beer_hayunn"), "start",
             BRING_ITEM_TASK + "; " + QUEST_COMPLETE)
    qa.check("缺少材料不发金币", after["money"], accepted["money"], BEER_QUEST_FLOW + "; " + QUEST_COMPLETE)
    qa.check("缺少材料不发经验", after["xp"], accepted["xp"], BEER_QUEST_FLOW + "; " + QUEST_COMPLETE)
    qa.check("缺少材料不增加karma", after["karma"], accepted["karma"], BEER_QUEST_FLOW + "; " + QUEST_COMPLETE)
    qa.check("缺少材料不凭空生成beer", quantity(after, "beer"), 0, BRING_ITEM_TASK)


@pytest.mark.parametrize("stage", [
    pytest.param("initial", id="initial", marks=pytest.mark.case(
        id="ST-QUEST-API-004-initial", game="stendhal", module="quest", kind="api", title="拒绝接取送酒任务：记为rejected、扣5 karma")),
    pytest.param("handoff", id="handoff", marks=pytest.mark.case(
        id="ST-QUEST-API-004-handoff", game="stendhal", module="quest", kind="api", title="拒绝交付啤酒：任务保持start、不扣beer")),
])
def test_reject_quest_offer_or_item_handoff(stage, qa, api_player, observer, prepare):
    initial = stage == "initial"
    before = prepare(money=100, items={"beer": 0 if initial else 1},
                     quests={"beer_hayunn": None if initial else "start", "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    messages = hello(api_player, NPC)
    messages += decline_quest(api_player) if initial else refuse_hand_over(api_player)
    expected_phase = "rejected" if initial else "start"
    after = await_phase(observer, "beer_hayunn", expected_phase)
    if initial:
        qa.check("NPC实际提出初次任务", said(messages, NPC, "My mouth is dry"), True, BEER_QUEST_FLOW)
        qa.check("NPC实际回应拒绝接取", said(messages, NPC, "Oh, well forget it then."),
                 True, BEER_QUEST_FLOW)
        qa.check("初次拒绝记为rejected", quest_phase(after, "beer_hayunn"), "rejected", QUEST_OFFER)
        qa.check("初次拒绝扣5 karma", after["karma"], before["karma"] - 5,
                 BEER_QUEST_FLOW + "; " + QUEST_OFFER)
    else:
        qa.check("NPC实际提出交付确认", said(messages, NPC, "Is that beer for me?"),
                 True, BEER_QUEST_FLOW + "; " + QUEST_COMPLETE)
        qa.check("NPC实际回应拒绝交付", said(messages, NPC, "Drat! You remembered"),
                 True, BEER_QUEST_FLOW)
        qa.check("拒绝交付任务保持start", quest_phase(after, "beer_hayunn"), "start", QUEST_COMPLETE)
        qa.check("拒绝交付不增加karma", after["karma"], before["karma"], QUEST_COMPLETE)
    qa.check("拒绝分支不发金币", after["money"], before["money"],
             BEER_QUEST_FLOW + "; " + QUEST_OFFER + "; " + QUEST_COMPLETE)
    qa.check("拒绝分支不发经验", after["xp"], before["xp"],
             BEER_QUEST_FLOW + "; " + QUEST_OFFER + "; " + QUEST_COMPLETE)
    qa.check("拒绝分支保留已有beer", quantity(after, "beer"), quantity(before, "beer"),
             BRING_ITEM_TASK + "; " + QUEST_COMPLETE)


@pytest.mark.case(id="ST-QUEST-API-005", game="stendhal", module="quest", kind="api", title="有2瓶beer只消耗1瓶、奖励只发一次")
def test_extra_beer_consumes_only_one_and_rewards_once(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 2},
                     quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    messages = hello(api_player, NPC) + hand_over(api_player)
    after = await_phase(observer, "beer_hayunn", "done")
    qa.check("NPC实际确认领取beer", said(messages, NPC, "Is that beer for me?"), True, BEER_QUEST_FLOW)
    qa.check("NPC实际完成交付", said(messages, NPC, "Ah! That hit the spot."), True, BEER_QUEST_FLOW)
    qa.check("有额外材料也只完成一次", quest_phase(after, "beer_hayunn"), "done", QUEST_COMPLETE)
    qa.check("两瓶beer只消耗一瓶", quantity(after, "beer"), 1,
             BEER_QUEST_FLOW + "; " + BRING_ITEM_TASK)
    qa.check("奖励只有20金币", after["money"], before["money"] + 20, BEER_QUEST_FLOW)
    qa.check("奖励只有50经验", after["xp"], before["xp"] + 50, BEER_QUEST_FLOW)
    qa.check("奖励只有10 karma", after["karma"], before["karma"] + 10, BEER_QUEST_FLOW)


@pytest.mark.case(id="ST-GROWTH-API-003", game="stendhal", module="growth", kind="api", title="50+50经验恰好到2级并回满血")
def test_quest_reward_reaches_exact_level_two_threshold_and_heals(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 1},
                     quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=50, hp=1, karma=0, near_npc=NPC)
    qa.check("奖励前经验恰好50", before["xp"], 50, "测试夹具：XP50")
    qa.check("50经验处于1级", before["level"], 1, LEVEL_RULES)
    qa.check("准备受伤状态验证升级回满血", before["hp"], 1, "测试夹具：HP1")
    messages = hello(api_player, NPC) + hand_over(api_player)
    after = await_phase(observer, "beer_hayunn", "done")
    qa.check("NPC实际发放任务奖励", said(messages, NPC, "Ah! That hit the spot."), True, BEER_QUEST_FLOW)
    qa.check("真实任务已完成", quest_phase(after, "beer_hayunn"), "done", QUEST_COMPLETE)
    qa.check("交付实际消耗beer", quantity(after, "beer"), 0, BRING_ITEM_TASK)
    qa.check("50+50恰好达到100经验", after["xp"], 100, BEER_QUEST_FLOW + "; " + LEVEL_RULES)
    qa.check("100经验恰好达到2级", after["level"], 2, LEVEL_RULES)
    qa.check("一级升级增加10最大生命", after["base_hp"], before["base_hp"] + 10, LEVEL_UPDATE)
    # 用新的最大生命而不是 before+10：世界重建后角色 base_hp 基数不同，硬算 +10 不再成立
    qa.check("升级时恢复到新最大生命", after["hp"], after["base_hp"], LEVEL_UPDATE)


@pytest.mark.case(id="ST-GROWTH-API-005", game="stendhal", module="growth", kind="api",
                  title="重复请求已完成的送酒任务：不发奖励、不重复消耗beer")
def test_repeat_request_of_done_quest_grants_nothing(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 1},
                     quests={"beer_hayunn": "done", "meet_hayunn": "done"},
                     xp=50, karma=0, near_npc=NPC)
    qa.check("奖励前XP恰好50", before["xp"], 50, "测试夹具：XP50")
    qa.check("奖励前处于1级", before["level"], 1, LEVEL_RULES)
    messages = hello(api_player, NPC) + accept_quest(api_player)
    after = observer.inspect()
    qa.check("NPC实际回应任务不可重复", said(messages, NPC, "Thanks all the same"),
             True, BEER_QUEST_FLOW)
    qa.check("重复请求不改变任务阶段", quest_phase(after, "beer_hayunn"), "done",
             QUEST_COMPLETE + "; " + BEER_QUEST_FLOW)
    qa.check("重复请求不重复发经验", after["xp"], before["xp"], BEER_QUEST_FLOW + "; " + LEVEL_RULES)
    qa.check("重复请求不改变等级", after["level"], before["level"], LEVEL_RULES)
    qa.check("重复请求不改变最大生命", after["base_hp"], before["base_hp"], LEVEL_UPDATE)
    qa.check("重复请求不再消耗beer", quantity(after, "beer"), 1, BRING_ITEM_TASK)
    qa.check("重复请求不发金币", after["money"], before["money"], BEER_QUEST_FLOW + "; " + QUEST_COMPLETE)
