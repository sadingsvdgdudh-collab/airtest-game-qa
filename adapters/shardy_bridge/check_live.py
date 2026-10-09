"""Run real two-client protocol checks; preserve original rule defects."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path

from gameqa.bridge import Bridge


def close_player(client):
    if client.closed:
        return
    state = client.call("get_messages", read_only=True)["state"]
    if state["connected"]:
        client.call("exit" if state["game"] and state["matched"] else "stop")
        client.call("disconnect")


def scenario(command, moves, expected):
    with ExitStack() as stack:
        clients = [stack.enter_context(Bridge(command)) for _ in range(2)]
        for client in clients:
            stack.callback(close_player, client)
        for client in clients:
            client.call("connect")
            client.call("start")
        states = [client.call("get_messages", {"name": "round", "wait_ms": 6000}, read_only=True)["state"] for client in clients]
        assert states[0]["game"] and states[0]["game"] == states[1]["game"], states
        players = {state["player"]: client for state, client in zip(states, clients)}
        assert set(players) == {0, 1}, states
        starter = states[0]["turn"]
        before = dict(states[0])
        turn = starter
        for x, y in moves:
            players[turn].call("turn", {"x": x, "y": y})
            turn = 1 - turn
        after = [client.call("get_messages", read_only=True) for client in clients]
        assert after[0]["state"]["board"] == after[1]["state"]["board"], after
        assert after[0]["state"]["score"] == after[1]["state"]["score"], after
        actual = after[0]["state"]
        if expected == "win":
            conformant = actual["score"][starter] == 1 and all(value is None for value in actual["board"])
        else:
            conformant = sum(value is not None for value in actual["board"]) == 8
        return {"expected": expected, "conformant": conformant, "starting_player": starter,
                "moves": moves, "before": before, "after": [item["state"] for item in after],
                "trace": [client.messages for client in clients]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--vendor")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    command = [args.node, str(Path(__file__).with_name("bridge.mjs"))]
    if args.vendor:
        command.append(args.vendor)
    horizontal = scenario(command, [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)], "win")
    anti_diagonal = scenario(command, [(0, 2), (0, 0), (1, 1), (1, 0), (2, 0)], "win")
    premature_draw = scenario(command, [(0, 0), (1, 0), (2, 0), (1, 1), (0, 1), (2, 1), (1, 2), (0, 2)], "eight occupied cells before the ninth move")
    report = {"source_commit": "ed8e978917cbe5aba79009928e8c3b92a34b81cc",
              "dependency_shardy": "1.2.0", "horizontal_win": horizontal,
              "anti_diagonal_win": anti_diagonal, "premature_draw": premature_draw}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"horizontal_win": horizontal["conformant"],
                      "anti_diagonal_win": anti_diagonal["conformant"],
                      "eight_cell_state": premature_draw["conformant"],
                      "evidence": str(args.output)}, ensure_ascii=False))
    assert horizontal["conformant"], "Normal horizontal win failed"
    assert not anti_diagonal["conformant"], "Original anti-diagonal defect did not reproduce"
    assert not premature_draw["conformant"], "Original premature-draw defect did not reproduce"


if __name__ == "__main__":
    main()
