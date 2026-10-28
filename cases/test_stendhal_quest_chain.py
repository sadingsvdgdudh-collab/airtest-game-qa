"""Accept with no material, walk to buy it, return, grow and reconnect."""
import pytest

from gameqa.stendhal import await_phase, await_quantity, quantity, quest_phase
from gameqa.sources import SOURCE
from cases.test_stendhal_quest_ui import (BEER, LEVEL, LEVEL_UPDATE, STATS,
                                         LOG_REGION, STATS_REGION, REWARD_FIELDS)

MAPS = SOURCE + 'data/conf/zones/semos.xml'
SHOP = SOURCE + 'data/conf/shops/sell_items.xml#L6-L16 (beer=10)'
GUARD, VILLAGE, CITY, TAVERN = ('int_semos_guard_house', '0_semos_village_w',
                              '0_semos_city', 'int_semos_tavern_0')


def travel(ui, observer, outward):
    def walk(zone, size, points, next_zone=None):
        for point in points:
            ui.walk(observer, zone, size, point)
        if next_zone:
            ui.walk(observer, zone, size, next_zone[0], next_zone=next_zone[1])
    if outward:
        walk(GUARD, (22, 18), [(13, 11)], ((13, 16), VILLAGE))
        # Original Nishiya patrol occupies y43/44; y46 has clear waypoint tiles.
        walk(VILLAGE, (64, 64), [(16, 40), (19, 46), (24, 46), (32, 46), (41, 46), (50, 46), (58, 46)],
             ((63.25, 46), CITY))  # world x=2040 > 2048-15: original extend=2.
        # Carmen patrols west y46; east y47 is blocked. Join the clear y46 at x19.
        walk(CITY, (64, 64), [(4, 47), (12, 47), (19, 47), (19, 46), (27, 46), (35, 46), (42, 46), (42, 39)],
             ((42, 37), TAVERN))
        walk(TAVERN, (32, 19), [(22, 16), (15, 16), (15, 7)])
    else:
        walk(TAVERN, (32, 19), [(15, 14), (22, 16)], ((22, 17), CITY))
        walk(CITY, (64, 64), [(42, 39), (42, 46), (35, 46), (27, 46), (19, 46), (19, 47), (12, 47), (4, 47)],
             ((-.25, 46), VILLAGE))  # world x=8: original extend=4.
        walk(VILLAGE, (64, 64), [(58, 46), (50, 46), (41, 46), (32, 46), (24, 46), (19, 46), (16, 40)],
             ((16, 34), GUARD))
        walk(GUARD, (22, 18), [(13, 11), (7, 11)])


def checkpoint(qa, state, title, money, beer, xp, level, karma, phase):
    qa.check(title, [state['money'], quantity(state, 'beer'), state['xp'], state['level'],
                     quest_phase(state, 'beer_hayunn')],
             [money, beer, xp, level, phase], BEER + '; ' + SHOP + '; ' + LEVEL)
    if karma is not None:
        qa.check(title + '：karma', state['karma'], karma, BEER)


@pytest.mark.case(id='ST-QUEST-UI-007', game='stendhal', module='quest', kind='ui',
                  title='界面全链路：接取→跨图行走→买酒→交付→升级→重登',
                  # 设计 ST-QUEST-API-007（跨商店/成长）当前由本 UI 链路执行：判据同为本例的
                  # 金币20→10→30、beer0→1→0、done/XP50/level1/HP110、karma+10 与重登持久化。
                  # 协议侧独立 API 用例仍未实现，见 docs/功能用例目录.md 该行备注。
                  covers=['ST-QUEST-API-007'])
