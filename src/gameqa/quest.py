"""quest 业务封装层：Hayunn Naratha 送酒任务的对话原子。

一次发言一个原子：接受/拒绝接取、交付/拒绝交付分别是不同意图，同一个 "yes" 在不同
上下文里含义不同，所以按意图命名而不是按词命名。
"""

from .stendhal import dialogue

NPC = "Hayunn Naratha"


def accept_quest(player):
    """询问任务并接受：task → yes。返回两段回应。"""
    return dialogue(player, "task", "yes")


def decline_quest(player):
    """询问任务并拒绝：task → no。"""
    return dialogue(player, "task", "no")


def hand_over(player):
    """交付确认：yes。"""
    return dialogue(player, "yes")


def refuse_hand_over(player):
    """拒绝交付：no。"""
    return dialogue(player, "no")
