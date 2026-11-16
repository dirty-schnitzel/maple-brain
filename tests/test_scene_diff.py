"""D = frame - expected scene (PLAN-perception.md step 3.1, scene.Scene.diff + scene.patches) on the synthetic fixture
(tests/fixtures/synth_ant4, exact truth): the GPU blobs are the label tool's rule (tools/perc/labels/patches.py: cv2
erode 3x3 / dilate 13x13 / >= 60 px) to the pixel; every pasted mob lies in one patch's box (>= 90 % of its body box
on screen outside the UI); on mob-free frames patches lie only at our blob / the UI ("dontcare") or at a pasted
distractor. Needs the scene build (`python -m maplebrain assets scene 10005063`, not in git): skipped without it."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from maplebrain import scene as sc  # noqa: E402
from maplebrain.perception import hud  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "synth_ant4"
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "labels"))


@pytest.fixture(scope="module")
def setup():
    meta = json.loads((FIX / "synth.json").read_text())
    if not sc.Scene.have(meta["map"]):
        pytest.skip(f"needs python -m maplebrain assets scene {meta['map']}")
    s = sc.Scene.load(meta["map"])
    ui = hud.ui_mask((768, sc.W)) > 0
    return meta, s, ui, torch.from_numpy(np.ascontiguousarray(ui[:sc.PLAY_H])).to(s.dev)


def frames(meta, s):
    """(n, frame, full-screen picture: the stored window over the expected scene)."""
    for n, f in meta["frames"].items():
        C = tuple(f["C"])
        exp, _ = s.expected(C)
        full = exp.round().clamp(0, 255).byte().cpu().numpy()
        x0, y0, x1, y1 = f["window"]
        full[y0:y1, x0:x1] = cv2.imread(str(FIX / "frames" / f["frame"]))
        yield n, f, full


def test_gpu_blobs_are_the_label_tools_rule(setup):
    from patches import patches as label_patches
    meta, s, ui, ui_t = setup
    for n, f, full in frames(meta, s):
        C = tuple(f["C"])
        exp, known = s.expected(C)
        d = (torch.from_numpy(full).to(s.dev).float() - exp).abs().amax(dim=2)
        bad = ((d > 4) & known).cpu().numpy() & ui[:sc.PLAY_H]
        assert sc.patches(s.diff(full, C, tol=4, mask=ui_t)) == label_patches(bad), n


def test_every_mob_is_in_a_patch_and_mob_free_frames_only_show_what_was_pasted(setup):
    import dcheck
    meta, s, ui, ui_t = setup
    n_mobs = 0
    for n, f, full in frames(meta, s):
        ps = sc.patches(s.diff(full, tuple(f["C"]), tol=4, mask=ui_t))
        for m in f["mobs"]:
            j = dcheck.judge(m["box"], ps, ui)
            if j is not None:
                n_mobs += 1
                assert j[0], (n, m)
        if f["case"] == "free":
            ok = [(b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in f["dontcare"]] + \
                 [tuple(d[:4]) for d in f.get("distractors", [])]
            assert all(any(dcheck.inter(p, b) > 0 for b in ok) for p in ps), (n, ps)
    assert n_mobs >= 55
