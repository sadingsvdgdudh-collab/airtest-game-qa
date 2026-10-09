"""minigame 业务封装层：赌桌这类"先问注、再确认"的小游戏词汇。

一次发言一个原子的分工见 stendhal.hello / quest.py；yes/no 这种"回答问题"的意图在会话层
（stendhal.confirm），这里只放这个小游戏特有的词汇。
"""

from .stendhal import dialogue

NPC = "Ricardo"


def play(player):
    """向赌桌发起开局：play。返回报价或拒绝理由。"""
    return dialogue(player, "play")
