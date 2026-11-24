"""Tracker plan, Part 2: FEET AND PLACEMENT OF MOBS THAT JUMP - Part 1's two findings, measured.

    python tools/perc/track/proto_feet.py CAP [CAP ...] | --sound

1. Look-alike poses (one picture under two feet points, e.g. a Bubbling's jump = its walking picture drawn 17 px
   higher). The fit names either, so a jump's feet jump by 17 px. A hop is a parabola (the client's physics): each
   hop of the truth's tracklets gets a parabola fitted to its feet as the fit names them (raw) and as the
   prototype settles them (the reading that continues the motion). The residual says which feet are right.
2. Stand or air. Truth = inside a fitted hop: air; on a surface for 10+ frames: stand. Four rules are graded:
   today's (within 16 px of a surface = on it), 3 px on the raw feet, 3 px on the settled feet, and the model's
   rule (3 px + not moving up or down: 3 frames still before "standing").
3. Speed: what each kind's sightings do in a quarter second against the client files' top speed (the possible
   set widens at that speed).
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache  # noqa: E402
from load import Map, map_of, ticks, tracklets  # noqa: E402
from oracle import FACE, POSE, T, X, Y, I  # noqa: E402
from proto_mobs import kinds_of  # noqa: E402


def settle_series(k, nav, pts):
    """The tracklet's feet, settled: every look-alike reading, the one closest to the last feet wins (the first
    point: the one standing on a surface, else the air pose's). -> [(t, x, y_raw, y, pose)]."""
    out, prev, vy, floor = [], None, 0.0, None
    for q in pts:
        cands = [(q[POSE], q[X], q[Y])] + [(p2, q[X] + dx, q[Y] + dy) for p2, dx, dy in k.alike.get((q[POSE], q[FACE]), [])]
        if len(cands) > 1 and floor is not None:               # never under the floor it stands on / jumped from
            ok = [c for c in cands if not (floor.left <= c[1] <= floor.right and (floor.y_at(c[1]) or 1e9) + 3 < c[2])]
            cands = ok or cands
        if len(cands) == 1:
            c = cands[0]
        elif prev is None:
            on = [c for c in cands if nav.platform_at(c[1], c[2], tol=1.5) is not None]
            air = [c for c in cands if c[0].startswith(("jump", "fly"))]
            c = on[0] if len(on) == 1 else (air[0] if air and not on else cands[0])
        else:                                                  # where its motion takes it (a hop is ballistic)
            dt = q[T] - prev[2]
            yp = prev[1] + (vy * dt if dt < 0.05 else 0.0)
            c = min(cands, key=lambda c: abs(c[2] - yp) + abs(c[1] - prev[0]))
        vy = (c[2] - prev[1]) / (q[T] - prev[2]) if prev is not None and 0 < q[T] - prev[2] < 0.05 else 0.0
        p = nav.platform_at(c[1], c[2], tol=1.5)
        if p is not None and abs(vy) < 120:
            floor = p
        prev = (c[1], c[2], q[T])
        out.append((q[T], c[1], q[Y], c[2], c[0], q[I]))
    return out


def height(nav, x, y):
    """Feet height over the first surface at or under them (px, >= 0), that platform's id; None over nothing."""
    best = None
    for p, yp in nav.surfaces(x):
        if yp >= y - 3 and (best is None or yp < best[1]):
            best = (p, yp)
    return (None, None) if best is None else (max(0.0, best[1] - y), best[0].id if hasattr(best[0], "id") else best[0])


