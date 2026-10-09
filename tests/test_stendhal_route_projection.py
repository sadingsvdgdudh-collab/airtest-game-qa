"""Fixed camera calibration: endpoints, border transitions and unsafe taps."""
import pytest
from gameqa.stendhal_ui import map_touch, minimap_touch


def test_camera_projection_centres_clamps_and_rejects_unseen_targets():
    assert map_touch((32, 32), (64, 64), (32, 32)) == (330, 379)
    assert map_touch((7, 11), (22, 18), (13, 11)) == (413, 402)
    assert map_touch((58, 44), (64, 64), (63.25, 44)) == (559, 379)
    assert map_touch((6, 44), (64, 64), (-.25, 44)) == (102, 379)
    for destination in [(-1, 4), (64, 4), (32, 32)]:
        with pytest.raises(ValueError):
            map_touch((6, 44), (64, 64), destination)


def test_material_template_needs_real_material_line():
    import cv2
    from airtest.core.api import Template
    from gameqa.stendhal_ui import ASSETS
    screen = cv2.imread(str(ASSETS / 'calibration/quest-start.png'))
    matcher = Template(str(ASSETS / 'quest-material-ready.png'), threshold=.9)
    assert matcher.match_in(screen[290:555, 290:597])
    screen[434:453, 299:460] = 0
    assert matcher.match_in(screen[290:555, 290:597]) is None
    missing = cv2.imread(str(ASSETS / 'calibration/chain-no-material.png'))
    bought = cv2.imread(str(ASSETS / 'calibration/chain-material.png'))
    assert matcher.match_in(missing[290:555, 290:597]) is None
    assert matcher.match_in(bought[290:555, 290:597])


def test_unpanned_minimap_projection_selects_exact_tiles_after_browser_rounding():
    for size in [(22, 18), (32, 19), (64, 64)]:
        width, height = size
        scale = max(2, min(128 / height, 128 / width))
        for x in range(width):
            for y in range(height):
                sx, sy = minimap_touch(size, (x, y))
                # Original HTMLManager rounds MouseEvent offsets before tile selection.
                selected = (int(int((sx - .5) * 980 / 720 + .5) / scale),
                            int(int((sy - 202.55) * 980 / 720 + .5) / scale))
                assert selected == (x, y)
    # Passive DOM listener measured actual ADB clicks; it never submitted game actions.
    measured = [(35,269,47,90),(36,269,48,90),(37,269,50,90),(38,269,51,90),
                (39,269,52,90),(53,268,71,89),(54,268,73,89),(55,268,74,89),
                (25,252,33,67),(29,253,39,69),(36,260,48,78),(37,261,50,80),
                (47,262,63,81),(61,267,82,88),(74,268,100,89),(86,269,116,90),
                (36,270,48,92),(37,271,50,93),(38,273,51,96),(39,275,52,99)]
    for sx, sy, ox, oy in measured:
        assert (int((sx - .5) * 980 / 720 + .5),
                int((sy - 202.55) * 980 / 720 + .5)) == (ox, oy)
    for size, point in [((65, 64), (0, 0)), ((64, 64), (-.25, 44)), ((22, 18), (22, 0))]:
        with pytest.raises(ValueError): minimap_touch(size, point)
