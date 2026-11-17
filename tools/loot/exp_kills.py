"""E-L0 (PLAN-loot.md): what happens on screen where a mob died - a strip of crops per death, at fixed MAP position.

    python tools/loot/exp_kills.py RUN [--n 12] [--t0 S] [--dts 0.2,0.5,...] [--out NAME]

A death = a track's first tick in state "dying" (the recording's own tracker). Per death one row: the crop around its
map position (camera of each saved frame) at death + dts seconds. Writes RUN/loot/kills_<NAME>.png.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, run_ticks  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--n", type=int, default=12)
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--dts", default="0.0,0.3,0.6,0.9,1.2,1.6,2.0,3.0,5.0")
ap.add_argument("--w", type=int, default=180)
ap.add_argument("--h", type=int, default=130)
ap.add_argument("--out", default="a")
a = ap.parse_args()
run = Path(a.run)
dts = [float(x) for x in a.dts.split(",")]
ticks = [k for k in run_ticks(run) if k["cam"] is not None]
ts = np.array([k["t"] for k in ticks])
seen, deaths = set(), []
for k in ticks:
    for m in k["mobs"]:
        if m.get("state") == "dying" and m["id"] not in seen and k["t"] >= a.t0:
            seen.add(m["id"])
            deaths.append((k["t"], m["sx"] + k["cam"][0], m["sy"] + k["cam"][1], m["id"], m.get("mob")))
print(f"{run.name}: {len(ticks)} saved frames with a camera, {len(deaths)} deaths (first dying tick)")
step = max(1, len(deaths) // a.n)
rows = []
for t, mx, my, tid, mob in deaths[::step][:a.n]:
    tiles = []
    for dt in dts:
        i = int(np.argmin(np.abs(ts - (t + dt))))
        k = ticks[i]
        if abs(k["t"] - (t + dt)) > 0.25:
            tiles.append(np.zeros((a.h, a.w, 3), np.uint8))
            continue
        f = frame(run, k["frame"])
        x, y = int(round(mx - k["cam"][0])), int(round(my - k["cam"][1]))
        x0, y0 = x - a.w // 2, y - a.h + 30
        crop = np.zeros((a.h, a.w, 3), np.uint8)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(f.shape[1], x0 + a.w), min(f.shape[0], y0 + a.h)
        if sx1 > sx0 and sy1 > sy0:
            crop[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = f[sy0:sy1, sx0:sx1]
        cv2.putText(crop, f"+{dt:.1f}", (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        tiles.append(crop)
    row = np.concatenate(tiles, axis=1)
    cv2.putText(row, f"t {t:.1f} #{tid} mob {mob}", (3, a.h - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    rows.append(row)
out = run / "loot"
out.mkdir(exist_ok=True)
p = out / f"kills_{a.out}.png"
cv2.imwrite(str(p), np.concatenate(rows, axis=0))
print("->", p)
