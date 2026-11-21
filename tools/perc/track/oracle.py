"""The hindsight truth for the tracker plan: the fit's own mobs (no tracker) linked over consecutive ticks into
tracklets, then tracklets of one mob STITCHED across the ticks it went unseen - looking both ways in time, which a live
tracker can't. A stitched chain = one mob's life on screen; its gaps = the moments it was alive but not seen (the
native "lost-alive" set, PLAN-perception.md E4); its start / end say how it was born and how it went.

    from oracle import chains          (python tools/perc/track/oracle.py RUN = a summary)

Stitch rule (A's end -> B's start): same type, 0 < dt <= max_dt, |dx| <= reach(dt) = 30 + vmax * dt + knock (a hit
can throw it), |dy| <= dy_max; A did not end in a die pose unless B starts in one; B is not a birth (first opacity
< birth_o: the start of a spawn fade - a mob that fades in is a new one). Cheapest pairs first (|dx| + |dy| + 60 px
per second apart), each end / start used once; `amb` counts the other ends / starts the pair competed with.
"""
import sys
from collections import Counter

import numpy as np

from load import Map, anim_of, map_of, pct, ticks, tracklets

SW, PLAY_H = 1366, 700
# pts columns
I, T, X, Y, POSE, FACE, O, TINT, SEEN, COV, NS, SX, SY = range(13)


def edge(sx, sy, m=70) -> bool:
    return sx < m or sx > SW - m or sy > PLAY_H - 10 or sy < 60


def chains(tk, max_dt=4.0, vmax=160.0, knock=140.0, dy_max=45.0, birth_o=0.3, tl=None) -> list:
    """-> [{"type", "parts": [tracklet], "gaps": [(t_end, t_start, dx, dy, amb)], "start": kind, "end": kind}]."""
    tl = tl if tl is not None else tracklets(tk, max_gap=0)
    ends = [(t["pts"][-1], k) for k, t in enumerate(tl)]
    starts = [(t["pts"][0], k) for k, t in enumerate(tl)]
    starts.sort(key=lambda s: s[0][T])
    st_t = np.array([s[0][T] for s in starts])
    cand = []
    for pe, a in ends:
        die_a = anim_of(pe[POSE]).startswith("die")
        lo = np.searchsorted(st_t, pe[T], side="right")
        hi = np.searchsorted(st_t, pe[T] + max_dt, side="right")
        for ps, b in starts[lo:hi]:
            if tl[b]["type"] != tl[a]["type"] or a == b:
                continue
            dt = ps[T] - pe[T]
            dx, dy = ps[X] - pe[X], ps[Y] - pe[Y]
            if abs(dx) > 30 + vmax * dt + knock or abs(dy) > dy_max:
                continue
            die_b = anim_of(ps[POSE]).startswith("die")
            if die_a and not die_b:
                continue
            if ps[O] < birth_o and not (pe[O] < 0.9):          # B starts a spawn fade: a new mob
                continue
            cand.append((abs(dx) + abs(dy) + 60 * dt, a, b, dt, dx, dy))
    cand.sort()
    n_a, n_b = Counter(c[1] for c in cand), Counter(c[2] for c in cand)
    nxt, prv = {}, {}
    for _, a, b, dt, dx, dy in cand:
        if a in nxt or b in prv:
            continue
        nxt[a] = (b, dt, dx, dy, n_a[a] + n_b[b] - 2)
        prv[b] = a
    out = []
    t0, t1 = tk[0]["t"], tk[-1]["t"]
    for k in range(len(tl)):
        if k in prv:
            continue
        parts, gaps, a = [tl[k]], [], k
        while a in nxt:
            b, dt, dx, dy, amb = nxt[a]
            gaps.append((tl[a]["pts"][-1][T], tl[b]["pts"][0][T], dx, dy, amb))
            parts.append(tl[b])
            a = b
        p0, p1 = parts[0]["pts"][0], parts[-1]["pts"][-1]
        if p0[T] - t0 < 0.5:
            s = "run start"
        elif anim_of(p0[POSE]).startswith("die"):
            s = "die pose"
        elif p0[O] < 0.9:
            s = "fade-in"
        elif edge(p0[SX], p0[SY]):
            s = "edge"
        else:
            s = "appeared"
        if t1 - p1[T] < 0.5:
            e = "run end"
        elif anim_of(p1[POSE]).startswith("die"):
            e = "died"
        elif edge(p1[SX], p1[SY]):
            e = "edge"
        elif p1[O] < 0.9:
            e = "faint"
        else:
            e = "vanished"
        out.append({"type": tl[k]["type"], "parts": parts, "gaps": gaps, "start": s, "end": e})
    return out


def die_t(ch):
    """The first tick the chain shows a die pose (None: never)."""
    for p in ch["parts"]:
        for q in p["pts"]:
            if anim_of(q[POSE]).startswith("die"):
                return q[T]
    return None


def main():
    for run in sys.argv[1:]:
        tk = ticks(run)
        mp = Map(map_of(run))
        ch = chains(tk)
        g = [x for c in ch for x in c["gaps"]]
        dt = np.array([b - a for a, b, *_ in g])
        dx = np.array([abs(x[2]) for x in g])
        print(f"== {run}: {len(ch)} chains from {sum(len(c['parts']) for c in ch)} tracklets; starts "
              f"{dict(Counter(c['start'] for c in ch))}; ends {dict(Counter(c['end'] for c in ch))}")
        print(f"  gaps (alive, unseen): {len(g)}; s p50/p90/p99/max {pct(dt, (50, 90, 99, 100))}; <= 0.1 s {np.mean(dt <= 0.1):.0%}, "
              f"> 0.5 s {np.mean(dt > 0.5):.0%}, > 1.5 s {np.mean(dt > 1.5):.0%}; |dx| px p50/p90/p99/max {pct(dx, (50, 90, 99, 100))}; "
              f"ambiguous {np.mean([x[4] > 0 for x in g]):.0%}")
        for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.5), (1.5, 9)):
            m = (dt > lo) & (dt <= hi)
            if m.any():
                print(f"     gap {lo}-{hi} s: n {int(m.sum()):3d}, |dx| p50/p90/max {pct(dx[m], (50, 90, 100))}, > 30 px {np.mean(dx[m] > 30):.0%}, "
                      f"> 60 px {np.mean(dx[m] > 60):.0%}")
        _ = mp


if __name__ == "__main__":
    main()
