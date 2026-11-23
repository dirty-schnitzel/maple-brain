"""PLAN-moving-scenery.md step 5: mobs under the weather clouds, truth by construction (tools/perc/synth/under_clouds.py)
- a fixed-seed set on Perion Street Corner's own expected picture (no footage): a mob pasted on a foothold, one of the
client's cloud pictures blended over it; the frame undone (perception/clouds.py) and the fit with the cloud (the
tolerant vote) finds every one, no false mob; with the cloud left in it loses mobs. Needs the local builds (assets/mcw,
assets/scene for the map, assets/scene/clouds): skipped without."""
import random
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[1]
MAP = 10004040                                   # Perion Street Corner
from maplebrain.scene import PLAY_H, ROOT as SCENES, W  # noqa: E402

if not ((SCENES / str(MAP) / "scene.json").exists() and (SCENES / "clouds" / "clouds.json").exists()
        and (ROOT / "assets" / "mcw" / "maps" / str(MAP)).exists()):
    pytest.skip("needs assets/mcw + python -m maplebrain assets scene (Perion Street Corner, the clouds)",
                allow_module_level=True)
sys.path.append(str(ROOT / "tools" / "perc" / "synth"))
import under_clouds as uc  # noqa: E402
from maplebrain.config import Perception  # noqa: E402
from maplebrain.perception.clouds import Clouds  # noqa: E402
from maplebrain.perception.fit import Fitter  # noqa: E402
from maplebrain.scene import Scene  # noqa: E402


@pytest.fixture(scope="module")
def rig():
    sc = Scene.load(MAP)
    fz = Fitter(sc, MAP, ROOT / "assets" / "mcw")
    return sc, fz, Clouds(sc.dev, Perception())


def _set(rig, n=40, seed=3):
    sc, fz, cl = rig
    rnd = random.Random(seed)
    fhs, poses = uc.footholds(MAP, ROOT / "assets" / "mcw"), uc.standing(fz)
    ch, cw = sc.canvas.shape[:2]
    cams = [(sc.x0 + int(fx * (cw - W)), sc.y0 + int(fy * (ch - PLAY_H))) for fy in (0.3, 0.6, 0.9)
            for fx in (0.1, 0.3, 0.5, 0.7, 0.9)]
    ui = torch.ones((PLAY_H, W), dtype=torch.bool, device=sc.dev)
    res = []
    while len(res) < n:
        C = rnd.choice(cams)
        E, known = sc.expected(C)
        f = E.round().clamp(0, 255).to(torch.uint8)
        base = fz.fit(f, C, E, known, ui)
        assert base == []                                  # the scene alone: no mob
        pl = uc.place(rnd, fz, cl, fhs, poses, f, C, known & ((f.float() - E).abs().amax(dim=2) <= 4), base)
        if pl is not None:
            res.append({**pl, **uc.judge(fz, cl, pl, C, E, known, ui, base)})
    return res


def test_mobs_under_clouds_are_found_undone_and_none_made_up(rig):
    res = _set(rig)
    assert all(r["none"] for r in res)                     # the fit finds each mob without the cloud
    assert sum(r["am"] >= 0.3 for r in res) >= 10          # the set has thick clouds over mobs
    assert all(r["undone"] for r in res), [(r["type"], r["am"]) for r in res if not r["undone"]]
    assert sum(r["undone_extra"] for r in res) == 0
    assert sum(r["raw"] for r in res) < 0.8 * len(res)     # left in, the cloud hides mobs: the undo is what finds them
    for r in res:                                          # the cloud number: seen through how much cloud
        assert r["mob"].n_cloud == 0                       # these clouds are never too thick to undo (<= 0.88)
        assert abs(r["mob"].cloud - r["am"]) < 0.15
