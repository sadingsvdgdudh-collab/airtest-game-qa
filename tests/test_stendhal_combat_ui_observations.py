"""Recorded UI counterexamples and recovery ordering; no live accounts or devices."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest
from PIL import Image
from airtest.core.api import Template

from cases.test_stendhal_combat import rat_fixture
from gameqa.evidence import Evidence


ASSETS = Path(__file__).resolve().parents[1] / 'assets/stendhal'
MAP = (96, 203, 565, 555)
STATS = (0, 325, 96, 470)


def crop_screen(name, region):
    screen = cv2.imread(str(ASSETS / 'calibration' / (name + '.png')))
    assert screen is not None
    x1, y1, x2, y2 = region
    return screen[y1:y2, x1:x2]


def test_combat_templates_replay_source_and_reject_recorded_counterexamples():
    manifest = json.loads((ASSETS / 'combat-templates.json').read_text())
    for name, spec in manifest.items():
        path = ASSETS / (name + '.png')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == spec['sha256']
        with Image.open(ASSETS / spec['source']) as source, Image.open(path) as template:
            assert source.crop(spec['crop']).tobytes() == template.tobytes()
    for template, good, wrong, roi, threshold in (
        ('xp-800', 'combat-rat', 'combat-killed', STATS, .98),
        ('xp-805', 'combat-killed', 'combat-rat', STATS, .98),
        ('rat-corpse', 'combat-killed', 'combat-rat', MAP, .9),
        ('attack-menu', 'combat-menu', 'combat-rat', MAP, .85),
        ('rat-title', 'combat-menu', 'combat-killed', MAP, .9),
    ):
        matcher = Template(str(ASSETS / (template + '.png')), threshold=threshold)
        assert matcher.match_in(crop_screen(good, roi))
        assert matcher.match_in(crop_screen(wrong, roi)) is None
    attack = Template(str(ASSETS / 'attack-menu.png'), threshold=.85)
    assert attack.match_in(crop_screen('combat-menu-position-2', MAP))
    # A menu exists here, but its other genuine rows must never select an attack.
    assert attack.match_in(crop_screen('combat-menu-position-2', (372, 349, 431, 369))) is None
    assert attack.match_in(crop_screen('combat-menu-position-2', (372, 386, 431, 407))) is None


@pytest.mark.parametrize('online', [True, False])
def test_combat_cleanup_restores_ui_presence_before_removing_fixture(tmp_path, online):
    operations = []
    def call(operation, params, **kwargs):
        operations.append(operation)
        if operation == 'combat_prepare': return {'fixture_id': 'fixture'}
        if operation == 'presence': return {'name': 'qaplayer', 'online': online}
        if operation == 'combat_cleanup': return {'rat_present': False, 'corpse_present': False}
        raise AssertionError(operation)
    observer = SimpleNamespace(config={'target': 'qaplayer'}, bridge=SimpleNamespace(call=call),
                               evidence=Evidence('cleanup', tmp_path),
                               _guarded=lambda op, fields=None, **kw: call(op, {'target': 'qaplayer', **(fields or {})}, **kw),
                               await_presence=lambda value: operations.append('await-online'))
    ui = SimpleNamespace(ensure_login=lambda: operations.append('ui-login'))
    request = SimpleNamespace(node=SimpleNamespace(_qa_meta={'kind': 'ui'}), getfixturevalue=lambda name: ui)
    fixture = rat_fixture.__wrapped__(observer, request)
    start = next(fixture)
    assert start()['fixture_id'] == 'fixture'
    with pytest.raises(StopIteration): next(fixture)
    assert operations == (['combat_prepare', 'presence', 'combat_cleanup'] if online else
                          ['combat_prepare', 'presence', 'ui-login', 'await-online', 'combat_cleanup'])