def main():
    caps = cache.SOUND if "--sound" in sys.argv else [a for a in sys.argv[1:] if not a.startswith("--")]
    hops = []                                  # (kind, rms raw, rms settled, apex px, air s, gravity px/s2, frames)
    lab = {r: Counter() for r in ("today (16 px)", "3 px, raw feet", "3 px, settled feet", "3 px + still (the model)",
                                  "3 px + this step still", "3 px + step within 1 px")}
    passing = Counter()
    jolt = {"raw": [0, 0], "settled": [0, 0]}
    speed = defaultdict(list)
    names = {}
    for cap in caps:
        tk = ticks(cap)
        mp = Map(map_of(cap))
        nav, kinds = mp.nav, kinds_of(mp)
        names.update(mp.names)
        for tl in tracklets(tk, max_gap=0):
            k = kinds.get(tl["type"])
            if k is None or len(tl["pts"]) < 15:
                continue
            ser = settle_series(k, nav, tl["pts"])
            t = np.array([s[0] for s in ser])
            x = np.array([s[1] for s in ser])
            # ---- speed over a quarter second (move poses, on the ground or not)
            j = 0
            for i in range(len(ser)):
                while t[i] - t[j] > 0.25:
                    j += 1
                if i - j >= 10 and t[i] - t[j] >= 0.2 and all(s[4].startswith(("move", "fly")) for s in ser[j:i + 1]):
                    speed[tl["type"]].append(abs(x[i] - x[j]) / (t[i] - t[j]))
            if not k.jump:
                continue
            # ---- jolts: a feet point that leaves its line by >= 13 px for one frame step (a 17 px look-alike flip)
            yr_, ys_ = np.array([s[2] for s in ser], float), np.array([s[3] for s in ser], float)
            okd = (np.diff(t)[:-1] < 0.03) & (np.diff(t)[1:] < 0.03)
            for nm, yy in (("raw", yr_), ("settled", ys_)):
                d2 = np.abs(yy[2:] - 2 * yy[1:-1] + yy[:-2])[okd]
                jolt[nm][0] += int((d2 >= 13).sum())
                jolt[nm][1] += len(d2)
            hs = [height(nav, s[1], s[3]) for s in ser]
            h = np.array([np.nan if v[0] is None else v[0] for v in hs])
            hr = np.array([np.nan if (v := height(nav, s[1], s[2]))[0] is None else v[0] for s in ser])
            # ---- hops: runs off the surface, standing before and after, no frame missing
            i, n = 0, len(ser)
            truth = np.full(n, "", dtype=object)                 # "air" / "stand" where known
            run = 0
            for a in range(n):                                   # stand = 10+ frames in a row within 1.5 px
                run = run + 1 if (not np.isnan(h[a]) and h[a] <= 1.5) else 0
                if run >= 10:
                    truth[a - 9:a + 1] = "stand"
            while i < n:
                if np.isnan(h[i]) or h[i] <= 3:
                    i += 1
                    continue
                a = i
                while i < n and not np.isnan(h[i]) and h[i] > 3:
                    i += 1
                b = i                                            # frames a..b-1 are off the surface
                if a == 0 or b >= n or not (12 <= b - a <= 70) or np.ptp(np.diff(t[a - 1:b + 1])) > 0.012:
                    continue
                tt = t[a:b] - t[a]
                ys = np.array([s[3] for s in ser[a:b]], float)
                yr = np.array([s[2] for s in ser[a:b]], float)
                cs = np.polyfit(tt, ys, 2)
                cr = np.polyfit(tt, yr, 2)
                rs = float(np.sqrt(np.mean((np.polyval(cs, tt) - ys) ** 2)))
                rr = float(np.sqrt(np.mean((np.polyval(cr, tt) - yr) ** 2)))
                hops.append((tl["type"], rr, rs, float(np.nanmax(h[a:b])), float(t[b] - t[a - 1]), 2 * cs[0], b - a))
                if rs <= 2.0:
                    truth[a:b] = "air"
                    for q in range(a, b):                        # a jump passing a platform's level
                        p16 = nav.platform_at(ser[q][1], ser[q][2], tol=16)
                        if p16 is not None:
                            passing["air frames today calls standing"] += 1
                            if p16.id not in (hs[a - 1][1], hs[min(b, n - 1)][1]):
                                passing["... on a platform it neither left nor landed on"] += 1
            # ---- the four rules against the truth
            still = 0
            air_m = False
            for q in range(n):
                on_raw16 = nav.platform_at(ser[q][1], ser[q][2], tol=16) is not None
                on_raw3 = nav.platform_at(ser[q][1], ser[q][2], tol=3) is not None
                on_set3 = nav.platform_at(ser[q][1], ser[q][3], tol=3) is not None
                dy = abs(ser[q][3] - ser[q - 1][3]) if q else 0.0
                dx = abs(ser[q][1] - ser[q - 1][1]) if q else 0.0
                still = still + 1 if (on_set3 and dy <= 1.5 + dx) else 0
                stand_m = on_set3 and (still >= 3 if air_m else dy <= 3 + dx)
                air_m = not stand_m
                stand_1 = on_set3 and dy <= 3 + dx
                stand_2 = on_set3 and dy <= 1 + 0.9 * dx
                if truth[q]:
                    for name, st in (("today (16 px)", on_raw16), ("3 px, raw feet", on_raw3),
                                     ("3 px, settled feet", on_set3), ("3 px + still (the model)", stand_m),
                                     ("3 px + this step still", stand_1), ("3 px + step within 1 px", stand_2)):
                        lab[name][(truth[q], "stand" if st else "air")] += 1
    H = np.array([(a, b, c, d, e, f) for _, a, b, c, d, e, f in hops]) if hops else np.zeros((0, 6))
    print(f"hops fitted: {len(hops)} ({dict(Counter(names.get(h[0], h[0]) for h in hops))})")
    if len(H):
        pc = lambda v, ps=(50, 90, 99): [round(float(np.percentile(v, p)), 2) for p in ps]  # noqa: E731
        print(f"  parabola residual, px rms p50 / p90 / p99: feet as the fit names them {pc(H[:, 0])}, settled {pc(H[:, 1])}")
        print(f"  hops within 1.5 px rms: raw {np.mean(H[:, 0] <= 1.5):.1%}, settled {np.mean(H[:, 1] <= 1.5):.1%}; within 2.0: raw "
              f"{np.mean(H[:, 0] <= 2):.1%}, settled {np.mean(H[:, 1] <= 2):.1%}")
        good = H[H[:, 1] <= 2.0]
        print(f"  the hop itself (settled, residual <= 2 px, n {len(good)}): apex px p10 / p50 / p90 {pc(good[:, 2], (10, 50, 90))}, "
              f"air s {pc(good[:, 3], (10, 50, 90))}, gravity px/s2 {pc(good[:, 4], (10, 50, 90))}")
    print(f"feet jolts of 13 px or more between frames (jumper kinds, {jolt['raw'][1]} frame steps): as the fit names them "
          f"{jolt['raw'][0]}, settled {jolt['settled'][0]}")
    print("stand or air, against the hops (air) and 10-frame stands (stand):")
    for name, c in lab.items():
        n_air, n_st = c[("air", "air")] + c[("air", "stand")], c[("stand", "stand")] + c[("stand", "air")]
        print(f"  {name:26s} air frames called standing {c[('air', 'stand')]:6d} of {n_air} ({100 * c[('air', 'stand')] / max(1, n_air):.2f} %); "
              f"standing frames called air {c[('stand', 'air')]:6d} of {n_st} ({100 * c[('stand', 'air')] / max(1, n_st):.3f} %)")
    print("  ", dict(passing))
    print("speed over a quarter second in a move pose, px/s (the client files' top speed -> seen):")
    for ty, v in sorted(speed.items()):
        v = np.array(v)
        kk = None
        for cap in caps:
            if ty in (m := Map(map_of(cap))).mobs:
                kk = kinds_of(m)[ty]
                break
        print(f"  {names.get(ty, ty):18s} files {kk.v:6.1f}  seen p50 {np.percentile(v, 50):6.1f} p95 {np.percentile(v, 95):6.1f} p99 "
              f"{np.percentile(v, 99):6.1f} max {v.max():6.1f}  (n {len(v)}); over the files' speed + 10 %: {np.mean(v > 1.1 * kk.v):.2%}")


if __name__ == "__main__":
    main()
