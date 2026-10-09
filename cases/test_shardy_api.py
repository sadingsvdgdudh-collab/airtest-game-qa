"""Real two-player Shardy regressions. Known defects deliberately remain failed."""
import os

import pytest

from gameqa.bridge import Bridge, redact
from gameqa.config import resolve_path
from gameqa.sources import (SHARDY_ROUND, SHARDY_RULES_DOC, SHARDY_SCORE, SHARDY_STATE_SYNC,
                            SHARDY_T3_BROADCAST, SHARDY_TURN, SHARDY_TURN_ORDER, SHARDY_WIN)
from gameqa.shardy import Shardy




@pytest.fixture
def players(bridge, qa_config, game_config, qa):
    command = [os.path.expandvars(part) for part in game_config["bridge_command"]]
    opponent = Bridge(command, cwd=resolve_path(qa_config, game_config.get("bridge_cwd", ".")),
                      timeout=game_config.get("timeout", 20))
    clients = []
    try:
        qa.data["metadata"].update(game_version=game_config["version"], transport="real Shardy WebSocket")
        clients.append(Shardy(bridge, game_config, qa, "A"))
        clients.append(Shardy(opponent, game_config, qa, "B"))
        for client in clients:
            client.start()
        for client in clients:
            result = client.receive("round", 6000)
            qa.check(f"{client.label}收到开局广播", any(m["name"] == "round" for m in result["messages"]), True,
                     SHARDY_T3_BROADCAST)
        qa.check("两玩家进入同一个真实对局", bool(clients[0].state["game"]) and
                 clients[0].state["game"] == clients[1].state["game"], True, SHARDY_ROUND)
        qa.check("身份是互补的X和O", sorted(c.state["player"] for c in clients), [0, 1], SHARDY_ROUND)
        yield {client.state["player"]: client for client in clients}
    finally:
        cleanup_errors = []
        try:
            for client in clients:
                try:
                    client.close()
                except Exception as error:
                    cleanup_errors.append(error)
        finally:
            opponent.close()
            qa.data["diagnostics"]["opponent_interface_messages"] = redact(opponent.messages)
            qa.data["diagnostics"]["opponent_bridge_stderr"] = opponent.stderr
        if cleanup_errors:
            raise cleanup_errors[0]


def same_state(qa, players, title):
    states = [players[index].state for index in (0, 1)]
    public = lambda state: {key: state[key] for key in ("game", "turn", "score", "board")}
    qa.check(title, public(states[0]), public(states[1]), SHARDY_STATE_SYNC)
    return states[0]


def move(qa, players, x, y, expected_round=False):
    actor = players[0].state["turn"]
    players[actor].turn(x, y)
    for client in players.values():
        result = client.receive("turn", 2000)
        qa.check(f"{client.label}收到实际落子({x},{y})广播",
                 any(m["name"] == "turn" and m["data"] == {"t": actor, "x": x, "y": y}
                     for m in result["messages"]), True, SHARDY_TURN)
        if expected_round and not any(m["name"] == "round" for m in result["messages"]):
            result = client.receive("round", 2000)
            qa.check(f"{client.label}收到胜后新回合广播", any(m["name"] == "round" for m in result["messages"]), True, SHARDY_WIN)
    # Drain terminal round broadcasts before comparing the two asynchronous clients.
    for client in players.values():
        client.receive(wait_ms=50)
    return same_state(qa, players, "落子后的两端棋盘、轮次和比分一致")


@pytest.mark.case(id="SH-MATCH-API-001", game="shardy", module="core", kind="api", title="两端真实客户端匹配成局：比分0:0、九格全空、先手合法")
def test_two_real_clients_match_with_empty_board(qa, players):
    state = same_state(qa, players, "两端实际开局状态一致")
    qa.check("初始比分为零", state["score"], [0, 0], SHARDY_SCORE)
    qa.check("棋盘九格全空", state["board"], [None] * 9, SHARDY_ROUND)
    qa.check("随机先手是有效玩家", state["turn"] in players, True, SHARDY_TURN_ORDER)


@pytest.mark.case(id="SH-TURN-API-001", game="shardy", module="core", kind="api", title="合法落子轮流切换：双方各一子、其余格保持空")
def test_accepted_turn_broadcasts_and_advances_to_opponent(qa, players):
    starter = players[0].state["turn"]
    after = move(qa, players, 0, 0)
    qa.check("第一步记录实际先手", after["board"][0], starter, SHARDY_TURN)
    qa.check("第一步后轮到对方", after["turn"], 1 - starter, SHARDY_TURN)
    after = move(qa, players, 2, 2)
    expected = [None] * 9
    expected[0], expected[8] = starter, 1 - starter
    qa.check("双方各落一子且其余格子保持空", after["board"], expected, SHARDY_TURN)
    qa.check("第二步后轮次回到先手", after["turn"], starter, SHARDY_TURN)


