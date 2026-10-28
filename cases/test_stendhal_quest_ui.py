"""Real Android quest dialogue, TravelLog, growth and reconnect persistence."""
import pytest

from gameqa.stendhal import await_phase, quantity, quest_phase
from gameqa.sources import SOURCE


BEER = SOURCE + "src/games/stendhal/server/maps/quests/BeerForHayunn.java#L55-L97"
LEVEL = SOURCE + "src/games/stendhal/common/Level.java#L38-L43"
LEVEL_UPDATE = SOURCE + "src/games/stendhal/server/entity/RPEntity.java#L1162-L1175"
STATS = SOURCE + "src/js/stendhal/ui/component/PlayerStatsComponent.ts#L117-L161"
NPC_POSITION = SOURCE + "src/games/stendhal/server/maps/semos/guardhouse/RetiredAdventurerNPC.java#L92-L109"
LOG_REGION = (290, 290, 597, 555)
STATS_REGION = (0, 325, 96, 470)
REWARD_FIELDS = ("money", "xp", "karma", "level", "base_hp", "hp")


@pytest.mark.case(id="ST-QUEST-UI-001", game="stendhal", module="quest", kind="ui",
                  title="界面接取并交付送酒任务：奖励、升级、重登后保持",
                  # 设计 ST-GROWTH-UI-001（成长显示/持久化）没有独立 pytest 用例：它要求的判据
                  # 就是本例交付后的等级/最大生命/统计栏与重登、重复对话幂等断言，故声明共用。
                  covers=["ST-GROWTH-UI-001"])
