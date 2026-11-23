"""PLAN-moving-scenery.md step 3's gate, the sightings: the kept replay (the live Perceiver with the movers followed,
tools/perc/track/dump.py) against run_fit.py (the prototype: A today's picture, B the movers drawn at the
reference's places) on the same frames.
    python tools/perc/scenery/run_fit.py CAP --every K          (first: -> OUT/fit_<cap>.json)
    python tools/perc/scenery/live3.py CAP [CAP ...] [--sheet 40] [--seed 0]
Per capture: the live sightings on run_fit's frames against B's and A's counts (the gate: live >= 99 % of B); the
live sightings A does not give (no mob of the same type within 12 px). With --sheet N: N of those, at random over
all the captures, cut out of their frames with the mob's feet marked -> OUT/live3_sheet_<k>.png for the look by
eye (a ghost = no mob there)."""
import argparse
import json
import random
import sys

import cv2
import numpy as np

import msl
sys.path.insert(0, str(msl.ROOT / "tools" / "perc" / "track"))
from dump import rows as kept_rows      # noqa: E402

ASSETS = msl.ROOT / "assets" / "mcw"


def match(A, B, r=12):
    """Mobs of A (dicts) with no mob of the same type within r px in B."""
    return [m for m in A if not any(n["type"] == m["type"] and abs(n["feet"][0] - m["feet"][0]) <= r
                                    and abs(n["feet"][1] - m["feet"][1]) <= r for n in B)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="+")
    ap.add_argument("--sheet", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    pool, tot = [], {"live": 0, "A": 0, "B": 0, "new": 0, "frames": 0}
    for cap in a.caps:
        fit = json.loads((msl.OUT / f"fit_{cap.replace('#', '_')}.json").read_text())
        kr = kept_rows(cap)
        c = msl.clip(cap)
        fr = c.frames()
        assert len(kr) == len(fr), (cap, len(kr), len(fr))
        nl = nA = nB = nn = 0
        for r in fit:
            i = r["i"]
            assert kr[i]["frame"] == fr[i][1]
            live = kr[i]["facts"].get("fit") or []
            nl += len(live)
            nA += len(r["A"])
            nB += len(r["B"])
            new = match(live, r["A"])
            nn += len(new)
            pool += [(cap, i, m) for m in new]
        print(f"{cap}: map {c.map_id}, {len(fit)} frames: sightings live {nl}, run_fit B {nB} -> live / B "
              f"{100 * nl / max(1, nB):.1f} %; A (today's picture) {nA}; live ones A does not give {nn}")
        for k, v in (("live", nl), ("A", nA), ("B", nB), ("new", nn), ("frames", len(fit))):
            tot[k] += v
    print(f"all: {tot['frames']} frames, live {tot['live']}, B {tot['B']} ({100 * tot['live'] / max(1, tot['B']):.1f} %), "
          f"A {tot['A']}, live not in A {tot['new']}")
    if not a.sheet:
        return
    random.seed(a.seed)
    pick = random.sample(pool, min(a.sheet, len(pool)))
    names, tiles = {}, []
    for k, (cap, i, m) in enumerate(pick):
        c = msl.clip(cap)
        img = c.read(c.frames()[i][1])
        x, y = int(m["feet"][0]), int(m["feet"][1])
        x0, y0 = max(0, min(1366 - 240, x - 120)), max(0, min(700 - 180, y - 140))
        crop = img[y0:y0 + 180, x0:x0 + 240].copy()
        cv2.drawMarker(crop, (x - x0, y - y0), (0, 255, 0), cv2.MARKER_CROSS, 10, 1)
        t = m["type"]
        if t not in names:
            p = ASSETS / "mobs" / str(t) / "mob.json"
            names[t] = json.loads(p.read_text(encoding="utf-8")).get("name") if p.exists() else str(t)
        crop = cv2.resize(crop, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST)
        lab = f"{k}: {names[t]} {m['pose']} seen {m.get('seen', 0):.2f} {cap} fr {i}"
        cv2.putText(crop, lab, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 3)
        cv2.putText(crop, lab, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        tiles.append(crop)
    for s in range(0, len(tiles), 10):
        p = msl.save(f"live3_sheet_{s // 10}.png", msl.tile(tiles[s:s + 10], cols=5))
        print("  sheet ->", p)


if __name__ == "__main__":
    main()
