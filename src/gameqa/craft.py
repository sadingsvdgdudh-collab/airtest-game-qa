"""craft 业务封装层：采集生产（磨面这类"交材料、等产出"）的词汇。

一次发言一个原子的分工见 stendhal.hello / quest.py；yes/no 的"回答问题"在会话层
stendhal.confirm，这里只放生产特有的词汇。
"""

from .stendhal import dialogue

NPC = "Jenny"
ORDER = "jenny_mill_flour"     # 生产订单记在这个任务槽里（ProducerBehaviour 的 questSlot）


def mill(player, item="flour", qty=None):
    """请求生产：mill [N] item。返回受理回应或材料不足的拒绝理由。"""
    return dialogue(player, f"mill {qty} {item}" if qty else f"mill {item}")
