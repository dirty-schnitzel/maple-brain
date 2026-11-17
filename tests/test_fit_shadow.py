"""The fit in shadow in the Perceiver (PLAN-perception.md step 3.3): with config perception.fit the live rig
(tools/perf/bench.build) writes FrameFacts.fit / fit_ms / fit_hints on every frame with a scene camera, and nothing
reads them: the tracks are the same with the fit off. The perf fixture (45 native frames, Ant Tunnel IV); needs the
scene build (`python -m maplebrain assets scene 10005063`), assets/mcw and a GPU: skipped without."""
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


def _run(fit: bool, n: int = 10, fit_tracks: bool = False):
    from maplebrain.scene import Scene
    if not Scene.have(bench.ANT4):
        pytest.skip(f"needs python -m maplebrain assets scene {bench.ANT4}")
    sys.path.insert(0, str(ROOT / "tools" / "perc"))
    import frames as rec
    per = bench.build(bench.ANT4, fit=fit, fit_tracks=fit_tracks)[0]
    fs = bench.fixture_frames()[:n]
    shift = rec.xshift(fs[0].parent)
    out = []
    for i, p in enumerate(fs):
        obs = per.observe(rec.unshift(cv2.imread(str(p)), shift), 0.06 * i)
        out.append((obs.mobs, per.facts, dict(per.parts)))
    return per, out


def test_the_fit_runs_in_shadow_and_the_tracks_stay_the_same():
    per_on, on = _run(True)
    per_off, off = _run(False)
    assert per_on.fitter is not None and per_off.fitter is None
    n_fit = 0
    for (m1, f1, p1), (m0, f0, p0) in zip(on, off):
        key = lambda m: (m["id"], m["mob"], m["state"], m["src"], m["sx"], m["sy"], m["anim"])  # noqa: E731
        assert [key(m) for m in m1] == [key(m) for m in m0]
        assert all(abs(a["score"] - b["score"]) <= 0.01 for a, b in zip(m1, m0))
        assert f0.fit is None and f0.fit_hints is None and "fit" not in p0
        if f1.scene_cam is not None:
            n_fit += 1
            assert isinstance(f1.fit, list) and isinstance(f1.fit_hints, list) and f1.fit_ms > 0 and "fit" in p1
            json.dumps(f1.as_dict())                                    # strict JSON
            sighted = [m for m in m1 if m["src"] != "none" and m["state"] == "live" and m["score"] >= 0.9]
            found = [m for m in sighted if any(x["type"] == m["mob"] and abs(x["feet"][0] - m["sx"]) <= 20
                                               and abs(x["feet"][1] - m["sy"]) <= 20 for x in f1.fit)]
            assert len(found) >= len(sighted) - 1, (f1.t, sighted, f1.fit)
            looked = {h["id"] for h in f1.fit_hints}
            assert looked <= {m["id"] for m in m1}
    assert n_fit >= len(on) - 1                                         # the first frame may have no camera yet


def test_the_fit_feeds_the_tracker_where_the_scene_camera_is_found():
    """Step 3.4: on ticks with the scene camera the old search (part `gpu`) and find_near don't run; every track
    sighted this tick is a fit mob (acq) or a SEEN look (near), at score 1.0; a tick without the camera runs the old
    detector whole."""
    per, on = _run(True, fit_tracks=True)
    assert per.fit_tracks
    n_fit, prev = 0, False
    for mobs, f, parts in on:
        if f.scene_cam is None:
            assert "gpu" in parts and f.fit is None
            prev = False
            continue
        n_fit += 1
        # the old search runs only when the camera was not found on the tick before (decided before it's known)
        assert ("gpu" in parts) == (not prev) and "fit" in parts and "hints" in parts and f.hits == []
        prev = True
        json.dumps(f.as_dict())
        looked = {h["id"]: h for h in f.fit_hints}
        for m in mobs:
            if m["src"] == "acq":
                assert m["score"] == 1.0 and any(x["type"] == m["mob"] and tuple(x["feet"]) == (m["sx"], m["sy"])
                                                 for x in f.fit), (f.t, m)
            elif m["src"] == "near":
                h = looked[m["id"]]
                assert m["score"] == 1.0 and (h["sx"], h["sy"]) == (m["sx"], m["sy"]) and per.fitter.seen(h)
    assert n_fit >= len(on) - 1
