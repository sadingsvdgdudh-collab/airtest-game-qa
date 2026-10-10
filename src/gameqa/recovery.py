"""失败后的自动回收：把角色拉回可用状态。

一次中断/失败会让"用例改了但没能还原"的东西留在角色身上：装备被换掉、背包塞满夹具道具。
这些在**手动工具**和**框架自动收尾**里是同一套动作，所以实现在这里，两边都调它。
"""
import time

from .stendhal import equip

FACTORY_WEAPON = "club"


def normalize_weapon(player, observer, weapon=FACTORY_WEAPON):
    """把右手换成出厂武器（默认 club），其余装备退回背包。用真实 equip 动作。"""
    steps = []
    state = observer.inspect()
    # 出厂状态只有右手一把武器：先把其它槽位（左手/双手/身上的）统统退回背包。
    # 实测踩到过：一次失败把 buckler 留在左手，之后所有"默认空手"的用例都失败。
    # 注意：探针的 slots 里除了真正的装备槽，还有 keyed 记录槽（!quests / !kills / skills ...）。
    # 那些不是穿在身上的东西，对它们发 equip 是错的（实测会打出 "!quests None -> 背包" 这种动作）。
    keyed = set(state.get("keyed") or {})
    for slot, items in list(state["slots"].items()):
        if slot in ("bag", "rhand") or slot in keyed or slot.startswith("!"):
            continue
        for item in items:
            equip(player, state, item, slot, "bag")
            steps.append(f"{slot} {item['name']} -> 背包")
            time.sleep(0.4)
            state = observer.inspect()
    rhand = state["slots"]["rhand"]
    if rhand and rhand[0]["name"] != weapon:
        equip(player, state, rhand[0], "rhand", "bag")
        steps.append(f"右手 {rhand[0]['name']} -> 背包")
        time.sleep(0.6)
        state = observer.inspect()
    if not state["slots"]["rhand"]:
        candidate = next((item for item in state["slots"]["bag"] if item["name"] == weapon), None)
        if candidate is None:
            # 背包里没有出厂武器（可能被前一次失败弄丢了）：先用探针造一把放进背包。
            # 实测踩到过：回收时只看到“背包里没有 club”，于是什么都没做，装备漂移一直留着。
            state = observer.prepare(items={weapon: 1})["after"]
            observer.forget()
            candidate = next((item for item in state["slots"]["bag"] if item["name"] == weapon), None)
            steps.append(f"背包里没有 {weapon}，已补一把")
        if candidate:
            equip(player, state, candidate, "bag", "rhand")
            steps.append(f"背包 {weapon} -> 右手")
            time.sleep(0.6)
    return {"steps": steps, "rhand": [item["name"] for item in observer.inspect()["slots"]["rhand"]]}


def clear_bag(observer):
    """清空背包与金钱。

    这一步不能靠 restore（restore 会把道具还回来），所以准备完直接丢掉快照：
    效果留在服务端，快照用 forget 撤掉，不需要重启主服。
    """
    state = observer.inspect()
    names = sorted({item["name"] for item in state["inventory"] if item["slot"] == "bag"})
    # quests 一并清掉：失败用例没走还原时，任务状态会一直留着（实测残留过 beer_hayunn），
    # 之后所有"假设没有进行中任务"的用例都会受影响。prepare 里 quests 传 null 表示移除。
    quests = {name: None for name in (state.get("quests") or {})}
    fields = {"items": {name: 0 for name in names}, "money": 0}
    if quests:
        fields["quests"] = quests
    after = observer.prepare(**fields)["after"]
    observer.forget()
    return {"cleared": names, "cleared_quests": sorted(quests),
            "bag": [item["name"] for item in after["inventory"] if item["slot"] == "bag"]}


def clear_feature(observer, name):
    """关掉一个持久特性（例如背包扩容的 bag）。

    特性是玩家对象上的持久状态：让角色"能装无限"的 bag 特性一旦被某个用例打开，
    不显式关掉就会一直留着，之后所有"默认背包容量"的用例都会失败（实测踩到）。
    """
    observer.prepare(features={name: False})
    observer.forget()
    return {"cleared_feature": name}


def clear_pet(player, observer, species="sheep"):
    """放走角色身上的家畜。

    宠物**不在快照里**（QaProbe 的 RESTORABLE 不含它），所以用例中途失败时羊会一直留着，
    之后所有"没有羊"前置的用例都会失败（实测踩到）。这里用原版 forsake 动作放走。
    """
    state = observer.inspect()
    pet = state.get("pet") or {}
    if not (pet.get("has_sheep") or pet.get("has_pet")):
        return {"pet": "none"}
    animal = pet.get("animal") or {}
    kind = (animal.get("type") or species).lower()
    player.action({"type": "forsake", "zone": state["attributes"]["zoneid"], "species": kind},
                  f"回收：玩家放走 {kind}")
    after = observer.await_state(
        lambda state: not any((state.get("pet") or {}).get(flag) for flag in ("has_sheep", "has_pet")),
        f"等待 {kind} 放走后角色不再持有家畜")
    if any((after.get("pet") or {}).get(flag) for flag in ("has_sheep", "has_pet")):
        raise RuntimeError(f"角色仍持有家畜，放走 {kind} 未确认")
    return {"pet": f"forsook {kind}", "still": False}


def reset_character(player, observer, weapon=FACTORY_WEAPON):
    """失败后的自动收尾：清背包 + 装备复位。全程 best effort，返回做了什么。"""
    summary = {}
    # 顺序要紧：先复位武器（旧武器会被放进背包），再清背包——否则旧武器会留在包里。
    try:
        summary["weapon"] = normalize_weapon(player, observer, weapon)
    except Exception as error:
        summary["weapon_error"] = f"{type(error).__name__}: {error}"
    try:
        summary["pet"] = clear_pet(player, observer)
    except Exception as error:
        summary["pet_error"] = f"{type(error).__name__}: {error}"
    try:
        summary["feature"] = clear_feature(observer, "bag")
    except Exception as error:
        summary["feature_error"] = f"{type(error).__name__}: {error}"
    try:
        summary["bag"] = clear_bag(observer)
    except Exception as error:
        summary["bag_error"] = f"{type(error).__name__}: {error}"
    return summary