def test_accept_walk_buy_deliver_grow_and_reconnect(qa, stendhal_ui, observer, prepare):
    ui = stendhal_ui
    qa.data['diagnostics']['coverage_limit'] = (
        '只在开始用GM准备20金币、beer0及守卫室位置；所有接取、跨图行走、购买、交付和重登均真实UI。'
        '指定路线采用固定720x1280小地图点击与两次主画布边界点击，只读坐标确认到达，不声称任意分辨率自主导航。')
    before = prepare(money=20, items={'beer': 0}, quests={'beer_hayunn': None, 'meet_hayunn': 'done'},
                     xp=0, karma=20, zone=GUARD, x=7, y=11)
    checkpoint(qa, before, '精确前置20金币且没有任务材料', 20, 0, 0, 0, 20, '')
    qa.check('普通售价没有玩家击杀加价标记', 'last_player_kill_time' in before['attributes'], False, SHOP)
    qa.check('缓存重登比较前置：sold为空', before['item_counter_cache']['sold'], {},
             SOURCE + 'src/games/stendhal/server/entity/player/PlayerLootedItemsHandler.java; 原版已知sold重载问题')
    ui.dialogue('bye', 'hi Hayunn Naratha', 'task', 'yes')
    accepted = await_phase(observer, 'beer_hayunn', 'start')
    checkpoint(qa, accepted, '没有材料时接取只改变任务阶段', 20, 0, 0, 0, 20, 'start')
    ui.open_travel_log()
    ui.check_image('quest-promised', 'beer0任务日志实际显示买酒承诺', LOG_REGION, BEER)
    ui.check_image_absent('quest-material-ready', 'beer0任务日志没有已持有酒的记录', LOG_REGION, BEER)
    ui.close_travel_log()
    ui.say('bye')
    travel(ui, observer, True)
    reached = observer.inspect()
    checkpoint(qa, reached, '真实走到酒馆仍未获得任务奖励', 20, 0, 0, 0, None, 'start')
    qa.check('酒馆行走后角色存活', reached['hp'] > 0, True, MAPS)
    ui.dialogue('bye', 'hi Margaret', 'buy beer')
    quotation = observer.inspect()
    checkpoint(qa, quotation, '仅报价不扣款不发货', 20, 0, 0, 0, reached['karma'], 'start')
    ui.say('yes')
    bought = await_quantity(observer, 'beer', 1)
    checkpoint(qa, bought, '真实购买扣10金币且得到1瓶酒', 10, 1, 0, 0, reached['karma'], 'start')
    for mapping, key, delta in [('npc_purchases', 'Margaret', 10), ('looted_items', 'bought.beer', 1)]:
        qa.check('购买原版账目增量：' + key,
                 int(bought['commerce'][mapping].get(key, 0)) - int(before['commerce'][mapping].get(key, 0)), delta, SHOP)
    qa.check('购买beer缓存增加1', bought['item_counter_cache']['bought'].get('beer', 0) -
             before['item_counter_cache']['bought'].get('beer', 0), 1, SHOP)
    ui.open_travel_log()
    ui.check_image('quest-material-ready', '购买后任务日志实际出现持有一瓶酒', LOG_REGION, BEER)
    ui.close_travel_log()
    ui.say('bye')
    travel(ui, observer, False)
    returned = observer.inspect()
    checkpoint(qa, returned, '实际携带购买材料回到守卫室', 10, 1, 0, 0, None, 'start')
    ui.dialogue('bye', 'hi Hayunn Naratha', 'yes')
    reward = await_phase(observer, 'beer_hayunn', 'done')
    checkpoint(qa, reward, '购买与任务奖励完整闭环', 30, 0, 50, 1, returned['karma'] + 10, 'done')
    qa.check('升级后最大生命与当前生命110', [reward['base_hp'], reward['hp']], [110, 110], LEVEL_UPDATE)
    for field in ('commerce', 'item_counter_cache'):
        qa.check('任务奖励不伪装为第二次商店购买：' + field, reward[field], bought[field], BEER + '; ' + SHOP)
    ui.open_travel_log(completed=True)
    ui.check_image('quest-completed', '整条链路完成后日志显示交付和奖励', LOG_REGION, BEER)
    ui.close_travel_log()
    for name in ('xp-50', 'level-1', 'xp-next-50', 'hp-110'):
        ui.check_image(name, '整条链路完成后成长显示：' + name, STATS_REGION, STATS + '; ' + LEVEL_UPDATE)
    saved = {key: reward[key] for key in (*REWARD_FIELDS, 'quests', 'commerce', 'item_counter_cache') if key != 'karma'}
    qa.data['diagnostics']['quest_chain_checkpoints'] = {
        'prepared': before, 'accepted': accepted, 'quotation': quotation, 'bought': bought,
        'returned': returned, 'rewarded': reward}
    ui.relogin(observer)
    reconnected = observer.inspect()
    qa.check('实际离线重登后奖励任务购买账目完整保持', {key: reconnected[key] for key in saved}, saved,
             BEER + '; 原版角色持久化，完整任务值含时间戳和次数')
    qa.check('重登后karma保持，仅允许浮点序列化误差1e-9',
             abs(reconnected['karma'] - reward['karma']) <= 1e-9, True,
             SOURCE + 'src/games/stendhal/server/entity/player/Player.java; karma为double，实际原值均保留')
    qa.data['diagnostics']['karma_persistence'] = {'before': reward['karma'], 'after': reconnected['karma'], 'tolerance': 1e-9}
    qa.check('实际重登不重新发出已交付酒', quantity(reconnected, 'beer'), 0, BEER)
    ui.open_travel_log(completed=True)
    ui.check_image('quest-completed', '重登后交付奖励日志保持', LOG_REGION, BEER)
    ui.close_travel_log()
    for name in ('xp-50', 'level-1', 'xp-next-50', 'hp-110'):
        ui.check_image(name, '重登后成长显示：' + name, STATS_REGION, STATS + '; ' + LEVEL_UPDATE)
