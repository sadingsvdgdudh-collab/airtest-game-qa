"""NPC replies arrive after the player echo; waiting must not repeat a trade."""
from types import SimpleNamespace

from gameqa import stendhal


def player_and_clock(monkeypatch, replies):
    clock = SimpleNamespace(now=0.0)
    def sleep(seconds):
        clock.now += seconds
    monkeypatch.setattr(stendhal, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    responses = iter(replies)
    actions = []
    player = SimpleNamespace(
        bridge=SimpleNamespace(call=lambda *args, **kwargs: next(responses, [])),
        # dialogue() 的收信走 Stendhal._guarded（只读，可在断连后重连重试）；假 player 给同样的入口
        _guarded=lambda *args, **kwargs: next(responses, []),
        chat=lambda text: actions.append(text),
        evidence=SimpleNamespace(data={"diagnostics": {}}))
    return player, clock, actions


def test_waits_for_late_npc_reply_without_repeating_confirmation(monkeypatch):
    echo = {"type": "player", "name": "qaplayera", "text": "yes"}
    reply = {"type": "npc", "name": "Margaret", "text": "Congratulations!"}
    player, clock, actions = player_and_clock(monkeypatch, [[], [echo], [], [reply]])
    assert stendhal.dialogue(player, "yes") == [echo, reply]
    assert actions == ["yes"]
    assert clock.now > 0.6
    assert player.evidence.data["diagnostics"]["npc_dialogue"] == [echo, reply]


def test_silent_dialogue_stops_waiting_without_resending_action(monkeypatch):
    echo = {"type": "player", "name": "qaplayera", "text": "yes"}
    player, clock, actions = player_and_clock(monkeypatch, [[], [echo]])
    assert stendhal.dialogue(player, "yes") == [echo]
    assert actions == ["yes"]
    assert 1.8 <= clock.now <= 2.1
