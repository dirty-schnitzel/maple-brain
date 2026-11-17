"""The fit (maplebrain/perception/fit.py, PLAN-fit-speed.md) on the synthetic fixture (tests/fixtures/synth_ant4: 40
frames, exact truth; the stored window over the expected scene, as tests/test_scene_diff.py): every mob found (its
type within 25 px, as tools/perc/fit/sweep.py matches), 0 false mobs (unmatched and not at an "unsure" spot / in a
"dontcare" box: our blob and the UI the base frame could not erase), none on the mob-free frames, and the opaque
clear mobs exact: pose + facing (or an identical-picture alias) and feet to the pixel. A frozen mob pasted on bare
scenery: found with tint "frozen", pose and feet exact. Needs the scene build (`python -m maplebrain assets scene
10005063`, not in git), assets/mcw and a GPU: skipped without."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")
if not torch.cuda.is_available():
    pytest.skip("no GPU", allow_module_level=True)

from maplebrain import scene as sc  # noqa: E402
from maplebrain.perception import hud  # noqa: E402
from maplebrain.perception.fit import Fitter  # noqa: E402
from maplebrain.perception.vote import PLAY_H, SW, TINTS, tinted  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "synth_ant4"
sys.path.insert(0, str(ROOT / "tools" / "perc" / "fit"))
import sweep  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    meta = json.loads((FIX / "synth.json").read_text())
    if not sc.Scene.have(meta["map"]):
        pytest.skip(f"needs python -m maplebrain assets scene {meta['map']}")
    s = sc.Scene.load(meta["map"])
    ui = hud.ui_mask((768, sc.W)) > 0
    ui[630:PLAY_H, 285:850] = True                  # the chat rect is world at native (tools/perc/fit/run.py)
    ui_t = torch.from_numpy(np.ascontiguousarray(ui[:PLAY_H])).to(s.dev)
    return meta, s, ui_t, Fitter(s, meta["map"], ROOT / "assets" / "mcw")


def full_frame(s, f):
    exp, _ = s.expected(tuple(f["C"]))
    full = exp.round().clamp(0, 255).byte().cpu().numpy()
    x0, y0, x1, y1 = f["window"]
    full[y0:y1, x0:x1] = cv2.imread(str(FIX / "frames" / f["frame"]))
    return full


def fit(s, ui_t, fitter, full, C):
    exp, known = s.expected(tuple(C))
    return fitter.fit(full, tuple(C), exp, known, ui_t)


def aliases(fitter, type_, pose, facing):
    """(pose, facing, dx, dy) with the same picture as the given pose: feet' = feet + (dx, dy)."""
    p = next(q for q in fitter.poses if (q.type, q.pose, q.facing) == (type_, pose, facing))
    return {(q.pose, q.facing, q.ox - p.ox, q.oy - p.oy) for q in fitter.poses
            if q.type == p.type and q.pic.shape == p.pic.shape and np.array_equal(q.pic, p.pic)}


def test_synth_fixture_recall_no_false_exact_pose(setup):
    meta, s, ui_t, fitter = setup
    fits, n_exact = {}, 0
    for n, f in meta["frames"].items():
        mobs = fit(s, ui_t, fitter, full_frame(s, f), f["C"])
        fits[int(n)] = {"mobs": [{"sx": m.feet[0], "sy": m.feet[1], "mob": m.type, "anim": m.pose,
                                  "fit": m.to_dict()} for m in mobs]}
        if f["case"] == "clear":
            for t in f["mobs"]:
                if t["opacity"] < 1:
                    continue
                al = aliases(fitter, t["type"], t["pose"], t["facing"])
                ok = [m for m in mobs if m.type == t["type"] and any(
                    (m.pose, m.facing, m.feet[0] - t["feet"][0], m.feet[1] - t["feet"][1]) == a for a in al)]
                assert ok, (n, t, [m.to_dict() for m in mobs])
                assert all(m.tint == "" for m in ok)
                n_exact += 1
    truth = {int(n): f for n, f in meta["frames"].items()}
    per, fp, fl, wrong = sweep.score(truth, fits, (0, 0, 1), True)
    assert per["all"][0] >= 60 and per["all"][1] == per["all"][0], dict(per)
    assert sum(fp.values()) == 0 and wrong == 0, fl
    assert n_exact >= 4


