"""Ghost mobs at the screen edge (2026-11-09): on real frames, the share of a detection's body inside the screen
separates half a sprite matched to cave scenery from real mobs at the edge. Skipped without torch or the map."""
import json
from pathlib import Path

import cv2
import pytest

torch = pytest.importorskip("torch")

from maplebrain.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402
from maplebrain.perception.world import TrackCfg, World  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MCW = ROOT / "assets" / "mcw"
FX = Path(__file__).parent / "fixtures" / "edge_ghost"
ANT4, ZOMBIE = 10005063, 21

pytestmark = pytest.mark.skipif(not (MCW / "maps" / str(ANT4) / "map.json").exists(), reason="needs map 10005063")


@pytest.fixture(scope="module")
def rig():
    det = GpuSpriteDetector.for_map(ANT4, MCW)
    mj = json.loads((MCW / "maps" / str(ANT4) / "map.json").read_text(encoding="utf-8"))
    mob = json.loads((MCW / "mobs" / str(ZOMBIE) / "mob.json").read_text(encoding="utf-8"))
    return det, World(None, mj, {ZOMBIE: mob})


def look(rig, name, spot):
    """The tracker's own search there (visible-only, as live) -> (score, share of the body on screen)."""
    det, w = rig
    h = det.find_near(cv2.imread(str(FX / name)), [(ZOMBIE, *spot)], pad=24, min_score=0.0, vis=[None])[0]
    return h.score, w._onscreen(ZOMBIE, *h.feet)


@pytest.mark.parametrize("name, spot", [("ghost_58.1.jpg", (1367, 468)), ("ghost_air1_57.5.jpg", (1367, 469))])
def test_the_edge_ghost_scores_like_a_mob_but_is_mostly_off_screen(rig, name, spot):
    score, on = look(rig, name, spot)
    assert score >= TrackCfg.near_score                       # why it was followed (and born at a dying mob's spot)
    assert on < TrackCfg.new_onscreen                         # why it can't be born now
    assert score < TrackCfg.edge_score                        # ... nor keep a real mob's track alive there


@pytest.mark.parametrize("name, spot", [("real_press1_112.9.jpg", (1348, 695)), ("real_react1_47.8.jpg", (1338, 648))])
def test_real_mobs_at_the_edge_are_still_new_mobs(rig, name, spot):
    score, on = look(rig, name, spot)
    assert score >= 0.85 and on >= TrackCfg.new_onscreen
