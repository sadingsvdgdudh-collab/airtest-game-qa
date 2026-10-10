"""Stendhal-specific state and actions; shared transport is gameqa.bridge."""
import os
import time

from .bridge import IndeterminateAction, TransientError


class Stendhal:
    def __init__(self, bridge, config, evidence, *, observer=True):
        self.bridge, self.config, self.evidence = bridge, config, evidence
        self.observer = observer
        self.username = config["observer"] if observer else config["target"]
        self.password_env = config["observer_password_env"] if observer else config["player_password_env"]
        self._login()


    def _reconnect(self, reason):
        """瞬时断连之后：重开连接并重登，把原因记进证据（便于统计中断频率）。"""
        self.evidence.data["diagnostics"].setdefault("reconnects", []).append(reason)
        try:
            if not self.bridge.closed:
                self.bridge.close()
        except Exception:
            # 被杀的桥进程管道可能已经断了：close() 自己会抛，但状态照样要标记为已关，才能 reopen
            self.bridge.closed = True
        self.bridge.reopen()
        self._login()

    def _guarded(self, op, fields=None, *, read_only=False, with_target=True):
        """只读/恢复操作断连后重试一次；prepare 结果不明时保留原快照并报错。"""
        payload = {"target": self.config["target"], **(fields or {})} if with_target else dict(fields or {})
        for attempt in (1, 2):
            try:
                return self.bridge.call(op, payload, read_only=read_only)
            except (TransientError, IndeterminateAction) as error:
                # prepare 可能已改写角色；重放或丢弃快照都会失去原始状态。
                if op == "prepare" or attempt == 2:
                    self.evidence.data["diagnostics"].setdefault("transient_failures", []).append(f"{op}: {error}")
                    raise
                self.evidence.data["diagnostics"].setdefault("transient_retries", []).append(f"{op}: {error}")
                try:
                    self._reconnect(f"{op}: {error}")
                except Exception as reconnect_error:
                    # 连不回来（例如服务端也不在了）：把原始错误抛出去，它比"重连失败"更有信息量
                    self.evidence.data["diagnostics"].setdefault("transient_failures", []).append(
                        f"{op}: {error}; reconnect failed: {reconnect_error}")
                    raise error
        raise AssertionError("unreachable")

    def _login(self):
        env_key = self.password_env
        password = os.environ.get(env_key)
        if not password:
            raise ValueError(f"missing credential environment variable: {env_key}")
        self.bridge.call("connect", {"host": self.config["host"], "port": self.config["port"]}, read_only=True)
        self.bridge.call("login", {"username": self.username, "password": password, "character": self.username}, read_only=True)

    def inspect(self):
        if not self.observer:
            raise ValueError("target inspections require an independent observer")
        def read():
            if self.bridge.closed:
                self.bridge.reopen()
                self._login()
            return self.bridge.call("inspect", {"target": self.config["target"]}, read_only=True)
        result = self.evidence.observe("独立管理员读取目标角色", read, retries=1)
        if result.get("name") != self.config["target"]:
            raise ValueError(f"observer returned wrong player: {result.get('name')}")
        return result

    def await_presence(self, online, timeout=15):
        """Confirm the original server removed/added this exact UI character."""
        deadline = time.monotonic() + timeout
        readings = []
        while True:
            result = self.evidence.observe('独立管理员读取UI角色在线状态', lambda:
                self.bridge.call('presence', {'target': self.config['target']}, read_only=True))
            if result.get('name') != self.config['target'] or type(result.get('online')) is not bool:
                raise ValueError('invalid presence response for UI target')
            readings.append(result)
            if result['online'] is online or time.monotonic() >= deadline:
                break
            time.sleep(0.3)
        self.evidence.data['diagnostics'].setdefault('presence_observations', []).append(readings)
        self.evidence.check('原服确认UI角色在线' if online else '原服确认UI角色实际离线',
                            result['online'], online, 'QaProbe只读查询原服RuleProcessor.getPlayer')
        return result

    def forget(self, older_than_seconds=0, target=None, token=None):
        """丢弃某个角色名下的快照（不必知道 token）。

        显式清理工具使用；prepare/restore 失败不能自动丢弃快照，否则会失去原始状态。
        """
        fields = {"older_than_seconds": older_than_seconds}
        if token:
            fields["forget_token"] = token          # 只丢这一个：用例异常时精确回收自己的快照
        return self._guarded("forget", fields)

    def snapshots(self, target=None):
        """列出该角色名下还活着的快照（只读）。用于精确回收自己留下的残留。"""
        return self._guarded("snapshots", read_only=True)["snapshots"]

    def prepare(self, **fields):
        try:
            result = self._guarded("prepare", fields)
        except Exception:
            self.evidence.data["failure_kind"] = "preparation_error"
            raise
        self.evidence.data["diagnostics"]["preparation"] = result
        if not result.get("snapshot_id"):
            raise ValueError("preparation did not return a restorable snapshot")
        return result

    def restore(self, snapshot_id):
        result = self._guarded("restore", {"snapshot_id": snapshot_id})
        self.evidence.data["diagnostics"]["restoration"] = result
        if result.get("restored") is not True:
            raise ValueError("server did not confirm restoration")
        return result

    def action(self, fields, title):
        if self.observer:
            raise ValueError("business actions must come from the test player")
        return self.evidence.action(title, lambda: self.bridge.call("send_action", {"action": fields}))

    def chat(self, text):
        return self.action({"type": "chat", "text": text}, f"玩家对话：{text}")

    def await_state(self, condition, title, timeout=5):
        """Wait for asynchronous server ticks; business assertion is made by the case."""
        deadline = time.monotonic() + timeout
        observations = []
        while True:
            state = self.inspect()
            observations.append(state)
            if condition(state) or time.monotonic() >= deadline:
                self.evidence.data["diagnostics"].setdefault("state_observations", []).append(
                    {"title": title, "observations": observations})
                return state
            time.sleep(0.3)