def test_android_quest_rewards_log_growth_and_reconnect(qa, stendhal_ui, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "本例用管理员准备一瓶beer及NPC附近位置；真实UI完成接取、交付、任务日志和重登。"
        "不据此认定跨地图行走或到酒馆购买beer的界面流程已覆盖。")
    before = prepare(money=100, items={"beer": 1},
                     quests={"beer_hayunn": None, "meet_hayunn": "done"},
                     xp=0, karma=20, zone='int_semos_guard_house', x=7, y=11)
    qa.check("独立管理员读取UI角色", before["name"], "qaplayer", "本地隔离UI账户配置")
    qa.check("任务开始前尚未接取", quest_phase(before, "beer_hayunn"), "", "测试夹具：移除beer_hayunn")
    qa.check("任务开始前确有一瓶beer", quantity(before, "beer"), 1, "测试夹具：beer1")
    qa.check("任务开始前0经验0级", [before["xp"], before["level"]], [0, 0], LEVEL)
    qa.check("固定UI模板前置：0级最大生命100", before['base_hp'], 100,
             '本地原版测试角色初始100HP，等级调整后按每级10HP归一')
    # Hayunn patrols x=4..11, y=9..14; (7,11) stays inside his rectangular chat range 5.
    # A neighbour of his current position can fall outside that range after he walks away.
    qa.check('固定起点覆盖Hayunn整条巡逻的对话范围',
             [before['attributes']['zoneid'], int(before['attributes']['x']), int(before['attributes']['y'])],
             ['int_semos_guard_house', 7, 11], NPC_POSITION + '; SpeakerNPC默认对话范围5')

    stendhal_ui.dialogue("bye", "hi Hayunn Naratha", "task", "yes")
    accepted = await_phase(observer, "beer_hayunn", "start")
    qa.check("UI接取后任务进入start", quest_phase(accepted, "beer_hayunn"), "start", BEER)
    qa.check("仅接取不发金币经验karma奖励", [accepted[key] for key in ("money", "xp", "karma")],
             [100, 0, 20], BEER)
    qa.check("仅接取不消耗已有beer", quantity(accepted, "beer"), 1, BEER)
    stendhal_ui.open_travel_log()
    stendhal_ui.check_image("quest-title", "进行中任务日志显示Beer for Hayunn", LOG_REGION, BEER)
    stendhal_ui.check_image("quest-promised", "进行中任务日志显示送酒承诺", LOG_REGION, BEER)
    stendhal_ui.close_travel_log()

    stendhal_ui.dialogue("bye", "hi Hayunn Naratha", "yes")
    rewarded = await_phase(observer, "beer_hayunn", "done")
    qa.check("UI交付后任务完成", quest_phase(rewarded, "beer_hayunn"), "done", BEER)
    qa.check("UI交付实际消耗一瓶beer", quantity(rewarded, "beer"), 0, BEER)
    qa.check("UI交付奖励20金币", rewarded["money"], 120, BEER)
    qa.check("ST-GROWTH-UI-001/交付奖励50经验", rewarded["xp"], 50, BEER)
    qa.check("UI交付奖励10karma", rewarded["karma"], 30, BEER)
    qa.check("ST-GROWTH-UI-001/奖励使角色升到1级", rewarded["level"], 1, LEVEL)
    qa.check("ST-GROWTH-UI-001/一级升级增加10最大生命", rewarded["base_hp"], before["base_hp"] + 10, LEVEL_UPDATE)
    qa.check("ST-GROWTH-UI-001/升级恢复到新最大生命", rewarded["hp"], before["base_hp"] + 10, LEVEL_UPDATE)
    stendhal_ui.open_travel_log(completed=True)
    stendhal_ui.check_image("quest-completed", "完成日志显示交付及奖励记录", LOG_REGION, BEER)
    stendhal_ui.close_travel_log()
    for name, title in (("xp-50", "经验显示50"), ("level-1", "等级显示1"),
                        ("xp-next-50", "下一级尚需50经验"), ("hp-110", "生命显示110/110")):
        stendhal_ui.check_image(name, "ST-GROWTH-UI-001/首次奖励后" + title, STATS_REGION,
                                (LEVEL_UPDATE if name == 'hp-110' else LEVEL) + '; ' + STATS)

    # Keep the complete quest values, including their timestamp/count suffixes.
    saved_rewards = {key: rewarded[key] for key in REWARD_FIELDS}
    saved_quests = rewarded["quests"]
    qa.data["diagnostics"]["quest_ui_reward_checkpoint"] = {
        "rewards": saved_rewards, "beer": quantity(rewarded, "beer"), "quests": saved_quests}
    stendhal_ui.relogin(observer)
    reconnected = observer.inspect()
    qa.check("ST-GROWTH-UI-001/实际断开重登后所有奖励和成长字段保持", {key: reconnected[key] for key in REWARD_FIELDS},
             saved_rewards, BEER + "; " + LEVEL_UPDATE + "; 实际断开后的角色持久化")
    qa.check("实际断开重登后全部任务槽完整保持", reconnected["quests"], saved_quests,
             BEER + "; 实际断开后的角色持久化")
    qa.check("实际断开重登后已交付beer不再出现", quantity(reconnected, "beer"), 0, BEER)
    stendhal_ui.open_travel_log(completed=True)
    stendhal_ui.check_image("quest-completed", "重登后完成日志保持交付及奖励记录", LOG_REGION, BEER)
    stendhal_ui.close_travel_log()
    for name, title in (("xp-50", "经验显示50"), ("level-1", "等级显示1"),
                        ("xp-next-50", "下一级尚需50经验"), ("hp-110", "生命显示110/110")):
        stendhal_ui.check_image(name, "ST-GROWTH-UI-001/重登后" + title, STATS_REGION,
                                (LEVEL_UPDATE if name == 'hp-110' else LEVEL) + '; ' + STATS)

    stendhal_ui.dialogue("bye", "hi Hayunn Naratha", "task", "yes")
    # This is a fresh browser session: an old refusal cannot satisfy this check.
    stendhal_ui.check_image("quest-unrepeatable", "NPC实际回应已完成任务不可重复",
                            (100, 575, 565, 1220), BEER)
    repeated = observer.inspect()
    qa.check("ST-GROWTH-UI-001/重登后重复真实UI对话不重复领奖或升级", {key: repeated[key] for key in REWARD_FIELDS},
             saved_rewards, BEER + "; " + LEVEL_UPDATE)
    qa.check("重复真实UI对话不改写完整任务槽", repeated["quests"], saved_quests, BEER)
    qa.check("重复真实UI对话不生成beer", quantity(repeated, "beer"), 0, BEER)
