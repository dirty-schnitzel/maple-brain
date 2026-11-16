"""The synthetic fixture (PLAN-perception.md step 3.0b; tools/perc/synth/make.py --n 40 --seed 7 --webp --crop): frames
(each stored as the window around its mobs, "window" = its place on the screen)
with exact truth for the step-3 matcher. Needs only the fixture and assets/mcw (no scene build, no client export):
- the truth is where the pixels are: an opaque, uncovered, fully visible mob's sprite is in the frame 1:1;
- a see-through one is the sprite blended at its opacity: never further from the sprite than (1 - a) * 255;
- label_eval --synth scores the truth itself as 100 % found, 0 false.
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "synth_ant4"
MOBS = ROOT / "assets" / "mcw" / "mobs"


@pytest.fixture(scope="module")
def meta():
    return json.loads((FIX / "synth.json").read_text())


def sprite(m):
    im = cv2.imread(str(MOBS / str(m["type"]) / f"{m['pose']}.png"), cv2.IMREAD_UNCHANGED)
    return np.ascontiguousarray(im[:, ::-1]) if m["facing"] == "right" else im


def crop(frame, f, m):
    """The mob's box out of the stored window (f["window"]: its place on the screen)."""
    x, y, w, h = m["box"]
    x, y = x - f["window"][0], y - f["window"][1]
    return frame[y:y + h, x:x + w].astype(np.float32)


def test_fixture_complete(meta):
    fr = meta["frames"]
    assert meta["v"] == 2 and len(fr) == 40
    assert {f["case"] for f in fr.values()} == {"clear", "scenery", "fade", "dying", "hit", "edge", "effect",
                                                "player", "ui", "free"}
    for f in fr.values():
        assert (FIX / "frames" / f["frame"]).exists()
        assert (not f["mobs"]) == (f["case"] == "free")
        for m in f["mobs"]:
            assert {"feet", "type", "cls", "pose", "facing", "opacity", "onscreen", "vis", "cover", "box"} <= set(m)


def test_clear_mobs_are_the_sprite(meta):
    n = 0
    for f in meta["frames"].values():
        frame = None
        for m in f["mobs"]:
            if m["vis"] < 1 or m["opacity"] < 1 or m["onscreen"] < 1:
                continue
            frame = frame if frame is not None else cv2.imread(str(FIX / "frames" / f["frame"]))
            s = sprite(m)
            op = s[..., 3] == 255
            d = np.abs(crop(frame, f, m) - s[..., :3]).max(axis=2)[op]
            assert (d <= 4).mean() >= 0.99, (f["frame"], m["pose"])
            n += 1
    assert n >= 8


def test_fade_opacity_bound(meta):
    """frame = a * sprite + (1 - a) * behind on the sprite's opaque pixels, so |frame - sprite| <= (1 - a) * 255
    (+1 rounding) everywhere - and a see-through mob is not the sprite (few pixels within +-4)."""
    n = 0
    for f in meta["frames"].values():
        if f["case"] != "fade":
            continue
        frame = cv2.imread(str(FIX / "frames" / f["frame"]))
        for m in f["mobs"]:
            if m["vis"] < 0.99 * m["onscreen"] or m["onscreen"] < 1:
                continue
            s = sprite(m)
            op = s[..., 3] == 255
            d = np.abs(crop(frame, f, m) - s[..., :3]).max(axis=2)[op]
            assert d.max() <= (1 - m["opacity"]) * 255 + 1, (f["frame"], d.max(), m["opacity"])
            assert (d <= 4).mean() < 0.9
            n += 1
    assert n >= 3


def test_label_eval_scores_truth_perfectly(meta, tmp_path):
    rows = []
    for k, f in meta["frames"].items():
        rows.append({"n": int(k), "mobs": [{"sx": m["feet"][0], "sy": m["feet"][1], "state": "live", "mob": m["type"],
                                            "src": "acq"} for m in f["mobs"]]})
    (tmp_path / "synth.json").write_text(json.dumps(meta))
    (tmp_path / "truth.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "perc" / "label_eval.py"), str(tmp_path), "--labels",
                          "synth.json", "--tracks", "truth.jsonl", "--synth"], capture_output=True, text=True,
                         check=True).stdout
    total = sum(len(f["mobs"]) for f in meta["frames"].values())
    assert f"found {total} = 100.0 %" in out and "false tracks 0 " in out
    assert "ghost test: 4 mob-free frames, false tracks 0" in out
