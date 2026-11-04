"""Tracks drawn on frames, for checking by eye: python tools/perc/track_draw.py RUN OUTDIR [--every 160] [--per 3]
green = seen by the whole-screen pass, cyan = seen by the search around its track, yellow = coasting (unseen),
red = tentative. Label: id, type letter, anim, score. Crops the band y 360..660 (where mobs walk on most maps)."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

COL = {"acq": (0, 220, 0), "near": (255, 220, 0), "none": (0, 220, 255)}

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("out")
ap.add_argument("--every", type=int, default=160)
ap.add_argument("--per", type=int, default=3)
ap.add_argument("--y0", type=int, default=360)
ap.add_argument("--y1", type=int, default=660)
a = ap.parse_args()
run, out = Path(a.run), Path(a.out)
out.mkdir(parents=True, exist_ok=True)
rows = [json.loads(l) for l in open(run / "tracks.jsonl", encoding="utf-8")][::a.every]
tiles = []
for r in rows:
    f = cv2.imread(str(run / "frames" / r["frame"]))
    for t in r["tracks"]:
        c = (0, 0, 255) if t["state"] == "tentative" else COL[t["src"]]
        x, y = int(t["sx"]), int(t["sy"])
        cv2.rectangle(f, (x - 28, y - 50), (x + 28, y), c, 2)
        cv2.putText(f, f"{t['id']}{'P' if t['mob'] == 8 else 'R'} {t['anim'][:4]} {t['score']:.2f}", (x - 28, y + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, c, 1)
    if r.get("me"):
        cv2.drawMarker(f, (int(r["me"][0]), int(r["me"][1])), (255, 0, 255), cv2.MARKER_TRIANGLE_UP, 14, 2)
    crop = f[a.y0:a.y1].copy()
    cv2.putText(crop, f"n {r['n']} t {r['t']:.1f}", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    tiles.append(crop)
for i in range(0, len(tiles), a.per):
    group = tiles[i:i + a.per]
    cv2.imwrite(str(out / f"audit_{i // a.per:02d}.jpg"), np.vstack(group), [cv2.IMWRITE_JPEG_QUALITY, 90])
print(len(tiles), "frames ->", out)
