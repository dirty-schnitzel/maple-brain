"""The mob path in the Perceiver (PLAN-perception.md step 3.4; the only one since 2026-11-17): on the perf fixture (45
native frames, Ant Tunnel IV) through the live rig (tools/perf/bench.build), every frame with the scene camera gets
the fit's mobs as the tracker's sightings and the fit's look at each track it did not find; a frame without the
camera has no camera and no mobs. Needs the scene build (`python -m maplebrain assets scene 10005063`), assets/mcw
and a GPU: skipped without."""
import importlib.util
import json
import sys
from pathlib import Path

import cv2
import pytest

torch = pytest.importorskip("torch")
if not torch.cuda.is_available():
    pytest.skip("no GPU", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("perf_bench", ROOT / "tools" / "perf" / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def _run(n: int = 10):
    from maplebrain.scene import Scene
    if not Scene.have(bench.ANT4):
        pytest.skip(f"needs python -m maplebrain assets scene {bench.ANT4}")
    sys.path.insert(0, str(ROOT / "tools" / "perc"))
    import frames as rec
    per = bench.build(bench.ANT4)[0]
    fs = bench.fixture_frames()[:n]
    shift = rec.xshift(fs[0].parent)
    out = []
    for i, p in enumerate(fs):
        obs = per.observe(rec.unshift(cv2.imread(str(p)), shift), 0.06 * i)
        out.append((obs, per.facts, dict(per.parts)))
    return per, out


def test_the_fit_feeds_the_tracker_where_the_scene_camera_is_found():
    """Every track sighted this tick is a fit mob (acq) or a SEEN look (near), at score 1.0."""
    per, on = _run()
    assert per.fitter is not None
    n_fit = 0
    for obs, f, parts in on:
        if f.scene_cam is None:
            assert obs.mobs == [] and obs.cam is None and f.fit is None and "fit" not in parts
            continue
        n_fit += 1
        assert "fit" in parts and "hints" in parts and obs.cam_src == "exact" and obs.cam == f.scene_cam
        json.dumps(f.as_dict())                                         # strict JSON
        looked = {h["id"]: h for h in f.fit_hints}
        for m in obs.mobs:
            if m["src"] == "acq":
                assert m["score"] == 1.0 and any(x["type"] == m["mob"] and tuple(x["feet"]) == (m["sx"], m["sy"])
                                                 for x in f.fit), (f.t, m)
            elif m["src"] == "near":
                h = looked[m["id"]]
                assert m["score"] == 1.0 and (h["sx"], h["sy"]) == (m["sx"], m["sy"]) and per.fitter.seen(h)
    assert n_fit >= len(on) - 1                                         # the first frame may have no camera yet


def test_a_frame_without_the_scene_camera_has_no_camera_and_no_mobs():
    """The scene camera lost (here: a frame of another place): no camera, no mobs that tick - the tracks wait as
    they are (the hunt pauses on it) and the next good frame goes on with them."""
    per, on = _run(6)
    n_before = len(per.world.tracks)
    import numpy as np
    obs = per.observe(np.full((768, 1366, 3), 40, np.uint8), 0.06 * 6)
    assert obs.scene_cam is None and obs.cam is None and obs.mobs == [] and per.facts.fit is None
    assert len(per.world.tracks) == n_before
