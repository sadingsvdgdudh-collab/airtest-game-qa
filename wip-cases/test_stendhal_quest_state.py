"""任务状态判定：未开始/进行中/已完成三态与完成次数（AbstractQuest 默认口径）。

口径来自 4.5：hasQuest(slot) ⇒ isStarted；hasQuest 且已标记完成 ⇒ isCompleted；
完成次数取槽位 `phase;timestamp;count` 的第三段，未开始与进行中都是 0。

与同目录其它任务用例的分工：
- ST-QUEST-API-002/003/005 验证**奖励与材料**差量（金币/XP/karma/beer）；
- 本例组只验证**状态判定与完成次数**，不重复奖励断言；
- 拒绝接取在 ST-QUEST-API-004-initial 里验证 karma 扣减，本例从"槽位存在即算已开始"角度补判据。
"""
import pytest

from gameqa.quest import NPC, accept_quest, decline_quest, hand_over
from gameqa.sources import BEER_QUEST_FLOW, QUEST_COMPLETE, QUEST_OFFER
from gameqa.stendhal import await_phase, hello, quest_completed_count, quest_phase

NOT_STARTED = "测试夹具：移除beer_hayunn；4.5 无槽位⇒未开始未完成"


@pytest.mark.case(id="ST-QUEST-API-008", game="stendhal", module="quest", kind="api",
                  title="未接取：无任务槽，判定未开始未完成且完成次数为0")
def test_unstarted_quest_has_no_slot_and_zero_completions(qa, observer, prepare):
    before = prepare(money=100, items={"beer": 0},
                     quests={"beer_hayunn": None, "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    qa.check("未接取时任务阶段为空", quest_phase(before, "beer_hayunn"), "", NOT_STARTED)
    qa.check("未接取时任务槽不存在", "beer_hayunn" in before["quests"], False, NOT_STARTED)
    qa.check("未接取时完成次数为0", quest_completed_count(before, "beer_hayunn"), 0,
             "4.5 getCompletedCount 未完成→0")


@pytest.mark.case(id="ST-QUEST-API-009", game="stendhal", module="quest", kind="api",
                  title="接取后：阶段start、槽位已建立、完成次数仍为0")
def test_accept_moves_quest_to_start_without_completion(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 0},
                     quests={"beer_hayunn": None, "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    qa.check("接取前任务阶段为空", quest_phase(before, "beer_hayunn"), "", NOT_STARTED)

    hello(api_player, NPC)
    accept_quest(api_player)
    after = await_phase(observer, "beer_hayunn", "start")

    qa.check("接取后任务阶段为start", quest_phase(after, "beer_hayunn"), "start", BEER_QUEST_FLOW)
    qa.check("接取后任务槽已建立（hasQuest⇒isStarted）", "beer_hayunn" in after["quests"], True,
             BEER_QUEST_FLOW + "; 4.5 hasQuest(slot)⇒isStarted")
    qa.check("接取后完成次数仍为0", quest_completed_count(after, "beer_hayunn"), 0,
             "4.5 未完成→0")


@pytest.mark.case(id="ST-QUEST-API-010", game="stendhal", module="quest", kind="api",
                  title="交付后：阶段done、完成次数由0变1")
def test_hand_over_marks_completed_with_count_one(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 1},
                     quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    qa.check("交付前任务阶段为start", quest_phase(before, "beer_hayunn"), "start",
             "测试夹具：beer_hayunn=start")
    qa.check("交付前完成次数为0", quest_completed_count(before, "beer_hayunn"), 0, "4.5 未完成→0")

    hello(api_player, NPC)
    hand_over(api_player)
    after = await_phase(observer, "beer_hayunn", "done")

    qa.check("交付后任务阶段为done", quest_phase(after, "beer_hayunn"), "done", QUEST_COMPLETE)
    qa.check("交付后完成次数为1", quest_completed_count(after, "beer_hayunn"), 1,
             QUEST_COMPLETE + "; 4.5 已完成→1")


@pytest.mark.case(id="ST-QUEST-API-011", game="stendhal", module="quest", kind="api",
                  title="拒绝接取：阶段rejected但槽位存在，按默认口径算已开始且未完成")
def test_rejected_offer_still_counts_as_started(qa, api_player, observer, prepare):
    before = prepare(money=100, items={"beer": 0},
                     quests={"beer_hayunn": None, "meet_hayunn": "done"},
                     xp=0, karma=0, near_npc=NPC)
    qa.check("拒绝前任务阶段为空", quest_phase(before, "beer_hayunn"), "", NOT_STARTED)

    hello(api_player, NPC)
    decline_quest(api_player)
    after = await_phase(observer, "beer_hayunn", "rejected")

    qa.check("拒绝接取后任务阶段为rejected", quest_phase(after, "beer_hayunn"), "rejected", QUEST_OFFER)
    qa.check("拒绝接取后槽位存在，默认口径算已开始", "beer_hayunn" in after["quests"], True,
             QUEST_OFFER + "; 4.5 hasQuest(slot)⇒isStarted")
    qa.check("拒绝接取后完成次数为0", quest_completed_count(after, "beer_hayunn"), 0,
             "4.5 未完成→0")
