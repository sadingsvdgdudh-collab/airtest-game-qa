"""Recorded-image counterexamples; these tests never connect to the game or device."""
import hashlib
import json
from pathlib import Path

import cv2
import pytest
from PIL import Image
from airtest.core.api import Template

from gameqa.bridge import TransientError
from test_stendhal_ui_observations import offline_android


ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'stendhal'
FIRST_BAG = (568, 343, 596, 372)
STATS = (0, 325, 96, 470)
RHAND = (568, 260, 596, 289)


def screen(name):
    result = cv2.imread(str(ASSETS / 'calibration' / (name + '.png')))
    assert result is not None
    return result


def test_item_templates_replay_exact_recorded_crops():
    manifest = json.loads((ASSETS / 'item-templates.json').read_text())
    assert len(manifest) == 18
    for name, spec in manifest.items():
        path = ASSETS / (name + '.png')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == spec['sha256']
        with Image.open(ASSETS / spec['source']) as source, Image.open(path) as template:
            assert source.crop(spec['crop']).tobytes() == template.tobytes()


@pytest.mark.parametrize('expected,wrong', [('potion-two', 'potion-one'), ('potion-one', 'potion-two')])
def test_potion_count_rejects_the_other_recorded_quantity(tmp_path, monkeypatch, expected, wrong):
    path = ASSETS / (expected + '.png')
    android = offline_android(tmp_path, monkeypatch, screen(expected))
    assert android.locate_image(path, expected, region=FIRST_BAG, threshold=0.98)
    android.device.snapshot = lambda: screen(wrong)
    with pytest.raises(TransientError, match='image not found'):
        android.locate_image(path, 'wrong quantity', region=FIRST_BAG, threshold=0.98)
    assert android.evidence.data['unstable'] is True


def test_hp_assertions_reject_all_other_recorded_hp_values(tmp_path, monkeypatch):
    values = {'40': 'potion-two', '90': 'potion-one', '100': 'potion-empty'}
    for value, name in values.items():
        path = ASSETS / ('hp-' + value + '.png')
        android = offline_android(tmp_path, monkeypatch, screen(name))
        assert android.locate_image(path, value, region=STATS, threshold=0.98)
        for other, wrong in values.items():
            if other == value:
                continue
            android.device.snapshot = lambda wrong=wrong: screen(wrong)
            with pytest.raises(TransientError, match='image not found'):
                android.locate_image(path, 'wrong HP ' + other, region=STATS, threshold=0.98)


def test_sword_in_bag_cannot_satisfy_right_hand_roi(tmp_path, monkeypatch):
    image = screen('items-sword-first')
    path = ASSETS / 'short-sword-first.png'
    assert Template(str(path), threshold=0.9).match_in(image[343:461, 568:657])
    android = offline_android(tmp_path, monkeypatch, image)
    with pytest.raises(TransientError, match='image not found'):
        android.locate_image(path, 'sword in hand', region=RHAND, threshold=0.9)


def test_missing_server_refusal_does_not_pass_with_an_empty_feet_slot(tmp_path, monkeypatch):
    android = offline_android(tmp_path, monkeypatch, screen('items-sword-first'))
    with pytest.raises(TransientError, match='image not found'):
        android.locate_image(ASSETS / 'feet-refusal.png', 'actual refusal',
                             region=(100, 575, 565, 1220), threshold=0.9)


def test_remaining_potion_does_not_satisfy_first_slot_empty_check(tmp_path, monkeypatch):
    android = offline_android(tmp_path, monkeypatch, screen('potion-one'))
    # Other bag slots are genuinely empty; only this specific slot may satisfy the check.
    assert Template(str(ASSETS / 'bag-empty.png'), threshold=0.98).match_in(screen('potion-one')[343:461, 568:657])
    with pytest.raises(TransientError, match='image not found'):
        android.locate_image(ASSETS / 'bag-empty.png', 'consumed potion slot',
                             region=FIRST_BAG, threshold=0.98)
