"""One original Android Attack, followed by observed combat, cleanup and R1 restore."""
import time

import pytest

from gameqa.stendhal import await_quantity, await_slot_empty, quantity
from gameqa.stendhal_ui import ASSETS
from gameqa.sources import SOURCE
from cases.test_stendhal_combat import LOADER, REWARD, ATTACK, combat, rat_fixture
from cases.test_stendhal_items_ui import BAG, RHAND, STATS, SWORD, EQUIP


MAP = (96, 203, 565, 555)
MENU = SOURCE + 'src/js/stendhal/ui/TouchHandler.ts; ' + SOURCE + 'src/js/stendhal/ui/dialog/ActionContextMenu.ts#L67-L86'
CORPSE = SOURCE + 'src/games/stendhal/server/entity/RPEntity.java (die/makeCorpse)'


@pytest.mark.case(id='ST-COMBAT-UI-001', game='stendhal', module='combat', kind='ui', title='界面换装短剑并攻击击杀rat：真实获得经验')
def test_android_attack_kills_rat_and_grants_experience(qa, stendhal_ui, observer, prepare, rat_fixture):
    original = observer.inspect()
    if original['statuses'] or original['attributes'].get('target'):
        qa.data['failure_kind'] = 'preparation_error'
        raise ValueError('Combat UI needs no active status or attack; R1 does not restore statuses')
    before = prepare(money=0, items={'short sword': 1}, xp=800, hp=100,
                     zone='int_semos_guard_house', x=12, y=5)
    qa.data['diagnostics']['coverage_limit'] = (
        '原版rat、一次实际Attack、单人击杀；不验证固定伤害/时长、随机掉落内容、拾取、战中治疗或死亡复活。'
        '先清理专用rat及对应尸体，再R1恢复角色；不回滚血迹、审计日志或整个世界。')
    qa.check('原装右手木棍与固定背包前置',
             [[item['name'] for item in before['slots'][slot]] for slot in ('rhand', 'bag')],
             [['club'], ['short sword']], '专用UI角色原装基线；GM只准备短剑与等级')
    qa.check('短剑等级前置达标', before['level'] >= 5, True, SWORD)
    qa.check('战斗前生命与经验', [before['hp'], before['xp']], [100, 800], '本地隔离战斗前置')
    stendhal_ui.move_item('club-icon', RHAND, 'bag-empty', BAG)
    unarmed = await_slot_empty(observer, 'rhand')
    qa.check('真实UI卸下原木棍', [unarmed['slots']['rhand'], quantity(unarmed, 'club')], [[], 1], EQUIP)
    stendhal_ui.move_item('short-sword-first', BAG, 'rhand-empty', RHAND)
    armed = await_quantity(observer, 'short sword', 1, slot='rhand')
    qa.check('真实UI装备短剑且总量1',
             [quantity(armed, 'short sword', 'rhand'), quantity(armed, 'short sword', None)], [1, 1], EQUIP)
    stendhal_ui.check_image('short-sword-icon', '战斗前右手实际显示短剑', RHAND, EQUIP)
    stendhal_ui.check_image('xp-800', '战斗前界面显示XP800', STATS, REWARD, threshold=0.98)
    fixture = rat_fixture()
    qa.check('原版rat的HP/ATK/DEF未改弱',
             [int(fixture['rat'][key]) for key in ('hp', 'atk', 'def')], [20, 8, 3],
             SOURCE + 'data/conf/creatures/rodent.xml#L36-L48')
    qa.check('原版rat内部XP为5乘20', int(fixture['rat']['xp']), 100, LOADER)

    # Observe the original AI approaching naturally; a moving label can miss during client interpolation.
    deadline = time.monotonic() + 10
    approach = []
    previous = None
    while True:
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        approach.append(enemy)
        rat = enemy['rat']; player = armed['attributes']
        adjacent = max(abs(int(rat['x']) - int(player['x'])), abs(int(rat['y']) - int(player['y']))) == 1
        stopped = enemy['rat_present'] and adjacent and float(rat.get('speed', 1)) == 0
        current = (rat['x'], rat['y'])
        settled = stopped and current == previous
        previous = current if stopped else None
        if settled or time.monotonic() >= deadline:
            break
        time.sleep(0.3)
    qa.data['diagnostics']['combat_approach'] = approach
    qa.check('原版rat自然靠近并停止移动后才定位', settled, True, ATTACK + '; 原版rat AI，未修改移动/攻击')
    qa.check('界面攻击前rat仍为原版20HP', int(enemy['rat']['hp']), 20, ATTACK)
    time.sleep(0.6)

    # The unique rat label moves with its body; use its real screen location, not GM coordinates.
    stendhal_ui.open_creature_menu('rat-title', MAP)
    stendhal_ui.choose_creature_menu('attack', MAP)
    deadline = time.monotonic() + 45
    observations = []
    while True:
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        observations.append(enemy)
        if not enemy['rat_present'] or time.monotonic() >= deadline:
            break
        time.sleep(0.3)
    after = observer.inspect()
    qa.data['diagnostics'].update(combat_observations=observations, combat_before=armed, combat_after=after)
    qa.check('实际Attack使rat死亡离开地图', enemy['rat_present'], False, ATTACK)
    qa.check('死亡rat的HP为0', int(enemy['rat']['hp']), 0, ATTACK)
    qa.check('原版死亡流程生成该rat尸体', enemy['corpse_present'], True, CORPSE)
    qa.check('对应尸体记录实际击杀者', enemy['corpse']['killer'], observer.config['target'], CORPSE)
    qa.check('单人击杀获得5经验', after['xp'] - armed['xp'], 5, REWARD)
    qa.check('单人rat击杀记录增加1',
             int(after['keyed']['!kills'].get('solo.rat', 0)) - int(armed['keyed']['!kills'].get('solo.rat', 0)), 1, REWARD)
    qa.check('战斗结束角色存活且HP不高于初始100', 0 < after['hp'] <= armed['hp'], True,
             '实际原版战斗；本例无回血道具，不断言固定随机伤害')
    qa.check('击杀未触发新等级', [after['level'], after['base_hp']], [armed['level'], armed['base_hp']],
             SOURCE + 'src/games/stendhal/server/entity/player/Player.java (level thresholds)')
    qa.check('未拾取随机掉落，背包金币及武器数量保持',
             [after['money'], quantity(after, 'club'), quantity(after, 'short sword', 'rhand')],
             [armed['money'], quantity(armed, 'club'), 1], CORPSE + '; 本例不操作尸体槽')
    time.sleep(0.6)
    stendhal_ui.check_image('xp-805', '真实击杀后界面显示XP805', STATS, REWARD, threshold=0.98)
    stendhal_ui.check_image('rat-corpse', '地图实际显示rat尸体', MAP, CORPSE)
