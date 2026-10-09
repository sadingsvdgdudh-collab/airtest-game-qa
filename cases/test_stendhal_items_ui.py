"""Original mobile Hold/Drink actions, verified by UI and an independent observer."""
import pytest

from gameqa.stendhal import await_exact_quantity, await_quantity, await_slot_empty, quantity
from gameqa.sources import SOURCE
from cases.test_stendhal_items_edges import POTION, FEEDER, HEAL, USE


SWORD = SOURCE + 'data/conf/items/swords.xml#L717-L735'
EQUIP = SOURCE + 'src/games/stendhal/server/actions/equip/SourceObject.java#L318-L345'
ATK = SOURCE + 'src/games/stendhal/server/entity/RPEntity.java#L2755-L2775; ' + SOURCE + 'src/js/stendhal/ui/component/PlayerStatsComponent.ts#L140-L150'
BAG = (568, 343, 657, 461)
RHAND = (568, 260, 596, 289)
FEET = (597, 313, 625, 341)
STATS = (0, 325, 96, 470)
EQUIPMENT = ('head', 'armor', 'cloak', 'legs', 'feet', 'lhand', 'rhand', 'finger')


def sword_state(qa, state, slot, original):
    qa.check('短剑只在指定槽位且总量始终1：' + slot,
             [quantity(state, 'short sword', slot), quantity(state, 'short sword', None)], [1, 1], EQUIP)
    item = next(item for item in state['slots'][slot] if item['name'] == 'short sword')
    # RPSlot.add reassigns protocol IDs; the first real move may also add an audit logid.
    business = {k: v for k, v in item['attributes'].items() if k not in ('id', 'logid')}
    qa.check('移动保留短剑全部业务属性：' + slot, business, original, EQUIP)
    qa.data['diagnostics'].setdefault('weapon_transfers', []).append(
        {'slot': slot, 'attributes': item['attributes'], 'business_attributes': business})
    return item


@pytest.mark.case(id='ST-BAG-UI-001', game='stendhal', module='inventory', kind='ui', title='界面卸下木棍再装备短剑：槽位往返、空手攻击系数归零')
def test_android_equipment_round_trip_and_illegal_slot(qa, stendhal_ui, observer, prepare):
    before = prepare(money=0, items={'short sword': 1}, xp=800, hp=100,
                     zone='int_semos_guard_house', x=12, y=12)
    qa.data['diagnostics']['coverage_limit'] = '仅检查背包/装备槽和界面属性；不据此认定战斗伤害或世界掉落已覆盖。'
    qa.check('本地原装右手是单个club', [item['name'] for item in before['slots']['rhand']], ['club'],
             '专用UI角色原装木棍；通过真实UI卸下，管理员仅准备短剑与等级')
    qa.check('左手、手指和脚部为空，无其它攻击道具干扰',
             [before['slots'][slot] for slot in ('lhand', 'finger', 'feet')], [[], [], []], ATK)
    qa.check('短剑等级前置达标', before['level'] >= 5, True, SWORD)
    qa.check('固定属性模板前置基础ATK10', before['atk'], 10, ATK + '; 专用角色初始基础ATK10')
    qa.check('固定模板前置：背包仅一把短剑、在第一个格',
             [item['name'] for item in before['slots']['bag']], ['short sword'], '本地隔离UI角色背包基线')
    original_sword = next(item for item in before['slots']['bag'] if item['name'] == 'short sword')
    business = {k: v for k, v in original_sword['attributes'].items() if k not in ('id', 'logid')}
    qa.data['diagnostics']['weapon_initial'] = original_sword
    stendhal_ui.move_item('club-icon', RHAND, 'bag-empty', BAG)
    unarmed = await_slot_empty(observer, 'rhand')
    qa.check('真实UI卸下木棍，保留在背包', [unarmed['slots']['rhand'], quantity(unarmed, 'club')], [[], 1], EQUIP)
    qa.check('空手道具攻击系数为0', int(unarmed['attributes']['atk_item']), 0, ATK)
    stendhal_ui.check_image('atk-empty', '空手界面显示ATK10 x 0', STATS, ATK)

    stendhal_ui.move_item('short-sword-first', BAG, 'rhand-empty', RHAND)
    armed = await_quantity(observer, 'short sword', 1, slot='rhand')
    equipped_sword = sword_state(qa, armed, 'rhand', business)
    qa.check('短剑装备只改变道具攻击系数，基础ATK保持', [armed['atk'], int(armed['attributes']['atk_item'])], [before['atk'], 11], SWORD + '; ' + ATK)
    stendhal_ui.check_image('short-sword-icon', '右手界面实际显示短剑', RHAND, EQUIP)
    stendhal_ui.check_image('atk-sword', '装备后界面显示ATK10 x 11', STATS, ATK)

    stendhal_ui.move_item('short-sword-icon', RHAND, 'bag-empty', BAG, menu='hold-rhand')
    returned = await_quantity(observer, 'short sword', 1)
    returned_sword = sword_state(qa, returned, 'bag', business)
    qa.check('实际装备已建立原版日志物品编号', bool(equipped_sword['attributes'].get('logid')), True,
             SOURCE + 'src/games/stendhal/server/core/engine/db/StendhalItemDAO.java#L44-L65')
    qa.check('合法往返保留原版日志物品编号', returned_sword['attributes'].get('logid'),
             equipped_sword['attributes'].get('logid'), SOURCE + 'src/games/stendhal/server/core/engine/ItemLogger.java')
    qa.check('返回后短剑在木棍后的第二个背包格',
             [item['name'] for item in returned['slots']['bag']], ['club', 'short sword'], '固定UI基线；原版跨槽加入按顺序追加')
    qa.check('卸下后右手为空且道具攻击系数回到0', [returned['slots']['rhand'], int(returned['attributes']['atk_item'])], [[], 0], ATK)
    stendhal_ui.check_image('short-sword-icon', '背包界面实际显示返回的短剑', BAG, EQUIP)
    stendhal_ui.check_image('rhand-empty', '卸下后界面右手槽为空', RHAND, EQUIP)
    stendhal_ui.check_image('atk-empty', '卸下后界面恢复ATK10 x 0', STATS, ATK)

    stendhal_ui.move_item('short-sword-icon', BAG, 'feet-empty', FEET)
    # A fresh client session has no old rejection line; require the actual server reply.
    stendhal_ui.check_image('feet-refusal', '本次错误槽操作出现原服拒绝提示', (100, 575, 565, 1220), EQUIP)
    rejected = observer.inspect()
    sword_state(qa, rejected, 'bag', business)
    qa.check('错误槽拒绝后背包及全部装备物品完整保持',
             {slot: rejected['slots'][slot] for slot in ('bag',) + EQUIPMENT},
             {slot: returned['slots'][slot] for slot in ('bag',) + EQUIPMENT}, EQUIP)
    qa.check('错误槽拒绝后基础与道具攻击属性保持',
             [rejected['atk'], rejected['attributes']['atk_item']], [returned['atk'], returned['attributes']['atk_item']], EQUIP + '; ' + ATK)
    stendhal_ui.check_image('short-sword-icon', '拒绝后短剑仍显示在背包', BAG, EQUIP)
    stendhal_ui.check_image('feet-empty', '拒绝后脚部槽仍为空', FEET, EQUIP)


