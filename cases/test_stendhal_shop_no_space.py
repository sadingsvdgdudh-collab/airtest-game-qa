"""A full bag and occupied hands reject a purchase without charging or dropping it."""
import pytest

from gameqa.recovery import reset_character
from gameqa.shop import NPC, confirm, offer
from gameqa.sources import (BARMAID_NPC, BUCKLER_ITEM, FOOD_ITEMS, PLAYER_BAG_SLOT,
                            PLAYER_TRADE_SLOT, SELLER_BEHAVIOUR, SELLER_TRANSACT,
                            SELL_ITEMS_APPLE, STORAGE)
from gameqa.stendhal import await_quantity, hello, leave, quantity, said
from cases.test_stendhal_combat import equip


FILLERS = ("axe", "bardiche", "battle axe", "hand axe", "small axe", "dagger",
             "short sword", "broadsword", "scythe", "halberd")


@pytest.mark.case(id="ST-SHOP-API-006-no-space", game="stendhal", module="shop", kind="api", title="满储位（12槽+双手占用）：cheese报价20但拒绝、不扣款不落地")
def test_purchase_without_any_reachable_storage_does_not_charge(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "关联目录ST-SHOP-API-006的无可用储位子例；满槽合并正例仍未验收。"
        "真实装备buckler与购买apple形成满背包，随后仅确认一次cheese购买。"
        "独立读取原服目标区地面；本例不生成地面物品，不覆盖拾取容量边界。")
    # 前置不能靠环境：先按出厂状态回收装备与背包（否则守卫会因为残留的 buckler/短剑直接失败）
    qa.data["diagnostics"]["gear_reset"] = reset_character(api_player, observer)
    original = observer.inspect()
    required = {"features", "trade_state", "bag_full", "ground_items"}
    if not required.issubset(original):
        qa.data["failure_kind"] = "preparation_error"
        raise ValueError("No-space case needs independent features, trade, bag fullness and target-zone ground observations")
    nested = any(item["slots"] for contents in original["slots"].values() for item in contents)
    if (original["slots"]["bag"] or original["slots"]["lhand"]
            or [item["name"] for item in original["slots"]["rhand"]] != ["club"]
            or "bag" in original["features"] or original["trade_state"] != "NO_ACTIVE_TRADE"
            or nested or original["statuses"] or original["attributes"].get("target")
            or "last_player_kill_time" in original["attributes"]):
        qa.data["failure_kind"] = "preparation_error"
        raise ValueError("No-space fixture requires empty default bag/left hand, club in right hand, no nested containers, trade, statuses, combat or PK pricing")
    before = prepare(money=100, features={"bag": False}, items={"buckler": 1, **dict.fromkeys(FILLERS, 1)},
                     zone="int_semos_tavern_0", x=15, y=7)
    qa.check("管理员独立读取正确API角色", before["name"], api_player.config["target"], "隔离API账户配置")
    qa.check("默认背包容量前置：无bag扩容feature", "bag" in before["features"], False, PLAYER_BAG_SLOT)
    qa.check("贸易槽不可达前置：没有活动交易", before["trade_state"], "NO_ACTIVE_TRADE", PLAYER_TRADE_SLOT)
    qa.check("准备后背包恰好12件且原版判断已满", [len(before["slots"]["bag"]), before["bag_full"]],
             [12, True], PLAYER_BAG_SLOT)
    qa.check("准备起点覆盖Margaret全部巡逻的对话范围",
             [before["attributes"]["zoneid"], int(before["attributes"]["x"]), int(before["attributes"]["y"])],
             ["int_semos_tavern_0", 15, 7], BARMAID_NPC + "; SpeakerNPC默认对话范围5")
    buckler = next(item for item in before["slots"]["bag"] if item["name"] == "buckler")
    equip(api_player, before, buckler, "bag", "lhand")
    held = await_quantity(observer, "buckler", 1, slot="lhand")
    qa.check("0级合法buckler真实占据左手", quantity(held, "buckler", "lhand"), 1, BUCKLER_ITEM)
    qa.check("真实装备腾出一个bag槽", [len(held["slots"]["bag"]), held["bag_full"]],
             [11, False], PLAYER_BAG_SLOT + "; 原版equip跨槽移动")
    try:
        control = hello(api_player, NPC) + offer(api_player, "apple") + confirm(api_player)
        qa.check("构造正向对照：NPC实际确认apple成交", said(control, NPC, "Congratulations!"),
                 True, SELLER_BEHAVIOUR)
        full = await_quantity(observer, "apple", 1)
        qa.check("填满的apple购买只扣10金币", full["money"], 90, SELL_ITEMS_APPLE)
        qa.check("填满后bag确有12槽且原版判断已满", [len(full["slots"]["bag"]), full["bag_full"]],
                 [12, True], PLAYER_BAG_SLOT)
        qa.check("cheese可用的双手也已占用", [[item["name"] for item in full["slots"][slot]]
                                            for slot in ("lhand", "rhand")],
                 [["buckler"], ["club"]], FOOD_ITEMS + "; " + STORAGE)
        qa.check("没有嵌套content等候选容器", any(item["slots"] for contents in full["slots"].values()
                                              for item in contents), False, STORAGE)
        qa.check("满储位时贸易仍未激活", full["trade_state"], "NO_ACTIVE_TRADE", PLAYER_TRADE_SLOT)
        qa.check("购买前所有角色槽均没有cheese合并堆", quantity(full, "cheese", slot=None), 0,
                 FOOD_ITEMS + "; " + STORAGE)

        quotation = offer(api_player, "cheese")
        qa.check("无储位购买仍得到原价20的实际报价", said(quotation, NPC, "will cost 20."),
                 True, SELL_ITEMS_APPLE)
        quoted = observer.inspect()
        for field in ("money", "slots", "commerce", "item_counter_cache"):
            qa.check("报价不提前改动：" + field, quoted[field], full[field], SELLER_TRANSACT)
        ground_before = [item for item in quoted["ground_items"] if item["name"] == "cheese"]
        qa.data["diagnostics"]["no_space_checkpoint"] = {
            "money": quoted["money"], "slots": quoted["slots"], "commerce": quoted["commerce"],
            "item_counter_cache": quoted["item_counter_cache"], "ground_cheese": ground_before}

        refusal = confirm(api_player)
        qa.check("NPC实际拒绝没有可用储位的cheese购买",
                 said(refusal, NPC, "cannot equip the piece of cheese."), True, SELLER_TRANSACT)
        qa.check("拒绝阶段没有成功成交回复", said(refusal, NPC, "Congratulations!"),
                 False, SELLER_TRANSACT)
        after = observer.inspect()
        qa.check("没有储位时不扣款，金币仍90", after["money"], 90, SELLER_TRANSACT)
        qa.check("拒绝后所有角色槽均未获得cheese", quantity(after, "cheese", slot=None), 0,
                 SELLER_TRANSACT + "; " + STORAGE)
        for field in ("slots", "commerce", "item_counter_cache"):
            qa.check("拒绝不改完整数据：" + field, after[field], quoted[field], SELLER_TRANSACT)
        qa.check("拒绝不走地面发货回退", [item for item in after["ground_items"] if item["name"] == "cheese"],
                 ground_before, SELLER_TRANSACT + "; " + STORAGE)
        qa.check("拒绝后默认bag仍满12槽", [len(after["slots"]["bag"]), after["bag_full"]],
                 [12, True], PLAYER_BAG_SLOT)
    finally:
        leave(api_player)
