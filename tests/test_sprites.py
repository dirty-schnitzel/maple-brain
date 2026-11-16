"""Mob detection from game sprites (assets/mcw, map 42 = Snail Hunting Ground III)."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.config import Config
from maplebrain.perception.sprites import SpriteDetector, _cover, load_mob, signature_hues

ROOT = Path(__file__).resolve().parents[1]
MCW = ROOT / "assets" / "mcw"
FX = Path(__file__).parent / "fixtures"
SNAIL, BLUE, RED = 2, 3, 5

pytestmark = pytest.mark.skipif(not (MCW / "maps" / "42" / "map.json").exists(),
                                reason="run `python -m maplebrain assets update 42` first")


@pytest.fixture(scope="module")
def det():
    return SpriteDetector.for_map(42, MCW, min_score=Config().perception.sprite_score)


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


# ---------------------------------------------------------------- death animation (another player's kill)
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
