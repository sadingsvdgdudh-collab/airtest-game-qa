"""Reuse the same Android/Airtest infrastructure against a second real server."""
import time

import pytest

from gameqa.bridge import BridgeError
from gameqa.sources import SHARDY_ROUND, SHARDY_TURN
from gameqa.shardy import Shardy
from gameqa.shardy_ui import ShardyUI




@pytest.fixture
def ui_pair(android, bridge, game_config, qa):
    ui = ShardyUI(android, game_config)
    peer = None
    try:
        qa.data["metadata"].update(game_version=game_config["version"],
                                   ui_client="project's browser client of original Shardy server")
        ui.start()
        peer = Shardy(bridge, game_config, qa, "API对手")
        peer.start()
        result = peer.receive("round", 6000)
        if not any(m["name"] == "round" for m in result["messages"]):
            # 6 秒没开局有两种可能：界面玩家没连上（环境），或服务端真坏了（业务）。
            # 根因无法从协议侧区分，但"连上就会开局"由 SH-MATCH-API-001 单独守着，
            # 所以这里按环境问题处理：计入【环境未执行】并重试一次，不污染业务失败。
            raise BridgeError("UI 客户端未连上：6 秒内没有收到 round 广播；"
                              "检查界面是否停在「尚未连接」（scripts/shardy/start.sh、adb reverse 3000/3001）")
        qa.check("原服开局棋盘九格为空", peer.state["board"], [None] * 9, SHARDY_ROUND)
        time.sleep(0.6)
        android.screenshot("Android客户端与真实接口玩家进入同一局")
        yield ui, peer
    finally:
        if peer:
            peer.close()


@pytest.mark.case(id="SH-TURN-UI-001", game="shardy", module="core", kind="ui", title="界面与接口双方交替落子：棋盘与轮次两端一致")
def test_ui_and_api_turns_broadcast_and_render_in_both_directions(qa, ui_pair):
    ui, peer = ui_pair
    starter = peer.state["turn"]
    expected = [None] * 9
    actors = []
    for x, y in [(0, 0), (1, 0)]:
        actor = peer.state["turn"]
        actors.append(actor)
        if actor == peer.state["player"]:
            peer.turn(x, y)
        else:
            ui.turn(x, y)
        result = peer.receive("turn", 2000)
        qa.check(f"实际落子({x},{y})由原服广播确认",
                 any(m["name"] == "turn" and m["data"] == {"t": actor, "x": x, "y": y}
                     for m in result["messages"]), True, SHARDY_TURN)
        expected[y * 3 + x] = actor
        qa.check("接口观察的棋盘等于规则预期", peer.state["board"], expected.copy(), SHARDY_TURN)
        qa.check("轮次切换到另一玩家", peer.state["turn"], 1 - actor, SHARDY_TURN)
        time.sleep(0.5)
        ui.check_piece(x, y, actor)
    qa.check("两次动作分别覆盖界面玩家和接口玩家", sorted(actors), [0, 1], SHARDY_TURN)
    qa.check("两步后轮次回到先手", peer.state["turn"], starter, SHARDY_TURN)
