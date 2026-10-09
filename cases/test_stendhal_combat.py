import time

import pytest

from gameqa.stendhal import (await_position, await_quantity, await_slot_empty,
                             position, quantity)
from gameqa.stendhal import equip as session_equip
from gameqa.sources import LEVEL_RULES, LEVEL_UPDATE, SOURCE


LOADER = SOURCE + "src/games/stendhal/server/core/config/CreaturesXMLLoader.java#L206 (XML experience×20)"
REWARD = LOADER + "; " + SOURCE + "src/games/stendhal/server/entity/RPEntity.java#L1567-L1628 (rat 5×20×0.05 = 5 XP)"
ATTACK = SOURCE + "src/games/stendhal/server/actions/attack/AttackAction.java; " + SOURCE + "src/games/stendhal/server/core/rp/StendhalRPAction.java"
MOVEMENT = SOURCE + "src/games/stendhal/server/actions/move/MoveToAction.java; " + SOURCE + "src/games/stendhal/server/core/pathfinder/EntityPathfinder.java"
COLLISION = SOURCE + "src/games/stendhal/server/core/engine/StendhalRPZone.java#L1114-L1126 (collides)"
PORTAL = SOURCE + "src/games/stendhal/server/core/engine/StendhalRPZone.java#L245 (getPortals); " + SOURCE + "src/games/stendhal/server/actions/move/MoveToAction.java#L109-L111 (extendPathForZoneChangeIfRequested)"
DIRECTIONS = (("右", (1, 0)), ("下", (0, 1)), ("左", (-1, 0)), ("上", (0, -1)))


def combat(observer, operation, **fields):
    # 走观察者的 _guarded：战斗夹具操作也享受"瞬断后重连+重登+重试一次"。
    # 不这么做的话，一次瞬断就会把夹具留在服务端（Clean the active combat fixture first），
    # 后面所有战斗用例连环失败——实测过。
    try:
        result = observer._guarded("combat_" + operation, fields,
                                   read_only=operation in {"inspect", "layout"})
    except Exception as error:
        # 上一次中断把夹具留在了服务端：先按目标清掉全部夹具，再重试一次（不必重启主服）。
        if operation != "prepare" or "Clean the active combat fixture first" not in str(error):
            raise
        cleaned = observer._guarded("combat_cleanup_all", {}, read_only=False)
        observer.evidence.data["diagnostics"].setdefault("combat_fixture_recovery", []).append(cleaned)
        result = observer._guarded("combat_" + operation, fields, read_only=False)
    observer.evidence.data["diagnostics"].setdefault("combat_fixture", []).append({"operation": operation, "result": result})
    return result


@pytest.fixture
def rat_fixture(observer, request):
    fixture_id = None
    def start(**fields):
        nonlocal fixture_id
        try:
            result = combat(observer, "prepare", **fields)
        except Exception:
            observer.evidence.data["failure_kind"] = "preparation_error"
            raise
        fixture_id = result["fixture_id"]
        return result
    yield start
    if fixture_id:
        if request.node._qa_meta['kind'] == 'ui':
            presence = observer.evidence.observe('清理前独立读取UI角色在线状态', lambda:
                observer.bridge.call('presence', {'target': observer.config['target']}, read_only=True))
            if presence.get('name') != observer.config['target'] or type(presence.get('online')) is not bool:
                raise ValueError('invalid UI presence before combat cleanup')
            observer.evidence.data['diagnostics']['combat_cleanup_presence'] = presence
            if not presence['online']:
                request.getfixturevalue('stendhal_ui').ensure_login()
                observer.await_presence(True)
        result = combat(observer, "cleanup", fixture_id=fixture_id)
        assert result["rat_present"] is False and result["corpse_present"] is False


def equip(player, state, item, source, destination):
    """委托会话层 stendhal.equip：实现只有一份，用例层保留这个名字方便既有调用。"""
    return session_equip(player, state, item, source, destination)




