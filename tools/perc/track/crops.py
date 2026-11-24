"""Tracker plan: crops of a capture's frames around a MAP place, side by side, for a look by eye.

    python tools/perc/track/crops.py CAP OUT.png MAPX MAPY N [N ...] [--w 320 --h 240 --zoom 2]

Each N is a frame number of the session (the kept replay's `n`); the crop follows the map place (x, y) through
the camera, a cross marks it. Frames without a camera are skipped.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dump  # noqa: E402


def crops(cap, mx, my, ns, w=320, h=240, zoom=2):
    import frames as rec
    c = dump.clip_of(cap)
    want = set(ns)
    rows = {r["n"]: r for r in dump.rows(cap) if r["n"] in want}
    out = []
    for n in ns:
        r = rows.get(n)
        if r is None or r["C"] is None:
            continue
        img = rec.read(c.run, r["frame"])
        sx, sy = int(mx - r["C"][0]), int(my - r["C"][1])
        pad = cv2.copyMakeBorder(img, h, h, w, w, cv2.BORDER_CONSTANT, value=(60, 0, 60))
        cr = pad[sy + h - h // 2:sy + h + h // 2, sx + w - w // 2:sx + w + w // 2].copy()
        cv2.drawMarker(cr, (w // 2, h // 2), (0, 255, 255), cv2.MARKER_CROSS, 14, 1)
        cr = cv2.resize(cr, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
        cv2.putText(cr, f"n {n} t {r['t']:.2f} screen ({sx}, {sy})", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        out.append(cr)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("out")
    ap.add_argument("mx", type=float)
    ap.add_argument("my", type=float)
    ap.add_argument("ns", type=int, nargs="+")
    ap.add_argument("--w", type=int, default=320)
    ap.add_argument("--h", type=int, default=240)
    ap.add_argument("--zoom", type=int, default=2)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--at", type=int, default=None, help="MAPX MAPY are SCREEN px on this frame number")
    a = ap.parse_args()
    if a.at is not None:
        r = next(x for x in dump.rows(a.cap) if x["n"] == a.at)
        a.mx, a.my = a.mx + r["C"][0], a.my + r["C"][1]
    cs = crops(a.cap, a.mx, a.my, a.ns, a.w, a.h, a.zoom)
    rows = []
    for k in range(0, len(cs), a.cols):
        row = cs[k:k + a.cols]
        while len(row) < a.cols:
            row.append(np.zeros_like(cs[0]))
        rows.append(np.hstack(row))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(a.out, np.vstack(rows))
    print(a.out, len(cs), "crops")


if __name__ == "__main__":
    main()
