"""Helper (PLAN-loot.md): save a crop of a frame (screen coordinates), optionally scaled, with the finder's drops of
that frame boxed.

    python tools/loot/exp_crop.py RUN FRAME X0 Y0 X1 Y1 [--scale 2] [--find NAME] [--out FILE]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("frame")
ap.add_argument("box", type=int, nargs=4)
ap.add_argument("--scale", type=int, default=2)
ap.add_argument("--find", default="")
ap.add_argument("--out", default="")
a = ap.parse_args()
run = Path(a.run)
f = frame(run, a.frame).copy()
if a.find:
    for l in open(run / "loot" / f"find_{a.find}.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r["frame"] == a.frame:
            for d in r.get("drops") or []:
                x, y, w, h = d["box"]
                cv2.rectangle(f, (x - 1, y - 1), (x + w, y + h), (0, 255, 0), 1)
            break
x0, y0, x1, y1 = a.box
c = cv2.resize(f[y0:y1, x0:x1], None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_NEAREST)
out = a.out or str(run / "loot" / f"crop_{Path(a.frame).stem}_{x0}_{y0}.png")
cv2.imwrite(out, c)
print("->", out)
