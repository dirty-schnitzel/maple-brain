"""A contact sheet of one drop's last moments at the full frame rate: crops around its map place, one per frame
(the camera of each frame = the replay rows', interpolated). Used 2026-11-21 for PLAN-loot.md section 13: an expiring
drop fades out in place over ~1 s; a picked-up one hops up for ~0.5 s, then fades in ~0.15 s.

    python tools/loot/end_sheet.py SESSION#K ROWS.jsonl T_END MX MY OUT.png [--before 0.5 --after 0.6 --half 44 --scale 2]
"""
import argparse
import bisect
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import frames as F  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("rows")
    ap.add_argument("t", type=float)
    ap.add_argument("mx", type=float)
    ap.add_argument("my", type=float)
    ap.add_argument("out")
    ap.add_argument("--before", type=float, default=0.5)
    ap.add_argument("--after", type=float, default=0.6)
    ap.add_argument("--half", type=int, default=44)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--cols", type=int, default=12)
    a = ap.parse_args()
    cams = []
    with open(a.rows, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("cam") is not None and a.t - a.before - 1 <= r["t"] <= a.t + a.after + 1:
                cams.append((r["t"], r["cam"][0], r["cam"][1]))
    ts = [c[0] for c in cams]
    c = F.clip(a.clip, False, "drop_end_sheet")
    fr = c.frames(a.t - a.before, a.t + a.after, a.every)
    tiles = []
    h = a.half
    for n, name, t in fr:
        img = c.read(name)
        if img is None:
            continue
        k = min(len(ts) - 1, max(1, bisect.bisect_left(ts, t)))
        (t0, x0, y0), (t1, x1, y1) = cams[k - 1], cams[k]
        w = 0.0 if t1 == t0 else min(1.0, max(0.0, (t - t0) / (t1 - t0)))
        cx, cy = x0 + w * (x1 - x0), y0 + w * (y1 - y0)
        sx, sy = int(round(a.mx - cx)), int(round(a.my - cy)) - 14
        pad = cv2.copyMakeBorder(img, h, h, h, h, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        crop = pad[sy:sy + 2 * h, sx:sx + 2 * h]
        if crop.shape[:2] != (2 * h, 2 * h):
            crop = np.zeros((2 * h, 2 * h, 3), np.uint8)
        crop = cv2.resize(crop, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_NEAREST)
        cv2.putText(crop, f"{t - a.t:+.2f}", (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
        tiles.append(crop)
    if not tiles:
        raise SystemExit("no frames")
    cols = a.cols
    rows = [np.hstack(tiles[i:i + cols] + [np.zeros_like(tiles[0])] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    cv2.imwrite(a.out, np.vstack(rows))
    print(f"{len(tiles)} frames -> {a.out}")


if __name__ == "__main__":
    main()
