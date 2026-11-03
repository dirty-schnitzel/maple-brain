"""Which map are we on (nav/identify.py): the on-screen minimap vs every map's canvas in assets/mcw.

Fixtures (tests/fixtures/mapid/*.png) are the minimap search area (localize.SEARCH, 330x290 from y 40) of recorded
frames, 3 consecutive saved frames (~0.15-0.3 s apart) per map; the matching runs against all ~300 downloaded
minimaps (`assets update --all`), so look-alikes are in play (East Rocky Mountain I vs IV, Snail Hunting Ground III
vs Hot Sand, Henesys Townstreet's single house that matched anything before the frame check).
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebot.nav.identify import MapIdentifier, frame_contrast
from maplebot.nav.localize import SEARCH

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "fixtures" / "mapid"
MCW = ROOT / "assets" / "mcw"


def frame(name: str) -> np.ndarray:
    """A 1366x768 frame with the fixture crop in its place."""
    f = np.zeros((768, 1366, 3), np.uint8)
    crop = cv2.imread(str(FX / f"{name}.png"))
    x0, y0, x1, y1 = SEARCH
    f[y0:y1, x0:x1] = crop
    return f


@pytest.fixture(scope="module")
def ident():
    i = MapIdentifier.load(MCW)
    if len(i.canvases) < 250:
        pytest.skip("needs every map's minimap: python -m maplebot assets update --all")
    return i


MAPS = [("42_snail3", 42), ("50_split_road_crowd", 50), ("10004040_perion", 10004040),
        ("10004050_east_rocky", 10004050)]


@pytest.mark.parametrize("name,map_id", MAPS)
def test_recognises_the_map_from_three_frames(ident, name, map_id):
    m = ident.identify([frame(f"{name}_{i}") for i in range(3)])
    assert m.map_id == map_id, m
    assert m.score - m.runner_score >= 0.1                 # a clear lead, not a coin toss
    assert m.origin is not None and m.origin[1] == 72      # the canvas sits under the window's title (y 72)


@pytest.mark.parametrize("name,map_id", MAPS)
def test_each_single_frame_is_never_another_map(ident, name, map_id):
    for i in range(3):
        assert ident.identify(frame(f"{name}_{i}")).map_id in (map_id, None)


def test_crowded_minimap_with_markers_against_one_edge(ident):
    """A Split Road with ~30 red player dots, portals against the right edge (that edge's contrast 34 vs ~140)."""
    m = ident.identify(frame("50_split_road_crowd_0"))
    assert m.map_id == 50


def test_minimap_covered_by_the_inventory_is_no_answer(ident):
    m = ident.identify(frame("covered_inventory_0"))
    assert m.map_id is None and m.why


def test_no_minimap_at_all(ident):
    m = ident.identify(np.full((768, 1366, 3), 90, np.uint8))
    assert m.map_id is None and "no minimap window" in m.why


def test_a_covered_frame_among_good_ones_is_skipped(ident):
    shots = [frame("covered_inventory_0"), frame("10004050_east_rocky_0"), frame("10004050_east_rocky_1")]
    assert ident.identify(shots).map_id == 10004050


# ---------------------------------------------------------------- synthetic: frame check and look-alikes
def _window(canvas_bgr, at=(10, 72)):
    """A frame with `canvas_bgr` drawn half-transparent in a bright-bordered window (like the game's minimap)."""
    f = np.full((768, 1366, 3), 120, np.uint8)
    x, y = at
    h, w = canvas_bgr.shape[:2]
    cv2.rectangle(f, (x - 3, y - 30), (x + w + 2, y + h + 6), (235, 235, 235), -1)       # window body + border
    f[y:y + h, x:x + w] = (0.5 * canvas_bgr + 40).astype(np.uint8)
    return f


def _art(seed, h=60, w=140):
    rng = np.random.default_rng(seed)
    img = cv2.resize(rng.integers(0, 255, (h // 6, w // 6, 3), dtype=np.uint8), (w, h), interpolation=cv2.INTER_CUBIC)
    return np.dstack([img, np.full((h, w), 255, np.uint8)])


def test_frame_contrast_peaks_where_the_canvas_sits():
    f = _window(_art(1)[..., :3], at=(20, 72))
    x0, y0, x1, y1 = SEARCH
    fc = frame_contrast(cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY), 140, 60)
    y, x = np.unravel_index(fc.argmax(), fc.shape)
    assert (x + 1 + x0, y + 1 + y0) == (20, 72) and fc.max() > 50


def test_picks_the_right_one_of_two_same_size_maps():
    a, b = _art(1), _art(2)
    ident = MapIdentifier({1: a, 2: b})
    m = ident.identify(_window(b[..., :3]))
    assert m.map_id == 2 and m.runner_up == 1


def test_identical_minimaps_are_refused():
    a = _art(1)
    m = MapIdentifier({1: a, 2: a.copy()}).identify(_window(a[..., :3]))
    assert m.map_id is None and m.why == "two maps look alike"


def test_a_canvas_of_another_size_never_fits():
    """Only canvases whose size matches the window's frame are considered (a small canvas matched some patch of any
    minimap before)."""
    big, small = _art(1), _art(3, 30, 50)
    m = MapIdentifier({1: big, 2: small}).identify(_window(big[..., :3]))
    assert m.map_id == 1 and all(k != 2 for _, k in m.fits)
