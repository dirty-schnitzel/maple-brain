"""tools/perc/replay: the module swap (maplebrain's code from a git ref under the working tree's file names) and the
old-vs-new comparison of tracks. The replay itself needs recorded runs + the GPU: proven by hand (its README)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"replay_{name}", ROOT / "tools" / "perc" / "replay" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mob(i, sx, sy, score=0.9, state="live", mob=19, src="acq"):
    return {"id": i, "mob": mob, "state": state, "sx": sx, "sy": sy, "score": score, "src": src, "anim": "move",
            "facing": "left", "platform": 1}


def _rows(per_frame):
    return [{"n": n, "frame": f"{n:06d}.jpg", "t": n * 0.1, "cam": [0.0, 0.0], "mobs": mobs}
            for n, mobs in enumerate(per_frame, 1)]


def test_compare_counts_real_and_weak_tracks_and_what_the_other_replay_lost():
    cmp = _load("compare")
    a = _rows([[_mob(1, 100, 300), _mob(2, 500, 300, 0.62)], [_mob(1, 104, 300), _mob(2, 500, 300, 0.62)],
               [_mob(1, 108, 300), _mob(3, 700, 300, state="tentative")]])
    b = _rows([[_mob(7, 101, 300)], [_mob(7, 105, 301)], [_mob(7, 300, 300)]])     # no weak track; real one off at the end
    c = cmp.compare(a, b)
    assert (c["a"]["real"], c["a"]["weak"], c["a"]["confirmed"]) == (1, 1, 2)       # the tentative one isn't a track
    assert (c["b"]["real"], c["b"]["weak"]) == (1, 0)
    assert c["a_in_b"]["total"] == {"real": [3, 2], "weak": [2, 0]}
    assert c["b_in_a"]["total"] == {"real": [3, 2], "weak": [0, 0]}
    assert c["same_frames"] == 0


def test_compare_calls_gpu_noise_the_same_tracks_but_not_a_moved_or_missing_track():
    cmp = _load("compare")
    a = _rows([[_mob(1, 100, 300, 0.907)], [_mob(1, 104, 300)], [_mob(1, 108, 300)]])
    b = _rows([[_mob(1, 100, 300, 0.911)], [_mob(1, 107, 300)], []])
    c = cmp.compare(a, b)
    assert (c["same_frames"], c["identical_frames"]) == (1, 0)


def test_the_swap_serves_a_module_from_git_under_the_working_trees_file_name():
    run = _load("run")
    if subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True).returncode:
        pytest.skip("not a git checkout")
    src = run.GitSource("HEAD", ["geometry.py"])
    assert src.files == {"maplebrain/geometry.py"}
    assert src.find_spec("maplebrain.config") is None and src.find_spec("json") is None      # not swapped: as always
    spec = src.find_spec("maplebrain.geometry")
    assert Path(spec.origin) == ROOT / "maplebrain" / "geometry.py"
    mod = importlib.util.module_from_spec(spec)                   # (not put into sys.modules: nothing else sees it)
    spec.loader.exec_module(mod)
    assert Path(mod.__file__) == ROOT / "maplebrain" / "geometry.py" and mod.cx((10, 0, 20, 5)) == 20
    assert "maplebrain.geometry" not in sys.modules or sys.modules["maplebrain.geometry"] is not mod
    with pytest.raises(SystemExit):
        run.GitSource("HEAD", ["no_such_file.py"])
