"""Helper (PLAN-loot.md): every PNG of a folder (optionally a name filter) on one sheet, over grey, labelled.

    python tools/loot/exp_pngsheet.py DIR OUT.png [--filter TEXT] [--cols 12] [--scale 2] [--max 200]
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import sheet  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("dir")
ap.add_argument("out")
ap.add_argument("--filter", default="")
ap.add_argument("--cols", type=int, default=12)
ap.add_argument("--scale", type=int, default=2)
ap.add_argument("--max", type=int, default=200)
a = ap.parse_args()
tiles, labels = [], []
for p in sorted(Path(a.dir).rglob("*.png")):
    if a.filter and a.filter not in p.name:
        continue
    pic = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if pic is None or pic.ndim != 3:
        continue
    if pic.shape[2] == 4:
        al = pic[..., 3:4] / 255.0
        pic = (pic[..., :3] * al + 90 * (1 - al)).astype(np.uint8)
    tiles.append(pic)
    labels.append(p.stem[-14:])
    if len(tiles) >= a.max:
        break
cv2.imwrite(a.out, sheet(tiles, cols=a.cols, labels=labels, scale=a.scale))
print(len(tiles), "pictures ->", a.out)
