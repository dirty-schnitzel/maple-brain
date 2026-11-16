"""The fit's vote (maplebrain/perception/vote.py, PLAN-fit-speed.md S1) on the synthetic fixture (tests/fixtures/
synth_ant4: 40 frames, exact truth): every opaque mob's true (pose, feet) cell - or an identical-picture alias of it
(Zombie Mushroom stand_1 = move_2, origins 4 px apart) - gets >= 24 exclusive votes, without any scene. Needs only the
fixture, assets/mcw and a GPU."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")
if not torch.cuda.is_available():
    pytest.skip("no GPU", allow_module_level=True)

from maplebrain.perception.vote import PLAY_H, SW, Voter, load_poses  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "synth_ant4"
CAND = 24


@pytest.fixture(scope="module")
def setup():
    meta = json.loads((FIX / "synth.json").read_text())
    return meta, Voter(load_poses(meta["map"], ROOT / "assets" / "mcw"))


def screen(f):
    """The stored window pasted at its place on a frame of a colour no sprite has (no stray features)."""
    out = np.empty((768, SW, 3), np.uint8)
    out[:] = (1, 2, 3)
    x0, y0, x1, y1 = f["window"]
    out[y0:y1, x0:x1] = cv2.imread(str(FIX / "frames" / f["frame"]))[:y1 - y0, :x1 - x0]
    return out


def aliases(v, g):
    """Poses with the same picture as pose g (same type): [(g', dx, dy)], feet' = feet + (dx, dy)."""
    p = v.poses[g]
    return [(h, q.ox - p.ox, q.oy - p.oy) for h, q in enumerate(v.poses)
            if q.type == p.type and q.pic.shape == p.pic.shape and np.array_equal(q.pic, p.pic)]


def test_table(setup):
    _, v = setup
    assert v.G == 46 and v.n_colors < 215 and v.kdt == torch.int32
    assert all(k > 100 for k in v.kept)                     # every pose keeps features


def test_opaque_mobs_have_their_cell(setup):
    meta, v = setup
    gi = {(p.type, p.pose, p.facing): i for i, p in enumerate(v.poses)}
    assert (v.lut[1 | 2 << 8 | 3 << 16] == 0).item()
    n = 0
    for f in meta["frames"].values():
        mobs = [m for m in f["mobs"] if m["opacity"] >= 1]
        if not mobs:
            continue
        fr = torch.from_numpy(screen(f)[:PLAY_H].copy()).cuda()
        g, x, y, nv, ex, c = v.cells(v.ids(fr), CAND)
        got = {(int(a), int(b), int(d)): int(e) for a, b, d, e in zip(g, x, y, ex)}
        for m in mobs:
            g0 = gi[(m["type"], m["pose"], m["facing"])]
            fx, fy = m["feet"]
            best = max((got.get((h, fx + dx, fy + dy), 0) for h, dx, dy in aliases(v, g0)), default=0)
            assert best >= CAND, (f["frame"], m["type"], m["pose"], m["facing"], m["feet"], m["vis"], best)
            n += 1
    assert n >= 30
