"""E10 (tracker plan): what the fit's own mobs say at the live rate, before any tracker - speeds per pose vs the
client's speed stat, how tracklets start (fade-in at a spawn point? screen edge? mid-screen at full opacity = a known
mob re-appearing) and how they end (die pose, edge, or just gone = covered / unwitnessed death).

    python tools/perc/track/e10_basics.py RUN [RUN ...]
"""
import sys
from collections import Counter, defaultdict

import numpy as np

from load import Map, anim_of, map_of, pct, ticks, tracklets

SW, PLAY_H = 1366, 700


def edge(sx, sy, m=70):
    return sx < m or sx > SW - m or sy > PLAY_H - 10 or sy < 60


def main():
    for run in sys.argv[1:]:
        tk = ticks(run)
        mp = Map(map_of(run))
        fit_t = [k for k in tk if k["fit"] is not None]
        dts = np.diff([k["t"] for k in tk])
        lost = [k["n"] for k in tk[5:] if k["C"] is None]
        print(f"== {run}: {len(tk)} ticks, {tk[-1]['t'] - tk[0]['t']:.0f} s, dt p50/p90/p99/max {pct(dts * 1000, (50, 90, 99, 100))} ms; "
              f"fit on {len(fit_t)}; camera lost after tick 5 on {len(lost)} ticks {lost[:10]}; "
              f"fit mobs / tick p50 {np.median([len(k['fit']) for k in fit_t]):.0f} max {max(len(k['fit']) for k in fit_t)}")
        tl = tracklets(tk, max_gap=0)
        n = np.array([len(t["pts"]) for t in tl])
        print(f"  tracklets (consecutive fit ticks): {len(tl)}, ticks each p50/p90/max {pct(n, (50, 90, 100))}, 1-tick ones {int((n == 1).sum())}")
        # --- speed per (type, anim): displacement over 8 ticks of one anim + facing
        sp = defaultdict(list)
        for t in tl:
            p = t["pts"]
            for a in range(0, len(p) - 8, 4):
                b = a + 8
                an = {anim_of(q[4]) for q in p[a:b + 1]}
                fc = {q[5] for q in p[a:b + 1]}
                if len(an) == 1 and len(fc) == 1 and p[b][0] - p[a][0] == 8 and min(q[6] for q in p[a:b + 1]) > 0.95:
                    v = (p[b][2] - p[a][2]) / (p[b][1] - p[a][1])
                    sp[(t["type"], an.pop())].append(v if fc.pop() == "right" else -v)     # + = the way it faces
        for (ty, an), v in sorted(sp.items()):
            st = (mp.mobs[ty].get("info") or {}).get("speed")
            print(f"  speed {mp.names[ty]:16s} {an:6s} n {len(v):5d}  px/s toward its facing p5/25/50/75/95 {pct(v, (5, 25, 50, 75, 95))}"
                  f"  |v|<5: {np.mean(np.abs(v) < 5):.0%}   (client speed stat {st})")
        # --- starts
        t0 = tk[0]["t"]
        cat, ex = Counter(), defaultdict(list)
        o_first = defaultdict(list)
        sd = defaultdict(list)
        for t in tl:
            i, tt, x, y, pose, fc, o, tint, seen, cov, ns, sx, sy = t["pts"][0]
            an = anim_of(pose)
            if tt - t0 < 0.5:
                c = "run start"
            elif an.startswith("die"):
                c = "die pose"
            elif o < 0.9:
                c = "fading in (o < 0.9)"
            elif edge(sx, sy):
                c = "screen edge"
            else:
                c = "mid-screen, opaque"
            cat[c] += 1
            ex[c].append((round(tt, 2), t["type"], int(sx), int(sy), round(o, 2), pose, len(t["pts"])))
            if c.startswith("fading"):
                o_first[t["type"]].append(o)
                sd[t["type"]].append(mp.spawn_dist(t["type"], x, y)[0])
        print(f"  tracklet starts: {dict(cat)}")
        for ty in o_first:
            print(f"    fading-in starts {mp.names[ty]}: first opacity p5/50/95 {pct(o_first[ty])}; x distance to the nearest spawn "
                  f"point of its type p50/p90/max {pct(sd[ty], (50, 90, 100))}; within 15 px {np.mean(np.array(sd[ty]) <= 15):.0%}")
        # --- ends
        cat2 = Counter()
        tend = tk[-1]["t"]
        for t in tl:
            i, tt, x, y, pose, fc, o, tint, seen, cov, ns, sx, sy = t["pts"][-1]
            an = anim_of(pose)
            if tend - tt < 0.5:
                c = "run end"
            elif an.startswith("die"):
                c = "die pose"
            elif edge(sx, sy):
                c = "screen edge"
            elif o < 0.9:
                c = "faint (o < 0.9)"
            else:
                c = "mid-screen, opaque, live pose"
            cat2[c] += 1
        print(f"  tracklet ends: {dict(cat2)}")


if __name__ == "__main__":
    main()
