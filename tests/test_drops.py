"""Loot by sight (perception/drops.py): items lying on the ground bob up and down in place (the user: 'items are
shimmering, floating and slightly moving vertically'); nothing else on the ground line does that."""
import cv2
import numpy as np

from maplebrain.perception.drops import DropSpotter

FEET = 579


def centre(b):
    return b[0] + b[2] / 2


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
