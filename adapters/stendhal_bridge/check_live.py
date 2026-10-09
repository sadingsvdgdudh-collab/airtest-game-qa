"""One real local-server check: observer, shop purchase, and fixture rollback.

Requires the official Stendhal 1.49 server and qaobserver/qaplayera accounts.
Reads local credentials from a private file; does not contact the public game.
"""
import argparse
import json
import pathlib
import select
import subprocess
import time


class Client:
    def __init__(self, command, name, work):
        self.log = (work / f"{name}.stderr.log").open("w")
        self.process = subprocess.Popen([str(command)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, bufsize=1)
        self.sequence = 0
        self.evidence = []

    def call(self, operation, **args):
        self.sequence += 1
        self.process.stdin.write(json.dumps({"id": self.sequence, "op": operation, "args": args}) + "\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 25)[0]:
            raise TimeoutError(operation)
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"Bridge exited during {operation}")
        response = json.loads(line)
        assert response["id"] == self.sequence, response
        self.evidence.append({"op": operation, "response": response})
        if not response["ok"]:
            raise RuntimeError(response["error"])
        return response["result"]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", required=True, type=pathlib.Path)
    parser.add_argument("--evidence", required=True, type=pathlib.Path)
    parser.add_argument("--occupy-original-tile", action="store_true", help="Verify reported one-tile restoration when the observer occupies the original tile")
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(args.credentials.read_text())
    command = pathlib.Path(__file__).with_name("run.sh")
    player = Client(command, "player", args.evidence)
    observer = Client(command, "observer", args.evidence)
    snapshot = None
    observer_location = None
    target = credentials["qaplayera"]["character"]
    try:
        for client, account in [(player, credentials["qaplayera"]), (observer, credentials["qaobserver"])]:
            client.call("connect")
            client.call("login", **account)
        observed = observer.call("inspect", target=target)
        assert observed["name"] == player.call("get_self_state")["name"] == target
        prepared = observer.call("prepare", target=target, money=100, items={"cheese": 0}, near_npc="Margaret")
        snapshot = prepared["snapshot_id"]
        assert prepared["after"]["money"] == 100
        for text in ["hi", "buy cheese", "yes"]:
            player.call("send_action", action={"type": "chat", "text": text})
            time.sleep(1.1)
        state = observer.call("inspect", target=target)
        assert state["money"] == 80, state
        assert sum(item["quantity"] for item in state["inventory"] if item["name"] == "cheese" and item["slot"] == "bag") == 1, state
        messages = player.call("get_chat_messages")
        assert any(message["name"] == "Margaret" for message in messages), messages
        # An observer inspection must leave the target's separate game session alive.
        assert player.call("get_self_state")["name"] == target
        if args.occupy_original_tile:
            observer_location = observer.call("get_self_state")["attributes"]
            original = prepared["before"]["attributes"]
            observer.call("send_action", action={"type": "teleport", "target": "qaobserver", "zone": original["zoneid"], "x": original["x"], "y": original["y"]})
            time.sleep(.6)
        restored = observer.call("restore", target=target, snapshot_id=snapshot)
        snapshot = None
        assert restored["restored"] is True
        if args.occupy_original_tile:
            assert restored["location_adjusted"] is True, restored["location"]
            requested, actual = restored["location"]["requested"], restored["location"]["actual"]
            assert requested["zone"] == actual["zone"] and abs(requested["x"] - actual["x"]) + abs(requested["y"] - actual["y"]) == 1
        print("PASS: real server purchase, separate observer, and checked fixture restoration")
    finally:
        try:
            if snapshot is not None:
                observer.call("restore", target=target, snapshot_id=snapshot)
        finally:
            if observer_location is not None:
                observer.call("send_action", action={"type": "teleport", "target": "qaobserver", "zone": observer_location["zoneid"], "x": observer_location["x"], "y": observer_location["y"]})
                time.sleep(.4)
            (args.evidence / "player.json").write_text(json.dumps(player.evidence, ensure_ascii=False, indent=2))
            (args.evidence / "observer.json").write_text(json.dumps(observer.evidence, ensure_ascii=False, indent=2))
            player.close()
            observer.close()


if __name__ == "__main__":
    main()
