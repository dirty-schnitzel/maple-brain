"""E-L10 (PLAN-loot.md): frames for the eye - the whole play area with what the prototype says drawn on it, to count
by eye the drops it misses and the boxes that are no drop.

    python tools/loot/exp_eye.py RUN [--find v3] [--n 3] [--t T1,T2,..] [--out NAME] [--min-drops 0]

Boxes: green = REST (at the resting height, unexplained cover <= 0.2, not a mob), cyan = AIR (same, off the ground,
ring >= 0.3), red = a loose sighting the rule drops (covered / worn / UI). Frames: --t times, else --n evenly spread
(with >= --min-drops loose sightings). One PNG per frame: RUN/loot/eye_<NAME>_<frame>.png (native size, play area).
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items, frame, map_of, PLAY_H, ROOT  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--find", default="v3")
ap.add_argument("--n", type=int, default=3)
ap.add_argument("--t", default="")
ap.add_argument("--out", default="a")
ap.add_argument("--min-drops", type=int, default=0)
a = ap.parse_args()
run = Path(a.run)
it = Items()
rows = [json.loads(l) for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("drops") is not None]
mp = json.loads((ROOT / "assets" / "mcw" / "maps" / str(map_of(run)) / "map.json").read_text(encoding="utf-8"))
FH = np.array([[f["x1"], f["y1"], f["x2"], f["y2"]] if f["x1"] < f["x2"] else [f["x2"], f["y2"], f["x1"], f["y1"]]
               for f in (mp.get("footholds") or {}).values() if f["x1"] != f["x2"]], float)


def ground(mx, my):
    on = (FH[:, 0] <= mx) & (FH[:, 2] >= mx)
    if not on.any():
        return None
    ya = FH[on, 1] + (mx - FH[on, 0]) * (FH[on, 3] - FH[on, 1]) / (FH[on, 2] - FH[on, 0])
    below = ya >= my - 14
    return float(ya[below].min()) if below.any() else None


def kind(d, cam):
    n = max(1, d["n_op"])
    byb = d["box"][1] + d["box"][3] + cam[1]
    gy = ground(d["box"][0] + d["box"][2] / 2 + cam[0], byb)
    at_rest = gy is not None and -7 <= byb - gy <= 5
    u = 1 - (d["n_seen"] + d["n_abs"] + d.get("n_cd", 0) + (d.get("n_front", 0) if at_rest else 0)) / n
    if u > 0.2 or d.get("n_mob", 0) >= 0.5 * d["n_seen"]:
        return "weak"
    if at_rest:
        return "REST"
    ring = d["ring_e2"] / d["ring_n2"] if d.get("ring_n2", 0) >= 60 else 1.0
    return "AIR" if ring >= 0.3 else "weak"


if a.t:
    pick = [min(rows, key=lambda r: abs(r["t"] - float(t))) for t in a.t.split(",")]
else:
    ok = [r for r in rows if len(r["drops"]) >= a.min_drops]
    pick = [ok[int(i)] for i in np.linspace(0, len(ok) - 1, a.n + 2)[1:-1]] if ok else []
col = {"REST": (0, 255, 0), "AIR": (255, 255, 0), "weak": (0, 0, 255)}
for r in pick:
    f = frame(run, r["frame"])[:PLAY_H].copy()
    names = []
    for d in r["drops"]:
        k = kind(d, r["cam"])
        x, y, w, h = d["box"]
        cv2.rectangle(f, (x - 2, y - 2), (x + w + 1, y + h + 1), col[k], 1)
        names.append(f"{k} {it.name(d['item'])[:18] if d['item'] < 9000000 else 'meso'} at ({x}, {y}) seen {d['n_seen']}/{d['n_op']}")
    p = run / "loot" / f"eye_{a.out}_{Path(r['frame']).stem}.png"
    cv2.imwrite(str(p), f)
    print(f"{p.name} t {r['t']:.2f}: " + "; ".join(names))
