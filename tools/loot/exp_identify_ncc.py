"""E-L6b (PLAN-loot.md): name an unknown thing by SHAPE - masked normalised correlation of every exported picture
(grey, alpha > 0) over a window; for pictures that are drawn see-through (no exact colour on screen).

    python tools/loot/exp_identify_ncc.py RUN FRAME X Y [--r 44] [--top 10] [--also DIR ...]
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
ap.add_argument("--r", type=int, default=44)
ap.add_argument("--top", type=int, default=10)
ap.add_argument("--also", nargs="*", default=[])
ap.add_argument("--min-px", type=int, default=250)
a = ap.parse_args()
run = Path(a.run)
f = frame(run, a.frame)
x0, y0 = max(0, a.x - a.r), max(0, a.y - a.r)
win = cv2.cvtColor(f[y0:a.y + a.r, x0:a.x + a.r], cv2.COLOR_BGR2GRAY).astype(np.float32)
res = []
for d in [EXPORT / "png"] + [Path(p) for p in a.also]:
    for p in sorted(d.rglob("*.png")):
        pic = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if pic is None or pic.ndim != 3 or pic.shape[2] != 4:
            continue
        h, w = pic.shape[:2]
        m = pic[..., 3] > 0
        if h > win.shape[0] or w > win.shape[1] or m.sum() < a.min_px:
            continue
        g = cv2.cvtColor(pic[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32)
        if g[m].std() < 8:
            continue
        r = cv2.matchTemplate(win, g, cv2.TM_CCOEFF_NORMED, mask=m.astype(np.float32))
        r[~np.isfinite(r)] = -1
        _, sc, _, loc = cv2.minMaxLoc(r)
        res.append((float(sc), p.name, int(m.sum()), pic))
res.sort(key=lambda r: -r[0])
for sc, name, n, pic in res[:a.top]:
    print(f"   {name:44s} ncc {sc:.3f} drawn px {n} {pic.shape[1]}x{pic.shape[0]}")
tiles = [f[y0:a.y + a.r, x0:a.x + a.r]]
for r in res[:a.top]:
    pic = r[3]
    al = pic[..., 3:4] / 255.0
    tiles.append((pic[..., :3] * al + 90 * (1 - al)).astype(np.uint8))
out = run / "loot" / f"identify_ncc_{Path(a.frame).stem}_{a.x}_{a.y}.png"
cv2.imwrite(str(out), sheet(tiles, cols=11, scale=3, labels=["frame"] + [r[1][:14] for r in res[:a.top]]))
print("->", out)
