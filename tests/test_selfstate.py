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
