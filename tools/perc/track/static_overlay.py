"""Tracker plan, Part 2: WHAT IS ALWAYS DRAWN OVER THE WORLD AND NOT MASKED. Screen pixels the kept replay calls
judgeable (`world`) that almost never show the scene (`shows`) although the camera moves: parts of the UI the
mask misses (the minimap window's edge, keycaps, ...). A track remembered there can never be checked.

    python tools/perc/track/static_overlay.py CAP [--every 30] [--share 0.9] [--png OUT.png]

Prints the pixels, their connected areas (screen boxes) and how far the camera moved over the sample.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dump  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--share", type=float, default=0.9)
    ap.add_argument("--png", default=None)
    a = ap.parse_args()
    rows = {r["n"]: r["C"] for r in dump.rows(a.cap)}
    busy = np.zeros((700, 1366), np.int32)
    world = np.zeros((700, 1366), np.int32)
    n, cams = 0, []
    for k, (num, sh, wo) in enumerate(dump.bits_rows(a.cap, packed=True)):
        if k % a.every or sh is None:
            continue
        s, w = dump.bits(sh), dump.bits(wo)
        busy += w & ~s
        world += w
        n += 1
        cams.append(rows[num])
    cams = np.array(cams, float)
    print(f"{a.cap}: {n} frames sampled; the camera spans {np.ptp(cams[:, 0]):.0f} x {np.ptp(cams[:, 1]):.0f} map px")
    always_world = world >= a.share * n
    static = always_world & (busy >= a.share * world)
    print(f"  judgeable on >= {a.share:.0%} of frames: {int(always_world.sum())} px; of them never showing the scene: {int(static.sum())} px")
    never_world = world <= (1 - a.share) * n
    print(f"  never judgeable (masked UI / unknown scenery at a fixed screen place): {int(never_world.sum())} px")
    nlab, lab, st, _ = cv2.connectedComponentsWithStats(static.astype(np.uint8), connectivity=8)
    areas = sorted(((int(st[i, 4]), tuple(int(v) for v in st[i, :4])) for i in range(1, nlab)), reverse=True)
    for ar, (x, y, w, h) in areas[:20]:
        print(f"     {ar:6d} px  screen box x {x}-{x + w} y {y}-{y + h}")
    print(f"  areas: {len(areas)}; in the 20 largest: {sum(a_ for a_, _ in areas[:20])} px")
    if a.png:
        img = np.zeros((700, 1366, 3), np.uint8)
        img[never_world] = (90, 90, 90)
        img[static] = (0, 0, 255)
        Path(a.png).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(a.png, img)
        print("  ->", a.png, "(grey: masked; red: judgeable but never the scene)")


if __name__ == "__main__":
    main()
