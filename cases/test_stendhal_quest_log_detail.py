"""旅行日志详情：任务说明文案与进度历史（界面断言，Airtest 模板匹配）。

这两条只能走 UI：说明文案来自客户端任务目录、历史条目由客户端按槽位时间戳格式化，
服务端 inspect 只有 `quests` 的 `phase;timestamp;count`，读不到文本。

历史条数与持有状态绑定：第三条是 "I have a bottle of beer."，
因此前置必须同时满足 beer_hayunn=start 与 beer=1，否则只有两条历史，模板必然失配。
"""
import pytest

from gameqa.quest import NPC
from gameqa.sources import SOURCE
from gameqa.stendhal import quantity, quest_phase

BEER = SOURCE + "src/games/stendhal/server/maps/quests/BeerForHayunn.java#L55-L97"
LOG_REGION = (290, 290, 597, 555)


@pytest.mark.case(id="ST-QUEST-UI-002", game="stendhal", module="quest", kind="ui",
                  title="旅行日志显示任务说明文案")
def test_travel_log_shows_quest_description(qa, stendhal_ui, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "本例只验证 Beer for Hayunn 一条任务在日志里的说明文案；"
        "说明来自客户端任务目录，不据此认定 15 条手稿任务的展示名都正确。")
    before = prepare(money=100, items={"beer": 1},
                     quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=0, karma=0, zone='int_semos_guard_house', x=7, y=11)
    qa.check("准备后任务处于start", quest_phase(before, "beer_hayunn"), "start",
             "测试夹具：beer_hayunn=start")

    stendhal_ui.open_travel_log()
    stendhal_ui.check_image("quest-detail-description", "旅行日志显示任务说明文案", LOG_REGION, BEER)
    stendhal_ui.close_travel_log()


@pytest.mark.case(id="ST-QUEST-UI-003", game="stendhal", module="quest", kind="ui",
                  title="旅行日志按序显示三条进度历史")
def test_travel_log_history_items_in_order(qa, stendhal_ui, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "顺序靠整块模板匹配成立（三条连成一张图，整块命中即顺序正确），"
        "不逐条比对单行文本。")
    before = prepare(money=100, items={"beer": 1},
                     quests={"beer_hayunn": "start", "meet_hayunn": "done"},
                     xp=0, karma=0, zone='int_semos_guard_house', x=7, y=11)
    qa.check("准备后任务处于start", quest_phase(before, "beer_hayunn"), "start",
             "测试夹具：beer_hayunn=start")
    qa.check("持有beer，第三条历史才存在", quantity(before, "beer"), 1,
             "测试夹具：beer=1；三条历史含持有酒记录")

    stendhal_ui.open_travel_log()
    stendhal_ui.check_image("quest-history-start", "三条进度历史按序显示", LOG_REGION, BEER)
    stendhal_ui.close_travel_log()
