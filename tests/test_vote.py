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

from maplebrain.perception.vote import PLAY_H, SW, TINTS, Voter, load_poses, tinted  # noqa: E402

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


def test_tint_rounding():
    """frame = round(s m / 255) per channel (exp_tint.py: exact on 8299 of 8299 opaque pixels of 3 frozen mobs;
    floor / >> 8 variants miss 8-35 % of them)."""
    s = np.array([[0, 0, 0], [255, 255, 255], [40, 100, 230], [13, 64, 191]], np.uint8)
    m = TINTS["frozen"]
    assert tinted(s, m).tolist() == [[0, 0, 0], [255, 168, 10], [40, 66, 9], [13, 42, 7]]


def test_frozen_mob_has_its_cell(setup):
    """A frozen mob (every pose of the map, both facings, tinted, alone on a blank frame) gets its own cell: the
    tinted colours map to the plain ids."""
    _, v = setup
    for g, p in enumerate(v.poses):
        out = np.empty((PLAY_H, SW, 3), np.uint8)
        out[:] = (1, 2, 3)
        h, w = p.pic.shape[:2]
        fx, fy = 600, 450
        box = out[fy - p.oy:fy - p.oy + h, fx - p.ox:fx - p.ox + w]
        op = p.pic[..., 3] == 255
        box[op] = tinted(p.pic[..., :3], TINTS["frozen"])[op]
        gg, x, y, nv, ex, c = v.cells(v.ids(torch.from_numpy(out).cuda()), CAND)
        got = {(int(a), int(b), int(d)): int(e) for a, b, d, e in zip(gg, x, y, ex)}
        best = max((got.get((k, fx + dx, fy + dy), 0) for k, dx, dy in aliases(v, g)), default=0)
        assert best >= CAND, (p.type, p.pose, p.facing, best)
