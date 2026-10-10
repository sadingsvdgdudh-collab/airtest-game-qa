"""家畜不在角色快照里，失败时也必须实际放走并确认。"""
from types import SimpleNamespace

import pytest

from cases import test_stendhal_pet as pet_case
from gameqa.evidence import Evidence
from gameqa.recovery import clear_pet


def sheep_state(owned):
    return {"attributes": {"zoneid": "sheep-zone"}, "money": 100,
            "pet": {"has_sheep": owned, "has_pet": False,
                    "animal": {"type": "Sheep"} if owned else None}}


def test_clear_pet_forsakes_a_sheep_and_confirms_both_ownership_flags():
    state, actions = sheep_state(True), []

    def action(fields, title):
        actions.append(fields)
        state.update(sheep_state(False))

    def await_state(condition, title):
        assert condition(state)
        return state

    observer = SimpleNamespace(inspect=lambda: state, await_state=await_state)
    result = clear_pet(SimpleNamespace(action=action), observer)
    assert actions == [{"type": "forsake", "zone": "sheep-zone", "species": "sheep"}]
    assert result == {"pet": "forsook sheep", "still": False}


def test_clear_pet_does_not_report_success_when_sheep_remains():
    state = sheep_state(True)
    observer = SimpleNamespace(inspect=lambda: state, await_state=lambda condition, title: state)
    with pytest.raises(RuntimeError, match="未确认"):
        clear_pet(SimpleNamespace(action=lambda *args: None), observer)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_sheep_case_runs_cleanup_after_a_post_purchase_assertion_failure(tmp_path, monkeypatch, cleanup_fails):
    state, actions = sheep_state(False), []
    state["money"] = 130
    qa = Evidence("pet-failure", tmp_path)
    monkeypatch.setattr(pet_case, "hello", lambda *args: [])
    monkeypatch.setattr(pet_case, "buy", lambda *args: [
        {"name": pet_case.NPC, "text": "A sheep will cost 30. Do you want to buy it?"}])

    def confirm(*args):
        state.update(sheep_state(True))
        return []  # 羊已生成，但缺少成交回话，业务断言必须失败。

    monkeypatch.setattr(pet_case, "confirm", confirm)
    monkeypatch.setattr(pet_case, "leave", lambda *args: None)

    def action(fields, title):
        actions.append(fields)
        if cleanup_fails:
            raise RuntimeError("cleanup unavailable")
        state.update(sheep_state(False))

    observer = SimpleNamespace(inspect=lambda: state, await_state=lambda condition, title: state)
    player = SimpleNamespace(action=action)
    error, message = ((RuntimeError, "cleanup unavailable") if cleanup_fails
                      else (AssertionError, "成交时 NPC 实际交出羊"))
    with pytest.raises(error, match=message):
        pet_case.test_second_sheep_purchase_is_refused_and_not_charged(
            qa, player, observer, lambda **fields: state)
    assert len(actions) == 1 and actions[0]["type"] == "forsake"
    assert any(step.get("outcome") == "failed" for step in qa.data["steps"])
    if cleanup_fails:
        assert qa.data["failure_kind"] == "cleanup_error"
    else:
        assert state["pet"]["has_sheep"] is False
        assert "failure_kind" not in qa.data
