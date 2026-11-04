"""Mob detection from game sprites (assets/mcw, map 42 = Snail Hunting Ground III)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebot.config import Config
from maplebot.perception.perceiver import Perceiver
from maplebot.perception.sprites import SpriteDetector, _cover, feet_of, load_mob, signature_hues

ROOT = Path(__file__).resolve().parents[1]
MCW = ROOT / "assets" / "mcw"
FX = Path(__file__).parent / "fixtures"
SNAIL, BLUE, RED = 2, 3, 5

pytestmark = pytest.mark.skipif(not (MCW / "maps" / "42" / "map.json").exists(),
                                reason="run `python -m maplebot assets update 42` first")


@pytest.fixture(scope="module")
def det():
    return SpriteDetector.for_map(42, MCW, min_score=Config().perception.sprite_score)


def img(name):
    f = cv2.imread(str(FX / name))
    assert f is not None, name
    return f


def near(box, xy, tol=4):
    return abs(box[0] - xy[0]) <= tol and abs(box[1] - xy[1]) <= tol


def test_map_42_has_the_three_snails(det):
    assert sorted(m.mob_id for m in det.mobs) == [SNAIL, BLUE, RED]


def test_signature_colour_is_the_shell():
    hues = {m: signature_hues([cv2.imread(str(MCW / f"mobs/{m}/stand_0.png"), cv2.IMREAD_UNCHANGED)])
            for m in (SNAIL, BLUE, RED)}
    assert hues[SNAIL] == [(80, 94)] and hues[BLUE] == [(100, 109)] and hues[RED] == [(165, 174)]


def test_load_mob_puts_the_stand_pair_first_for_the_quick_check():
    m = load_mob(MCW / "mobs" / str(SNAIL))
    stand = cv2.imread(str(MCW / f"mobs/{SNAIL}/stand_0.png"), cv2.IMREAD_UNCHANGED)
    assert np.array_equal(m.frames[0][0], stand[..., :3]) and np.array_equal(m.frames[1][0], stand[:, ::-1, :3])
    assert 150 < m.sig_px < 300


@pytest.mark.parametrize("mob", [SNAIL, BLUE, RED])
@pytest.mark.parametrize("flip", [False, True])
def test_finds_a_pasted_sprite_on_real_grass(det, mob, flip):
    frame = img("library_grass.jpg")
    feet = 300                                       # a band of plain grass/trees without snails
    bg = frame.copy()
    spr = cv2.imread(str(MCW / f"mobs/{mob}/move_1.png"), cv2.IMREAD_UNCHANGED)
    spr = spr[:, ::-1] if flip else spr
    h, w = spr.shape[:2]
    x, y = 600, feet - h + 5
    a = spr[..., 3:4] / 255.0
    bg[y:y + h, x:x + w] = (spr[..., :3] * a + bg[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)
    before = det.find(frame, feet, below=40)
    hits = [d for d in det.find(bg, feet, below=40) if d not in before]
    assert len(hits) == 1
    box, mid, score = hits[0]
    assert mid == mob and near(box, (x, y), tol=3) and score > 0.8


@pytest.mark.parametrize("flip", [False, True])
def test_find_reports_the_pose_and_the_exact_feet(det, flip):
    """Perception rework (2026-11-03): which frame matched, which way it faces, and its feet from the client's
    origin (mob.json 'frames'), mirrored with the sprite."""
    import json
    frame = img("library_grass.jpg")
    feet = 300
    bg = frame.copy()
    spr = cv2.imread(str(MCW / f"mobs/{RED}/move_1.png"), cv2.IMREAD_UNCHANGED)
    meta = next(f for f in json.loads((MCW / f"mobs/{RED}/mob.json").read_text())["frames"]["move"]
                if f["file"] == "move_1.png")
    h, w = spr.shape[:2]
    ox, oy = meta["origin"]
    if flip:
        spr, ox = spr[:, ::-1], w - ox
    x, y = 600, feet - h + 5
    a = spr[..., 3:4] / 255.0
    bg[y:y + h, x:x + w] = (spr[..., :3] * a + bg[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)
    before = [d[0] for d in det.find(frame, feet, below=40)]
    hits = [d for d in det.find(bg, feet, below=40, with_pose=True) if d[0] not in before]
    assert len(hits) == 1
    box, mid, score, pose = hits[0]
    assert mid == RED and pose.facing == ("right" if flip else "left")
    fx, fy = feet_of(box, pose)
    assert abs(fx - (x + ox)) <= 3 and abs(fy - (y + oy)) <= 3


def test_finds_six_mobs_nobody_has_hit(det):
    """pkg_sweep1 frame 714: five Snails + one Blue Snail standing around, no HP bars (old blind spot)."""
    found = det.find(img("sprites_six_unhit.jpg"), 579, below=80)
    want = [((892, 554), SNAIL), ((928, 554), SNAIL), ((1302, 554), SNAIL), ((1174, 554), SNAIL),
            ((750, 552), SNAIL), ((1206, 544), BLUE)]
    assert len(found) == len(want)
    for xy, mob in want:
        assert any(near(b, xy) and m == mob for b, m, _ in found), (xy, mob)


def test_grass_that_once_fooled_the_library_is_not_a_mob(det):
    """library_grass.jpg: only its three real snails, nothing on the grass."""
    found = [d for f in range(100, 740, 60) for d in det.find(img("library_grass.jpg"), f)]
    assert sorted((b[0] // 10, m) for b, m, _ in found) == [(14, BLUE), (33, BLUE), (119, SNAIL)]


def test_skips_mobs_already_known_by_their_hp_bar(det):
    bar_box = (1199, 536, 50, 50)                   # hud.bar_mob_box shape over the Blue Snail at (1206, 544)
    found = det.find(img("sprites_six_unhit.jpg"), 579, below=80, exclude=[bar_box])
    assert not any(m == BLUE for _, m, _ in found)
    assert len(found) == 5                          # the Snail touching it (1174..1210) stays


def test_perceiver_adds_sprite_mobs_to_known_mobs(det):
    frame = img("sprites_six_unhit.jpg")
    p = Perceiver(Config(), np.load(FX / "self_tag_gray.npy"), det)
    obs = p.observe(frame, 0.0)
    assert obs.me is not None
    assert len(obs.sprite_mobs) == 6
    assert all(s[0] in obs.known_mobs for s in obs.sprite_mobs)
    plain = Perceiver(Config(), np.load(FX / "self_tag_gray.npy")).observe(frame, 0.0)
    assert plain.sprite_mobs == [] and len(plain.known_mobs) < len(obs.known_mobs)


def test_after_a_knockback_the_nearest_real_snail_is_the_target_not_our_body(det):
    frame = img("sprites_six_unhit.jpg")
    p = Perceiver(Config(), np.load(FX / "self_tag_gray.npy"), det)
    me = p.observe(frame, 0.0).me
    p.track(frame, (int(me[0]) - 20, int(me[1]) - 50, 40, 45))
    obs = p.observe(frame, 0.05)
    assert obs.target_src == "sprite" and near(obs.target, (750 - 4, 552 - 4), tol=4)


def test_target_is_re_found_by_its_sprite_each_frame(det):
    frame = img("sprites_six_unhit.jpg")
    p = Perceiver(Config(), np.load(FX / "self_tag_gray.npy"), det)
    p.observe(frame, 0.0)
    p.track(frame, (1300, 552, 40, 26))                 # a bit off the Snail at (1302, 554)
    obs = p.observe(frame, 0.05)
    assert obs.target_src == "sprite" and near(obs.target, (1302 - 4, 554 - 4), tol=4)


def test_tracker_sliding_onto_our_own_body_is_not_a_sighting(det):
    """pkg_sprites4 44.9s: knocked back, the template tracker latched onto JenkinsJob; 7.5 s of swinging at air."""
    class NoSprites:                                    # nothing near us that a sprite explains
        def find(self, *a, **k):
            return []
    frame = img("sprites_six_unhit.jpg")
    p = Perceiver(Config(), np.load(FX / "self_tag_gray.npy"), NoSprites())
    me = p.observe(frame, 0.0).me
    body = (int(me[0]) - 20, int(me[1]) - 50, 40, 45)
    p.track(frame, body)
    obs = p.observe(frame, 0.05)
    assert obs.target is None


def test_tracker_alone_does_not_keep_a_target_alive_for_long():
    """pkg_sprites7b: the snail was gone, the template tracker drifted onto flowers and kept 'seeing' it."""
    class NoSprites:
        def find(self, *a, **k):
            return []
    frame = img("library_grass.jpg")
    p = Perceiver(Config(), np.load(FX / "self_tag_gray.npy"), NoSprites())
    o = p.observe(frame, 0.0)
    if o.me is None:
        pytest.skip("fixture has no own tag")
    box = (int(o.me[0]) - 150, int(o.me[1]) - 30, 40, 30)                  # some scenery next to us
    p.track(frame, box)
    assert p.observe(frame, 0.3).target is not None                        # bridges a short gap
    assert p.observe(frame, 1.0).target is None                            # but not for long


# ---------------------------------------------------------------- death animation (another player's kill)
def test_death_animation_is_recognized_where_the_target_was():
    """pkg_human5m 242 s: another player killed our Shroom as our first hit landed (frame 004164: dying;
    004152: alive). Crops of y 470-610, x 600-1100: the Shroom stood at x 833-600, our feet at 579-470."""
    import cv2
    from maplebot.config import Config
    det = SpriteDetector.for_map(50, ROOT / "assets" / "mcw", min_score=0.65)
    thr = Config().perception.die_score
    dying = cv2.imread(str(FX / "dying_shroom.png"))
    live = cv2.imread(str(FX / "live_shroom.png"))
    assert det.dying(dying, 233, 109, mob_id=4) >= thr
    assert det.dying(live, 233, 109, mob_id=4) < thr


@pytest.mark.skipif(not (MCW / "maps" / "10004040" / "map.json").exists(), reason="needs map 10004040 (Perion)")
def test_stumps_coloured_like_perions_rock_are_found_by_shape():
    """perion1/2: Stumps share the brown of Perion's rock - the colour blob was the whole floor, 0.1 mobs found per
    frame, the bot walked past them and got hit. Camouflaged mobs are scanned by shape (every distinct pose)."""
    d = SpriteDetector.for_map(10004040, MCW, min_score=Config().perception.sprite_score, camo_frames=1)
    stump = next(m for m in d.mobs if m.name == "Stump")
    frame = img("perion_stumps.png")                               # perion2 66.7 s, feet 571
    y0 = 571 - 75
    band = cv2.resize(frame[y0:571 + 8], None, fx=d.scale, fy=d.scale, interpolation=cv2.INTER_AREA)
    assert d.camouflaged(cv2.cvtColor(band, cv2.COLOR_BGR2HSV), stump)
    xs = sorted(b[0] for b, _, _ in d.find(frame, 571, below=80))
    assert len(xs) == 2 and abs(xs[0] - 748) <= 6 and abs(xs[1] - 1216) <= 6   # both Stumps, nothing else


def test_snails_on_grass_are_not_camouflaged(det):
    frame = img("self_normal.png")                                   # map 42, snails on grass
    hsv = cv2.cvtColor(cv2.resize(frame[480:600], None, fx=0.5, fy=0.5), cv2.COLOR_BGR2HSV)
    assert not any(det.camouflaged(hsv, m) for m in det.mobs)


@pytest.mark.skipif(not (MCW / "maps" / "10004040" / "map.json").exists(), reason="needs map 10004040 (Perion)")
def test_a_camouflaged_mob_stays_scanned_on_a_slope_with_sky_in_the_band():
    """perion4 9-12 s: standing on the slope, half the band is sky - the Stump share fell below the cut and the
    Stump down the slope was never seen; the bot stood 'waiting for a spawn'. Once camouflaged, always scanned."""
    d = SpriteDetector.for_map(10004040, MCW, min_score=Config().perception.sprite_score, camo_frames=1)
    d.find(img("perion_stumps.png"), 571, below=80)                         # flat rock: Stumps are camouflaged
    found = d.find(img("perion_slope_stump.jpg"), 511, below=80)            # perion4 11.2 s, feet 511 on the slope
    assert [(b[0] // 10, m) for b, m, _ in found] == [(42, 11)]


def test_one_odd_frame_does_not_make_a_mob_camouflaged(det):
    blue = next(m for m in det.mobs if m.mob_id == BLUE)
    sky = np.zeros((40, 300, 3), np.uint8)
    sky[:] = (255, 140, 40)                                                   # BGR sky blue: all Blue Snail hue
    hsv = cv2.cvtColor(sky, cv2.COLOR_BGR2HSV)
    fresh = SpriteDetector([blue])
    assert not fresh.camouflaged(hsv, blue)


# ---------------------------------------------------------------- the quick check covers every pose (Pigs)
PIG_FEET = 519      # Rain-Forest East of Henesys (10001070), serve 2026-11-02 00:58, our feet on these frames


@pytest.fixture(scope="module")
def pigs():
    return SpriteDetector.for_map(10001070, MCW, min_score=Config().perception.sprite_score)


@pytest.mark.parametrize("name", ["ribbon_pig_stand2.jpg", "ribbon_pig_hit.jpg", "ribbon_pig_move.jpg"])
def test_finds_a_ribbon_pig_in_any_pose(pigs, name):
    """The quick check used to try only stand_0 (both ways): a Ribbon Pig in stand_2 / hit / move scored 0.36-0.44
    on it and was dropped before its own pose was tried (0.75-0.89); 22 of 52 Pigs found in that hunt."""
    found = pigs.find(img(name), PIG_FEET)
    assert any(mid == 10 for _, mid, _ in found), found


def test_old_stand_pair_quick_check_missed_them(pigs):
    old = SpriteDetector.for_map(10001070, MCW, min_score=Config().perception.sprite_score, quick_cover=None,
                                 quick_gray=False)
    assert not any(mid == 10 for _, mid, _ in old.find(img("ribbon_pig_hit.jpg"), PIG_FEET))


def test_quick_poses_cover_every_pose(pigs):
    for m in pigs.mobs:
        q = pigs.quick[m.mob_id]
        covered = set(q) | {j for i in q for j in pigs.groups[m.mob_id][i]}
        assert covered == set(range(len(m.frames))) and len(q) < len(m.frames)


def test_cover_ends_when_poses_match_nothing():
    """A flat (one-colour) picture scores -1 even on itself: _cover looped forever (found 2026-11-03 building a fake
    export in test_gamedata; the client has 1x1 placeholder frames)."""
    assert _cover(np.full((3, 3), -1.0), 0.5) == [0, 1, 2]
    S = np.array([[1.0, 0.9, -1.0], [0.9, 1.0, -1.0], [-1.0, -1.0, -1.0]])
    assert _cover(S, 0.5) == [0, 2]
