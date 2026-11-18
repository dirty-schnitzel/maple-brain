"""The synthetic drop fixture (PLAN-loot.md S3; tools/loot/synth_drops.py tests/fixtures/synth_drops --fixture
--seed 7): 40 frames (crops = `window`) with exact truth. Needs only the fixture and assets/mcw/items (in git):
- complete: every case of section 7.2;
- the truth is where the pixels are: a drop with nothing over it is its picture 1:1 in the frame;
- drop_eval scores the truth itself: 100 % found, 0 false, 0 wrong identity, feet exact;
- the prototype's output on it (finder_before.jsonl, S4's reference for the product) has a row per frame."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "synth_drops"
sys.path.insert(0, str(ROOT / "tools" / "loot"))


@pytest.fixture(scope="module")
def meta():
    if not FIX.exists():
        pytest.skip("no synth_drops fixture")
    return json.loads((FIX / "synth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def items():
    from maplebrain import gamedata
    if not (gamedata.ROOT / "items" / "items.npz").exists():
        pytest.skip("assets/mcw/items not built")
    return gamedata.load_items()


def test_fixture_complete(meta):
    fr = meta["frames"]
    assert meta["v"] == 1 and meta["fixture"] and len(fr) == 40
    assert {f["case"] for f in fr.values()} == {"cat", "pile", "mob", "player", "effect", "ui", "edge", "flight",
                                                "window", "worn", "mobpart", "free"}
    masks = np.load(FIX / "masks.npz")
    for n, f in fr.items():
        assert (FIX / "frames" / f["frame"]).exists() and (FIX / "exp" / f["frame"]).exists()
        assert f"{n}_known" in masks.files and f"{n}_world" in masks.files
        if f["case"] == "free":
            assert not f["drops"] and not f["notdrops"]
        elif f["case"] in ("window", "worn", "mobpart"):
            assert f["notdrops"] and not f["drops"]
        else:
            assert f["drops"]
        for d in f["drops"]:
            assert {"g", "item", "f", "box", "feet", "kind", "cls", "vis", "onscreen", "front"} <= set(d)
            x, y, w, h = d["box"]
            assert d["feet"] == [x + w // 2, y + h]


def test_clear_drops_are_the_picture(meta, items):
    n = 0
    for f in meta["frames"].values():
        img = None
        for d in f["drops"]:
            if d["vis"] < 1 or d["onscreen"] < 1 or d["front"] > 0:
                continue
            img = img if img is not None else cv2.imread(str(FIX / "frames" / f["frame"]))
            x, y, w, h = d["box"]
            x, y = x - f["window"][0], y - f["window"][1]
            p = items.pics[d["g"]]
            op = p[..., 3] == 255
            assert np.array_equal(img[y:y + h, x:x + w][op], p[..., :3][op]), d
            n += 1
    assert n >= 40


def test_eval_scores_the_truth_perfect(meta, items):
    from drop_eval import evaluate
    rows = {}
    for name, f in meta["frames"].items():
        rows[name] = {"drops": [{"item": d["item"], "f": d["f"], "box": d["box"], "kind": d["kind"], "seen": 1,
                                 "n_op": 1, "dy": 0, "ring": [0, 0]} for d in f["drops"]]}
    ev = evaluate(meta, rows, items)
    found = sum(r["rest"] + r["air"] for r in ev["recall"].values())
    assert found == sum(len(f["drops"]) for f in meta["frames"].values())
    assert not ev["false"] and not ev["wrong"] and set(ev["pos"]) == {(0, 0)}


def test_reference_rows(meta):
    p = FIX / "finder_before.jsonl"
    if not p.exists():
        pytest.skip("no reference run yet (tools/loot/synth_find.py tests/fixtures/synth_drops)")
    rows = [json.loads(line) for line in open(p, encoding="utf-8")]
    assert {r["frame"] for r in rows} == set(meta["frames"])
    for r in rows:
        for s in r["drops"]:
            assert s["kind"] in ("rest", "air", "weak") and len(s["box"]) == 4
