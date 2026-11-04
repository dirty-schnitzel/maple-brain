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

from maplebot.nav.identify import NAME_FONT, MapIdentifier, frame_contrast, name_scores
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


# ---------------------------------------------------------------- look-alikes told apart by the name
def test_line1_area1_is_told_apart_by_its_name(ident):
    """Line 1 <Area 1> / <Area 2> / Line 2 <Area 1>: minimaps 0.89 / 0.87 / 0.85 - the name above the canvas decides
    (frames from runs/l1a1_trk2, JPEG)."""
    shots = [frame(f"10003061_line1_area1_{i}") for i in range(3)]
    m = ident.identify(shots)
    assert m.map_id == 10003061, m
    assert m.why == "told apart by the name"
    sc = name_scores(shots[0], m.origin, {k: ident.names[k] for k in (10003061, 10003063, 10003066)})
    assert sc[10003061] - max(sc[10003063], sc[10003066]) >= 0.15


def _named_window(canvas_bgr, name, at=(10, 72)):
    """_window with the map's name printed white on a darker strip above the canvas (like the game's title)."""
    from PIL import Image, ImageDraw, ImageFont
    f = _window(canvas_bgr, at)
    x, y = at
    f[y - 30:y - 6, x:x + 200] = 150
    im = Image.fromarray(f[..., ::-1].copy())
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((x + 40, y - 26), name, fill=(255, 255, 255), font=ImageFont.truetype(str(NAME_FONT), 12))
    return np.ascontiguousarray(np.array(im)[..., ::-1])


@pytest.mark.skipif(not NAME_FONT.exists(), reason="needs Arial Bold")
@pytest.mark.parametrize("shown", [1, 2])
def test_identical_minimaps_with_different_names_pick_the_named_one(shown):
    a = _art(1)
    names = {1: "Line 1 <Area 1>", 2: "Line 1 <Area 2>"}
    m = MapIdentifier({1: a, 2: a.copy()}, names=names).identify(_named_window(a[..., :3], names[shown]))
    assert m.map_id == shown and m.why == "told apart by the name"


def test_identical_minimaps_with_the_same_name_are_still_refused():
    a = _art(1)
    names = {1: "Mushroom Town", 2: "Mushroom Town"}
    m = MapIdentifier({1: a, 2: a.copy()}, names=names).identify(_named_window(a[..., :3], "Mushroom Town"))
    assert m.map_id is None and m.why == "two maps look alike"
