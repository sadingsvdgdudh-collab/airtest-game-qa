"""Original attack/stop actions; two executions cover design ST-COMBAT-API-004."""
import time

import pytest

from gameqa.recovery import reset_character
from gameqa.sources import SOURCE
from cases.test_stendhal_combat import ATTACK, combat, rat_fixture


DISTANCE = (SOURCE + 'src/games/stendhal/server/core/rp/StendhalRPAction.java#L302-L317; '
            + SOURCE + 'src/games/stendhal/server/entity/Entity.java#L399-L425')
STOP = (SOURCE + 'src/games/stendhal/server/actions/attack/StopAction.java#L34-L41; '
        + SOURCE + 'src/games/stendhal/server/entity/RPEntity.java#L1240-L1255')
TURNS = SOURCE + 'src/games/stendhal/server/entity/player/Player.java#L2085-L2098'
EVENTS = (SOURCE + 'src/games/stendhal/server/events/AttackEvent.java#L57-L71; '
          + SOURCE + 'src/games/stendhal/server/core/rp/StendhalRPAction.java#L423-L430')
CLUB = SOURCE + 'data/conf/items/clubs.xml#L28-L38'


def events(player, qa):
    # Consuming the original event queue is not retried; every returned event is retained.
    return qa.observe('读取并保留玩家原版事件队列', lambda:
                      player.bridge.call('get_events', read_only=True), retries=0)


def own_attacks(player, rows):
    return [row for row in rows if row.get('event') == 'attack'
            and row.get('source_name') == player.config['target']]


def prepare_club_character(qa, api_player, observer, prepare, *, x=12):
    # 前置不能靠环境：上一个用例失败可能把武器留成别的（实测短剑），这里先按出厂状态回收
    qa.data['diagnostics']['gear_reset'] = reset_character(api_player, observer)
    original = observer.inspect()
    if original['statuses'] or original['attributes'].get('target'):
        qa.data['failure_kind'] = 'preparation_error'
        raise ValueError('Combat edges need no active status or attack; R1 does not restore statuses')
    before = prepare(xp=800, hp=100, zone='int_semos_guard_house', x=x, y=5)
    qa.check('使用角色既有原版木棍', [item['name'] for item in before['slots']['rhand']], ['club'], CLUB)
    return before


@pytest.mark.case(id='ST-COMBAT-API-004-distance', game='stendhal', module='combat', kind='api', title='远距近战只选中目标：连续两个攻击周期不造成伤害')
def test_distant_melee_attack_selects_target_without_dealing_damage(
        qa, api_player, observer, prepare, rat_fixture):
    # (17,15) is clear floor, 10 tiles from the player and >8 from GM at (8,12).
    before = prepare_club_character(qa, api_player, observer, prepare, x=17)
    fixture = rat_fixture(placement='far')
    qa.data['diagnostics']['coverage_limit'] = (
        '原版协议远距离近战；允许选中远方目标，验证连续两个实际攻击周期不能造成伤害。'
        'rat保留AI，逐次读取真实邻接/距离；不验证远程武器或Android菜单。')
    qa.check('远距前置没有远程武器射程', fixture['range'], 0, DISTANCE)
    qa.check('远距前置确实不邻接且超出射程',
             [fixture['next_to'], fixture['squared_distance'] > fixture['range'] ** 2], [False, True], DISTANCE)
    qa.check('远距rat初始为原版20HP', int(fixture['rat']['hp']), 20,
             SOURCE + 'data/conf/creatures/rodent.xml#L36-L48')
    qa.data['diagnostics']['events_before_attack'] = events(api_player, qa)
    api_player.action({'type': 'attack', 'target': '#' + fixture['rat']['id']}, '玩家一次实际选择远处rat攻击')

    acknowledgements = qa.data['diagnostics']['distant_attack_ack_observations'] = []
    recorded_events = qa.data['diagnostics']['distant_combat_events'] = []
    deadline = time.monotonic() + 10
    while True:
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        acknowledgements.append(enemy)
        recorded_events.extend(events(api_player, qa))
        if enemy['target_fixture'] or time.monotonic() >= deadline:
            break
        time.sleep(0.15)
    qa.check('原版允许选中远处rat但尚未造成伤害',
             [enemy['target_fixture'], int(enemy['rat']['hp'])], [True, 20], ATTACK + '; ' + DISTANCE)
    start_turn, rate = enemy['turn'], enemy['attack_rate']
    readings = qa.data['diagnostics']['distant_combat_observations'] = [enemy]
    while enemy['turn'] - start_turn < rate * 2 and time.monotonic() < deadline:
        time.sleep(0.15)
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        readings.append(enemy)
        recorded_events.extend(events(api_player, qa))
        if enemy['next_to'] or not enemy['rat_present']:
            break
    qa.check('按原服回合覆盖至少两个实际攻击周期', enemy['turn'] - start_turn >= rate * 2, True, TURNS)
    qa.check('整个远距窗口均非邻接、超射程、目标仍为该rat',
             all(not row['next_to'] and row['squared_distance'] > row['range'] ** 2
                 and row['target_fixture'] and row['rat_present'] for row in readings), True, DISTANCE)
    qa.check('远距窗口rat始终20HP且没有尸体',
             all(int(row['rat']['hp']) == 20 and not row['corpse_present'] for row in readings), True, DISTANCE)
    qa.check('远距没有本玩家命中、未命中或伤害事件', own_attacks(api_player, recorded_events), [], EVENTS + '; ' + DISTANCE)
    after = observer.inspect()
    qa.check('远距没有错误改变角色生命、经验、金币及击杀记录',
             [after[key] for key in ('hp', 'xp', 'money')] + [after['keyed']['!kills']],
             [before[key] for key in ('hp', 'xp', 'money')] + [before['keyed']['!kills']], DISTANCE)


