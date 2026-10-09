"""shop 业务封装层：报价、确认与完整购买。

一次发言一个原子的分工见 stendhal.hello / quest.py；这里只放商店特有的词汇。
原语无状态、不持有 Evidence：对话住在这里，记账（qa.check）留在用例层。
"""

from .stendhal import confirm as answer_confirm
from .stendhal import dialogue, hello

NPC = "Margaret"
SIANDRA = "Siandra"


def offer(player, item, qty=None):
    """询价：buy [N] item。返回报价或拒绝理由。"""
    return dialogue(player, f"buy {qty} {item}" if qty else f"buy {item}")


def sell(player, item, qty=None):
    """报价出售：sell [N] item。返回收购报价、拒绝理由或成交回应。"""
    return dialogue(player, f"sell {qty} {item}" if qty else f"sell {item}")


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
