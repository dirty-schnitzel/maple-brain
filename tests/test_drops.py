"""perception/drops.py (PLAN-loot.md S7): the product DropFinder (fixed-size CUDA graph) against the reference
(tools/loot/dropvote.py, eager) on the synthetic fixture (tests/fixtures/synth_drops: the live inputs stored - expected
scene, known / world masks, front planes per layer, the fit's explained pixels, character boxes):
- the same drops with the same facts and kinds (exclusive `votes` aside: the graph's table keeps keys in <= MAXP
  places, the reference's <= 64);
- drop_eval on its rows: feet exact, 0 false REST, 0 wrong identity; drop-free frames: no sighting at all;
- every searchable picture of the catalogue, pasted alone on a plain scene, is found REST with its class and box."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "synth_drops"
sys.path.insert(0, str(ROOT / "tools" / "loot"))

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA (the drop pass is a CUDA graph)")


@pytest.fixture(scope="module")
def meta():
    if not FIX.exists():
        pytest.skip("no synth_drops fixture")
    return json.loads((FIX / "synth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def finder():
    from maplebrain import gamedata
    if not (gamedata.ROOT / "items" / "items.npz").exists():
        pytest.skip("assets/mcw/items not built")
    from maplebrain.perception.drops import DropFinder
    fz = DropFinder()
    fz.warm()
    return fz


@pytest.fixture(scope="module")
def runs(meta, finder):
    """Per fixture frame: (reference facts, product facts)."""
    from dropvote import DropFinder as Ref, facts
    from lootlib import Footholds, PLAY_H, SW
    from synth_find import frame_inputs
    ref = Ref(items=finder.items, cand_votes=finder.cfg.cand_votes)
    masks, mf = np.load(FIX / "masks.npz"), np.load(FIX / "masks_fit.npz")
    dev = finder.dev
    out = {}
    for name, f in meta["frames"].items():
        img, exp, known, world, front = frame_inputs(FIX, name, f, True, {}, masks)
        x0, y0, x1, y1 = f["window"]
        taken = np.zeros((PLAY_H, SW), bool)
        taken[y0:y1, x0:x1] = np.unpackbits(mf[f"{name}_taken"])[:(y1 - y0) * (x1 - x0)].reshape(y1 - y0, x1 - x0)
        chars = np.zeros((PLAY_H, SW), bool)
        for b in f.get("chars") or []:
            chars[max(0, int(b[1])):max(0, int(b[3])), max(0, int(b[0])):max(0, int(b[2]))] = True
        C, fh = tuple(f["C"]), Footholds(f["map"])
        ft = torch.from_numpy(np.ascontiguousarray(img)).to(dev)
        et, kt = torch.from_numpy(exp).to(dev), torch.from_numpy(known).to(dev)
        wt = torch.from_numpy(np.ascontiguousarray(world)).to(dev)

        def layer_of(sx, sy, C=C, fh=fh):
            u = fh.under(sx + C[0], sy + C[1])
            return u[1] if u is not None else None

        a = [facts(d, C, fh) for d in ref.find(ft, et, kt, wt, mob_taken=taken, chars=chars, front=front,
                                               layer_of=layer_of)]
        finder.set_map(f["map"])
        finder.launch(ft, C, et, kt, wt, front={L: torch.from_numpy(p).to(dev) for L, p in front.items()})
        out[name] = (a, finder.fetch(taken, f.get("chars") or []))
    return out


def _sig(rows):
    return sorted(json.dumps({k: v for k, v in d.items() if k != "votes"}, sort_keys=True) for d in rows)


def test_same_drops_as_the_reference(meta, runs):
    bad = {n: (_sig(a), _sig(b)) for n, (a, b) in runs.items() if _sig(a) != _sig(b)}
    assert not bad, {n: ([x for x in a if x not in b], [x for x in b if x not in a]) for n, (a, b) in bad.items()}
    assert sum(len(a) for a, _ in runs.values()) >= 100
    assert sum(d["kind"] == "rest" for _, b in runs.values() for d in b) >= 60


def test_eval_on_the_fixture(meta, runs, finder):
    from drop_eval import evaluate
    ev = evaluate(meta, {n: {"drops": b} for n, (_, b) in runs.items()}, finder.items)
    assert not [k for k in ev["false"] if k[1] == "rest"]
    assert not ev["wrong"]
    assert set(ev["pos"]) == {(0, 0)}
    for n, f in meta["frames"].items():
        if f["case"] == "free":
            assert runs[n][1] == [], n


def test_every_catalogue_picture_found_alone(finder):
    """Each searchable picture alone (48 a frame, 170 x 116 px apart) on a plain known scene, its bottom on a
    foothold: found REST with its class, meso frame and box."""
    from types import SimpleNamespace
    from maplebrain.perception.drops import Footholds, PLAY_H, SW
    fz, dev = finder, finder.dev
    bg = np.array([23, 41, 67], np.uint8)
    rows = {str(r): {"x1": 0, "y1": 100 + 116 * r, "x2": SW, "y2": 100 + 116 * r, "layerId": 1} for r in range(6)}
    fz.map = SimpleNamespace(fh=Footholds({"footholds": rows}), slot_of={}, planes=None, x0=0, y0=0)
    exp = torch.from_numpy(np.broadcast_to(bg, (PLAY_H, SW, 3)).astype(np.float32).copy()).to(dev)
    known = torch.ones((PLAY_H, SW), dtype=torch.bool, device=dev)
    missed, n = [], len(fz.poses)
    for s in range(0, n, 48):
        img = np.broadcast_to(bg, (768, SW, 3)).copy()
        want = {}
        for k, gi in enumerate(range(s, min(n, s + 48))):
            p = fz.poses[gi].pic
            h, w = p.shape[:2]
            fx, fy = 85 + 170 * (k % 8), 100 + 116 * (k // 8)
            x, y = fx - w // 2, fy - h
            a = p[..., 3:4].astype(np.float64) / 255
            img[y:y + h, x:x + w] = np.floor(img[y:y + h, x:x + w] * (1 - a) + p[..., :3] * a + 0.5).astype(np.uint8)
            want[(x, y, w, h)] = fz.meta[gi]
        fz.launch(torch.from_numpy(img).to(dev), (0, 0), exp, known, known)
        got = {tuple(d["box"]): ((d["item"], d["f"]), d["kind"]) for d in fz.fetch()}
        missed += [(m, box) for box, m in want.items() if got.get(box) != (m, "rest")]
    assert not missed, f"{len(missed)} of {n} pictures not found REST alone: {missed[:10]}"
