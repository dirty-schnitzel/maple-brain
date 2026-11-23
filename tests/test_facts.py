"""FrameFacts (perception/facts.py, PLAN-perception.md step 2): what one frame shows, recordable and read back
unchanged."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.config import Config
from maplebrain.perception.facts import VERSION, FrameFacts
from maplebrain.perception.perceiver import Perceiver
from maplebrain.runtime.recorder import Recorder

ROOT = Path(__file__).resolve().parents[1]
FX = Path(__file__).parent / "fixtures" / "perf_ant4"


def _frames(n=6):
    fs = sorted(FX.glob("*.webp"))
    if not fs:
        pytest.skip("no tests/fixtures/perf_ant4")
    return [cv2.imread(str(p)) for p in fs[:n]]


def test_real_frames_round_trip_through_strict_json():
    per = Perceiver(Config(), np.load(ROOT / "assets" / "self_tag_gray.npy"))
    seen = 0
    for i, frame in enumerate(_frames()):
        per.observe(frame, 0.1 * i)
        f = per.facts
        f.tags = [(100, 200, 60, 12)]
        d = json.loads(json.dumps(f.as_dict()))                   # no default=str: numpy types would fail here
        assert FrameFacts.from_dict(d) == f
        seen += f.tag is not None and f.hp is not None and f.exp_points is not None
    assert seen >= 3                                              # the readings are really in there


def test_the_recorder_writes_the_facts(tmp_path):
    per = Perceiver(Config(), np.load(ROOT / "assets" / "self_tag_gray.npy"))
    rec = Recorder(tmp_path, every=0)
    for i, frame in enumerate(_frames(3)):
        obs = per.observe(frame, 0.1 * i)
        rec.tick(frame, obs, [], "IDLE", {}, facts=per.facts)
    rec.close()
    rows = [json.loads(line) for line in (tmp_path / "ticks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [FrameFacts.from_dict(r["facts"]).t for r in rows] == [0.0, 0.1, 0.2]


def test_fit_fields_round_trip_and_older_records_read():
    f = FrameFacts(t=1.5, fit=[{"type": 19, "pose": "move_1", "facing": "left", "feet": [300, 480], "opacity": 1.0,
                                "seen": 0.91, "absent": 0.01, "covered": 0.08, "n_inf": 1800, "n_seen": 1638,
                                "votes": 410, "layer": 1, "tint": ""}], fit_ms=4.31,
                   fit_hints=[{"id": 7, "mob": 21, "sx": 540, "sy": 274, "pose": "move_0", "facing": "right",
                               "n_inf": 1898, "n_seen": 0, "n_abs": 39, "o": 0.992}],
                   drops=[{"item": 9000001, "f": 2, "box": [400, 300, 25, 24], "feet": [412, 324], "kind": "rest",
                           "n_op": 380, "seen": 380, "absent": 0, "under": 0, "front": 0, "mob": 0, "ring": [400, 410],
                           "dy": 3, "fh": 12, "layer": 1, "votes": 210, "n_fseen": 300}],
                   drops_ms={"launch": 0.25, "fetch": 0.07, "pick": 0.1, "feat": 9000, "feat2": 40, "cands": 3},
                   movers=[(1, 517.0, True, 0.91), (3, None, False, 0.0)], movers_ms=0.84)
    assert f.v == VERSION == 6
    assert FrameFacts.from_dict(json.loads(json.dumps(f.as_dict()))) == f
    for v in (1, 2, 4, 5):
        old = FrameFacts.from_dict({"t": 0.0, "v": v})
        assert old.movers is None and old.movers_ms is None
    for v in (1, 2, 4):
        old = FrameFacts.from_dict({"t": 0.0, "v": v})
        assert old.drops is None and old.drops_ms is None
    for v in (1, 2):
        old = FrameFacts.from_dict({"t": 0.0, "v": v})
        assert old.fit is None and old.fit_ms is None and old.fit_hints is None
    old = FrameFacts.from_dict({"t": 0.0, "v": 3, "scene_shift": [1.0, 2.0], "plat_shift": None,   # v1-v3's
                                "hits": [{"mob_id": 21}], "fit": []})                            # old camera
    assert old.fit == [] and not hasattr(old, "hits")                                               # + detector


def test_another_version_is_refused():
    with pytest.raises(ValueError):
        FrameFacts.from_dict({"t": 0.0, "v": VERSION + 1})
