"""The data model's graph audit (docs/prompts/tracker-plan.md, Part 1 item 1): today's nav/navmap.py measured on
every map of assets/mcw - nodes, placement, edges, routes - so each part gets keep / change / rebuild with numbers.
Reads only; nothing in maplebrain/ is touched.

    python tools/model/nav_audit.py nodes          chains, floors, joins, slopes, layers (all maps)
    python tools/model/nav_audit.py place          platform_at / surfaces / below: time per call, close surfaces
    python tools/model/nav_audit.py edges [--n N]  link counts by kind, build time and where it goes, drop edges
    python tools/model/nav_audit.py routes         route() time, an all-pairs table's build time and size
    python tools/model/nav_audit.py all
    python tools/model/nav_audit.py graph [--no-edges]   PLAN-tracker step 2's gate: maplebrain/track/graph.py on
                                                         every map against navmap (nodes, floors, placement, the
                                                         edges and the seconds table; ~5 minutes with the edges)

Timing: this process pins itself to the performance cores (maplebrain/procperf.py); say what else was running.
"""
import argparse
import cProfile
import io
import json
import pstats
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ASSETS = ROOT / "assets" / "mcw"

from maplebrain.config import Config  # noqa: E402
from maplebrain.nav.navmap import NavMap, SAME  # noqa: E402


def maps() -> list:
    out = []
    for p in sorted((ASSETS / "maps").iterdir(), key=lambda p: int(p.name)):
        out.append(json.loads((p / "map.json").read_text(encoding="utf-8")))
    return out


def pct(v, ps=(50, 90, 99, 100)):
    v = np.asarray(v, float)
    return [round(float(np.percentile(v, p)), 2) for p in ps] if len(v) else None


def nav_nolinks(m, cfg):
    """A NavMap without its links (the nodes only): from_json with _find_links skipped."""
    orig = NavMap._find_links
    NavMap._find_links = lambda self: []
    try:
        return NavMap.from_json(m, cfg)
    finally:
        NavMap._find_links = orig


class UF:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def join(self, a, b):
        self.p[self.find(a)] = self.find(b)

    def groups(self):
        g = defaultdict(list)
        for i in self.p:
            g[self.find(i)].append(i)
        return list(g.values())


# ---------------------------------------------------------------------------------------------------- nodes
def joins(nm, tol=SAME):
    """Where two chains' surfaces meet, by geometry (not by sampling):
    end-end   A's right end == B's left end (within tol in x and y)
    end-mid   an end of A lies on B's surface inside B (within tol in y), not at B's own end  (a T: a ramp's foot)
    cross     neither: the surfaces cross inside both (found by the sign change of yA - yB over their shared x)
    -> [(kind, a id, b id, x)]"""
    out = []
    ps = list(nm.platforms.values())
    for a in ps:
        for end_x, end_y, side in ((a.left, a.segs[0].y1, "L"), (a.right, a.segs[-1].y2, "R")):
            for b in ps:
                if b is a:
                    continue
                yb = b.y_at(end_x)
                if yb is None or abs(yb - end_y) > tol:
                    continue
                at_b_end = abs(end_x - b.left) <= tol or abs(end_x - b.right) <= tol
                if at_b_end:
                    if side == "R" and abs(end_x - b.left) <= tol:      # counted once, from the left chain
                        out.append(("end-end", a.id, b.id, end_x))
                    elif side == "L" and abs(end_x - b.left) <= tol:
                        out.append(("end-end-same-side", a.id, b.id, end_x))
                    elif side == "R" and abs(end_x - b.right) <= tol:
                        out.append(("end-end-same-side", a.id, b.id, end_x))
                else:
                    out.append(("end-mid", a.id, b.id, end_x))
    # crossings: shared x span, yA - yB changes sign strictly inside
    for i, a in enumerate(ps):
        for b in ps[i + 1:]:
            lo, hi = max(a.left, b.left), min(a.right, b.right)
            if hi - lo < 2 * tol + 2:
                continue
            xs = np.arange(lo + tol + 1, hi - tol, 2.0)
            if len(xs) < 2:
                continue
            d = np.array([a.y_at(x) - b.y_at(x) for x in xs])
            s = np.sign(d)
            k = np.nonzero((s[:-1] * s[1:] < 0) | (np.abs(d[:-1]) < 0.5))[0]
            if len(k):
                out.append(("cross", a.id, b.id, float(xs[k[0]])))
    return out


