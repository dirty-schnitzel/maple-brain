"""GPU full-screen sprite detector (perception rework, 2026-11-03). Skipped without torch or the map assets."""
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")

from maplebot.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MCW = ROOT / "assets" / "mcw"
FX = Path(__file__).parent / "fixtures"
RAIN = 10001070

pytestmark = pytest.mark.skipif(not (MCW / "maps" / str(RAIN) / "map.json").exists(), reason="needs map 10001070")


@pytest.fixture(scope="module")
def det():
    return GpuSpriteDetector.for_map(RAIN, MCW)


def paste(bg, spr, x, y):
    h, w = spr.shape[:2]
    a = spr[..., 3:4] / 255.0
    bg[y:y + h, x:x + w] = (spr[..., :3] * a + bg[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)


def test_scores_equal_opencv(det):
    frame = cv2.imread(str(FX / "library_grass.jpg"))
    small = cv2.resize(frame[:700], None, fx=det.scale, fy=det.scale, interpolation=cv2.INTER_AREA)
    got = det.scores(small)[0].cpu().numpy()
    _, t, m, _ = det.items[0]
    ts = cv2.resize(t, None, fx=det.scale, fy=det.scale, interpolation=cv2.INTER_AREA)
    ms = (cv2.resize(m * 255, (ts.shape[1], ts.shape[0]), interpolation=cv2.INTER_AREA) > 160).astype(np.uint8)
    ref = cv2.matchTemplate(small, ts, cv2.TM_CCOEFF_NORMED, mask=ms)
    ok = np.isfinite(ref)
    a = got[:ref.shape[0], :ref.shape[1]]
    ok &= a > -1                                          # flat windows: both say "no shape"
    d = np.abs(a[ok] - ref[ok])
    # rounding differs on nearly flat windows (fixture sky, |scores| < 0.25): only where a score could matter
    assert (d < 0.01).mean() > 0.99
    likely = (np.maximum(a[ok], ref[ok]) >= 0.4)
    assert likely.any() and d[likely].max() < 0.01


@pytest.mark.parametrize("mob,flip", [(8, False), (8, True), (10, False), (10, True)])
def test_finds_a_pasted_pig_anywhere_with_pose_and_feet(det, mob, flip):
    """Whole screen: a Pig pasted high up in the trees (no band around our feet) is found, its feet exact."""
    import json
    frame = cv2.imread(str(FX / "library_grass.jpg"))
    before = det.find(frame)
    spr = cv2.imread(str(MCW / f"mobs/{mob}/move_2.png"), cv2.IMREAD_UNCHANGED)
    meta = next(f for f in json.loads((MCW / f"mobs/{mob}/mob.json").read_text())["frames"]["move"]
                if f["file"] == "move_2.png")
    h, w = spr.shape[:2]
    ox, oy = meta["origin"]
    if flip:
        spr, ox = np.ascontiguousarray(spr[:, ::-1]), w - ox
    x, y = 500, 120
    paste(frame, spr, x, y)
    hits = [h_ for h_ in det.find(frame) if all(abs(h_.feet[0] - b.feet[0]) > 10 for b in before)]
    assert len(hits) == 1
    hit = hits[0]
    assert hit.mob_id == mob and hit.pose.anim == "move" and hit.pose.facing == ("right" if flip else "left")
    assert abs(hit.feet[0] - (x + ox)) <= 2 and abs(hit.feet[1] - (y + oy)) <= 2 and hit.score > 0.9


def test_flat_areas_are_not_mobs(det):
    """A plain sky-blue frame: noise over ~zero variance once scored 32 and gave 10k peaks (23 s a frame)."""
    frame = np.full((768, 1366, 3), (235, 170, 90), np.uint8)
    frame += np.random.default_rng(0).integers(0, 2, frame.shape, dtype=np.uint8)
    assert det.find(frame) == []


def test_gpu_band_gives_the_perceiver_only_our_band(det):
    """--gpu: the whole screen is searched once per frame, `find` keeps the CPU detector's contract (the band
    around our feet, excludes)."""
    from maplebot.perception.gpu_sprites import GpuBand
    from maplebot.perception.sprites import SpriteDetector
    frame = cv2.imread(str(FX / "library_grass.jpg"))
    spr = cv2.imread(str(MCW / "mobs/8/move_2.png"), cv2.IMREAD_UNCHANGED)
    paste(frame, spr, 300, 120)                          # up in the trees
    paste(frame, spr, 800, 300 - spr.shape[0] + 5)       # on our ground line (feet 300)
    band = GpuBand(det, SpriteDetector.for_map(RAIN, MCW))
    got = band.find(frame, 300, below=40, above=80)
    assert [b[0][0] for b in got if b[1] == 8] == [800] or [abs(b[0][0] - 800) <= 2 for b in got if b[1] == 8] == [True]
    assert any(abs(h.box[0] - 300) <= 2 for h in band.all_hits)          # the tree Pig is still seen (whole screen)
    x, y, w, h = got[0][0]
    assert band.find(frame, 300, below=40, above=80, exclude=[(x - 5, y - 5, w + 10, h + 10)]) == []


def _pig_scene(det, cover_rows=0):
    """library_grass + a Pig (move_2) at feet (600, 400); the lowest `cover_rows` px of it painted over with a
    flat grass colour (what a foreground object does) -> (frame, feet, visibility map)."""
    import json
    frame = cv2.imread(str(FX / "library_grass.jpg"))
    spr = cv2.imread(str(MCW / "mobs/8/move_2.png"), cv2.IMREAD_UNCHANGED)
    meta = next(f for f in json.loads((MCW / "mobs/8/mob.json").read_text())["frames"]["move"]
                if f["file"] == "move_2.png")
    ox, oy = meta["origin"]
    x, y = 600 - ox, 400 - oy
    paste(frame, spr, x, y)
    vis = np.ones((700, frame.shape[1]), bool)
    if cover_rows:
        h, w = spr.shape[:2]
        frame[y + h - cover_rows:y + h, x - 10:x + w + 10] = (40, 160, 60)
        vis[y + h - cover_rows:y + h, x - 10:x + w + 10] = False
    return frame, (600, 400), vis


def test_visible_only_search_equals_the_plain_one_with_nothing_covered(det):
    frame, (fx, fy), vis = _pig_scene(det)
    plain = det.find_near(frame, [(8, fx, fy)], pad=24)[0]
    ones = det.find_near(frame, [(8, fx, fy)], pad=24, vis=[None])[0]
    assert plain and ones and abs(plain.score - ones.score) < 0.01 and plain.feet == ones.feet


def test_visible_only_search_sees_a_pig_half_in_the_grass(det):
    """The lower half of the Pig painted over (grass in front): the plain search drops, the visible-only one
    (told what is covered) still finds it, feet exact."""
    frame, (fx, fy), vis = _pig_scene(det, cover_rows=22)
    plain = det.find_near(frame, [(8, fx, fy)], pad=24, min_score=-5)[0]
    seen = det.find_near(frame, [(8, fx, fy)], pad=24, vis=[vis])[0]
    assert seen is not None and seen.score > 0.85 and seen.score > plain.score + 0.2
    assert abs(seen.feet[0] - fx) <= 2 and abs(seen.feet[1] - fy) <= 2
