"""Helper (PLAN-loot.md): a strip of crops at one MAP place over time, for the eye.

    python tools/loot/exp_strip.py RUN MX MY T0 T1 [--n 16] [--w 120] [--h 110] [--find all] [--scale 2] [--out NAME]

MX, MY = map x / y of the crop's bottom-centre (as exp_residue / exp_tracks print). One tile per picked frame between
T0 and T1 (evenly), labelled with its time. -> RUN/loot/strip_<NAME>.png
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, sheet  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("mx", type=float)
ap.add_argument("my", type=float)
ap.add_argument("t0", type=float)
ap.add_argument("t1", type=float)
ap.add_argument("--n", type=int, default=16)
ap.add_argument("--w", type=int, default=120)
ap.add_argument("--h", type=int, default=110)
ap.add_argument("--find", default="all")
ap.add_argument("--scale", type=int, default=2)
ap.add_argument("--cols", type=int, default=8)
ap.add_argument("--out", default="")
ap.add_argument("--screen-at", type=float, default=-1.0,
                help="MX MY are SCREEN x / y at this time (the camera of the nearest frame makes them map x / y)")
ap.add_argument("--boxes", action="store_true", help="draw the finder's drops (green) on the tiles")
a = ap.parse_args()
run = Path(a.run)
rows = [json.loads(l) for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("cam")]
if a.screen_at >= 0:
    r0 = min(rows, key=lambda r: abs(r["t"] - a.screen_at))
    a.mx, a.my = a.mx + r0["cam"][0], a.my + r0["cam"][1]
    print(f"map place ({a.mx:.0f}, {a.my:.0f})")
rows = [r for r in rows if a.t0 <= r["t"] <= a.t1]
pick = [rows[int(i)] for i in np.linspace(0, len(rows) - 1, min(a.n, len(rows)))] if rows else []
tiles, labels = [], []
for r in pick:
    f = frame(run, r["frame"])
    if a.boxes:
        f = f.copy()
        for d in r.get("drops") or []:
            x, y, w, h = d["box"]
            cv2.rectangle(f, (x - 1, y - 1), (x + w, y + h), (0, 255, 0), 1)
    cx, by = int(round(a.mx - r["cam"][0])), int(round(a.my - r["cam"][1]))
    x0, y0 = cx - a.w // 2, by - a.h + 16
    crop = np.zeros((a.h, a.w, 3), np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(f.shape[1], x0 + a.w), min(f.shape[0], y0 + a.h)
    if sx1 > sx0 and sy1 > sy0:
        crop[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = f[sy0:sy1, sx0:sx1]
    tiles.append(crop)
    labels.append(f"t {r['t']:.2f}")
p = run / "loot" / f"strip_{a.out or f'{int(a.mx)}_{int(a.my)}_{int(a.t0)}'}.png"
cv2.imwrite(str(p), sheet(tiles, cols=a.cols, labels=labels, scale=a.scale))
print("->", p, len(tiles), "tiles")