def cmd_nodes(ms, cfg):
    rows = []
    kinds = Counter()
    ex = defaultdict(list)
    slope_n = Counter()
    lay_mixed = grp_mixed = gap_chains = loops = 0
    n_chain = n_fh = n_walk = n_wall = n_ceil = 0
    grp_split = 0
    for m in ms:
        fh = {int(k): v for k, v in m["footholds"].items()}
        nm = nav_nolinks(m, cfg)
        n_fh += len(fh)
        walk = [f for f in fh.values() if f["x1"] < f["x2"]]
        n_walk += len(walk)
        n_wall += sum(1 for f in fh.values() if f["x1"] == f["x2"])
        n_ceil += sum(1 for f in fh.values() if f["x1"] > f["x2"])
        for f in walk:
            s = abs(f["y2"] - f["y1"]) / (f["x2"] - f["x1"])
            slope_n["> 0.9" if s > 0.9 else "0.5-0.9" if s > 0.5 else "0.1-0.5" if s > 0.1 else "flat (<= 0.1)"] += 1
        by_xy = {(f["x1"], f["y1"], f["x2"], f["y2"]): f for f in walk}
        n_chain += len(nm.platforms)
        chain_of = {}
        for p in nm.platforms.values():
            lays, grps = set(), set()
            for a, b in zip(p.segs, p.segs[1:]):
                if a.x2 != b.x1 or a.y2 != b.y1:
                    gap_chains += 1
                    break
            for s in p.segs:
                f = by_xy.get((s.x1, s.y1, s.x2, s.y2))
                if f is not None:
                    lays.add(f["layerId"])
                    grps.add((f["layerId"], f["groupId"]))
                    chain_of[f["id"]] = p.id
            lay_mixed += len(lays) > 1
            grp_mixed += len(grps) > 1
        # a client "group" (layer, groupId) split over several chains?
        g2c = defaultdict(set)
        for f in walk:
            if f["id"] in chain_of:
                g2c[(f["layerId"], f["groupId"])].add(chain_of[f["id"]])
        grp_split += sum(1 for v in g2c.values() if len(v) > 1)
        js = joins(nm)
        for j in js:
            kinds[j[0]] += 1
            if len(ex[j[0]]) < 6:
                ex[j[0]].append((m["id"], m["name"], j[1], j[2], round(j[3])))
        uf = UF(nm.platforms)
        for k, a, b, _ in js:
            if k in ("end-end", "end-mid"):
                uf.join(a, b)
        floors = uf.groups()
        rows.append({"id": m["id"], "name": m["name"], "fh": len(fh), "chains": len(nm.platforms), "floors": len(floors),
                     "max_chains_floor": max((len(g) for g in floors), default=0), "ropes": len(nm.ropes),
                     "joins": Counter(j[0] for j in js)})
    ch = [r["chains"] for r in rows]
    fl = [r["floors"] for r in rows]
    print(f"maps {len(rows)}; footholds {n_fh}: walkable {n_walk}, walls {n_wall}, ceilings {n_ceil}")
    print(f"chains (today's nodes) {n_chain}: per map p50/p90/p99/max {pct(ch)}; ropes per map {pct([r['ropes'] for r in rows])}")
    print(f"walkable footholds by slope |dy/dx|: {dict(slope_n)}")
    print(f"chains with a gap inside {gap_chains}, over several layers {lay_mixed}, over several (layer, group) {grp_mixed};"
          f" client groups split over several chains {grp_split}")
    print(f"joins by geometry (within {SAME} px): {dict(kinds)}")
    for k, v in ex.items():
        print(f"   e.g. {k}: {v}")
    multi = [r for r in rows if r["floors"] < r["chains"]]
    print(f"floors (chains joined end-end / end-mid): per map {pct(fl)}; maps where floors < chains: {len(multi)} of {len(rows)};"
          f" chains in the largest floor per map {pct([r['max_chains_floor'] for r in rows])}")
    print(f"total chains {sum(ch)} -> floors {sum(fl)}")
    return rows


