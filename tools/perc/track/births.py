"""Tracker plan, Part 2: WHICH SIGHTINGS MAY START A TRACK. The truth's chains by length, and what the first
sightings of short chains (1-3 frames: mostly false sightings of the fit) and of long ones (real mobs) look like:
the share of the body box on screen, the SEEN pixels against the kind's full size.

    python tools/perc/track/births.py CAP [CAP ...] | --sound
"""
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache  # noqa: E402
from load import Map, map_of, ticks  # noqa: E402
from oracle import NS, POSE, SX, SY, T  # noqa: E402

SW, PLAY_H = 1366, 700


def onscreen(m, sx, sy) -> float:
    fr = m.get("frames") or {}
    f0 = (fr.get("stand") or fr.get("move") or fr.get("fly") or [{}])[0]
    lt, rb = f0.get("lt") or [-30, -50], f0.get("rb") or [30, 0]
    w, h = max(1, rb[0] - lt[0]), max(1, rb[1] - lt[1])
    x0, y0 = sx + lt[0], sy + lt[1]
    return max(0.0, min(x0 + w, SW) - max(x0, 0)) * max(0.0, min(y0 + h, PLAY_H) - max(y0, 0)) / (w * h)


def main():
    caps = cache.SOUND if "--sound" in sys.argv else [a for a in sys.argv[1:] if not a.startswith("--")]
    short, long_first, long_all = [], [], []
    lens = Counter()
    k_need = Counter()
    for cap in caps:
        tk = ticks(cap)
        mp = Map(map_of(cap))
        ch = cache.chains(cap, tk)
        full = {}
        for c in ch:
            for p in c["parts"]:
                for q in p["pts"]:
                    full[c["type"]] = max(full.get(c["type"], 1), q[NS])
        for c in ch:
            pts = [q for p in c["parts"] for q in p["pts"]]
            n = len(pts)
            lens["1" if n == 1 else "2-3" if n <= 3 else "4-9" if n <= 9 else "10-29" if n <= 29 else "30+"] += 1
            m = mp.mobs[c["type"]]
            rec = [(onscreen(m, q[SX], q[SY]), q[NS] / full[c["type"]], q[POSE].startswith("die"), q[T]) for q in pts]
            if n <= 3:
                short += [(r[0], r[1], r[2], cap, round(pts[0][T], 2), int(pts[0][SX]), int(pts[0][SY]), n) for r in rec[:1]]
            elif n >= 30:
                long_first.append(rec[0][:2])
                long_all += [r[:2] for r in rec]
                # frames until a sighting with >= 25 % of the full size and >= 30 % on screen
                k = next((i for i, r in enumerate(rec) if r[1] >= 0.25 and r[0] >= 0.3), None)
                k_need["never" if k is None else "0" if k == 0 else "1-2" if k <= 2 else "3-5" if k <= 5 else "6-15" if k <= 15 else "16+"] += 1
    print("chains by length (frames):", dict(lens))
    s = np.array([(a, b) for a, b, *_ in short]) if short else np.zeros((0, 2))
    lf, la = np.array(long_first), np.array(long_all)

    def table(name, v):
        if not len(v):
            return
        print(f"  {name} (n {len(v)}): on-screen share < 0.3: {np.mean(v[:, 0] < 0.3):.1%}, 0.3-0.6: {np.mean((v[:, 0] >= 0.3) & (v[:, 0] < 0.6)):.1%}, "
              f">= 0.6: {np.mean(v[:, 0] >= 0.6):.1%} | SEEN / full < 0.1: {np.mean(v[:, 1] < 0.1):.1%}, 0.1-0.25: "
              f"{np.mean((v[:, 1] >= 0.1) & (v[:, 1] < 0.25)):.1%}, 0.25-0.5: {np.mean((v[:, 1] >= 0.25) & (v[:, 1] < 0.5)):.1%}, >= 0.5: {np.mean(v[:, 1] >= 0.5):.1%}")
        for lo, hi in ((0, 0.3), (0.3, 0.6), (0.6, 1.01)):
            b = v[(v[:, 0] >= lo) & (v[:, 0] < hi)]
            if len(b):
                print(f"       on-screen {lo}-{hi}: n {len(b)}, SEEN / full p10 / p50 / p90 {[round(float(np.percentile(b[:, 1], p)), 2) for p in (10, 50, 90)]}")
    table("short chains (1-3 frames), first sighting", s)
    table("long chains (30+ frames), first sighting", lf)
    table("long chains, every sighting", la)
    print("  long chains: frames until a sighting with SEEN >= 25 % of full and >= 30 % on screen:", dict(k_need))
    die = sum(1 for x in short if x[2])
    print(f"  short chains that are a die pose: {die} of {len(short)}")
    big = [x for x in short if x[1] >= 0.25 and x[0] >= 0.3 and not x[2]]
    print(f"  short chains that would pass 'SEEN >= 25 % and on-screen >= 30 %' at once: {len(big)}")
    for x in big[:12]:
        print("      ", x[3], "t", x[4], "screen", (x[5], x[6]), "frames", x[7], "on-screen", round(x[0], 2), "seen/full", round(x[1], 2))


if __name__ == "__main__":
    main()