@pytest.mark.case(id="SH-ILLEGAL-API-001", game="shardy", module="core", kind="api", title="错误轮次与重复格子被拒：棋盘、轮次、比分都不变")
def test_wrong_turn_and_occupied_cell_do_not_change_game(qa, players):
    starter = players[0].state["turn"]
    before = dict(players[0].state)
    players[1 - starter].turn(2, 2)
    for client in players.values():
        result = client.receive(wait_ms=400)
        qa.check(f"{client.label}错误轮次未广播落子", [m for m in result["messages"] if m["name"] == "turn"], [], SHARDY_TURN)
    state = same_state(qa, players, "错误轮次后的两端状态一致")
    qa.check("错误轮次不改变棋盘或轮次", (state["board"], state["turn"]),
             (before["board"], before["turn"]), SHARDY_TURN)
    before = move(qa, players, 0, 0)
    players[1 - starter].turn(0, 0)
    for client in players.values():
        result = client.receive(wait_ms=400)
        qa.check(f"{client.label}重复格子未广播落子", [m for m in result["messages"] if m["name"] == "turn"], [], SHARDY_TURN)
    state = same_state(qa, players, "重复格子后的两端状态一致")
    qa.check("重复格子不改变棋盘、轮次或比分", (state["board"], state["turn"], state["score"]),
             (before["board"], before["turn"], before["score"]), SHARDY_TURN)


@pytest.mark.case(id="SH-WIN-API-001", game="shardy", module="core", kind="api", title="横排三子获胜：加一分、棋盘重置、同局ID新回合且胜者先手")
def test_horizontal_win_scores_resets_and_next_round_accepts_turn(qa, players):
    starter, game = players[0].state["turn"], players[0].state["game"]
    for index, (x, y) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]):
        state = move(qa, players, x, y, expected_round=index == 4)
    expected_score = [0, 0]
    expected_score[starter] = 1
    qa.check("横排三子获胜加一分", state["score"], expected_score, SHARDY_WIN + "; " + SHARDY_RULES_DOC)
    qa.check("结算后棋盘重置九格", state["board"], [None] * 9, SHARDY_WIN)
    qa.check("下一回合保留同一局ID", state["game"], game, SHARDY_ROUND)
    qa.check("胜者获得下一回合先手", state["turn"], starter, SHARDY_WIN)
    state = move(qa, players, 1, 1)
    qa.check("新回合能实际落子", state["board"][4], starter, SHARDY_TURN)
    qa.check("新回合保留累计比分", state["score"], expected_score, SHARDY_ROUND)


@pytest.mark.case(id="SH-DEFECT-API-001", game="shardy", module="known_defects", kind="api", title="【已知缺陷】反对角线三子未判胜：比分不加分")
def test_anti_diagonal_win_must_score_and_reset(qa, players):
    starter = players[0].state["turn"]
    for x, y in [(0, 2), (0, 0), (1, 1), (1, 0), (2, 0)]:
        move(qa, players, x, y)
    for client in players.values():
        client.receive("round", 600)
    state = same_state(qa, players, "反对角线完成后的实际两端状态一致")
    expected = [0, 0]
    expected[starter] = 1
    qa.check("反对角线三子胜者应加一分", state["score"], expected, SHARDY_RULES_DOC)
    qa.check("反对角线获胜后应重置棋盘", state["board"], [None] * 9, SHARDY_RULES_DOC)


@pytest.mark.case(id="SH-DEFECT-API-002", game="shardy", module="known_defects", kind="api", title="【已知缺陷】第八步无三连却提前结算：棋盘被清空")
def test_eight_non_winning_moves_must_keep_board_until_ninth(qa, players):
    starter = players[0].state["turn"]
    moves = [(0, 0), (1, 0), (2, 0), (1, 1), (0, 1), (2, 1), (1, 2), (0, 2)]
    expected = [None] * 9
    for index, (x, y) in enumerate(moves):
        expected[y * 3 + x] = starter if index % 2 == 0 else 1 - starter
        move(qa, players, x, y)
    for client in players.values():
        client.receive("round", 600)
    state = same_state(qa, players, "第八步后的实际两端状态一致")
    qa.check("没有三子连线时第八步保留八枚棋子", state["board"], expected, SHARDY_RULES_DOC)
    qa.check("第八步不改变比分", state["score"], [0, 0], SHARDY_RULES_DOC)
    qa.check("第九步应轮到初始先手", state["turn"], starter, SHARDY_RULES_DOC)
