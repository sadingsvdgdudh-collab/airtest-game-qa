"""测试账号池：目标角色与观察者的命名与轮换。

为什么需要：服务端对**同一账号**的重复登录会静默踢掉前一个会话；上一条用例的角色会话若断开得
比本次登录更晚，服务端会把新会话当成旧的移除（实测复现），表现为用例突然报
`Target character is not online`，而服务端日志里什么都没有。让相邻用例用不同账号就能绕开这个时间窗。

命名沿用 Stendhal 的保留规则：目标是 `qaplayera`、`qaplayerb`、……；观察者是 `qaobserver`、
`qaobserverb`、……（第 0 个不带后缀，保持与既有配置兼容）。
"""


def pool_size(game):
    try:
        return max(1, int(game.get("pool_size", 1)))
    except (TypeError, ValueError):
        return 1


def target_pool(game):
    """API 目标角色池（第一个是配置里的 api_target，没有就按命名规则生成）。"""
    size = pool_size(game)
    first = game.get("api_target") or game.get("target") or "qaplayera"
    names = [first]
    names += [f"qaplayer{chr(ord('a') + index)}" for index in range(1, size)]
    return names


def observer_pool(game):
    """观察者池（第一个是配置里的 observer）。"""
    size = pool_size(game)
    first = game.get("observer") or "qaobserver"
    return [first] + [f"qaobserver{chr(ord('a') + index)}" for index in range(1, size)]


def pair_for(index, game):
    """按用例序号取一对（观察者, 目标）：相邻用例用不同账号。"""
    targets, observers = target_pool(game), observer_pool(game)
    return observers[index % len(observers)], targets[index % len(targets)]