@pytest.mark.case(id="ST-COMBAT-API-001", game="stendhal", module="combat", kind="api", title="单人攻击击杀rat：死亡离开地图、留下尸体、得5经验")
def test_player_equips_weapon_and_really_kills_rat(qa, api_player, observer, prepare, rat_fixture):
    before = prepare(xp=800, hp=100, items={"short sword": 1}, zone="int_semos_guard_house", x=12, y=5)
    # Every equipment move still comes through the real player's original equip action.
    if before["slots"]["rhand"]:
        equip(api_player, before, before["slots"]["rhand"][0], "rhand", "bag")
        before = await_slot_empty(observer, "rhand")
    sword = next(item for item in before["slots"]["bag"] if item["name"] == "short sword")
    equip(api_player, before, sword, "bag", "rhand")
    armed = await_quantity(observer, "short sword", 1, slot="rhand")
    qa.check("玩家真实装备short sword", quantity(armed, "short sword", "rhand"), 1,
             SOURCE + "src/games/stendhal/server/actions/equip/EquipAction.java")
    fixture = rat_fixture()
    qa.check("rat初始HP未削减", int(fixture["rat"]["hp"]), 20, SOURCE + "data/conf/creatures/rodent.xml#L36-L48")
    qa.check("rat原版内部经验为配置5×20", int(fixture["rat"]["xp"]), 100,
             SOURCE + "data/conf/creatures/rodent.xml#L36-L48; " + LOADER)
    api_player.action({"type": "attack", "target": "#" + fixture["rat"]["id"]}, "玩家真实攻击rat")
    deadline = time.monotonic() + 45
    observations = []
    while True:
        enemy = combat(observer, "inspect", fixture_id=fixture["fixture_id"])
        observations.append(enemy)
        if not enemy["rat_present"] or time.monotonic() >= deadline:
            break
        time.sleep(0.3)
    after = observer.inspect()
    qa.data["diagnostics"]["combat_observations"] = observations
    qa.check("真实攻击使rat死亡离开地图", enemy["rat_present"], False, ATTACK)
    qa.check("原版死亡流程生成该rat的尸体", enemy["corpse_present"], True,
             SOURCE + "src/games/stendhal/server/entity/RPEntity.java (die/makeCorpse)")
    qa.check("单人击杀获得5经验", after["xp"] - armed["xp"], 5, REWARD)
    qa.check("单人击杀记录增加1", int(after["keyed"]["!kills"].get("solo.rat", 0)) -
             int(armed["keyed"]["!kills"].get("solo.rat", 0)), 1, REWARD)
    qa.check("玩家存活", after["hp"] > 0, True, "夹具准备100HP；测试真实rat战斗，不测试死亡")


@pytest.mark.case(id="ST-COMBAT-API-002", game="stendhal", module="combat", kind="api", title="非法目标不开启攻击：HP/XP/技能经验都不变")
def test_nonexistent_and_self_targets_do_not_start_combat(qa, api_player, observer, prepare):
    before = prepare(xp=0, hp=100, zone="int_semos_guard_house", x=12, y=12)
    for target in ("#2147483647", api_player.config["target"]):
        api_player.action({"type": "attack", "target": target}, "玩家攻击非法目标：" + target)
        time.sleep(1.2)
        after = observer.inspect()
        qa.check("非法目标不会开启攻击：" + target, after["attributes"].get("target"), None, ATTACK)
        qa.check("非法目标不修改HP/XP/技能经验：" + target,
                 [after[key] for key in ("hp", "xp", "atk_xp", "def_xp")],
                 [before[key] for key in ("hp", "xp", "atk_xp", "def_xp")], ATTACK)


@pytest.mark.case(id="ST-MAP-API-001", game="stendhal", module="combat", kind="api", title="寻路移动一格：位置按路径点实际变化（正向对照）")
def test_valid_movement_control_then_outside_map_is_rejected(qa, api_player, observer, prepare):
    before = prepare(zone="int_semos_guard_house", x=12, y=12)
    layout = combat(observer, "layout")
    tile = layout["adjacent_free"]
    api_player.action({"type": "moveto", **tile}, "玩家真实移动到可通行相邻格")
    moved = await_position(observer, tile["x"], tile["y"])
    qa.check("正向对照实际移动一格", position(moved), [layout["zone"], tile["x"], tile["y"]], MOVEMENT)
    qa.check("正向对照位置确实变化", position(moved) != position(before), True, MOVEMENT)
    for x, y in ((-1, tile["y"]), (layout["width"], tile["y"]), (tile["x"], layout["height"])):
        api_player.action({"type": "moveto", "x": x, "y": y}, f"玩家请求地图外坐标({x},{y})")
        time.sleep(1.2)
        after = observer.inspect()
        qa.check(f"越界坐标({x},{y})不移动角色", position(after), position(moved), MOVEMENT)


@pytest.mark.case(id="ST-MAP-API-002", game="stendhal", module="combat", kind="api",
                  title="朝墙连续移动：位置不变、不换区域，可走邻格作对照")