# ---------------------------------------------------------------------------------------------------- place
class Index:
    """A prototype of an indexed placement: every walkable foothold as a row of arrays, bucketed by x.
    surfaces_many(xs) -> for each x the candidate segments; nearest(xs, ys) -> (chain id, y, dy) vectorised."""

    def __init__(self, nm, bucket=64):
        segs = [(s.x1, s.y1, s.x2, s.y2, p.id) for p in nm.platforms.values() for s in p.segs]
        a = np.array(segs, float).reshape(-1, 5)
        self.x1, self.y1, self.x2, self.y2, self.pid = a.T
        self.slope = (self.y2 - self.y1) / (self.x2 - self.x1)
        self.W = bucket
        self.x0 = float(self.x1.min()) if len(a) else 0.0
        nb = int((self.x2.max() - self.x0) // bucket) + 1 if len(a) else 1
        b = [[] for _ in range(nb)]
        for i in range(len(a)):
            for k in range(int((self.x1[i] - self.x0) // bucket), int((self.x2[i] - self.x0) // bucket) + 1):
                b[k].append(i)
        self.b = [np.array(v, int) for v in b]
        self.nb = nb

    def nearest_many(self, xs, ys, tol):
        """All points at once, no buckets (N x S broadcast): -> (pid or -1, dy signed = feet - surface)."""
        xs, ys = np.asarray(xs, float)[:, None], np.asarray(ys, float)[:, None]
        on = (self.x1[None] <= xs) & (xs <= self.x2[None])
        y = self.y1[None] + (xs - self.x1[None]) * self.slope[None]
        d = np.where(on, np.abs(y - ys), np.inf)
        k = d.argmin(1)
        r = np.arange(len(k))
        ok = d[r, k] <= tol
        return np.where(ok, self.pid[k], -1), np.where(ok, (ys[:, 0] - y[r, k]), np.nan)

    def nearest(self, x, y, tol):
        """One point through the buckets (pure python + small arrays)."""
        k = int((x - self.x0) // self.W)
        if not 0 <= k < self.nb:
            return None
        best = None
        x1, y1, x2, sl, pid = self.x1, self.y1, self.x2, self.slope, self.pid
        for i in self.b[k]:
            if x1[i] <= x <= x2[i]:
                d = abs(y1[i] + (x - x1[i]) * sl[i] - y)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, pid[i])
        return best


def cmd_place(ms, cfg):
    rnd = random.Random(1)
    t_at, t_surf, t_below, t_idx1, t_idxN, sizes = [], [], [], [], [], []
    close = []
    wrong = 0
    checked = 0
    for m in ms:
        nm = nav_nolinks(m, cfg)
        ps = list(nm.platforms.values())
        if not ps:
            continue
        pts = []
        for _ in range(200):
            p = rnd.choice(ps)
            x = rnd.uniform(p.left, p.right)
            pts.append((x, p.y_at(x) + rnd.uniform(-10, 10)))
        t0 = time.perf_counter()
        ref = [nm.platform_at(x, y, tol=16) for x, y in pts]
        t1 = time.perf_counter()
        for x, y in pts:
            nm.surfaces(x)
        t2 = time.perf_counter()
        for x, y in pts:
            nm.below(x, y)
        t3 = time.perf_counter()
        ix = Index(nm)
        t4 = time.perf_counter()
        got1 = [ix.nearest(x, y, 16) for x, y in pts]
        t5 = time.perf_counter()
        xs, ys = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
        reps = 20
        t6 = time.perf_counter()
        for k in range(reps):
            ix.nearest_many(xs[k * 10 % 180:k * 10 % 180 + 20], ys[k * 10 % 180:k * 10 % 180 + 20], 16)
        t7 = time.perf_counter()
        t_at.append(1e6 * (t1 - t0) / len(pts))
        t_surf.append(1e6 * (t2 - t1) / len(pts))
        t_below.append(1e6 * (t3 - t2) / len(pts))
        t_idx1.append(1e6 * (t5 - t4) / len(pts))
        t_idxN.append(1e6 * (t7 - t6) / reps)
        sizes.append((len(ps), sum(len(p.segs) for p in ps), m["id"], m["name"]))
        # the index against platform_at where platform_at needed no +-8/16 px retry (same rule: nearest within tol)
        for (x, y), r, g in zip(pts, ref, got1):
            direct = min(((abs(yp - y), p.id) for p, yp in nm.surfaces(x) if abs(yp - y) <= 16), default=None)
            if direct is None:
                continue
            checked += 1
            wrong += g is None or int(g[1]) != direct[1]
        # two different surfaces close above each other at one x
        gaps = []
        for p in ps:
            for x in np.arange(p.left + 1, p.right, 8.0):
                ya = p.y_at(x)
                for q, yq in nm.surfaces(x):
                    if q is not p and yq > ya:
                        gaps.append(yq - ya)
        close.append((min(gaps) if gaps else np.inf, sum(1 for g in gaps if g < 32), len(gaps), m["id"], m["name"]))
    order = np.argsort([s[0] for s in sizes])
    med, big = order[len(order) // 2], order[-1]
    print(f"placement, us per call over {len(sizes)} maps (200 random points near surfaces each):")
    for name, v in (("platform_at", t_at), ("surfaces", t_surf), ("below", t_below), ("index: one point", t_idx1),
                    ("index: 20 points in one call (us per CALL)", t_idxN)):
        print(f"   {name:44s} p50/p90/p99/max {pct(v)};  median map {v[med]:.1f}, largest {v[big]:.1f}")
    print(f"   median map = {sizes[med]}, largest = {sizes[big]}")
    print(f"   the index gives platform_at's own answer (nearest within 16 px at that x) on {checked - wrong} / {checked}")
    c = np.array([x[0] for x in close])
    print(f"two surfaces above each other at one x: the smallest gap per map p1/p10/p50 {pct(c[np.isfinite(c)], (1, 10, 50))};"
          f" maps with a gap < 32 px (twice a 16 px tolerance): {int((c < 32).sum())}, < 18 px (twice 9): {int((c < 18).sum())},"
          f" < 9 px: {int((c < 9).sum())}")
    worst = sorted(close)[:8]
    print("   smallest gaps: " + "; ".join(f"{w[4]} ({w[3]}) {w[0]:.0f} px" for w in worst))


# ---------------------------------------------------------------------------------------------------- edges
def cmd_edges(ms, cfg, n=None):
    sel = ms if n is None else sorted(ms, key=lambda m: len(m["footholds"]))[::max(1, len(ms) // n)]
    kinds = Counter()
    t_all, per = [], []
    drop_n = drop_forbid = drop_far = drop_cant = 0
    fall_join = fall_n = 0
    walk_n = walk_pairs = 0
    for m in sel:
        t0 = time.perf_counter()
        nm = NavMap.from_json(m, cfg)
        dt = time.perf_counter() - t0
        t_all.append(dt)
        per.append((dt, len(nm.platforms), len(nm.ropes), len(nm.links), m["id"], m["name"]))
        kinds.update(k.kind for k in nm.links)
        fh = {int(k): v for k, v in m["footholds"].items()}
        first = {}                                           # chain id -> its footholds (by geometry)
        by_x1 = defaultdict(list)
        for f in fh.values():
            if f["x1"] < f["x2"]:
                by_x1[(f["x1"], f["y1"], f["x2"], f["y2"])].append(f)
        for p in nm.platforms.values():
            first[p.id] = [by_x1[(s.x1, s.y1, s.x2, s.y2)][0] for s in p.segs if by_x1.get((s.x1, s.y1, s.x2, s.y2))]
        for k in nm.links:
            if k.kind == "drop":
                drop_n += 1
                src, dst = nm.platforms[k.src], nm.platforms[k.dst]
                xm = (k.lo + k.hi) / 2
                ya, yb = src.y_at(xm), dst.y_at(xm)
                fs = [f for f in first.get(k.src, []) if f["x1"] <= xm <= f["x2"]]
                if fs and fs[0].get("forbidFallDown"):
                    drop_forbid += 1
                if fs and fs[0].get("cantThrough"):
                    drop_cant += 1
                if ya is not None and yb is not None and yb - ya >= 600:
                    drop_far += 1
            elif k.kind == "fall":
                fall_n += 1
                src, dst = nm.platforms[k.src], nm.platforms[k.dst]
                x = k.lo
                ya = src.y_at(src.clamp(x))
                yb = dst.y_at(dst.clamp(x + k.dir * 8))
                if ya is not None and yb is not None and abs(yb - ya) <= SAME + 2:
                    fall_join += 1                           # "walking off an end" that is really a level join
            elif k.kind == "walk":
                walk_n += 1
        walk_pairs += len({(k.src, k.dst) for k in nm.links if k.kind == "walk"})
    print(f"edges on {len(sel)} maps: build s p50/p90/p99/max {pct(t_all)}; total {sum(t_all):.1f} s")
    per.sort()
    print(f"   median: {per[len(per) // 2]}")
    print(f"   slowest: {per[-3:]}")
    print(f"   links by kind: {dict(kinds)}")
    print(f"   walk links {walk_n} ({walk_pairs} ordered chain pairs); fall links {fall_n}, of them onto a surface at the "
          f"same height (a join the sampling calls a fall): {fall_join}")
    print(f"   drop links {drop_n}: from a forbidFallDown foothold {drop_forbid}, from a cantThrough one {drop_cant}, "
          f"landing >= 600 px lower {drop_far}")
    # where the build time goes, on the slowest map
    slow = max(sel, key=lambda m: len(m["footholds"]))
    pr = cProfile.Profile()
    pr.enable()
    NavMap.from_json(slow, cfg)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(12)
    print(f"   profile of {slow['name']} ({slow['id']}):")
    for line in s.getvalue().splitlines()[4:24]:
        if line.strip():
            print("      " + line[:150])


# ---------------------------------------------------------------------------------------------------- routes
def cmd_routes(ms, cfg):
    rnd = random.Random(2)
    by = sorted(ms, key=lambda m: len(m["footholds"]))
    picks = [by[len(by) // 2], by[int(len(by) * 0.9)], by[-1]] + [m for m in ms if m["id"] == 10003061]
    for m in picks:
        nm = NavMap.from_json(m, cfg)
        nodes = list(nm.platforms) + [nm.rope_id(i) for i in range(len(nm.ropes))]
        if len(nodes) < 2:
            continue
        ts, none = [], 0
        for _ in range(60):
            a, b = rnd.sample(nodes, 2)
            pos = nm.rope(a).top if nm.is_rope(a) else nm.platforms[a].left
            t0 = time.perf_counter()
            r = nm.route(a, pos, b)
            ts.append(1e3 * (time.perf_counter() - t0))
            none += r is None
        # an all-pairs seconds table: one Dijkstra per source over an adjacency list (node-level costs: the cheapest
        # take-off is not known without a position, so the walk to the take-off point is left out = a lower bound)
        cost = {"walk": 0.0, "fall": 0.5, "drop": 0.8, "jump": 0.7, "grab": 0.7, "descend": 0.4, "exit": 0.4,
                "let_go": 0.5, "leap": 0.7}
        ix = {n: i for i, n in enumerate(nodes)}
        adj = [[] for _ in nodes]
        for k in nm.links:
            adj[ix[k.src]].append((ix[k.dst], cost[k.kind]))
        import heapq
        t0 = time.perf_counter()
        N = len(nodes)
        D = np.full((N, N), np.inf, np.float32)
        for s in range(N):
            d = D[s]
            d[s] = 0.0
            h = [(0.0, s)]
            while h:
                c, u = heapq.heappop(h)
                if c > d[u]:
                    continue
                for v, w in adj[u]:
                    if c + w < d[v]:
                        d[v] = c + w
                        heapq.heappush(h, (c + w, v))
        dt = time.perf_counter() - t0
        reach = np.isfinite(D)
        # strongly connected? how many nodes can reach / be reached from the biggest component
        print(f"{m['name']} ({m['id']}): {len(nm.platforms)} chains + {len(nm.ropes)} ropes, {len(nm.links)} links; "
              f"route() ms p50/p90/max {pct(ts, (50, 90, 100))}, no way {none} / 60; all-pairs table {dt * 1e3:.0f} ms, "
              f"{D.nbytes / 1024:.0f} KB; ordered pairs with a way {reach.mean():.0%}")


# ---------------------------------------------------------------------------------------------------- graph
def frame_things(g, xs, ys):
    """20 things as a frame hands them to the placement: a 2 px step sideways, none up or down, the node each
    stood on last (the nearest within 16 px), the first three climbers (us, two players)."""
    n = len(xs)
    last, _ = g.nearest(xs, ys, 16)
    climb = np.zeros(n, bool)
    climb[:3] = True
    return dict(dx=np.full(n, 2.0), dy=np.zeros(n), last=last, last_from=last, climb=climb)


def today_footholds(m) -> dict:
    """navmap's platform id -> its foothold ids in order (NavMap.from_json's own loop, replayed on the ids)."""
    fh = {int(k): v for k, v in m["footholds"].items()}
    floor = {i for i, f in fh.items() if f["x1"] < f["x2"]}
    out, seen = {}, set()
    for i in sorted(floor):
        if i in seen or fh[i]["prev"] in floor:
            continue
        ch, j = [], i
        while j in floor and j not in seen:
            seen.add(j)
            ch.append(j)
            j = fh[j]["next"]
        out[i] = ch
    for i in sorted(floor - seen):
        out[i] = [i]
    return out


def time_place(g, xs, ys, rounds=7):
    """us per call of 20 things (the same 20 slices of the 200 points as `place`), the median of `rounds`."""
    args = [(xs[k * 10 % 180:k * 10 % 180 + 20], ys[k * 10 % 180:k * 10 % 180 + 20]) for k in range(20)]
    extra = [frame_things(g, x, y) for x, y in args]
    out = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        for (x, y), e in zip(args, extra):
            g.place(x, y, **e)
        out.append(1e6 * (time.perf_counter() - t0) / len(args))
    return float(np.median(out))


def cmd_graph(ms, cfg, edges=True):
    """PLAN-tracker step 2's gate: maplebrain/track/graph.py built on every map, against navmap."""
    from maplebrain.config import Track
    from maplebrain.track.graph import Graph, route_table
    tr = Track()
    rnd = random.Random(1)                              # the same 72,800 points as `place`
    n_chains = 0
    id_diff, comp_diff, ok_maps = [], [], 0
    links_same = links_cmp = 0
    floors_j, floors_bad, joints_all = [], 0, Counter()
    eq = checked = 0
    t_build, t_links, t_table, sizes, timed = [], [], [], [], {}
    for m in ms:
        t0 = time.perf_counter()
        g = Graph(m, cfg, tr, edges=edges)
        t_build.append(time.perf_counter() - t0)
        nm = nav_nolinks(m, cfg)
        n_chains += g.n_chains
        mine = {int(i): tuple((s.x1, s.y1, s.x2, s.y2) for s in g.platforms[int(i)].segs) for i in g.ids[:g.n_chains]}
        today = {p.id: tuple((s.x1, s.y1, s.x2, s.y2) for s in p.segs) for p in nm.platforms.values()}
        if set(mine) != set(today):
            id_diff.append((m["id"], m["name"]))
        elif mine != today:
            comp_diff.append((m["id"], m["name"]))
        else:
            ok_maps += 1
        # floors: every joint with no wall is one floor; nothing else is joined
        for a, b, x, y, wall, links in g.joints:
            joints_all[("a wall stands at the joint" if wall else "no wall") + ", links " + links] += 1
        for a, b, *_ in g.floor_joints:
            floors_j.append((m["id"], a, b))
            floors_bad += int(g.floor[g.index[a]] != g.floor[g.index[b]])
        floors_bad += int(g.n_floors != g.n_chains - len({tuple(sorted((a, b))) for a, b, *_ in g.floor_joints}))
        # placement: the node = platform_at's (16 px), mapped through the foothold under it at x
        ps = list(nm.platforms.values())
        if not ps:
            continue
        pts = []
        for _ in range(200):
            p = rnd.choice(ps)
            x = rnd.uniform(p.left, p.right)
            pts.append((x, p.y_at(x) + rnd.uniform(-10, 10)))
        xs, ys = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
        got, _ = g.nearest(xs, ys, 16)
        fhs = today_footholds(m)
        for (x, y), gv in zip(pts, got):
            r = nm.platform_at(x, y, tol=16)
            if r is None:
                continue
            k = next(k for k, s in enumerate(r.segs) if s.x1 <= x <= s.x2)
            checked += 1
            eq += int(g.chain_of[fhs[r.id][k]] == gv)
        sizes.append((len(ps), m["id"], m["name"]))
        timed[m["id"]] = (m, xs, ys)
        if edges:
            t_links.append(g.edges.links_s)
            t_table.append(g.edges.table_s)
            if mine == today:                           # the edges are navmap's own where the nodes are
                ref = NavMap.from_json(m, cfg).links
                links_cmp += 1
                links_same += int(sorted(ref, key=repr) == sorted(g.edges.nav.links, key=repr))
    print(f"maps built {len(t_build)} of {len(ms)}; build s p50 / p90 / max {pct(t_build, (50, 90, 100))}")
    print(f"chains {n_chains}; against navmap: other ids on {len(id_diff)} maps, the same ids but other footholds on "
          f"{len(comp_diff)} maps {comp_diff}, the same nodes on {ok_maps}")
    print(f"joints of two chains' ends at one point: {dict(joints_all)}")
    print(f"floor joints {len(floors_j)} (one floor each, nothing else joined: {'yes' if not floors_bad else f'NO, {floors_bad} wrong'})"
          f" e.g. {floors_j[:3]}")
    print(f"the node = platform_at's (16 px, through the foothold at x): {eq} of {checked}")
    order = np.argsort([s[0] for s in sizes])
    med, big = sizes[order[len(order) // 2]], sizes[order[-1]]
    for name, s in (("median map", med), ("largest", big)):
        m, xs, ys = timed[s[1]]
        g = Graph(m, cfg, tr, edges=False)
        print(f"20 things placed in one call, {name} {s[2]} ({s[1]}, {s[0]} chains): {time_place(g, xs, ys):.1f} us "
              f"(steps, last nodes, 3 climbers); bare {time_place_bare(g, xs, ys):.1f} us")
    if not edges:
        return
    print(f"edges: navmap's own links on {links_same} of {links_cmp} maps with navmap's nodes; build s p50 / p90 / max "
          f"{pct(t_links, (50, 90, 100))}; the table ms p50 / p90 / max {pct(1e3 * np.array(t_table), (50, 90, 100))}")
    line1 = next(m for m in ms if m["id"] == 10003061)
    g = Graph(line1, cfg, tr)
    nav = g.edges.nav
    bt = []
    for _ in range(7):
        t0 = time.perf_counter()
        route_table(nav, g.ids, g.start)
        bt.append(1e3 * (time.perf_counter() - t0))
    r2 = random.Random(3)
    bad = 0
    for _ in range(1000):
        a, b = r2.sample(range(len(g.ids)), 2)
        r = nav.route(int(g.ids[a]), float(g.start[a]), int(g.ids[b]), with_cost=True)
        bad += int((np.inf if r is None else r[1]) != g.edges.seconds[a, b])
    print(f"the table on Line 1 ({len(g.ids)} nodes): = route()'s seconds on {1000 - bad} of 1000 random pairs; built in "
          f"{min(bt):.2f} ms (best of 7; p50 {np.median(bt):.2f})")


def time_place_bare(g, xs, ys, rounds=7):
    args = [(xs[k * 10 % 180:k * 10 % 180 + 20], ys[k * 10 % 180:k * 10 % 180 + 20]) for k in range(20)]
    out = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        for x, y in args:
            g.place(x, y)
        out.append(1e6 * (time.perf_counter() - t0) / len(args))
    return float(np.median(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("nodes", "place", "edges", "routes", "all", "graph"))
    ap.add_argument("--n", type=int, default=None, help="edges: only about N maps, spread by size")
    ap.add_argument("--no-edges", action="store_true", help="graph: nodes, floors and placement only")
    a = ap.parse_args()
    try:
        from maplebrain.procperf import prefer_performance
        print("pinned:", prefer_performance())
    except Exception as e:                                  # noqa: BLE001
        print("not pinned:", e)
    cfg = Config().nav
    ms = maps()
    if a.what in ("nodes", "all"):
        cmd_nodes(ms, cfg)
    if a.what in ("place", "all"):
        cmd_place(ms, cfg)
    if a.what in ("edges", "all"):
        cmd_edges(ms, cfg, a.n)
    if a.what in ("routes", "all"):
        cmd_routes(ms, cfg)
    if a.what == "graph":
        cmd_graph(ms, cfg, edges=not a.no_edges)


if __name__ == "__main__":
    main()
