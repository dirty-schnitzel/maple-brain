"""FrameFacts (perception/facts.py, PLAN-perception.md step 2): what one frame shows, recordable and read back
unchanged."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from maplebrain.config import Config
from maplebrain.perception.facts import VERSION, FrameFacts
from maplebrain.perception.gpu_sprites import Hit
from maplebrain.perception.perceiver import Perceiver
from maplebrain.perception.sprites import Pose
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
        f.hits = [Hit(21, (100, 200, 60, 50), (130, 250), Pose("move", 2, "right", 30, 50), 0.912)]
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


def test_another_version_is_refused():
    with pytest.raises(ValueError):
        FrameFacts.from_dict({"t": 0.0, "v": VERSION + 1})
