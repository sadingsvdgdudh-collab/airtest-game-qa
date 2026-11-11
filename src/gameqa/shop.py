"""shop 业务封装层：报价、确认与完整购买。

一次发言一个原子的分工见 stendhal.hello / quest.py；这里只放商店特有的词汇。
原语无状态、不持有 Evidence：对话住在这里，记账（qa.check）留在用例层。
"""

from .stendhal import confirm as answer_confirm
from .stendhal import dialogue, hello

NPC = "Margaret"
SIANDRA = "Siandra"
HAROLD = "Harold"


def offer(player, item, qty=None):
    """询价：buy [N] item。返回报价或拒绝理由。"""
    return dialogue(player, f"buy {qty} {item}" if qty else f"buy {item}")


def sell(player, item, qty=None):
    """报价出售：sell [N] item。返回收购报价、拒绝理由或成交回应。"""
    return dialogue(player, f"sell {qty} {item}" if qty else f"sell {item}")


def post_offer(player, item, price, number=None):
    """寄售上架报价：sell <item> <总价>，带数量时为 sell <N> <item> <总价>。

    服务端把表达式 1 的 amount 当数量、把句子里唯一的数字当总价，
    所以多件寄售必须把数量写在物品名前面。返回费用报价或拒绝理由。

    与 sell() 的区别：sell 是「卖给 NPC」的 N 件报价（sell [N] item），
    寄售要的是「sell 物品 总价」，两个动词同名但语义不同，不能共用一个函数。
    """
    return dialogue(player, f"sell {number} {item} {price}" if number else f"sell {item} {price}")


def remove_offer(player, number):
    """请求撤回自己第 number 笔寄售；需要随后 confirm 确认。"""
    return dialogue(player, f"remove {number}")


def clear_offers(player):
    """清空本玩家在市场的活跃寄售，返回清掉的单数。

    寄售订单不随 prepare 快照恢复（QaProbe 的 RESTORABLE 里没有 offers），
    上一轮留下的单会占掉「最多 3 单」的额度，让后续用例被上限拦住。
    每条寄售用例开始前先清一次，用例之间才互不影响。
    """
    removed = 0
    # 每清掉一单，剩下的单会重新编号，所以始终 remove 1。
    # 服务端要求先"看过"报价才允许撤单（RemoveOfferHandler：Please check your offers first），
    # 所以在每次 remove 前先 show 一次；show 的正文是私有文本，这里不需要读它。
    for _ in range(6):
        show_offers(player, "mine")
        reply = remove_offer(player, 1)
        if not any("Do you want to remove your offer" in message.get("text", "")
                   for message in reply):
            break
        confirm(player, "yes")
        removed += 1
    return removed


def show_offers(player, item=None):
    """浏览寄售：show 或 show <物品名>。"""
    return dialogue(player, f"show {item}" if item else "show")


def confirm(player, answer="yes"):
    """商店语境的"确认/拒绝报价"；实体在会话层 stendhal.confirm（这里只保留域内叫法）。"""
    return answer_confirm(player, answer)


def stock(player):
    """查询在售商品列表（原版 offer），用来证明会话仍然活着。"""
    return dialogue(player, "offer")


def buy_and_confirm(player, item, qty=None):
    """一次完整购买：hello → offer → confirm(yes)，返回三段的全部回应。

    名字里带 confirm 是故意的：取消/拒绝场景不能用它——它会替你把成交确认掉，
    用例就会"只断言报价而其实已经买了"。这类误用靠命名在调用点暴露，不加门禁规则：
    机械近似检查（比如"buy 不得与 confirm/stock 同现"）会误伤"买完再查商品列表"这类
    合法写法，而一条会误伤的规则比没有规则更糟——它训练人去加豁免。
    """
    return hello(player, NPC) + offer(player, item, qty) + confirm(player)
