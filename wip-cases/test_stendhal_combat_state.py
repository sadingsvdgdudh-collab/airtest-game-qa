"""攻击状态与频率：攻击间隔、射程、目标设置与停止、命中扣血、击杀经验。

这些用例全部读战斗夹具的体检字段（attack_rate / range / squared_distance /
target_fixture / rat.attributes），不依赖随机骰的具体数值，因此可稳定判定。

夹具约定：rat 为原版 AI 与数值（hp 20、经验 100、atk 8、def 3），放置在守卫室；
玩家初始右手持 club（rate 4），需要空手时必须先卸下。
"""
import time

import pytest

from gameqa.stendhal import await_quantity, quantity
from gameqa.sources import SOURCE
from cases.test_stendhal_combat import ATTACK, combat, equip, rat_fixture

BASE = dict(zone="int_semos_guard_house", x=12, y=5)
RATE = SOURCE + "src/games/stendhal/server/entity/ActiveEntity.java（getAttackRate）"
RANGE = SOURCE + "src/games/stendhal/server/entity/ActiveEntity.java（getMaxRangeForArcher）"
STOP = SOURCE + "src/games/stendhal/server/actions/attack/StopAction.java"
REWARD = SOURCE + "src/games/stendhal/server/entity/RPEntity.java（rewardKillers）"


