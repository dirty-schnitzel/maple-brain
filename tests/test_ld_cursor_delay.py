"""tools/perc/ld/cursor_delay.py: how many frames the picture is behind the logged mouse, from the green
crosshair the Lie Detector's mouse game draws. Tested on drawn frames: a crosshair that follows a scripted mouse
path a known number of frames late, at a known place against it; no game, no bank, no GPU."""
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "perc" / "ld"))
import cursor_delay as cd  # noqa: E402

W, H = 640, 400
GREEN = (0, 255, 80)                                         # BGR, as the client's crosshair reads in the mask


def crosshair(img, x, y):
    cv2.circle(img, (int(x), int(y)), 14, GREEN, 3)
    cv2.line(img, (int(x) - 5, int(y)), (int(x) + 5, int(y)), GREEN, 1)


def path(n=260):
    """A smooth hand path with a still start: whole pixels, 1-6 px a frame."""
    out = [(300, 200)] * 12
    for i in range(n):
        out.append((int(round(300 + 150 * math.sin(i / 17.0))), int(round(200 + 90 * math.sin(i / 11.0)))))
    return out


def drawn_late(cur, late, off=(0, 0)):
    """What `green_centre` reads on frames drawn `late` frames behind the log, the crosshair `off` px from the mouse."""
    out = []
    for i, c in enumerate(cur):
        src = cur[max(0, i - late)]
        img = np.full((H, W, 3), (40, 90, 140), np.uint8)    # a brown ground, no green
        crosshair(img, src[0] + off[0], src[1] + off[1])
        out.append(cd.green_centre(img, c[0], c[1]))
    return out


def test_green_centre_finds_the_ring_and_nothing_else():
    img = np.full((H, W, 3), (40, 90, 140), np.uint8)
    assert cd.green_centre(img, 300, 200) is None                         # no crosshair
    cv2.rectangle(img, (250, 150), (340, 240), GREEN, -1)                 # a green area, not a ring: too large
    assert cd.green_centre(img, 300, 200) is None
    img[:] = (40, 90, 140)
    crosshair(img, 310, 190)
    x, y = cd.green_centre(img, 300, 200)
    assert abs(x - 310) <= 1 and abs(y - 190) <= 1
    crosshair(img, 360, 230)                                              # two: the one nearest the mouse
    x, y = cd.green_centre(img, 355, 228)
    assert abs(x - 360) <= 1 and abs(y - 230) <= 1
    assert cd.green_centre(img, 600, 380) is None                         # none within reach of the mouse


@pytest.mark.parametrize("late, off", [(2, (0, 0)), (2, (30, 30)), (3, (0, 0)), (0, (0, 0))])
def test_measure_finds_the_delay_and_the_crosshairs_place(late, off):
    cur = path()
    fit = cd.measure(cur, drawn_late(cur, late, off))
    assert fit["best"] == late
    s = fit["shifts"][late]
    assert s["p90"] <= 1.0                                                # the path fits to the pixel at that shift
    assert abs(s["offset"][0] - off[0]) <= 1 and abs(s["offset"][1] - off[1]) <= 1
    wrong = fit["shifts"][late + 1 if late < 5 else late - 1]
    assert wrong["p50"] > s["p50"] + 1.0                                  # ... and clearly worse one frame off
    assert max(fit["votes"], key=fit["votes"].get) == late


def test_measure_needs_a_moving_mouse():
    cur = [(300, 200)] * 200
    assert cd.measure(cur, drawn_late(cur, 2)) is None


def test_game_stretch_leaves_out_the_panels_still_pictures():
    still = [(500.0, 100.0)] * 60 + [(540.0, 100.0)] * 3 + [(500.0, 100.0)] * 40    # the panel: two pictures, a flip
    cur = path()
    game = drawn_late(cur, 2)
    a, b = cd.game_stretch(still + game + [None] * 30)
    assert len(still) <= a <= len(still) + 18                             # begins with the game's own crosshair
    assert len(still) + len(game) - 6 <= b <= len(still) + len(game) - 1
    assert cd.game_stretch(still) is None
