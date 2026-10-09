"""pet 业务封装层：买羊/放走羊这类家畜词汇。

一次发言一个原子的分工见 stendhal.hello / quest.py；yes/no 的"回答问题"在会话层
stendhal.confirm，这里只放宠物特有的词汇。
"""

from .stendhal import dialogue

NPC = "Nishiya"
SPECIES = "sheep"


def buy(player, item=SPECIES):
    """向卖羊人询价/请求购买：buy <item>。返回报价或拒绝理由。"""
    return dialogue(player, f"buy {item}")


def forsake(player, state, species=SPECIES):
    """放走自己的家畜（原版 forsake 动作，等于客户端右键 LEAVE）。

    买羊会在世界里生成一只生物，而快照恢复**不含宠物**——所以用例必须在 finally 里放走它，
    否则角色会一直"already has a sheep"，下一次购买直接被拒。
    """
    return player.action({"type": "forsake", "zone": state["attributes"]["zoneid"], "species": species},
                         f"玩家通过原版forsake动作放走 {species}")
