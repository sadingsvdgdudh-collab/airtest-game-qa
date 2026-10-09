"""Shardy actions and broadcast observations over the shared JSONL bridge."""


class Shardy:
    def __init__(self, bridge, config, evidence, label="player"):
        self.bridge, self.config, self.evidence, self.label = bridge, config, evidence, label
        self.cursor = 0
        self.state = bridge.call("connect", {"host": config["host"], "port": config["port"]})["state"]

    def start(self):
        return self.evidence.action(f"{self.label}开始真实匹配", lambda: self.bridge.call("start"))

    def receive(self, name=None, wait_ms=0):
        args = {"after": self.cursor, "wait_ms": wait_ms}
        if name:
            args["name"] = name
        result = self.evidence.observe(
            f"{self.label}读取{name or '全部'}广播",
            lambda: self.bridge.call("get_messages", args, read_only=True))
        self.cursor, self.state = result["cursor"], result["state"]
        self.evidence.data["diagnostics"].setdefault("shardy_observations", []).append(
            {"player": self.label, **result})
        return result

    def turn(self, x, y):
        return self.evidence.action(
            f"{self.label}真实落子({x},{y})", lambda: self.bridge.call("turn", {"x": x, "y": y}))

    def close(self):
        # Exit removes the upstream game; disconnect alone only stops matchmaking.
        current = self.receive()["state"]
        if current["connected"]:
            if current["game"] and current["matched"]:
                result = self.bridge.call("exit")
            else:
                result = self.bridge.call("stop")
            self.state = self.bridge.call("disconnect")["state"]
            self.evidence.data["diagnostics"].setdefault("shardy_cleanup", []).append(
                {"player": self.label, "exit_or_stop": result, "disconnected": self.state})