@pytest.mark.case(id='ST-BAG-UI-007', game='stendhal', module='inventory', kind='ui', title='界面连喝两瓶药水：一次一瓶、回血50并按100封顶')
def test_android_two_potions_heal_and_cap_at_maximum(qa, stendhal_ui, observer, prepare):
    original = observer.inspect()
    if original['statuses'] or original['attributes'].get('target'):
        qa.data['failure_kind'] = 'preparation_error'
        raise ValueError('Potion UI fixture needs no active status or combat; R1 does not restore statuses')
    before = prepare(money=0, items={'minor potion': 2}, xp=0, hp=40,
                     zone='int_semos_guard_house', x=12, y=12)
    qa.data['diagnostics']['coverage_limit'] = '安全地图、无持续状态、两次实际Drink；不覆盖交战中的治疗与伤害事件时序。'
    qa.check('药水固定前置：最大HP100、当前40、两瓶',
             [before['base_hp'], before['hp'], quantity(before, 'minor potion')], [100, 40, 2], POTION + '; 专用0级角色最大HP100')
    qa.check('专用角色背包仅含待使用药水，空槽断言不会被其它道具混淆',
             [item['name'] for item in before['slots']['bag']], ['minor potion'], '固定本地UI背包基线；R1完整恢复')
    qa.check('前置没有持续状态或主动战斗', [before['statuses'], before['attributes'].get('target')], [[], None], HEAL)
    stendhal_ui.check_image('hp-40', '开始时界面显示HP40/100', STATS, HEAL, threshold=0.98)
    stendhal_ui.check_image('potion-two', '开始时背包显示两瓶药水', (568, 343, 596, 372), POTION, threshold=0.98)
    for remaining, hp, image in ((1, 90, 'potion-one'), (0, 100, 'bag-empty')):
        stendhal_ui.choose_item_menu('minor-potion-icon', BAG, 'drink')
        after = await_exact_quantity(observer, 'minor potion', remaining)
        qa.check('一次Drink只消耗一瓶：剩' + str(remaining), quantity(after, 'minor potion'), remaining, FEEDER)
        qa.check('回血50并封顶：HP' + str(hp), after['hp'], hp, POTION + '; ' + FEEDER + '; ' + HEAL)
        qa.check('使用保持最大HP、经验、金币与等级：剩' + str(remaining),
                 [after[key] for key in ('base_hp', 'xp', 'money', 'level')],
                 [before[key] for key in ('base_hp', 'xp', 'money', 'level')], USE + '; ' + HEAL)
        qa.check('即时药水不新增持续状态或攻击目标：剩' + str(remaining),
                 [after['statuses'], after['attributes'].get('target')], [[], None], FEEDER)
        stendhal_ui.check_image('hp-' + str(hp), 'Drink后界面显示HP' + str(hp) + '/100', STATS, HEAL, threshold=0.98)
        # Fixed dedicated character has no other bag items; final empty first slot is meaningful.
        stendhal_ui.check_image(image, 'Drink后背包数量或空槽：剩' + str(remaining), (568, 343, 596, 372), FEEDER, threshold=0.98)