def test_move_into_wall_is_refused_without_crossing_portal(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "房间取 Semos 卫兵室（int_semos_guard_house）内一处可走格；探针不暴露原始碰撞位图，"
        "所以'碰撞层'以**实测分类**记录：每个方向要么正好走到该邻格、要么原地不动。"
        "实测：服务器对朝墙移动**不回任何消息**，因此断言写'位置不变'而不是'收到拒绝消息'。"
    )
    before = prepare(zone="int_semos_guard_house", x=1, y=1)
    layout = combat(observer, "layout")
    zone, start_x, start_y = position(before)
    qa.check("前置：起点在目标区域内", zone, "int_semos_guard_house", COLLISION)

    # 对照组：可通行邻格必须真的移动，否则"没动"分不清是被墙挡住还是根本没连上
    free = layout["adjacent_free"]
    api_player.action({"type": "moveto", **free}, "玩家移动到可通行相邻格（对照组）")
    moved = await_position(observer, free["x"], free["y"])
    qa.check("对照：可通行邻格确实移动", position(moved)[1:], [free["x"], free["y"]], MOVEMENT)

    blocked, walked = [], []
    for label, (dx, dy) in DIRECTIONS:
        czone, cx, cy = position(observer.inspect())
        target = {"x": cx + dx, "y": cy + dy}
        api_player.action({"type": "moveto", **target}, f"朝{label}移动到({target['x']},{target['y']})")
        time.sleep(1.2)
        now = position(observer.inspect())
        if now == [czone, target["x"], target["y"]]:
            walked.append(label)
            qa.check(f"朝{label}可通行：位置正好移动到该邻格", now,
                     [czone, target["x"], target["y"]], MOVEMENT)
        elif now == [czone, cx, cy]:
            blocked.append(label)
            qa.check(f"朝{label}被挡：位置停在原地不进入该格", now, [czone, cx, cy], COLLISION)
            for attempt in (2, 3):                      # 设计要求的"连续移动"
                api_player.action({"type": "moveto", **target}, f"第{attempt}次朝{label}移动")
                time.sleep(1.0)
                qa.check(f"连续朝{label}移动第{attempt}次仍不进入被挡位置", position(observer.inspect()),
                         [czone, cx, cy], COLLISION)
        else:
            qa.check(f"朝{label}移动结果异常：既没到邻格也没停在原地", now, [czone, cx, cy], COLLISION)
        qa.check(f"朝{label}移动后仍在同一区域（未误触门户）", position(observer.inspect())[0], zone, PORTAL)

    qa.data["diagnostics"]["movement_probe"] = {"start": [zone, start_x, start_y], "blocked": blocked,
                                                "walked": walked, "width": layout["width"], "height": layout["height"]}
    qa.check("前置：起点至少邻接一堵被挡的格（否则本用例什么都没验）", bool(blocked), True, COLLISION)


@pytest.mark.case(id="ST-GROWTH-API-002", game="stendhal", module="growth", kind="api",
                  title="阈值下方击杀rat：44→49经验、仍0级、最大生命不变")
def test_kill_below_threshold_keeps_level_and_maximum_hp(qa, api_player, observer, prepare, rat_fixture):
    qa.data["diagnostics"]["coverage_limit"] = (
        "只覆盖「阈值下方」这一档（44+5=49，未到 50）；恰好到 1 级的相邻档由 ST-GROWTH-API-001（任务奖励 50）"
        "与 ST-GROWTH-API-003（50+50 到 2 级）覆盖。按设计也验证「未杀死前不先发经验」："
        "rat 存活期间每次抽样读到的经验都必须是 44。"
    )
    before = prepare(xp=44, hp=100, items={"short sword": 1}, zone="int_semos_guard_house", x=12, y=5)
    qa.check("前置：44经验、0级（阈值50以下）", [before["xp"], before["level"]], [44, 0],
             "测试夹具：xp=44；" + LEVEL_RULES)
    maximum = before["base_hp"]
    if before["slots"]["rhand"]:
        equip(api_player, before, before["slots"]["rhand"][0], "rhand", "bag")
        before = await_slot_empty(observer, "rhand")
    sword = next(item for item in before["slots"]["bag"] if item["name"] == "short sword")
    equip(api_player, before, sword, "bag", "rhand")
    armed = await_quantity(observer, "short sword", 1, slot="rhand")
    fixture = rat_fixture()
    api_player.action({"type": "attack", "target": "#" + fixture["rat"]["id"]}, "玩家真实攻击rat")

    deadline = time.monotonic() + 45
    samples = []
    while True:
        # 先读经验、再读 rat 是否还在：两次读之间 rat 可能刚好死掉。
        # 这个顺序保证"被算作存活的那次采样，其经验读数一定早于死亡"——否则会出现
        # rat_present=True 却已经读到击杀后的经验，把竞态误判成"提前发经验"（实跑第 3 轮踩到过）。
        state = observer.inspect()
        enemy = combat(observer, "inspect", fixture_id=fixture["fixture_id"])
        samples.append({"rat_present": enemy["rat_present"], "xp": state["xp"], "level": state["level"]})
        if not enemy["rat_present"] or time.monotonic() >= deadline:
            break
        time.sleep(0.3)
    after = observer.inspect()
    alive = [sample for sample in samples if sample["rat_present"]]
    qa.data["diagnostics"]["combat_samples"] = samples
    qa.data["diagnostics"]["alive_samples"] = len(alive)

    qa.check("真实攻击使rat死亡离开地图", enemy["rat_present"], False, ATTACK)
    qa.check("rat 存活期间经验一直是44（未杀死不先发）",
             sorted({sample["xp"] for sample in alive}), [44], REWARD)
    qa.check("击杀获得5经验：44→49", after["xp"] - armed["xp"], 5, REWARD)
    qa.check("49经验仍在0级（阈值50以下）", after["level"], 0, LEVEL_RULES)
    qa.check("未升级则最大生命不变", after["base_hp"], maximum, LEVEL_UPDATE)
    qa.check("击杀记录增加1", int(after["keyed"]["!kills"].get("solo.rat", 0))
             - int(armed["keyed"]["!kills"].get("solo.rat", 0)), 1, REWARD)
    qa.check("玩家存活", after["hp"] > 0, True, "夹具准备100HP；测试真实rat战斗，不测试死亡")