def wait_turns(observer, fixture_id, turns, timeout=40.0):
    """等服务器推进指定回合数；回合是攻击节奏的唯一时间基准。"""
    start = combat(observer, "inspect", fixture_id=fixture_id)["turn"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = combat(observer, "inspect", fixture_id=fixture_id)
        if state["turn"] - start >= turns:
            return state
        time.sleep(0.4)
    return combat(observer, "inspect", fixture_id=fixture_id)


def wait_adjacent(observer, fixture_id, timeout=40.0):
    """等 rat 的 AI 走到玩家相邻格。

    attack 在距离外提交时服务端不建立攻击目标；先等邻接再攻击，
    才能验证「发起后目标成立」这条规则。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = combat(observer, "inspect", fixture_id=fixture_id)
        if state["next_to"]:
            return state
        time.sleep(0.4)
    return combat(observer, "inspect", fixture_id=fixture_id)


def strip_to_bare_hand(player, state, observer):
    """卸下初始 club，返回空手后的状态。"""
    club = next(item for item in state["slots"]["rhand"] if item["name"] == "club")
    equip(player, state, club, "rhand", "bag")
    return await_quantity(observer, "club", 1, slot="bag")


@pytest.mark.case(id="ST-COMBAT-API-003", game="stendhal", module="combat", kind="api",
                  title="空手攻击间隔为5回合")
def test_bare_hand_attack_rate_is_five(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=0, hp=100, **BASE)
    fixture = rat_fixture()
    bare = strip_to_bare_hand(api_player, before, observer)
    qa.check("卸下 club 后右手为空", bare["slots"]["rhand"], [], RATE)

    state = combat(observer, "inspect", fixture_id=fixture["fixture_id"])
    qa.check("空手时攻击间隔为5", state["attack_rate"], 5, RATE)


@pytest.mark.case(id="ST-COMBAT-API-004", game="stendhal", module="combat", kind="api",
                  title="持械时攻击间隔取该武器rate")
def test_armed_attack_rate_follows_weapon_rate(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=0, hp=100, **BASE)
    fixture = rat_fixture()
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    qa.check("初始右手持 club", club["name"], "club", RATE)
    qa.check("club 的 rate 为4", club["attributes"]["rate"], "4", RATE)

    state = combat(observer, "inspect", fixture_id=fixture["fixture_id"])
    qa.check("持 club 时攻击间隔为4", state["attack_rate"], 4, RATE)


@pytest.mark.case(id="ST-COMBAT-API-005", game="stendhal", module="combat", kind="api",
                  title="首武器等级不足时攻击间隔按对数修正后向上取整")
def test_low_level_weapon_slows_attack_rate(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=0, hp=100, items={"short sword": 1}, **BASE)
    fixture = rat_fixture()
    bare = strip_to_bare_hand(api_player, before, observer)
    sword = next(item for item in bare["slots"]["bag"] if item["name"] == "short sword")
    qa.check("short sword 最低等级为5", sword["attributes"]["min_level"], "5", RATE)

    equip(api_player, bare, sword, "bag", "rhand")
    armed = await_quantity(observer, "short sword", 1, slot="rhand")
    qa.check("等级0仍可装备 short sword", quantity(armed, "short sword", "rhand"), 1, RATE)

    state = combat(observer, "inspect", fixture_id=fixture["fixture_id"])
    # ceil(4 × [1 − ln((0+1)/(5+1))]) = ceil(11.167) = 12
    qa.check("等级不足时攻击间隔修正为12", state["attack_rate"], 12, RATE)


@pytest.mark.case(id="ST-COMBAT-API-006", game="stendhal", module="combat", kind="api",
                  title="弓与弹药的射程相加")
def test_bow_and_ammunition_range_add_up(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=0, hp=100, items={"wooden bow": 1, "wooden arrow": 10}, **BASE)
    fixture = rat_fixture()
    bare = strip_to_bare_hand(api_player, before, observer)
    bow = next(item for item in bare["slots"]["bag"] if item["name"] == "wooden bow")
    arrows = next(item for item in bare["slots"]["bag"] if item["name"] == "wooden arrow")
    qa.check("wooden bow 射程为3", bow["attributes"]["range"], "3", RANGE)
    qa.check("wooden arrow 射程为2", arrows["attributes"]["range"], "2", RANGE)

    equip(api_player, bare, bow, "bag", "rhand")
    armed = await_quantity(observer, "wooden bow", 1, slot="rhand")
    equip(api_player, armed, arrows, "bag", "lhand")
    loaded = await_quantity(observer, "wooden arrow", 1, slot="lhand")
    qa.check("弓在右手、十支箭整堆在左手", [quantity(loaded, "wooden bow", "rhand"),
                                quantity(loaded, "wooden arrow", "lhand")], [1, 10], RANGE)

    state = combat(observer, "inspect", fixture_id=fixture["fixture_id"])
    qa.check("弓加弹药最大射程为5", state["range"], 5, RANGE)


@pytest.mark.case(id="ST-COMBAT-API-007", game="stendhal", module="combat", kind="api",
                  title="非邻接且无远程手段时攻击不造成伤害")
def test_ranged_attack_without_bow_deals_no_damage(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=0, hp=100, **BASE)
    fixture = rat_fixture(placement="far")
    fid = fixture["fixture_id"]
    start = combat(observer, "inspect", fixture_id=fid)
    qa.check("初始不与目标邻接", start["next_to"], False, RANGE)
    qa.check("无弓时最大射程为0", start["range"], 0, RANGE)

    strip_to_bare_hand(api_player, before, observer)
    api_player.action({"type": "attack", "target": "#" + start["rat"]["id"]}, "玩家攻击远处的rat")
    later = wait_turns(observer, fid, 8)

    qa.check("远处目标未被扣血", later["rat"]["hp"], "20", RANGE)


@pytest.mark.case(id="ST-COMBAT-API-008", game="stendhal", module="combat", kind="api",
                  title="发起攻击后该怪物成为攻击目标")
def test_attack_sets_combat_target(qa, api_player, observer, prepare, rat_fixture):
    prepare(xp=0, hp=100, **BASE)
    fixture = rat_fixture()
    fid = fixture["fixture_id"]
    before = combat(observer, "inspect", fixture_id=fid)
    qa.check("发起前未锁定该怪物", before["target_fixture"], False, ATTACK)

    near = wait_adjacent(observer, fid)
    qa.check("rat已靠近到相邻格", near["next_to"], True, ATTACK)
    api_player.action({"type": "attack", "target": "#" + near["rat"]["id"]}, "玩家真实攻击rat")
    after = wait_turns(observer, fid, 1)
    qa.check("发起后攻击目标指向该怪物", after["target_fixture"], True, ATTACK)


@pytest.mark.case(id="ST-COMBAT-API-009", game="stendhal", module="combat", kind="api",
                  title="重复发起与缺失目标不改变攻击状态")
def test_repeated_or_empty_attack_keeps_target(qa, api_player, observer, prepare, rat_fixture):
    prepare(xp=0, hp=100, **BASE)
    fixture = rat_fixture()
    fid = fixture["fixture_id"]
    near = wait_adjacent(observer, fid)
    rat_id = near["rat"]["id"]
    qa.check("rat已靠近到相邻格", near["next_to"], True, ATTACK)

    api_player.action({"type": "attack", "target": "#" + rat_id}, "首次攻击rat")
    first = wait_turns(observer, fid, 1)
    qa.check("首次攻击后目标指向该怪物", first["target_fixture"], True, ATTACK)

    api_player.action({"type": "attack", "target": "#" + rat_id}, "重复攻击同一rat")
    second = wait_turns(observer, fid, 1)
    qa.check("重复发起后目标仍是该怪物", second["target_fixture"], True, ATTACK)

    api_player.action({"type": "attack"}, "提交不带目标的攻击")
    third = wait_turns(observer, fid, 1)
    qa.check("不带目标提交后攻击状态不变", third["target_fixture"], True, ATTACK)


@pytest.mark.case(id="ST-COMBAT-API-010", game="stendhal", module="combat", kind="api",
                  title="停止攻击只在携带attack字段时生效")
def test_stop_clears_target_only_with_attack_field(qa, api_player, observer, prepare, rat_fixture):
    prepare(xp=0, hp=100, **BASE)
    fixture = rat_fixture()
    fid = fixture["fixture_id"]
    near = wait_adjacent(observer, fid)
    rat_id = near["rat"]["id"]
    qa.check("rat已靠近到相邻格", near["next_to"], True, STOP)

    api_player.action({"type": "attack", "target": "#" + rat_id}, "攻击rat")
    qa.check("攻击目标已建立", wait_turns(observer, fid, 1)["target_fixture"], True, STOP)

    api_player.action({"type": "stop"}, "提交不带attack字段的stop")
    still = combat(observer, "inspect", fixture_id=fid)
    qa.check("不带attack字段时攻击目标保留", still["target_fixture"], True, STOP)

    api_player.action({"type": "stop", "attack": "#" + rat_id}, "提交带attack字段的stop")
    cleared = wait_turns(observer, fid, 1)
    qa.check("带attack字段后攻击目标清除", cleared["target_fixture"], False, STOP)


@pytest.mark.case(id="ST-COMBAT-API-011", game="stendhal", module="combat", kind="api",
                  title="近战攻击命中后怪物生命下降")
def test_melee_hit_reduces_rat_hp(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=800, hp=100, items={"short sword": 1}, **BASE)
    fixture = rat_fixture()
    fid = fixture["fixture_id"]
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    equip(api_player, before, club, "rhand", "bag")
    bare = await_quantity(observer, "club", 1, slot="bag")
    sword = next(item for item in bare["slots"]["bag"] if item["name"] == "short sword")
    equip(api_player, bare, sword, "bag", "rhand")
    armed = await_quantity(observer, "short sword", 1, slot="rhand")
    qa.check("已装备短剑", quantity(armed, "short sword", "rhand"), 1, ATTACK)

    start = combat(observer, "inspect", fixture_id=fid)
    qa.check("rat初始生命为20", start["rat"]["hp"], "20", ATTACK)
    api_player.action({"type": "attack", "target": "#" + start["rat"]["id"]}, "玩家近战攻击rat")
    later = wait_turns(observer, fid, 8)

    qa.check("命中后rat生命下降", int(later["rat"]["hp"]) < 20, True, ATTACK)


@pytest.mark.case(id="ST-COMBAT-API-012", game="stendhal", module="combat", kind="api",
                  title="击杀rat获得持有经验5%的经验并留下尸体")
def test_kill_grants_five_percent_xp_and_corpse(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=0, hp=100, items={"short sword": 1}, **BASE)
    fixture = rat_fixture()
    fid = fixture["fixture_id"]
    club = next(item for item in before["slots"]["rhand"] if item["name"] == "club")
    equip(api_player, before, club, "rhand", "bag")
    bare = await_quantity(observer, "club", 1, slot="bag")
    sword = next(item for item in bare["slots"]["bag"] if item["name"] == "short sword")
    equip(api_player, bare, sword, "bag", "rhand")
    await_quantity(observer, "short sword", 1, slot="rhand")

    start = combat(observer, "inspect", fixture_id=fid)
    qa.check("rat持有经验为100", start["rat"]["xp"], "100", REWARD)
    api_player.action({"type": "attack", "target": "#" + start["rat"]["id"]}, "玩家攻击rat")

    deadline = time.monotonic() + 60
    state = start
    while time.monotonic() < deadline:
        state = combat(observer, "inspect", fixture_id=fid)
        if not state["rat_present"]:
            break
        time.sleep(0.5)

    qa.check("rat已死亡离开地图", state["rat_present"], False, REWARD)
    qa.check("地面留下尸体", state["corpse_present"], True, REWARD)
    killed = observer.inspect()
    qa.check("击杀经验为持有经验的5%", killed["xp"] - before["xp"], 5, REWARD)
