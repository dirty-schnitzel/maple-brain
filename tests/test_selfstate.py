from pathlib import Path

import pytest

from maplebrain.nav.navmap import NavMap
from maplebrain.nav.selfstate import SelfTracker

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


def test_a_walk_key_right_after_the_attack_key_is_no_hang(nav):
    st = SelfTracker(nav)                          # runs/v2 10:44 t=792: the swing's tail holds us still, next to a ladder
    t = 0.0
    for i in range(10):
        st.update(t, me_map=(2084, 73), map_pos=(2083.9, 74.2), held={"c"})
        t += 0.04
    for i in range(16):                            # key up, 0.64 s of a walk key without moving
        s = st.update(t, me_map=(2084, 73), map_pos=(2083.9, 74.2), held={"left"})
        t += 0.04
    assert s.state == "ground" and s.platform == 79
    for i in range(25):                            # still no move long after the swing: that's a real hang
        s = st.update(t, me_map=(2084, 73), map_pos=(2083.9, 74.2), held={"left"})
        t += 0.04
    assert s.state == "rope"


def test_climbing_a_ladder_whose_tag_reads_10_px_off_stays_on_it(nav):
    st = SelfTracker(nav)                          # ladder x 778, top 15: runs/v2 19:15, rope / air flips, `up` let go
    t, y = 0.0, 150.0
    for i in range(10):
        s = st.update(t, me_map=(788, y), map_pos=(787.7, y), held=set())
        t += 0.04
    assert s.state == "rope"
    while y > 40:
        y -= 5
        s = st.update(t, me_map=(788, y), map_pos=(787.7, y), held={"up"})
        t += 0.04
        assert s.state == "rope", y


def test_under_a_ladder_top_is_not_the_floor(nav):
    st = SelfTracker(nav)                          # runs/v2 19:13: y 26, floor 13: tag and minimap agree
    for i in range(12):
        s = st.update(i * 0.04, me_map=(788, 26.4), map_pos=(788, 26.4), held={"c"})
    assert s.state == "rope" and s.platform is None
    st = SelfTracker(nav)                          # on the floor there: the minimap reads 10.4, off camera or not
    for i in range(12):
        s = st.update(i * 0.04, me_map=(788, 26.4), map_pos=(788, 10.4), held={"c"})
    assert s.state == "ground" and s.platform == 65


def test_leaping_off_a_ladder_leaves_it(nav):
    st = SelfTracker(nav)
    t = 0.0
    for i in range(10):
        st.update(t, me_map=(788, 100), map_pos=(787.7, 100), held=set())
        t += 0.04
    for i in range(10):
        s = st.update(t, me_map=(788 + 8 * i, 100 - i), map_pos=(787.7, 100), held={"left"})
        t += 0.04
    assert s.state == "air"


def test_standing_just_past_a_platforms_end_is_on_it(nav):
    """runs/v2 20261106_162027_12 t=798: dropped onto cart 275 (right end 382), read x 388 y 266."""
    st = SelfTracker(nav)
    s = st.update(0.0, me_map=(388.1, 266.2), map_pos=(388.1, 266.2))
    assert s.state == "air"                          # not yet: could be passing through
    for i in range(1, 12):
        s = st.update(i * 0.05, me_map=(388.1, 266.2), map_pos=(388.1, 266.2))
    assert s.state == "ground" and s.platform == 275
    assert (s.x, s.y) == (382, 260)
    for i in range(12, 40):                          # and it stays so: no flipping back to air
        s = st.update(i * 0.05, me_map=(388.1, 266.2), map_pos=(388.1, 266.2))
        assert s.state == "ground" and s.platform == 275


def test_falling_past_a_platforms_end_stays_air(nav):
    st = SelfTracker(nav)
    for i in range(10):
        s = st.update(i * 0.05, me_map=(388, 240 + i * 8), map_pos=(388, 266))
        assert s.state == "air"


def test_leaving_a_platforms_end_lets_go_of_it(nav):
    st = SelfTracker(nav)
    for i in range(12):
        st.update(i * 0.05, me_map=(388.1, 266.2), map_pos=(388.1, 266.2))
    s = st.update(0.65, me_map=(396, 282), map_pos=(388, 282))
    assert s.state == "air" and st.ledge is None