def test_frozen_mob_found_with_its_tint(setup):
    """A frozen Horny / Zombie Mushroom (every 4th pose, both facings) on a foothold of a mob-free fixture frame."""
    meta, s, ui_t, fitter = setup
    f = min((fr for fr in meta["frames"].values() if fr["case"] == "free"), key=lambda fr: len(fr["dontcare"]))
    base = full_frame(s, f)
    m = TINTS["frozen"]
    n = 0
    for p in fitter.poses[::3]:                     # both facings (the list alternates left / right)
        if p.pose.startswith("die"):
            continue
        full = base.copy()
        h, w = p.pic.shape[:2]
        fx, fy = 700, 450
        y0, x0 = fy - p.oy, fx - p.ox
        a = p.pic[..., 3:].astype(np.float32) / 255
        box = full[y0:y0 + h, x0:x0 + w].astype(np.float32)
        full[y0:y0 + h, x0:x0 + w] = np.round(box * (1 - a) + tinted(p.pic[..., :3], m) * a).astype(np.uint8)
        got = fit(s, ui_t, fitter, full, f["C"])
        al = aliases(fitter, p.type, p.pose, p.facing)
        ok = [g for g in got if g.type == p.type and g.tint == "frozen" and any(
            (g.pose, g.facing, g.feet[0] - fx, g.feet[1] - fy) == a_ for a_ in al)]
        assert ok, (p.type, p.pose, p.facing, [g.to_dict() for g in got])
        n += 1
    assert n >= 8


def test_hints_look_once_at_tracks_the_fit_did_not_find(setup):
    """Fitter.hints (3.3): a track the fit found gets no look; one at a mob-free foothold spot reads ABSENT (the scene
    shows where its sprite would be); one at a real mob reads SEEN when nothing else explained those pixels, and
    COVERED when an accepted fit mob did."""
    from maplebrain.perception.world import Track
    meta, s, ui_t, fitter = setup
    f = next(fr for fr in meta["frames"].values() if fr["case"] == "clear" and any(t["opacity"] >= 1 for t in fr["mobs"]))
    t = next(t for t in f["mobs"] if t["opacity"] >= 1)
    mobs = fit(s, ui_t, fitter, full_frame(s, f), f["C"])
    tr = Track(1, t["type"], 0, 0, 0, 0, sx=t["feet"][0], sy=t["feet"][1], facing=t["facing"],
               anim=t["pose"].rsplit("_", 1)[0], state="live")
    assert fitter.hints([tr], mobs) == []                       # found: no look
    h = fitter.hints([tr], [])[0]                               # "not found": its pixels are the fit mob's
    assert h["n_inf"] > 300 and h["n_seen"] < 0.1 * h["n_inf"] and h["n_abs"] < 0.1 * h["n_inf"], h
    fitter.taken[:] = False                                     # nothing explained them: SEEN
    h = fitter.hints([tr], [])[0]
    assert h["n_seen"] > 0.8 * h["n_inf"] and h["id"] == 1 and h["mob"] == t["type"], h
    free = min((fr for fr in meta["frames"].values() if fr["case"] == "free"), key=lambda fr: len(fr["dontcare"]))
    fit(s, ui_t, fitter, full_frame(s, free), free["C"])
    ghost = Track(2, t["type"], 0, 0, 0, 0, sx=700, sy=450, facing="left", anim="stand", state="dying")
    h = fitter.hints([ghost, Track(3, t["type"], 0, 0, 0, 0, state="tentative")], [])
    assert len(h) == 1 and h[0]["n_abs"] > 0.8 * h[0]["n_inf"] > 300, h
    # tracks past the screen's sides / below the play area, with small sprites (Stirge: the box's padding is small;
    # Transfer Area's replay broke on such a track, 2026-11-17)
    small = Fitter(s, meta["map"], ROOT / "assets" / "mcw", types=[17])
    fit(s, ui_t, small, full_frame(s, f), f["C"])
    edge = [Track(i, 17, 0, 0, 0, 0, sx=x, sy=y, facing="left", anim="fly", state="live")
            for i, (x, y) in enumerate(((-39, 400), (SW + 39, 400), (600, PLAY_H + 67), (-39, PLAY_H + 67)), 10)]
    h = small.hints(edge, [])
    assert [x["id"] for x in h] == [10, 11, 12, 13] and all(x["n_seen"] <= x["n_inf"] for x in h), h
