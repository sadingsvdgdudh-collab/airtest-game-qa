"""Offline checks: a missing session or a matching chat line must not fake UI success."""
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest
from airtest.core import api as airtest

from gameqa import stendhal
from gameqa.bridge import TransientError
from gameqa.device import AndroidDevice
from gameqa.evidence import Evidence


ASSETS = Path(__file__).resolve().parents[1] / "assets" / "stendhal"
STATS_REGION = (0, 325, 96, 470)
LOG_REGION = (290, 290, 597, 555)


def observer_for(tmp_path, response):
    calls = []

    def call(operation, params, *, read_only):
        calls.append((operation, params, read_only))
        if isinstance(response, Exception):
            raise response
        return response

    observer = object.__new__(stendhal.Stendhal)
    observer.config = {"target": "qaplayer"}
    observer.bridge = SimpleNamespace(call=call)
    observer.evidence = Evidence("presence", tmp_path)
    return observer, calls


@pytest.mark.parametrize("response", [
    {"name": "qaplayera", "online": False},
    {"name": "qaplayer", "online": "false"},
    {"name": "qaplayer", "online": 0},
    {"name": "qaplayer", "online": None},
])
def test_presence_rejects_wrong_actor_or_non_boolean(tmp_path, response):
    observer, calls = observer_for(tmp_path, response)
    with pytest.raises(ValueError, match="invalid presence response"):
        observer.await_presence(False, timeout=0)
    assert calls == [("presence", {"target": "qaplayer"}, True)]
    assert not any(step.get("expected") is False for step in observer.evidence.data["steps"])


def test_presence_deadline_does_not_turn_an_online_player_into_offline(tmp_path, monkeypatch):
    clock = SimpleNamespace(now=0.0)

    def sleep(seconds):
        clock.now += seconds

    monkeypatch.setattr(stendhal, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    observer, calls = observer_for(tmp_path, {"name": "qaplayer", "online": True})
    with pytest.raises(AssertionError, match="actual=True"):
        observer.await_presence(False, timeout=0.6)
    assert len(calls) == 3
    readings = observer.evidence.data["diagnostics"]["presence_observations"][0]
    assert all(reading["online"] is True for reading in readings)
    assert observer.evidence.data["steps"][-1]["outcome"] == "failed"


def test_presence_transport_timeout_remains_an_error(tmp_path):
    observer, calls = observer_for(tmp_path, TransientError("bridge response timed out"))
    with pytest.raises(TransientError, match="timed out"):
        observer.await_presence(False, timeout=0)
    assert len(calls) == 2  # Existing read-only observation retry, never a logout action.
    assert observer.evidence.data["unstable"] is True
    assert observer.evidence.data["steps"][-1]["outcome"] == "failed"
    assert "presence_observations" not in observer.evidence.data["diagnostics"]


def test_presence_accepts_only_explicit_offline_result(tmp_path):
    response = {"name": "qaplayer", "online": False}
    observer, calls = observer_for(tmp_path, response)
    assert observer.await_presence(False, timeout=0) == response
    assert calls == [("presence", {"target": "qaplayer"}, True)]
    assert observer.evidence.data["steps"][-1]["outcome"] == "passed"


def offline_android(tmp_path, monkeypatch, screen):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline ROI check must not access a live device")

    monkeypatch.setattr(airtest, "connect_device", forbidden)
    monkeypatch.setattr(airtest, "exists", forbidden)
    android = object.__new__(AndroidDevice)
    android.device = SimpleNamespace(snapshot=lambda: screen.copy())
    android.evidence = Evidence("roi", tmp_path)
    android.screenshot = lambda label: None
    return android


def completed_screen():
    screen = cv2.imread(str(ASSETS / "calibration" / "quest-completed.png"))
    assert screen is not None
    return screen


def test_roi_match_returns_screen_coordinates(tmp_path, monkeypatch):
    android = offline_android(tmp_path, monkeypatch, completed_screen())
    position = android.locate_image(ASSETS / "xp-next-50.png", "next XP", region=STATS_REGION, threshold=0.9)
    # Centre of the independently recorded source crop [0, 417, 44, 443].
    assert position == (22, 430)
    assert android.evidence.data["diagnostics"]["visual_observations"][-1]["region"] == STATS_REGION


def test_quest_text_in_chat_does_not_satisfy_log_roi(tmp_path, monkeypatch):
    screen = completed_screen()
    screen[290:555, 290:597] = 0
    template_path = ASSETS / "quest-promised.png"
    template = cv2.imread(str(template_path))
    height, width = template.shape[:2]
    screen[650:650 + height, 120:120 + width] = template
    # An exact copy exists in the chat region; a full-screen lookup would succeed.
    assert airtest.Template(str(template_path), threshold=0.9).match_in(screen)
    android = offline_android(tmp_path, monkeypatch, screen)
    with pytest.raises(TransientError, match="image not found"):
        android.locate_image(template_path, "quest promise", region=LOG_REGION, threshold=0.9)
    observations = android.evidence.data["diagnostics"]["visual_observations"]
    assert all(item["matched"] is False for item in observations)


def test_next_xp_requires_level_line_even_when_other_fifties_remain(tmp_path, monkeypatch):
    screen = completed_screen()
    # Remove only Level: 1. Leave the real next-XP (50) and ATK/DEF (50) visible.
    screen[417:430, :44] = screen[454:467, :44]
    android = offline_android(tmp_path, monkeypatch, screen)
    with pytest.raises(TransientError, match="image not found"):
        android.locate_image(ASSETS / "xp-next-50.png", "next XP", region=STATS_REGION, threshold=0.9)
    assert all(item["matched"] is False
               for item in android.evidence.data["diagnostics"]["visual_observations"])


@pytest.mark.parametrize('filename,focused', [('login-focused.png', True), ('login-unfocused.png', False)])
def test_real_login_focus_guard_rejects_the_recorded_unfocused_failure(tmp_path, monkeypatch, filename, focused):
    screen = cv2.imread(str(ASSETS / 'calibration' / filename))
    assert screen is not None
    android = offline_android(tmp_path, monkeypatch, screen)
    if focused:
        assert android.locate_image(ASSETS / 'username-focused.png', 'focus',
                                    region=(170, 255, 352, 285), threshold=0.9)
    else:
        with pytest.raises(TransientError, match='image not found'):
            android.locate_image(ASSETS / 'username-focused.png', 'focus',
                                  region=(170, 255, 352, 285), threshold=0.9)