def dialogue(player, *words):
    """Send each NPC chat action once and retain the actual server replies."""
    player._guarded("get_chat_messages", read_only=True, with_target=False)
    messages = []
    for word in words:
        player.chat(word)
        started = time.monotonic()
        # The NPC replies in preLogic of a later turn, after the player echo.
        # Poll only received messages; a missing reply never resends the chat.
        time.sleep(0.6)
        received, reads = [], 0
        while True:
            received.extend(player._guarded("get_chat_messages", read_only=True, with_target=False))
            reads += 1
            if word == "bye" or any(row.get("type") == "npc" for row in received) or time.monotonic() - started >= 1.8:
                break
            time.sleep(0.15)
        messages.extend(received)
        player.evidence.data["diagnostics"].setdefault("dialogue_observations", []).append(
            {"input": word, "reads": reads, "elapsed": time.monotonic() - started, "messages": received})
    player.evidence.data["diagnostics"].setdefault("npc_dialogue", []).extend(messages)
    return messages


def quantity(state, item_name, slot="bag"):
    return sum(int(item.get("quantity", 1)) for item in state.get("inventory", [])
               if item.get("name") == item_name and (slot is None or item.get("slot") == slot))


def quest_phase(state, name):
    # SimpleQuestCompleteBuilder stores phase;timestamp;count; PlayerQuests reads index 0.
    return state.get("quests", {}).get(name, "").split(";", 1)[0]


def sold_count(state, item_name):
    """已售出数量：读**持久**计数，即 commerce.looted_items 里的 "sold.<item>"。

    不要读 item_counter_cache.sold：1.49 的 PlayerLootedItemsHandler 构造器有个 bug——
    它把持久映射里的 `sold.*` 条目装进了 **bought**（PlayerLootedItemsHandler.java#L78），
    `sold` 字段则从不加载，于是每次登录都从 0 开始。后果是"会话内字段增量"错位：
    实测卖 2 件时基线读到 0、之后读到"持久值+2"，看起来多 1（真机复现 2 件→+3、1 件→+2）。
    持久映射才是真值：同一次实测里卖 2 件是 3→5（正好 +2）。
    """
    value = state.get("commerce", {}).get("looted_items", {}).get(f"sold.{item_name}", 0)
    return int(value or 0)


def said(messages, name, snippet):
    """对话里某个说话人是否说过包含 snippet 的话；取数与匹配都收在这里，用例层不写生成器表达式。"""
    return any(row.get("name") == name and snippet in row.get("text", "") for row in messages)


