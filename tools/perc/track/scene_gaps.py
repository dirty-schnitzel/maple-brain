"""Tracker plan, Part 2: WHERE ON THE MAP THE FRAME NEVER SHOWS THE SCENE MODEL. Map places (8 px cells) that the
kept replay judges ("world") on many frames and that almost never equal the expected scene: not a mob (mobs
move) but a gap of the scene model - an animated object, a piece drawn in another order. There the fit cannot see
a mob and the tracker cannot check a remembered one.

    python tools/perc/track/scene_gaps.py CAP [--every 10] [--share 0.9] [--visits 60] [--png OUT.png]

Prints the gaps' area and largest boxes (map px), and how much of the truth's mob-time falls on them: sightings
whose feet stand on a gap cell, and the frames a mob was alive but unseen (the truth's gaps) on one.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache  # noqa: E402
import dump  # noqa: E402
import score as S  # noqa: E402
from load import ticks  # noqa: E402

CELL = 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--share", type=float, default=0.9)
    ap.add_argument("--visits", type=int, default=60)
    ap.add_argument("--png", default=None)
    a = ap.parse_args()
    rows = {r["n"]: r["C"] for r in dump.rows(a.cap)}
    cams = np.array([c for c in rows.values() if c is not None], float)
    x0, y0 = int(cams[:, 0].min()) // CELL * CELL, int(cams[:, 1].min()) // CELL * CELL
    W = (int(cams[:, 0].max()) + 1366 - x0) // CELL + 2
    H = (int(cams[:, 1].max()) + 700 - y0) // CELL + 2
    busy, seen = np.zeros((H, W), np.int32), np.zeros((H, W), np.int32)
    n = 0
    for k, (num, sh, wo) in enumerate(dump.bits_rows(a.cap, packed=True)):
        if k % a.every or sh is None:
            continue
        s, w = dump.bits(sh), dump.bits(wo)
        C = rows[num]
        ox, oy = (int(C[0]) - x0) % CELL, (int(C[1]) - y0) % CELL          # align the screen to the map's cells
        b = (w & ~s)[(CELL - oy) % CELL:, (CELL - ox) % CELL:]
        ww = w[(CELL - oy) % CELL:, (CELL - ox) % CELL:]
        hh, wd = b.shape[0] // CELL, b.shape[1] // CELL
        bc = b[:hh * CELL, :wd * CELL].reshape(hh, CELL, wd, CELL).mean(axis=(1, 3))
        wc = ww[:hh * CELL, :wd * CELL].reshape(hh, CELL, wd, CELL).mean(axis=(1, 3))
        cy = (int(C[1]) + (CELL - oy) % CELL - y0) // CELL
        cx = (int(C[0]) + (CELL - ox) % CELL - x0) // CELL
        judged = wc >= 0.75
        seen[cy:cy + hh, cx:cx + wd] += judged
        busy[cy:cy + hh, cx:cx + wd] += judged & (bc >= 0.5)
        n += 1
    gap = (seen >= a.visits) & (busy >= a.share * seen)
    known = seen >= a.visits
    print(f"{a.cap}: {n} frames sampled; map cells judged on {a.visits}+ of them: {int(known.sum())} ({int(known.sum()) * CELL * CELL} px2); "
          f"never the scene on {a.share:.0%}+: {int(gap.sum())} cells = {int(gap.sum()) * CELL * CELL} px2 ({100 * gap.sum() / max(1, known.sum()):.2f} %)")
    nlab, lab, st, _ = cv2.connectedComponentsWithStats(gap.astype(np.uint8), connectivity=8)
    areas = sorted(((int(st[i, 4]), tuple(int(v) for v in st[i, :4])) for i in range(1, nlab)), reverse=True)
    for ar, (x, y, w, h) in areas[:12]:
        print(f"     {ar * CELL * CELL:7d} px2  map box x {x0 + x * CELL}..{x0 + (x + w) * CELL}  y {y0 + y * CELL}..{y0 + (y + h) * CELL}")
    # ---- the truth's mob-time on the gaps (a mob's body: the 48 x 40 px over its feet)
    tk = ticks(a.cap)
    ch = cache.chains(a.cap, tk)

    def on_gap(x, y) -> bool:
        cx, cy = int(x - x0) // CELL, int(y - y0) // CELL
        sub = gap[max(0, cy - 5):cy + 1, max(0, cx - 3):cx + 4]
        return sub.size > 0 and sub.mean() >= 0.3
    seen_on = seen_all = gap_on = gap_all = 0
    for ci in S.index(tk, ch):
        for i, q in ci["pts"].items():
            seen_all += 1
            seen_on += on_gap(q[S.X], q[S.Y])
        for ga, gb in ci["gaps"]:
            for i in range(ga + 1, gb):
                if tk[i]["C"] is None:
                    continue
                p = S.pos_at(ci, i)
                sx, sy = p[0] - tk[i]["C"][0], p[1] - tk[i]["C"][1]
                if 30 <= sx < 1336 and 60 <= sy < 690:                      # in view
                    gap_all += 1
                    gap_on += on_gap(*p)
    print(f"  the truth's sightings with the body on a gap: {seen_on} of {seen_all} ({100 * seen_on / max(1, seen_all):.2f} %)")
    print(f"  frames a mob was alive, in view and NOT seen: {gap_all}; with the body on a gap: {gap_on} ({100 * gap_on / max(1, gap_all):.1f} %)")
    if a.png:
        img = np.zeros((H, W, 3), np.uint8)
        img[known] = (70, 70, 70)
        img[gap] = (0, 0, 255)
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        Path(a.png).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(a.png, img)
        print("  ->", a.png)


if __name__ == "__main__":
    main()
