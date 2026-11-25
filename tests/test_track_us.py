"""maplebrain/track/us.py (PLAN-tracker step 4b): our feet from our tag (or a piece of it in the tag list), placed by
the graph's one rule, and every stuck case nav/selfstate.py's docstring lists (the same cases as test_selfstate.py,
on Line 1 <Area 1>'s real graph: our feet = the tag's top - 1, SelfState's y = the tag's top)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from maplebrain.config import Track
from maplebrain.track.graph import Graph
from maplebrain.track.us import Us

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "mcw"
TAG = (100, 300, 74, 17)                 # our tag on the screen: centre x 137, top 300 -> feet (137, 299) + camera


@pytest.fixture(scope="module")
def graph():
    return Graph.for_map(10003061, ASSETS, edges=False)     # Line 1 <Area 1>: hub 273 at y 198, ladder 778, cart 275


def at(t, x, y, tags=(), tag=TAG):
    """A frame whose camera puts our feet at map (x, y) (the tag's top - 1)."""
    C = (x - (TAG[0] + TAG[2] / 2), y - (TAG[1] - 1))
    return SimpleNamespace(t=t, scene_cam=C, tag=tag, tags=list(tags), slots={}, hp=None, mp=None, exp_points=None)


def run(us, frames, held=()):
    """frames = [(t, x, y)] with `held` keys down from the first -> the last state."""
    keys = [{"t": 0.0, "key": k, "down": True} for k in held]
    for i, (t, x, y) in enumerate(frames):
        us.update(at(t, x, y), keys if i == 0 else None)
    return us.state()


def keys_now(us, held):
    """Change the keys held to exactly `held` (as events)."""
    ev = [{"t": 0, "key": k, "down": False} for k in us.held - set(held)]
    ev += [{"t": 0, "key": k, "down": True} for k in set(held) - us.held]
    return ev


def test_standing_on_the_hub(graph):
    s = run(Us(graph), [(i * 0.04, 1000 + i * 5, 198.5) for i in range(5)])
    assert s["place"] == "stand" and s["node"] == 273 and s["src"] == "tag" and s["seen"]
    assert s["vx"] == pytest.approx(125, abs=1) and s["act"] == "walk"


def test_on_a_rope_and_in_the_air(graph):
    s = run(Us(graph), [(i * 0.04, 1269, -1 - i * 5) for i in range(5)])          # climbing rope x 1267
    assert s["place"] == "rope" and graph.rope_x[-1 - s["node"]] == 1267 and s["act"] == "climb"
    s = run(Us(graph), [(i * 0.04, 1000 + 5 * i, 149 + 3 * i * i) for i in range(5)])   # jumping
    assert s["place"] == "air" and s["act"] == "air"


def test_tag_lost_keeps_the_last_place_unseen(graph):
    us = Us(graph)
    run(us, [(0.0, 1004, 197.5)])
    us.update(at(0.04, 1004, 197.5, tag=None))
    s = us.state()
    assert not s["seen"] and s["cover"] == "unseen" and s["place"] == "stand" and s["x"] == 1004


def test_hanging_still_a_few_px_off_a_ladder_is_on_it(graph):
    """runs/v2 08:51: ladder 778 (15..176), read at x 787.7 -> "air" 21 s."""
    s = run(Us(graph), [(i * 0.04, 787.7, 89.3) for i in range(12)])
    assert s["place"] == "rope" and graph.rope_x[-1 - s["node"]] == 778


def test_a_jump_apex_next_to_a_ladder_stays_air(graph):
    us = Us(graph)
    for i, y in enumerate([119, 99, 91, 89, 91, 99, 119]):    # up and down again: never still for 0.25 s
        us.update(at(i * 0.04, 790, y))
        assert us.state()["place"] == "air", (i, y)


def test_walk_key_held_without_moving_next_to_a_ladder_is_hanging_on_it(graph):
    """runs/v2 09:21: under the top of ladder 778 (SelfState read it as standing on 65 via the minimap's floor; the
    exact tag there is 12 px under the floor), and at the floor's own height: walking does nothing -> on the ladder."""
    s = run(Us(graph), [(i * 0.04, 787.8, 25.4) for i in range(15)], held=("right",))
    assert s["place"] == "rope" and graph.rope_x[-1 - s["node"]] == 778
    us = Us(graph)
    us.update(at(0.0, 787.8, 13.0), [{"t": 0, "key": "right", "down": True}])
    assert us.state()["place"] == "stand"                    # not yet: 0.4 s of a walk key first
    for i in range(1, 15):
        us.update(at(i * 0.04, 787.8, 13.0))
    s = us.state()
    assert s["place"] == "rope" and graph.rope_x[-1 - s["node"]] == 778


def test_walking_on_a_platform_past_a_ladder_top_stays_ground(graph):
    s = run(Us(graph), [(i * 0.04, 760 + 5 * i, 12) for i in range(15)], held=("right",))
    assert s["place"] == "stand" and s["node"] == 65


def test_a_found_hang_holds_until_we_move_and_attacking_doesnt_count(graph):
    us = Us(graph)
    run(us, [(i * 0.04, 787.8, 13.0) for i in range(15)], held=("right",))
    assert us.state()["place"] == "rope"
    us.update(at(0.7, 787.8, 13.0), keys_now(us, {"up"}))     # a ladder move now: still on it
    assert us.state()["place"] == "rope"
    us.update(at(0.9, 800.0, 13.0), keys_now(us, set()))      # moved off it
    assert us.state()["place"] == "stand" and us.place.hang is None
    s = run(Us(graph), [(i * 0.04, 1621, 197) for i in range(15)], held=("c", "right"))   # attack + a walk key next
    assert s["place"] == "stand"                              # to a rope: frozen by the swing, no hang


def test_a_walk_key_right_after_the_attack_key_is_no_hang(graph):
    """runs/v2 10:44 t=792: the swing's tail holds us still, next to a ladder."""
    us = Us(graph)
    t = 0.0
    for i in range(10):
        us.update(at(t, 2084, 72), keys_now(us, {"c"}))
        t += 0.04
    for i in range(16):                                       # key up, 0.64 s of a walk key without moving
        us.update(at(t, 2084, 72), keys_now(us, {"left"}))
        t += 0.04
    s = us.state()
    assert s["place"] == "stand" and s["node"] == 79
    for i in range(25):                                       # still no move long after the swing: a real hang
        us.update(at(t, 2084, 72))
        t += 0.04
    assert us.state()["place"] == "rope"


def test_climbing_a_ladder_whose_tag_reads_10_px_off_stays_on_it(graph):
    """runs/v2 19:15: ladder x 778, the tag at x 788 - rope / air flips let go of `up`."""
    us = Us(graph)
    t, y = 0.0, 149.0
    for i in range(10):
        us.update(at(t, 788, y))
        t += 0.04
    assert us.state()["place"] == "rope"
    us.update(at(t, 788, y), keys_now(us, {"up"}))
    while y > 40:
        y -= 5
        t += 0.04
        us.update(at(t, 788, y))
        assert us.state()["place"] == "rope", y


def test_under_a_ladder_top_is_not_the_floor(graph):
    """runs/v2 19:13: y 26 (tag), the floor at 13: 12 px under it is not standing on it."""
    s = run(Us(graph), [(i * 0.04, 788, 25.4) for i in range(12)], held=("c",))
    assert s["place"] == "rope"


def test_leaping_off_a_ladder_leaves_it(graph):
    us = Us(graph)
    for i in range(10):
        us.update(at(i * 0.04, 788, 99))
    assert us.state()["place"] == "rope"
    us.update(at(0.4, 788, 99), [{"t": 0, "key": "left", "down": True}])
    for i in range(1, 10):
        us.update(at(0.4 + i * 0.04, 788 + 8 * i, 99 - i))
    assert us.state()["place"] == "air"


def test_standing_just_past_a_platforms_end_is_on_it(graph):
    """runs/v2 20261106_162027_12 t=798: dropped onto cart 275 (right end 382, y 260), read x 388 y 266 (tag)."""
    us = Us(graph)
    us.update(at(0.0, 388.1, 265.2))
    assert us.state()["place"] == "air"                       # not yet: could be passing through
    for i in range(1, 12):
        us.update(at(i * 0.05, 388.1, 265.2))
    s = us.state()
    assert s["place"] == "stand" and s["node"] == 275 and s["x"] == 382
    for i in range(12, 40):                                   # and it stays so
        us.update(at(i * 0.05, 388.1, 265.2))
        assert us.state()["place"] == "stand" and us.state()["node"] == 275


def test_falling_past_a_platforms_end_stays_air(graph):
    us = Us(graph)
    for i in range(10):
        us.update(at(i * 0.05, 388, 239 + i * 8))
        assert us.state()["place"] == "air"


def test_leaving_a_platforms_end_lets_go_of_it(graph):
    us = Us(graph)
    for i in range(12):
        us.update(at(i * 0.05, 388.1, 265.2))
    us.update(at(0.65, 396, 281))
    assert us.state()["place"] == "air" and us.place.ledge is None


def test_our_tag_from_the_list_by_its_width_and_the_edge_that_kept_its_place(graph):
    """Our tag reader missed it: a list box of our width, or a piece of it (front scenery over part of it: "Jenk",
    "sJob") by the edge that kept its place - never another tag at our place."""
    us = Us(graph)
    us.update(at(0.0, 1000, 197.5))                           # exact: our tag 74 x 17 at screen (100, 300)
    f = at(0.02, 1000, 197.5, tags=[(102, 300, 74, 17)], tag=None)
    us.update(f)
    assert us.tag.src == "list" and us.box[:4] == (102, 300, 74, 17) and us.state()["x"] == 1002
    f = at(0.04, 1000, 197.5, tags=[(103, 300, 38, 17)], tag=None)              # the left piece: our left edge
    us.update(f)
    assert us.tag.src == "list" and us.box[:2] == (103, 300) and us.state()["x"] == 1003
    f = at(0.06, 1000, 197.5, tags=[(141, 300, 37, 17)], tag=None)              # the right piece: our right edge
    us.update(f)
    assert us.tag.src == "list" and us.box[:2] == (104, 300) and us.state()["x"] == 1004
    us = Us(graph)
    us.update(at(0.0, 1000, 197.5))
    us.update(at(0.02, 1000, 197.5, tags=[(130, 300, 65, 17)], tag=None))       # another player standing there
    assert us.box is None and not us.state()["seen"]
    us.update(at(2.1, 1000, 197.5, tags=[(100, 300, 74, 17)], tag=None))         # 2 s after our own tag: no more
    assert us.box is None


def test_facing_is_the_last_walk_key(graph):
    us = Us(graph)
    us.update(at(0.0, 1000, 197.5), [{"t": 0, "key": "left", "down": True}, {"t": 0, "key": "left", "down": False}])
    assert us.state()["facing"] == -1
    us.update(at(0.1, 1000, 197.5), [{"t": 0.05, "key": "q", "down": True}])
    assert us.state()["facing"] == -1
    us.update(at(0.2, 1000, 197.5), [{"t": 0.15, "key": "right", "down": True}])
    assert us.state()["facing"] == 1


def test_a_blind_frame_changes_nothing(graph):
    us = Us(graph)
    run(us, [(i * 0.04, 1000, 197.5) for i in range(3)])
    f = at(0.2, 900, 100)
    f.scene_cam = None
    us.update(f)
    s = us.state()
    assert s["cover"] == "blind" and not s["seen"] and s["x"] == 1000 and s["place"] == "stand"


def test_hp_mp_exp_held_while_unreadable(graph):
    us = Us(graph, Track())
    f = at(0.0, 1000, 197.5)
    f.hp, f.mp, f.exp_points = (500, 600), (100, 120), 1234
    us.update(f)
    us.update(at(0.1, 1000, 197.5))
    s = us.state()
    assert s["hp"] == [500, 600] and s["mp"] == [100, 120] and s["exp"] == 1234
