"""Tracker plan, Part 2: THE PROTOTYPE'S MEMORY, BY EYE. Random times a track was remembered (not seen, kept),
by how that ended, each as one row of crops: the frame it was last seen on, the middle of the time it was
remembered, the frame it ended on, half a second later.

    python tools/perc/track/mem_sheet.py CAP [--n 8] [--seed 1] [--min 0.3] [--set key=value ...]

Writes F:/dev/maple-corpus/work/track-plan/mobs/mem_<CAP>_<class>.png and prints each row's case (track id,
frames, seconds, cover, where it was seen again). Classes: seen again (0.3 s or more unseen), found gone (its
places showed the scene), limit (4 s: drawn over / nothing to check).
"""
import argparse
import random
import sys
from dataclasses import fields
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dump  # noqa: E402
import proto_mobs as P  # noqa: E402

OUT = Path(r"F:\dev\maple-corpus\work\track-plan\mobs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cap")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--min", type=float, default=0.3)
    ap.add_argument("--set", nargs="*", default=[])
    a = ap.parse_args()
    cfg = P.Cfg()
    types = {f.name: f.type for f in fields(P.Cfg)}
    for kv in a.set:
        k, v = kv.split("=")
        setattr(cfg, k, (v == "True") if types[k] is bool else types[k](v))
    rows, trk, _ = P.run(a.cap, cfg)
    import frames as rec
    c = dump.clip_of(a.cap)
    rws = {r["n"]: r for r in dump.rows(a.cap)}
    ns = sorted(rws)
    cls = {"seen again": [], "found gone": [], "limit": []}
    for e in trk.episodes:
        how = e[5]
        if how == "seen again" and e[7] >= a.min:
            cls["seen again"].append(e)
        elif how.startswith("gone: its places"):
            cls["found gone"].append(e)
        elif how.startswith(("gone: drawn", "left")) and "out of view" not in how:
            cls["limit"].append(e)
    rnd = random.Random(a.seed)
    W, H, Z = 300, 220, 2
    for name, es in cls.items():
        pick = rnd.sample(es, min(a.n, len(es)))
        print(f"{name}: {len(es)} cases, {len(pick)} shown")
        strips = []
        for k, e in enumerate(pick):
            tid, n0, n1, x, y, how, cover, secs, xa, ya = e
            mid = ns[(ns.index(n0) + ns.index(n1)) // 2]
            after = ns[min(len(ns) - 1, ns.index(n1) + 30)]
            crops = []
            for n in (n0, mid, n1, after):
                r = rws[n]
                if r["C"] is None:
                    crops.append(np.zeros((H * Z, W * Z, 3), np.uint8))
                    continue
                img = rec.read(c.run, r["frame"])
                sx, sy = int(x - r["C"][0]), int(y - r["C"][1])
                pad = cv2.copyMakeBorder(img, H, H, W, W, cv2.BORDER_CONSTANT, value=(60, 0, 60))
                cr = np.ascontiguousarray(pad[max(0, sy + H - H // 2):max(0, sy + H + H // 2), max(0, sx + W - W // 2):max(0, sx + W + W // 2)])
                if cr.shape[:2] != (H, W):                 # the place is far off the screen on this frame
                    cr = np.full((H, W, 3), (60, 0, 60), np.uint8)
                cv2.drawMarker(cr, (W // 2, H // 2), (0, 255, 255), cv2.MARKER_CROSS, 14, 1)
                if xa is not None and n in (n1, after):
                    cv2.drawMarker(cr, (W // 2 + int(xa - x), H // 2 + int(ya - y)), (0, 255, 0), cv2.MARKER_TILTED_CROSS, 12, 1)
                cr = cv2.resize(cr, None, fx=Z, fy=Z, interpolation=cv2.INTER_NEAREST)
                cv2.putText(cr, f"#{k} n {n}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                crops.append(cr)
            strips.append(np.hstack(crops))
            print(f"   #{k}: track {tid}, frames {n0}-{n1} ({secs} s), last seen at map ({x}, {y}), {how}, cover {cover}"
                  + (f", seen again at ({xa}, {ya})" if xa is not None else ""))
        if strips:
            p = OUT / f"mem_{a.cap.replace('#', '_')}_{name.replace(' ', '_')}.png"
            cv2.imwrite(str(p), np.vstack(strips))
            print("  ->", p)


if __name__ == "__main__":
    main()
