"""Nothing in sight: head for the map's densest spawn area (the user, 2026-11-02, Rain-Forest East of Henesys:
'the bot is just always pulling to the left ... gets stuck to the left of the portal where there is minimal spawn').
rain_base (2 min, started at map x 1118): 25 idle walks left, 1 right - patrol_dir defaulted to 'left' and only a
wall turned it - and the 2nd minute was spent at x -300..-720, past the left portal (-465..-647)."""
import pytest

from maplebot.brain.actions import Hold
from maplebot.brain.brain import Brain
from maplebot.config import Config, Nav
from maplebot.nav.navmap import NavMap
from test_jump import RAIN, at


@pytest.fixture(params=["exact", 1, 2, 3])
def nbrain(request):
    cfg = Config()
    cfg.perception.map_id = 10001070
    if request.param == "exact":
        cfg.humanize.jitter = 0.0
    else:
        cfg.humanize.seed = request.param
    return Brain(cfg, navmap=RAIN)


def held(acts):
    return [a.key for a in acts if isinstance(a, Hold) and a.key in ("left", "right")]


def test_rain_forest_spawns_densest_right_of_centre():
    assert len(RAIN.spawns) == 9
    c = RAIN.spawn_center(215.0)
    assert 750 <= c <= 950                     # between the 347-634 group and the right pit's 995-1215


def test_spawn_center_counts_only_our_level():
    m = {"footholds": {"1": {"x1": 0, "x2": 2000, "y1": 500, "y2": 500, "prev": 0, "next": 0}},
         "mobs": [{"x": 100, "y": 500}, {"x": 150, "y": 500},
                  {"x": 1800, "y": 100}, {"x": 1850, "y": 100}, {"x": 1900, "y": 100},
                  {"x": 1000, "y": 500, "hidden": True}]}
    nm = NavMap.from_json(m, Nav())
    assert nm.spawn_center(500.0) < 300           # the high platform's 3 don't pull us off our floor
    assert nm.spawn_center(100.0) > 1700
    assert NavMap.from_json({**m, "mobs": []}, Nav()).spawn_center(500.0) is None


def test_far_left_of_the_spawns_walks_right_and_keeps_going(nbrain):
    """Past the left portal (rain_base's 2nd minute): walk right, no standing after 2-3 s, until near the spawns."""
    nbrain.patrol_dir = "left"                    # the old default that dragged us left
    x, t = -650.0, 0.0
    while t < 12.0:
        acts = nbrain.step(at(t, 71, x, dot_x=40.0 + (x + 650) / 16))
        if held(acts) or nbrain.held == "right":
            assert nbrain.held == "right"
        x += 125 * 0.05 if nbrain.held == "right" else 0
        t += 0.05
        if x > -30:                                  # floor 71 ends at the left pit (39): stop the test there
            break
    assert x > -100, f"stood / turned at x {x:.0f}"
    assert nbrain.stats["spawn_walks"] >= 1 and nbrain.stats["waits"] == 0


def test_far_right_of_the_spawns_walks_left(nbrain):
    nbrain.patrol_dir = "right"
    acts = nbrain.step(at(0.0, 82, 1500.0, dot_x=140.0))
    assert held(acts) == ["left"]


def test_near_the_spawns_waits_as_before(nbrain):
    """Inside the dense area: the usual short walk, then stand still for a spawn (lie detector: no endless pacing)."""
    c = RAIN.spawn_center(215.0)
    t, x = 0.0, c - 150
    while t < 15.0:
        nbrain.step(at(t, 48 if x < 849 else 91, x, dot_x=90.0 + x / 16))
        x += (125 * 0.05) * {"right": 1, "left": -1}.get(nbrain.held, 0)
        t += 0.05
    # the 2-3 s walk may carry us out of the area once -> back in, then stand (no ping-pong)
    assert nbrain.stats["waits"] == 1 and nbrain.stats["spawn_walks"] <= 1
    assert nbrain.held is None and abs(x - c) <= nbrain.cfg.nav.spawn_home + 125 * 3.5


def test_no_spawn_walk_into_an_avoided_way(nbrain):
    nbrain.blocked["right"] = 99.0
    acts = nbrain.step(at(0.0, 71, -650.0, dot_x=40.0))
    assert held(acts) != ["right"]


def test_switched_off_keeps_the_old_patrol(nbrain):
    nbrain.cfg.nav.seek_spawns = False
    nbrain.patrol_dir = "left"
    acts = nbrain.step(at(0.0, 71, -400.0, dot_x=60.0))
    assert held(acts) == ["left"]
