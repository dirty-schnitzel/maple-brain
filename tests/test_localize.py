"""Our map position from the minimap, on recorded Perion Street Corner frames.
Fixture minimap_perion.npz: the screen's minimap corner (x 0-260, y 40-200) of 5 recorded frames, in order:
acc2 #3 (start on small platform 174), acc1 #24 (ground floor), acc3 #234 (ground, far right: the dot lay outside
the old minimap box), perion4 #1521 (on the rope at x 470: 173 perion4 frames there, median 0.4 px off),
perion5 #24 (in the air, knocked/dropped off platform 174), acc1 #687 (something yellow in the game world right
under the canvas)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebot.nav.localize import MinimapLocator
from maplebot.nav.navmap import NavMap
from maplebot.perception import hud

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "mcw"
CROPS = np.load(ROOT / "tests" / "fixtures" / "minimap_perion.npz")["crops"]


def frame(i):
    f = np.zeros((768, 1366, 3), np.uint8)
    f[40:200, 0:260] = CROPS[i]
    return f


@pytest.fixture
def loc():
    return MinimapLocator.for_map(10004040, ASSETS, navmap=NavMap.for_map(10004040, ASSETS))


def where(loc, i):
    f = frame(i)
    assert loc.calibrate(f)
    return loc.where(hud.minimap_dot(f, loc.dot_box()))


def test_canvas_found_where_perion_draws_it_to_a_fraction_of_a_px(loc):
    """The frame is scaled 3440 -> 1366, so the canvas sits at x 6.05 in some runs and 6.68 in others (10 runs,
    spread within a run <= 0.05 px); acc2 is a 6.68 run. 1 minimap px = 16 map px, so the fraction matters."""
    assert loc.calibrate(frame(0))
    assert loc.origin == pytest.approx((6.68, 72.1), abs=0.06)
    assert loc.dot_box() == (4, 66, 251, 159)              # the whole 243x85 canvas, same corner as before


def test_no_canvas_without_a_minimap(loc):
    assert not loc.calibrate(np.zeros((768, 1366, 3), np.uint8))
    assert loc.to_map((50, 50)) is None


def test_start_on_the_small_platform(loc):
    w = where(loc, 0)
    assert w.platform == 174 and -203 <= w.x <= -67 and abs(w.y - 1845) <= 14


def test_ground_floor(loc):
    w = where(loc, 1)
    assert w.platform == 54 and 400 <= w.x <= 470


def test_far_right_dot_outside_the_old_box(loc):
    f = frame(2)
    assert hud.minimap_dot(f) is None                       # the old box stopped at x 210
    w = where(loc, 2)
    assert w.platform == 54 and w.x > 1850


def test_on_a_rope(loc):
    w = where(loc, 3)
    assert w.platform is None and w.rope == 470 and abs(w.x - 470) <= 6


def test_in_the_air(loc):
    w = where(loc, 4)
    assert w.platform is None and w.rope is None


def test_yellow_world_pixels_under_the_canvas_are_ignored(loc):
    w = where(loc, 5)
    assert w is not None and w.platform is not None


def test_map_coordinates_formula(loc):
    """canvas px (dot + box corner - origin + marker) * 16 - (centerX, centerY) = (-1363, 966) at canvas (0, 0)."""
    loc.origin = (6, 72)
    mx, my = loc.cfg.marker_dx, loc.cfg.marker_dy
    x, y = loc.to_map((2 - mx, 6 - my))                      # a dot that lands on canvas px (0, 0)
    assert (x, y) == pytest.approx((-1363, 966))


def test_perceiver_reports_map_position_platform_and_rope(loc):
    """Wired into Observation (recorded in ticks.jsonl); no own name tag needed for it."""
    from maplebot.config import Config
    from maplebot.perception.perceiver import Perceiver
    p = Perceiver(Config(), np.load(ROOT / "assets" / "self_tag_gray.npy"), locator=loc)
    obs = p.observe(frame(0), 0.0)
    assert obs.platform == 174 and obs.map_pos is not None and obs.dot is not None
    obs = p.observe(frame(3), 0.1)
    assert obs.platform is None and obs.rope == 470


def test_perceiver_without_locator_keeps_the_old_dot():
    from maplebot.config import Config
    from maplebot.perception.perceiver import Perceiver
    p = Perceiver(Config(), np.load(ROOT / "assets" / "self_tag_gray.npy"))
    obs = p.observe(frame(1), 0.0)
    assert obs.dot is not None and obs.map_pos is None and obs.platform is None



# ---------------------------------------------------------------- a window showing part of the canvas (Ant Tunnel IV)
TALL = 10005063                  # canvas 219x172, window 219x112 at (6, 72), scrolled with the player


def tall_loc():
    return MinimapLocator.for_map(TALL, ASSETS, navmap=NavMap.for_map(TALL, ASSETS))


def tall_frame():
    """Live frame on the ladder at x 2150 in the lower right: rows 60-171 showing."""
    f = np.zeros((768, 1366, 3), np.uint8)
    f[40:330, 0:330] = cv2.imread(str(ROOT / "tests" / "fixtures" / "mapid" / "10005063_ant_tunnel4_lower_0.png"))
    return f


def scrolled_to(loc, row):
    """The live frame with the window redrawn from the canvas at `row` (the game's blend: half bright + offset)."""
    f = tall_frame()
    f[72:184, 6:225] = (0.5 * loc.canvas[row:row + 112] + 20).astype(np.uint8)
    return f


def test_a_scrolled_window_gives_the_real_position():
    loc = tall_loc()
    f = tall_frame()
    assert loc.calibrate(f) and loc.row == 60
    assert loc.origin == pytest.approx((6, 72 - 60), abs=0.5)
    w = loc.where(hud.minimap_dot(f, loc.dot_box()))
    assert w.rope == 2150 and abs(w.x - 2150) <= 6


def test_the_dot_is_looked_for_inside_the_window_not_the_canvas():
    """The canvas reaches 60 px below the window: game world, where yellow things made a second 'dot' before."""
    loc = tall_loc()
    assert loc.calibrate(tall_frame())
    assert loc.dot_box()[3] == 186


def test_follow_keeps_up_with_the_scroll():
    loc = tall_loc()
    assert loc.calibrate(scrolled_to(loc, 40)) and loc.row == 40
    y0 = loc.origin[1]
    for row in (42, 45, 41, 36):
        loc.follow(scrolled_to(loc, row))
        assert loc.row == row and loc.origin[1] == pytest.approx(y0 + 40 - row) and not loc.lost


def test_a_jump_past_the_step_loses_the_position_until_calibrated():
    """A portal inside the map: better no position than a wrong one."""
    loc = tall_loc()
    assert loc.calibrate(scrolled_to(loc, 0))
    far = scrolled_to(loc, 60)
    loc.follow(far)
    assert loc.lost and loc.to_map((50, 50)) is None
    assert loc.calibrate(far) and loc.row == 60 and not loc.lost and loc.to_map((50, 50)) is not None


def test_a_covered_window_loses_it_and_finds_it_again():
    loc = tall_loc()
    f = scrolled_to(loc, 30)
    assert loc.calibrate(f)
    covered = f.copy()
    covered[72:184, 6:225] = 200
    loc.follow(covered)
    assert loc.lost and not loc.calibrate(covered)
    assert loc.calibrate(f) and loc.row == 30


def test_a_full_canvas_never_scrolls(loc):
    assert loc.calibrate(frame(0)) and loc.view is None
    origin = loc.origin
    loc.follow(frame(1))
    assert loc.origin == origin and not loc.lost


def test_perceiver_reads_the_position_through_the_scroll():
    from maplebot.config import Config
    from maplebot.perception.perceiver import Perceiver
    p = Perceiver(Config(), np.load(ROOT / "assets" / "self_tag_gray.npy"), locator=tall_loc())
    obs = p.observe(tall_frame(), 0.0)
    assert obs.rope == 2150 and obs.map_pos is not None
