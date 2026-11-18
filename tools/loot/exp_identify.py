"""E-L6 (PLAN-loot.md): name an unknown thing on a frame - brute force over EVERY exported picture (iconRaw and
icon of all kinds, the meso frames), no vote: per picture the best placement in a window by the count of its drawn
pixels (alpha > 0) the frame shows within tol, alpha-aware (a see-through pixel is compared as s over the frame's own
neighbourhood: skipped; only alpha 255 pixels count, the rest reported).

    python tools/loot/exp_identify.py RUN FRAME X Y [--r 40] [--top 8] [--also DIR]

X, Y = the thing's centre on screen. Prints the best pictures: exact opaque pixels / opaque pixels, and saves a
sheet (the crop 4x + the top pictures) to RUN/loot/identify_<FRAME>_<X>_<Y>.png. --also: another folder of PNGs to
try too (e.g. an export of Item/Cash).
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import EXPORT, frame, sheet  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("frame")
ap.add_argument("x", type=int)
ap.add_argument("y", type=int)
ap.add_argument("--r", type=int, default=40)
ap.add_argument("--top", type=int, default=8)
ap.add_argument("--also", default="")
a = ap.parse_args()
run = Path(a.run)
f = frame(run, a.frame)
x0, y0 = max(0, a.x - a.r), max(0, a.y - a.r)
win = f[y0:a.y + a.r, x0:a.x + a.r].astype(np.int16)
res = []
dirs = [EXPORT / "png"] + ([Path(a.also)] if a.also else [])
for d in dirs:
    for p in sorted(d.rglob("*.png")):
        pic = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if pic is None or pic.ndim != 3 or pic.shape[2] != 4:
            continue
        h, w = pic.shape[:2]
        if h > win.shape[0] or w > win.shape[1] or h < 6 or w < 6:
            continue
        op = pic[..., 3] == 255
        n = int(op.sum())
        if n < 30:
            continue
        s = pic[..., :3].astype(np.int16)
        best = (0, 0, 0)
        for dy in range(win.shape[0] - h + 1):
            for dx in range(0, win.shape[1] - w + 1):
                m = int(((np.abs(win[dy:dy + h, dx:dx + w] - s).max(axis=2) <= 4) & op).sum())
                if m > best[0]:
                    best = (m, dx, dy)
        res.append((best[0] / n, best[0], n, p.name, best[1] + x0, best[2] + y0, pic))
res.sort(key=lambda r: (-r[0], -r[1]))
for sh, m, n, name, bx, by, pic in res[:a.top]:
    print(f"   {name:28s} exact {m} / {n} = {100 * sh:.1f} % at ({bx}, {by}) {pic.shape[1]}x{pic.shape[0]}")
tiles = [f[y0:a.y + a.r, x0:a.x + a.r]]
for r in res[:a.top]:
    pic = r[6]
    al = pic[..., 3:4] / 255.0
    tiles.append((pic[..., :3] * al + 90 * (1 - al)).astype(np.uint8))
out = run / "loot" / f"identify_{Path(a.frame).stem}_{a.x}_{a.y}.png"
cv2.imwrite(str(out), sheet(tiles, cols=9, scale=4, labels=["frame"] + [r[3][:12] for r in res[:a.top]]))
print("->", out)