@pytest.mark.case(id='ST-COMBAT-API-004-cancel', game='stendhal', module='combat', kind='api', title='造成真实伤害后取消攻击：停止出手且rat存活')
def test_cancel_after_real_damage_stops_player_attack_while_rat_remains_alive(
        qa, api_player, observer, prepare, rat_fixture):
    before = prepare_club_character(qa, api_player, observer, prepare)
    fixture = rat_fixture()
    qa.data['diagnostics']['coverage_limit'] = (
        '原版协议取消攻击；先证实本玩家实际造成正伤害且rat存活，再发送一次stop(attack空串)。'
        '停止后观察至少两个实际攻击周期；rat可以继续自主反击，不要求玩家HP恒定；不验证Android菜单。')
    approach = qa.data['diagnostics']['cancel_combat_approach'] = []
    deadline = time.monotonic() + 10
    while True:
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        approach.append(enemy)
        if enemy['next_to'] or time.monotonic() >= deadline:
            break
        time.sleep(0.15)
    qa.check('取消前正向对照rat自然靠近', [enemy['next_to'], int(enemy['rat']['hp'])], [True, 20], ATTACK)
    qa.data['diagnostics']['events_before_attack'] = events(api_player, qa)
    api_player.action({'type': 'attack', 'target': '#' + fixture['rat']['id']}, '玩家一次实际Attack启动战斗')
    attacks = qa.data['diagnostics']['before_cancel_events'] = []
    attacking = qa.data['diagnostics']['before_cancel_observations'] = []
    deadline = time.monotonic() + 20
    while True:
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        attacking.append(enemy)
        attacks.extend(events(api_player, qa))
        positive = any(int(row.get('damage', 0)) > 0 for row in own_attacks(api_player, attacks))
        if (positive and int(enemy['rat']['hp']) < 20) or not enemy['rat_present'] or time.monotonic() >= deadline:
            break
        time.sleep(0.15)
    qa.check('取消前本玩家确实造成正伤害且rat仍存活',
             [positive, enemy['rat_present'], 0 < int(enemy['rat']['hp']) < 20, enemy['target_fixture']],
             [True, True, True, True], ATTACK + '; ' + EVENTS)
    rate = enemy['attack_rate']
    api_player.action({'type': 'stop', 'attack': ''}, '玩家一次实际Stop attack取消攻击')
    acknowledgements = qa.data['diagnostics']['cancel_ack_observations'] = []
    ack_events = qa.data['diagnostics']['cancel_ack_events'] = []
    deadline = time.monotonic() + 5
    while True:
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        own_state = api_player.bridge.call('get_self_state', read_only=True)
        acknowledgements.append({'server': enemy, 'client': own_state})
        ack_events.extend(events(api_player, qa))
        if (not enemy['target_fixture'] and own_state['attributes'].get('target') is None) or time.monotonic() >= deadline:
            break
        time.sleep(0.15)
    qa.check('原服及实际客户端均确认攻击目标清空',
             [enemy['target_fixture'], own_state['attributes'].get('target')], [False, None], STOP)
    qa.check('停止执行时rat仍然活着', [enemy['rat_present'], int(enemy['rat']['hp']) > 0], [True, True], STOP)

    start_turn, remaining_hp = enemy['turn'], int(enemy['rat']['hp'])
    stopped = qa.data['diagnostics']['after_cancel_observations'] = [enemy]
    later_events = qa.data['diagnostics']['after_cancel_events'] = []
    deadline = time.monotonic() + 10
    while enemy['turn'] - start_turn < rate * 2 and time.monotonic() < deadline:
        time.sleep(0.15)
        enemy = combat(observer, 'inspect', fixture_id=fixture['fixture_id'])
        stopped.append(enemy)
        later_events.extend(events(api_player, qa))
    qa.check('取消后按原服回合覆盖至少两个实际攻击周期', enemy['turn'] - start_turn >= rate * 2, True, TURNS)
    qa.check('取消后攻击目标始终清空且rat始终存活、未生成尸体',
             all(not row['target_fixture'] and row['rat_present'] and not row['corpse_present'] for row in stopped),
             True, STOP)
    qa.check('取消后rat生命保持停止执行时的值', [int(row['rat']['hp']) for row in stopped],
             [remaining_hp] * len(stopped), STOP)
    qa.check('取消后没有本玩家继续攻击的命中、未命中或伤害事件',
             own_attacks(api_player, later_events), [], STOP + '; ' + EVENTS)
    after = observer.inspect()
    qa.data['diagnostics']['after_cancel_player'] = after
    qa.check('取消后角色无目标且存活', [after['attributes'].get('target'), after['hp'] > 0], [None, True], STOP)
    qa.check('未击杀rat，不增加经验金币或击杀记录',
             [after[key] for key in ('xp', 'money')] + [after['keyed']['!kills']],
             [before[key] for key in ('xp', 'money')] + [before['keyed']['!kills']], STOP)
