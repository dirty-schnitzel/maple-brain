from pathlib import Path

import pytest

from maplebot.nav.navmap import NavMap
from maplebot.nav.selfstate import SelfTracker

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"


@pytest.fixture(scope="module")
def nav():
    return NavMap.for_map(10003061, ASSETS)       # Line 1 <Area 1>: hub platform 273 at y 198, rope 1267


def test_standing_on_the_hub_is_ground_with_the_exact_floor_y(nav):
    st = SelfTracker(nav)
    for i in range(5):
        s = st.update(i * 0.04, me_map=(1000 + i * 5, 199.5), map_pos=(1004, 202))
    assert s.state == "ground" and s.platform == 273 and s.src == "tag"
    assert s.y == pytest.approx(198)
    assert s.vx == pytest.approx(125, abs=1)       # 5 px / 0.04 s


def test_camera_y_off_but_minimap_on_the_floor_is_still_ground(nav):
    st = SelfTracker(nav)
    for i in range(4):
        s = st.update(i * 0.04, me_map=(1000, 186), map_pos=(1004, 202))     # 12 px too high, not moving
    assert s.state == "ground" and s.platform == 273


def test_on_a_rope_and_in_the_air(nav):
    st = SelfTracker(nav)
    for i in range(5):
        s = st.update(i * 0.04, me_map=(1269, 0 - i * 5), map_pos=(1267, 0))  # climbing rope x 1267
    assert s.state == "rope" and nav.rope(s.rope).x == 1267
    assert s.vy == pytest.approx(-125, abs=1)
    st = SelfTracker(nav)
    for i in range(5):
        s = st.update(i * 0.04, me_map=(1000 + 5 * i, 150 + 3 * i * i), map_pos=(1004, 154))  # jumping
    assert s.state == "air" and s.platform is None and s.rope is None


def test_tag_lost_falls_back_to_the_minimap(nav):
    st = SelfTracker(nav)
    s = st.update(0.0, me_map=None, map_pos=(1004, 202))
    assert s.src == "minimap" and s.state == "ground" and s.platform == 273
    assert st.update(0.04) is s                       # nothing at all: the last state


def test_hanging_still_a_few_px_off_a_ladder_is_on_it(nav):
    st = SelfTracker(nav)                          # runs/v2 08:51: ladder 778 (15..176), read at x 787.7 -> "air" 21 s
    s = None
    for i in range(12):
        s = st.update(i * 0.04, me_map=(787.7, 90.3), map_pos=(787.7, 90.3))
    assert s.state == "rope" and nav.rope(s.rope).x == 778


def test_a_jump_apex_next_to_a_ladder_stays_air(nav):
    st = SelfTracker(nav)
    s = None
    for i, y in enumerate([120, 100, 92, 90, 92, 100, 120]):   # up and down again: never still for 0.25 s
        s = st.update(i * 0.04, me_map=(790, y), map_pos=(790, y))
        assert s.state == "air", (i, y)


def test_walk_key_held_without_moving_next_to_a_ladder_is_hanging_on_it(nav):
    st = SelfTracker(nav)                          # runs/v2 09:21: under the top of ladder 778, read as standing on 65
    s = None
    for i in range(15):
        s = st.update(i * 0.04, me_map=(787.8, 26.4), map_pos=(787.8, 26.4), held={"right"})
    assert s.state == "rope" and nav.rope(s.rope).x == 778


def test_walking_on_a_platform_past_a_ladder_top_stays_ground(nav):
    st = SelfTracker(nav)
    s = None
    for i in range(15):
        s = st.update(i * 0.04, me_map=(760 + 5 * i, 13), map_pos=(760 + 5 * i, 13), held={"right"})
    assert s.state == "ground" and s.platform == 65


def test_a_found_hang_holds_until_we_move_and_attacking_doesnt_count(nav):
    st = SelfTracker(nav)
    for i in range(15):
        s = st.update(i * 0.04, me_map=(787.8, 26.4), map_pos=(787.8, 26.4), held={"right"})
    s = st.update(0.7, me_map=(787.8, 26.4), map_pos=(787.8, 26.4), held={"up"})     # a ladder move now: still on it
    assert s.state == "rope"
    s = st.update(0.9, me_map=(787.8, 12.0), map_pos=(787.8, 10.4), held=set())     # climbed out
    assert s.state != "rope" or nav.rope(s.rope).x == 778
    st2 = SelfTracker(nav)                         # holding attack + a walk key next to a rope: frozen by the swing
    for i in range(15):
        s = st2.update(i * 0.04, me_map=(1621, 198), map_pos=(1619.6, 202.1), held={"c", "right"})
    assert s.state == "ground"
