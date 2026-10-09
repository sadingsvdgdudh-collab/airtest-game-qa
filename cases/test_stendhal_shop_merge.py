"""ST-SHOP-API-006 的可合并子例：满槽且已有 cheese 堆时，购买应合并进原堆而不是被拒绝。"""
import pytest

from gameqa.shop import NPC, buy_and_confirm
from gameqa.sources import PLAYER_BAG_SLOT, SELL_ITEMS_PRICES, STORAGE
from gameqa.stendhal import await_quantity, leave, quantity
from cases.test_stendhal_combat import equip
from cases.test_stendhal_shop_no_space import FILLERS


@pytest.mark.case(id="ST-SHOP-API-006-merge", game="stendhal", module="shop", kind="api",
                  title="满槽合并：12槽已满且其中cheese=3时买1个cheese应合并进原堆")
def test_purchase_with_full_bag_merges_into_existing_stack(qa, api_player, observer, prepare):
    qa.data["diagnostics"]["coverage_limit"] = (
        "关联目录ST-SHOP-API-006的可合并子例：满槽且已有同属性cheese堆时购买应合并。"
        "前一子例（无可用储位拒绝）见 ST-SHOP-API-006-no-space。本例用真实装备占用左手，"
        "独立读取服务端槽位与金币。"
    )
    # money 也占一个背包槽，所以 11 件道具 + money 恰好 12 槽；cheese=3 已在其中。
    before = prepare(money=100, items={"buckler": 1, **dict.fromkeys(FILLERS[:9], 1), "cheese": 3},
                     near_npc=NPC)
    qa.check("准备后背包恰好12槽且原版判断已满",
             [len(before["slots"]["bag"]), before["bag_full"]], [12, True], PLAYER_BAG_SLOT)
    qa.check("满槽中已有可合并的cheese堆", quantity(before, "cheese", "bag"), 3, STORAGE)
    buckler = next(item for item in before["slots"]["bag"] if item["name"] == "buckler")
    equip(api_player, before, buckler, "bag", "lhand")
    held = await_quantity(observer, "buckler", 1, slot="lhand")
    qa.check("真实装备腾出一个bag槽且双手已占用",
             [len(held["slots"]["bag"]), held["bag_full"]], [11, False],
             PLAYER_BAG_SLOT + "; 原版equip跨槽移动")
    try:
        buy_and_confirm(api_player, "cheese", 1)
        after = await_quantity(observer, "cheese", 4)
        qa.check("可合并子例金币减20", after["money"], 80, SELL_ITEMS_PRICES)
        qa.check("可合并子例cheese堆变为4", quantity(after, "cheese", "bag"), 4, STORAGE)
        qa.check("合并不新增背包槽", len(after["slots"]["bag"]), 11,
                 PLAYER_BAG_SLOT + "; 原版StackableItem合并同属性堆")
        qa.check("cheese仍只占一个bag槽",
                 len([item for item in after["slots"]["bag"] if item["name"] == "cheese"]), 1, STORAGE)
    finally:
        leave(api_player)
