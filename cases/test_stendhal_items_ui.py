"""Original mobile Hold/Drink actions, verified by UI and an independent observer."""
import pytest

from gameqa.stendhal import await_exact_quantity, await_quantity, quantity
from gameqa.sources import SOURCE
from cases.test_stendhal_items_edges import POTION, FEEDER, HEAL, USE


EQUIP = SOURCE + 'src/games/stendhal/server/actions/equip/SourceObject.java#L318-L345'
BAG = (566, 300, 660, 428)
RHAND = (565, 218, 598, 252)
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
