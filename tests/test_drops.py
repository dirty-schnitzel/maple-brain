"""Loot by sight (perception/drops.py): items lying on the ground bob up and down in place (the user: 'items are
shimmering, floating and slightly moving vertically'); nothing else on the ground line does that."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.perception.drops import DropSpotter

FIX = Path(__file__).parent / "fixtures" / "drops"
FEET = 579


def replay(name):
    """Feed a recorded stretch (the band around our floor, every 3rd live frame) through a fresh DropSpotter."""
    d = FIX / name
    seq = json.loads((d / "seq.json").read_text(encoding="utf-8"))
    y0, y1 = seq["rows"]
    sp, every = DropSpotter(), []
    for fr in seq["frames"]:
        f = np.zeros((768, 1366, 3), np.uint8)
        f[y0:y1] = cv2.imread(str(d / fr["file"]))
        rep = sp.update(f, fr["t"], fr["me"][1], fr["me"][0])
        every.append([b for b, _ in rep])
    return every, seq


def centre(b):
    return b[0] + b[2] / 2


def test_drops_on_a_crowded_map_are_found():
    """pkg_others2m 29.5-33.5 s, map 50: spores, a Blue Snail Shell and coins we never picked up lie left of us."""
    every, _ = replay("map50_drops")
    items = [186, 321, 400, 426, 525]         # last frame: spore, shell, coin, spore, a thin stick (centres)
    last = every[-1]
    assert len(last) >= 3
    for b in last:
        assert min(abs(centre(b) - x) for x in items) < 15, b
        assert 540 <= b[1] + b[3] <= FEET + 4          # lying on our floor


@pytest.mark.parametrize("name", ["map50_drops", "map50_crowd_none", "map42_snails_none", "map50_own_axe_none"])
def test_no_drop_is_ever_reported_on_a_character_or_a_mob(name):
    """pkg_human5m 242-246 s: 7 players, Shrooms, swings, no drops. pkg_decisive1 30-34 s: snails, flowers in the
    wind. pkg_sight1 130 s: standing still facing left, our own axe sticks out 28 px and bobs with our breathing -
    it was 'a drop at dx -28' (walked into a step at it for 5 s, many fake pickups). Characters stand over their name
    tags; we are at me."""
    every, seq = replay(name)
    for boxes, fr in zip(every, seq["frames"]):
        for b in boxes:
            assert abs(centre(b) - fr["me"][0]) > 45, (fr["file"], b)          # not on us (nor our weapon)
    if name.endswith("_none"):
        assert all(not boxes for boxes in every)


def test_drops_are_followed_while_the_camera_moves():
    """The camera slides with us; a remembered drop's box moves with the scenery, it isn't lost or doubled."""
    every, _ = replay("map50_drops")
    counts = [len(b) for b in every[12:]]      # (from ~2 s in: each needs a few recorded frames to be confirmed)
    assert min(counts) >= 2 and max(counts) <= 5


# ---------------------------------------------------------------- synthetic: what counts as a drop
def scene(seed=0):
    rng = np.random.default_rng(seed)
    bg = rng.integers(40, 120, (768, 1366, 3), dtype=np.uint8)
    return cv2.GaussianBlur(bg, (0, 0), 3)                    # textured but smooth, like painted scenery


def item():
    rng = np.random.default_rng(7)
    it = rng.integers(0, 255, (24, 24, 3), dtype=np.uint8)
    it[:2], it[-2:], it[:, :2], it[:, -2:] = 0, 0, 0, 0       # a dark outline, like item icons
    return it


def put(frame, it, x, y):
    f = frame.copy()
    f[y:y + it.shape[0], x:x + it.shape[1]] = it
    return f


def feed(positions, dt=0.05):
    """An item at (x, y) per frame on a fixed background; returns the last report."""
    sp, bg, it, rep = DropSpotter(), scene(), item(), []
    for i, (x, y) in enumerate(positions):
        rep = sp.update(put(bg, it, x, y), i * dt, FEET, me_x=200)
    return rep


def bob(n=30, x=700):
    return [(x, FEET - 26 + round(3 * np.sin(i * 0.6))) for i in range(n)]


def test_an_item_bobbing_in_place_is_a_drop():
    rep = feed(bob())
    assert len(rep) == 1 and abs(centre(rep[0][0]) - 712) <= 2


def test_something_sliding_sideways_is_not_a_drop():
    assert feed([(600 + 3 * i, FEET - 26) for i in range(30)]) == []


def test_something_perfectly_still_is_scenery_not_a_drop():
    assert feed([(700, FEET - 26)] * 30) == []


def test_bobbing_high_above_our_floor_is_not_a_drop():
    """Someone climbing a rope moves only vertically too (pkg_others2m 34.4 s): drops lie on the ground."""
    assert feed([(x, y - 45) for x, y in bob()]) == []


def test_a_drop_picked_up_is_forgotten():
    sp, bg, it = DropSpotter(), scene(), item()
    t = 0.0
    for x, y in bob():
        sp.update(put(bg, it, x, y), t, FEET, me_x=200)
        t += 0.05
    assert sp.update(bg, t, FEET, me_x=200)                   # just gone: still remembered a moment
    for _ in range(25):
        t += 0.05
        rep = sp.update(bg, t, FEET, me_x=200)
    assert rep == []


def test_a_drop_behind_our_own_body_is_not_reported_but_not_forgotten():
    """Standing on it, our body covers it: it can't be confirmed, but it isn't 'gone' either."""
    sp, bg, it = DropSpotter(), scene(), item()
    t = 0.0
    for x, y in bob():
        sp.update(put(bg, it, x, y), t, FEET, me_x=200)
        t += 0.05
    for _ in range(25):                                       # we stand on it (me_x over it), it's hidden
        sp.update(bg, t, FEET, me_x=712)
        t += 0.05
    assert len(sp.drops) == 1


def test_something_bobbing_below_our_floor_is_not_a_drop():
    """pkg_sight3: megaphone chat lines scrolling up under the ground line looked like bobbing items."""
    assert feed([(x, y + 40) for x, y in bob()]) == []