def await_quantity(observer, item, qty, slot="bag", timeout=5):
    """等某个槽位的物品数量达到 qty（至少）；谓词收在这里，用例层不写 lambda。"""
    return observer.await_state(lambda state: quantity(state, item, slot) >= qty,
                                f"等待 {item}×{qty} 在服务端落地（{slot}）", timeout=timeout)


def position(state):
    """角色位置 [区域, x, y]（原来住在用例文件里，取数归封装层）。"""
    attrs = state["attributes"]
    return [attrs["zoneid"], int(attrs["x"]), int(attrs["y"])]


def await_exact_quantity(observer, item, qty, slot="bag", timeout=5):
    """等数量恰好等于 qty。

    与 await_quantity 的区别是语义而非写法：那个是"至少"，用于等东西出现/落地；
    这个是"恰好"，用于等消耗到剩 N——"至少"在消耗发生前就已经满足，等于没等。
    """
    return observer.await_state(lambda state: quantity(state, item, slot) == qty,
                                f"等待 {item} 恰好剩 {qty}（{slot}）", timeout=timeout)


def await_slot_empty(observer, slot, timeout=5):
    """等某个槽位变空（卸下装备、换手这类递减观察）。"""
    return observer.await_state(lambda state: not state.get("slots", {}).get(slot),
                                f"等待 {slot} 槽腾空", timeout=timeout)


def await_position(observer, x, y, timeout=5):
    """等角色走到 (x, y)；口径与 position() 一致（只比坐标，不比区域）。"""
    return observer.await_state(lambda state: position(state)[1:] == [x, y],
                                f"等待走到 ({x}, {y})", timeout=timeout)


def use(player, state, item_name, slot="bag"):
    """从某个槽位使用一件道具（原版 use 动作）。

    道具 id 要从**玩家自己的投影**里取，所以调用方得把 prepare/await 拿到的 state 传进来；
    先找道具、再拼 action 载荷这两件框架细节收在这里，用例只说"用哪件"。
    """
    item = next(entry for entry in state["slots"][slot] if entry["name"] == item_name)
    return player.action({"type": "use", "baseobject": state["attributes"]["id"],
                          "baseslot": slot, "baseitem": item["attributes"]["id"]},
                         f"通过原版use动作使用 {item_name}（{slot}）")


def hello(player, npc):
    """开启 NPC 会话：bye → hi <npc>。返回这两句的回应。"""
    return dialogue(player, "bye", f"hi {npc}")


def equip(player, state, item, source, destination):
    """把一件已穿/在包里的道具从一个槽移到另一个槽（原版 equip 动作）。

    槽位与道具 id 都从玩家自己的投影里取：调用方把 inspect/prepare 拿到的 state 传进来即可。
    """
    return player.action({"type": "equip", "baseobject": state["attributes"]["id"],
                          "baseslot": source, "baseitem": item["attributes"]["id"],
                          "targetobject": state["attributes"]["id"], "targetslot": destination},
                         f"玩家把{item['name']}从{source}移到{destination}")


ANSWERS = ("yes", "no")


def confirm(player, answer="yes"):
    """回答 NPC 当前的是非问（yes / no）。

    刻意收紧成枚举：原先它接受任意字符串，于是可以拿它发业务指令
    （`confirm(player, "sell 2 cheese")`）——门禁查不出、真机还会全绿，回流通道就被绕过了
    （见 docs/实施记录.md 的 AI 生成试点 B 组）。缺什么业务指令，就在对应业务域里加原子。
    放在会话层是因为这是"回答提问"这个意图，与具体业务域无关；shop.confirm 保留为同义入口。
    """
    if answer not in ANSWERS:
        raise ValueError(f"confirm 只接受 {'/'.join(ANSWERS)}；{answer!r} 是业务指令，"
                         f"应在对应业务域里新增专用原子")
    return dialogue(player, answer)


def leave(player):
    """结束会话。"""
    return dialogue(player, "bye")


def await_phase(observer, quest, phase, timeout=5):
    """等任务阶段变成 phase。"""
    return observer.await_state(lambda state: quest_phase(state, quest) == phase,
                                f"等待任务 {quest} 进入 {phase}", timeout=timeout)


def await_field(observer, field, value, timeout=5):
    """等状态的某个字段等于 value。"""
    return observer.await_state(lambda state: state[field] == value,
                                f"等待 {field} == {value}", timeout=timeout)
