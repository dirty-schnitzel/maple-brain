"""The map's graph for the tracker (PLAN-tracker.md design 3 and step 2; docs/state_model.md sections 1-2): its nodes
and floors, where a thing is on them (the placement), the edges and the seconds table. Fixed per map, built from the
client's map.json before play. Nothing here knows the screen or the brain. Map coordinates: x right, y DOWN.

NODES. A floor node = one CHAIN: walkable footholds (x1 < x2) linked left to right by the client's prev / next, BOTH
ways. A chain starts at every walkable foothold whose prev is not walkable or does not name it as its next, and runs
along `next` while the next foothold is walkable and names this one as its prev (the reference:
tools/model/chains_fixed.py); a closed loop is cut at its lowest id. Its id = its first (leftmost) foothold's id. A
rope / ladder node = -1 - its index in map.json's list, as in nav/navmap.py. navmap builds its platforms otherwise
(a chain starts only where prev is not walkable and runs on across a one-way link), so the two differ on some maps
(`tools/model/nav_audit.py graph` counts them).

FLOORS. Two chains are one floor where the right end of one is the left end of the other at one point and no wall
rises from that point (19 joints in all 364 maps, none linked either way: the client's links are simply missing).
Every other joint is a step and stays an edge: a wall standing on the joint (the client links it one way), a T (an
end on another chain's middle), a crossing. Ropes have no floor (-1).

PLACEMENT: one rule for every kind, one call for every thing of a frame (`place`):
  1. stand: a surface at the feet's x is within `stand_tol` (3 px) - `stand_tol_slope` (5 px) when its foothold
     there is not level (mobs' feet sit 3.6-4.4 px off a slope: the user, 2026-11-24) - and the step since the last
     frame is within `stand_step` (1 px) up or down + the surface's own rise over the sideways step (its foothold's
     slope x the step, rounded UP to a whole pixel: feet and camera are whole pixels, so 1 px sideways on a 0.6
     slope shows up to 2 px up or down; mobs walk slopes of 1.8-1.9 - the user, 2026-11-25, PLAN-tracker "Step 3,
     the slope fix") - a jump passing a platform's level is not standing on it. A kind that flies is never standing (the user: "Stirges never land").
     Two surfaces within their tolerance: the node of the last frame wins; else the nearest, then the lower id
     (NavMap.platform_at's order). The foothold at a whole x where two of a chain meet: the one going on.
  2. rope: a kind that climbs (us, players), not standing: the feet within `rope_tol` of a rope's x and of its ends
     in y; the nearest rope by x. No speed test (PLAN-tracker step 4b try 3: try 2's broke grabs from a jump, and on
     other players it changed nothing on L5): whether a climber GRABBED the rope is its caller's (us: up or down down
     at the grab - track/us.py).
  3. otherwise air, or fly for a kind that flies; node = the first surface at or under the feet (none: NONE).
  from_node = the node stood or hung on last: this one on stand / rope, else the caller's last from_node (it changes
  only on stand or rope: where a remembered mob's places are, PLAN-tracker design 3-4). off = feet y - the node's
  surface y at that x (negative: above it); on a rope, feet x - rope x; NaN over nothing. The step and the last
  nodes come from the caller (step 0 and NONE for a thing with no last frame).
  The tests "within 3 px", "at or under" and the step's 1 px have EPS (1e-6 px) of rounding slack.
  Why it is fast: footholds end on whole pixels, so every whole x of the map holds the surfaces over [x, x + 1) in a
  row of slots (a foothold that ends at x counts at x only) with each one's tolerance, a flag for "two surfaces
  close" (only then can the last node decide) and one for "a rope within reach"; a call reads one row per thing instead of every
  foothold - 20 things in ~19 us on the median map and on the largest (PLAN-tracker step 2). At a whole x the
  surface's y is Seg.y_at's to the bit; between, within ~1e-12 px.

EDGES AND THE SECONDS TABLE (`Edges`). The edges are navmap's own (`NavMap._find_links`; nav/navmap.py is not
changed) found over these nodes. `seconds[a, b]` = the seconds NavMap.route gives from the middle of node a to node
b: route's own search, run once to the end from each node, so it is route()'s number exactly (`arrive[a, b]` =
where that way puts us on b: x on a floor, y on a rope). Both depend on dynamic values (jump height and reach,
speeds): `rebuild(cfg)` builds a new set on a worker thread and swaps it in whole; a reader takes `graph.edges` once
and uses it, the old set until the swap. The worker shares Python's GIL with the frame: while it runs (0.6 s on
Line 1, 7 s on the largest map), a frame's Python work now and then waits for it - up to ~20 ms on Line 1, ~30 ms
on the largest map (PLAN-tracker.md step 2).
"""
import heapq
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Nav, Track
from ..nav.navmap import NavMap, Platform, Rope, Seg, _walled

STAND, AIR, FLY, ROPE = 0, 1, 2, 3
PLACES = ("stand", "air", "fly", "rope")
NONE = 0                                # no node: foothold ids start at 1, ropes are -1 - index
NOWHERE = 1e9                           # the y of "nothing under": farther than any surface, finite (argmin finds it)
END = -1e12                             # the slope of a foothold at its right end: past it, it is far above everything
EPS = 1e-6                              # px of rounding slack in the rule's tests: a distance that is whole on paper
                                        # (3 px, 0 px) stays whole (the table's y at a fraction of x differs from
                                        # Seg.y_at's by ~1e-13)
STEEP = 0.9                             # the client's walkSlant: a foothold steeper than this is marked `steep`
# NavMap.route's price per move, seconds (route keeps them in a local; tests/test_track_graph.py keeps the table
# equal to route() on real maps, so a change there fails here)
ROUTE_COST = {"walk": 0.0, "fall": 0.5, "drop": 0.8, "jump": 0.7, "grab": 0.7, "descend": 0.4, "exit": 0.4,
              "let_go": 0.5, "leap": 0.7}


def chains(fh: dict) -> list:
    """The chains of a map's footholds {id: foothold}: [[foothold id, ...] left to right]."""
    floor = {i for i, f in fh.items() if f["x1"] < f["x2"]}

    def linked(a, b):                                   # a -> b is a two-way link
        return b in floor and fh[a]["next"] == b and fh[b]["prev"] == a

    out, seen = [], set()
    for i in sorted(floor):
        p = fh[i]["prev"]
        if p in floor and linked(p, i):
            continue                                    # not a left end
        ch, j = [], i
        while j not in seen:
            seen.add(j)
            ch.append(j)
            n = fh[j]["next"]
            if not linked(j, n):
                break
            j = n
        out.append(ch)
    for i in sorted(floor - seen):                      # a closed loop of two-way links: cut at its lowest id
        ch, j = [], i
        while j not in seen:
            seen.add(j)
            ch.append(j)
            j = fh[j]["next"]
        out.append(ch)
    return out


def joints(fh: dict, chain_list: list) -> list:
    """Where one chain's right end is another's left end at one point: [(a, b, x, y, wall, links)] with a, b the two
    chains' ids, wall = a wall rises from the joint, links = 'none' / 'a->b' / 'b->a' (the client's)."""
    walls = [(f["x1"], min(f["y1"], f["y2"]), max(f["y1"], f["y2"])) for f in fh.values() if f["x1"] == f["x2"]]
    lefts = {}
    for c in chain_list:
        f = fh[c[0]]
        lefts.setdefault((f["x1"], f["y1"]), []).append(c)
    out = []
    for c in chain_list:
        a = fh[c[-1]]
        x, y = a["x2"], a["y2"]
        for c2 in lefts.get((x, y), []):
            if c2 is c:
                continue
            wall = any(wx == x and y0 < y <= y1 for wx, y0, y1 in walls)
            fwd, back = a["next"] == c2[0], fh[c2[0]]["prev"] == c[-1]
            links = "a->b" if fwd and not back else "b->a" if back and not fwd else "both" if fwd else "none"
            out.append((c[0], c2[0], x, y, wall, links))
    return out


@dataclass
class Placed:
    """`Graph.place`'s answer, one entry per thing."""
    place: np.ndarray                   # int8: STAND / AIR / FLY / ROPE (PLACES names them)
    node: np.ndarray                    # int64 node id: stood / hung on, or (air, fly) the first surface under; NONE
    from_node: np.ndarray               # int64: the node stood or hung on last
    off: np.ndarray                     # float64 px: feet y - the node's surface y (rope: feet x - rope x); NaN


@dataclass(frozen=True)
class Edges:
    """The parts of the graph that depend on dynamic values, built together and swapped in whole."""
    nav: NavMap                         # navmap over the graph's nodes: links, route(), landing()
    seconds: np.ndarray                 # (N, N) float64: route()'s seconds from the middle of node i to node j; inf
    arrive: np.ndarray                  # (N, N) float64: where that way puts us on j (x; y on a rope); NaN
    cfg: Nav                            # the values they were built from
    links_s: float                      # build seconds: the links, the table
    table_s: float


class Graph:
    """One map's graph. Node arrays are indexed like `ids` (the chains by id, then the ropes -1, -2, ...)."""

    def __init__(self, m: dict, nav: Nav | None = None, track: Track | None = None, edges: bool = True):
        self.map_id, self.name = int(m["id"]), m.get("name", "")
        self.cfg = track or Track()
        fh = {int(k): v for k, v in m["footholds"].items()}
        self._build_nodes(m, fh)
        self._build_floors(fh)
        self._build_columns()
        self._build_fixed(m)
        self._lock = threading.Lock()
        self._gen = 0
        self._thread = None
        self.edges: Edges | None = build_edges(self, nav or Nav()) if edges else None

    @classmethod
    def for_map(cls, map_id: int, root: Path, nav: Nav | None = None, track: Track | None = None,
                edges: bool = True) -> "Graph":
        m = json.loads((Path(root) / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        return cls(m, nav, track, edges)

    # ---------------------------------------------------------------- building
    def _build_nodes(self, m, fh):
        ch = sorted(chains(fh), key=lambda c: c[0])
        self.chains = ch                                # [[foothold id, ...]] in node order
        self.n_chains = len(ch)
        rows = [(fh[i], ci) for ci, c in enumerate(ch) for i in c]
        a = np.array([(f["x1"], f["y1"], f["x2"], f["y2"]) for f, _ in rows], np.float64).reshape(-1, 4)
        self.seg_x1, self.seg_y1, self.seg_x2, self.seg_y2 = a.T
        self.seg_fh = np.array([f["id"] for f, _ in rows], np.int64)
        self.seg_layer = np.array([f.get("layerId", 0) for f, _ in rows], np.int64)
        self.seg_forbid = np.array([bool(f.get("forbidFallDown")) for f, _ in rows], bool)
        self.seg_cant = np.array([bool(f.get("cantThrough")) for f, _ in rows], bool)
        self.seg_ix = np.array([ci for _, ci in rows], np.int64)            # the chain's index
        self.seg_node = np.array([ch[ci][0] for _, ci in rows], np.int64)   # the chain's id
        with np.errstate(divide="ignore", invalid="ignore"):
            self.seg_steep = np.abs(self.seg_y2 - self.seg_y1) > STEEP * (self.seg_x2 - self.seg_x1)
        lens = np.array([len(c) for c in ch], np.int64)
        self.seg_lo = np.concatenate([[0], np.cumsum(lens)[:-1]]).astype(np.int64) if len(ch) else lens
        self.seg_hi = self.seg_lo + lens
        self.chain_of = {i: c[0] for c in ch for i in c}                    # foothold id -> chain id
        # navmap's own objects for these nodes (its link finder and route() run on them)
        walls = [Seg(f["x1"], min(f["y1"], f["y2"]), f["x2"], max(f["y1"], f["y2"]))
                 for f in fh.values() if f["x1"] == f["x2"]]
        xs = [v for f in fh.values() for v in (f["x1"], f["x2"])]
        x_min, x_max = (min(xs), max(xs)) if xs else (0, 0)
        plats = {}
        for c in ch:
            p = Platform(c[0], [Seg(fh[i]["x1"], fh[i]["y1"], fh[i]["x2"], fh[i]["y2"]) for i in c])
            p.open_left = not (p.left <= x_min + 1 or _walled(walls, p.left, p.segs[0].y1))
            p.open_right = not (p.right >= x_max - 1 or _walled(walls, p.right, p.segs[-1].y2))
            plats[p.id] = p
        self.platforms, self.walls = plats, walls
        self.ropes = [Rope(r["x"], min(r["y1"], r["y2"]), max(r["y1"], r["y2"]), bool(r.get("isLadder")))
                      for r in m.get("ladderRopes") or []]
        self._nav_spawns = [(float(v["x"]), float(v["y"])) for v in m.get("mobs") or [] if not v.get("hidden")]
        ps = list(plats.values())
        self.left = np.array([p.left for p in ps], np.float64)
        self.right = np.array([p.right for p in ps], np.float64)
        self.open_left = np.array([p.open_left for p in ps], bool)
        self.open_right = np.array([p.open_right for p in ps], bool)
        self.rope_x = np.array([r.x for r in self.ropes], np.float64)
        self.rope_top = np.array([r.top for r in self.ropes], np.float64)
        self.rope_bottom = np.array([r.bottom for r in self.ropes], np.float64)
        self.rope_ladder = np.array([r.ladder for r in self.ropes], bool)
        probe = NavMap(plats, self.ropes, walls, [], Nav())
        self.rope_top_node = np.array([(t.id if (t := probe._top_platform(r)) is not None else NONE)
                                       for r in self.ropes], np.int64)
        self.ids = np.array([c[0] for c in ch] + [-1 - i for i in range(len(self.ropes))], np.int64)
        self.index = {int(v): i for i, v in enumerate(self.ids)}
        self._sorted = np.argsort(self.ids, kind="stable")
        self._sorted_ids = self.ids[self._sorted]
        # where each node's table ways begin: its middle
        self.start = np.concatenate([(self.left + self.right) / 2, (self.rope_top + self.rope_bottom) / 2])

    def _build_floors(self, fh):
        self.joints = joints(fh, self.chains)
        parent = list(range(self.n_chains))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        self.floor_joints = [j for j in self.joints if not j[4]]
        for a, b, *_ in self.floor_joints:
            ra, rb = find(self.index[a]), find(self.index[b])
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
        roots = [find(i) for i in range(self.n_chains)]
        number = {r: k for k, r in enumerate(dict.fromkeys(roots))}
        self.floor = np.array([number[r] for r in roots] + [-1] * len(self.ropes), np.int64)
        self.n_floors = len(number)

    def _build_columns(self):
        """Every whole x = c of the map: the surfaces over [c, c + 1) as K slots, then one slot for "nothing under",
        then two flags. Row c - x0 + 1 (rows 0 and W + 1, off the map, are empty), so floor(x) - x0 + 1 is any x's
        row, clipped. A row = [y at c] * K1 + [slope] * K1 + [node id] * K1 + [tolerance] * K1 + [|own slope|] * K1 +
        [close] + [rope near], the slots sorted by node id (equal distances: the lower id, as NavMap.platform_at); y at c is computed
        as Seg.y_at computes it. A foothold that ends at c covers c only: its slope is END (far above anywhere past
        c). A chain's two footholds meeting at c: the one going on. tolerance: stand_tol, stand_tol_slope for a
        foothold that is not level (+ EPS). An empty slot: y inf, node NONE; the last slot: y NOWHERE, node NONE (the
        first surface under nothing). close: two of the row's surfaces come within twice the larger tolerance of
        each other on [c, c + 1]; rope near: a rope's x is within rope_tol of the row."""
        x1, x2 = self.seg_x1.astype(np.int64), self.seg_x2.astype(np.int64)
        S = len(x1)
        x0 = int(x1.min()) if S else 0
        W = (int(x2.max()) - x0 + 1) if S else 1
        n_c = x2 - x1 + 1
        segs = np.repeat(np.arange(S), n_c)
        cols = x1[segs] + np.arange(len(segs)) - np.repeat(np.cumsum(n_c) - n_c, n_c)
        rows = cols - x0 + 1
        end = cols == x2[segs]
        nid = self.seg_node[segs]
        order = np.lexsort((end, nid, rows))
        rows, segs, nid, cols, end = rows[order], segs[order], nid[order], cols[order], end[order]
        keep = np.ones(len(rows), bool)
        keep[1:] = (rows[1:] != rows[:-1]) | (nid[1:] != nid[:-1])
        rows, segs, cols, end = rows[keep], segs[keep], cols[keep], end[keep]
        first = np.ones(len(rows), bool)
        first[1:] = rows[1:] != rows[:-1]
        starts = np.flatnonzero(first)
        counts = np.diff(np.append(starts, len(rows)))
        slot = np.arange(len(rows)) - np.repeat(starts, counts)
        K1 = (int(counts.max()) if len(counts) else 0) + 1
        c = self.cfg
        T = np.zeros((W + 2, 5 * K1 + 2), np.float64)
        T[:, :K1] = np.inf
        T[:, K1 - 1] = NOWHERE
        T[:, 3 * K1:4 * K1] = c.stand_tol + EPS
        sx1, sy1 = self.seg_x1[segs], self.seg_y1[segs]
        dyy, dxx = self.seg_y2[segs] - sy1, self.seg_x2[segs] - sx1
        T[rows, slot] = sy1 + (cols - sx1) * dyy / dxx                  # Seg.y_at at the whole x
        T[rows, K1 + slot] = np.where(end, END, dyy / dxx)
        T[rows, 2 * K1 + slot] = self.seg_node[segs]
        T[rows, 3 * K1 + slot] = np.where(dyy != 0, c.stand_tol_slope, c.stand_tol) + EPS
        T[rows, 4 * K1 + slot] = np.abs(dyy / dxx)                     # its own slope (also at its end), for the step
        # flag: two surfaces of the row come within twice the larger tolerance of each other on [c, c + 1] (only
        # then can two be within their tolerance of one thing's feet, and the last frame's node decide)
        y0 = T[:, :K1 - 1]
        y1 = y0 + np.where(T[:, K1:2 * K1 - 1] == END, 0.0, T[:, K1:2 * K1 - 1])
        close = np.zeros(W + 2, bool)
        lim = 2 * (max(c.stand_tol, c.stand_tol_slope) + EPS)
        with np.errstate(invalid="ignore"):
            for i in range(K1 - 1):
                for j in range(i + 1, K1 - 1):
                    d0, d1 = y0[:, i] - y0[:, j], y1[:, i] - y1[:, j]
                    close |= (np.abs(d0) <= lim) | (np.abs(d1) <= lim) | (d0 * d1 < 0)
        T[:, -2] = close
        for rx in self.rope_x:                                  # a climber's x may be within rope_tol of a rope
            lo, hi = int(np.floor(rx - c.rope_tol)) - x0 + 1, int(np.ceil(rx + c.rope_tol)) - x0 + 1
            T[max(0, lo):max(0, min(W + 2, hi + 1)), -1] = 1.0
        if len(self.rope_x) and (self.rope_x.min() - c.rope_tol < x0 or self.rope_x.max() + c.rope_tol > x0 + W - 1):
            T[0, -1] = T[-1, -1] = 1.0                          # a rope beyond the footholds' ends
        self._T, self._K1, self._roff = T, K1, x0 - 1
        self._flats = {}                                        # n -> flat slot indices (see _flat)
        self._step, self._rtol = c.stand_step + EPS, c.rope_tol
        self._nr = len(self.ropes)
        self._rlo, self._rhi = self.rope_top - c.rope_tol, self.rope_bottom + c.rope_tol

    def _build_fixed(self, m):
        """The fixed places: spawn points (mob kind, x, y, node: its foothold's chain) and portals (x, y, node by the
        placement rule, target map), the NPCs (x, y: a name tag near one is the NPC's, track/players.py), the map's
        bounds (vrBounds)."""
        sp = [v for v in m.get("mobs") or [] if not v.get("hidden")]
        self.spawn_kind = np.array([int(v["id"]) for v in sp], np.int64)
        self.spawn_x = np.array([v["x"] for v in sp], np.float64)
        self.spawn_y = np.array([v["y"] for v in sp], np.float64)
        placed = self.place(self.spawn_x, self.spawn_y).node if sp else np.zeros(0, np.int64)
        self.spawn_node = np.array([self.chain_of.get(int(v.get("footholdId") or 0), int(p))
                                    for v, p in zip(sp, placed)], np.int64)
        self.spawn_index = np.array([int(v.get("index", i)) for i, v in enumerate(sp)], np.int64)    # map.json's
        self.spawn_sy = np.array([v.get("spriteY", v["y"]) for v in sp], np.float64)   # a flyer appears there
        self.spawn_time = np.array([int(v.get("mobTime") or 0) for v in sp], np.int64)
        po = m.get("portals") or []
        self.portal_name = [v.get("portalName", "") for v in po]
        self.portal_x = np.array([v["x"] for v in po], np.float64)
        self.portal_y = np.array([v["y"] for v in po], np.float64)
        self.portal_to = np.array([int(v.get("toMap") or 0) for v in po], np.int64)
        self.portal_node = self.place(self.portal_x, self.portal_y).node if po else np.zeros(0, np.int64)
        self.npcs = [(float(v["x"]), float(v["y"])) for v in m.get("npcs") or []]
        self.bounds = dict(m.get("vrBounds") or {})

    # ---------------------------------------------------------------- queries
    def _slots(self, x, y):
        """n things -> (the surfaces' y over their x (n, K1), feet y - that y (n, K1), the rows (n, 4 K1 + 2)).
        x - (x0 - 1) truncated is the row for every x on the map (off it: rows 0 / W + 1, clipped, empty)."""
        xr = x - self._roff
        ri = xr.astype(np.intp)
        g = self._T.take(ri, 0, mode="clip")
        K1 = self._K1
        sy = (xr - ri)[:, None] * g[:, K1:2 * K1]
        sy += g[:, :K1]
        return sy, y[:, None] - sy, g

    def _flat(self, n):
        """Flat indices of slot 0 of each thing: into an (n, K1) array, and into the rows' node ids."""
        f = self._flats.get(n)
        if f is None:
            a = np.arange(n, dtype=np.intp)
            f = self._flats[n] = (a * self._K1, a * (5 * self._K1 + 2) + 2 * self._K1)
        return f

    @staticmethod
    def _arr(v):
        return v if type(v) is np.ndarray and v.dtype == np.float64 and v.ndim == 1 else \
            np.asarray(v, np.float64).ravel()

    def nearest(self, xs, ys, tol: float):
        """The surface nearest the feet at their x within tol - NavMap.platform_at's rule without its +-8 / 16 px
        retries (they are for the minimap's coarse x) -> (node ids, NONE where none; the surface's y, NaN)."""
        x, y = self._arr(xs), self._arr(ys)
        sy, d, g = self._slots(x, y)
        ad = np.abs(d)
        kc = ad.argmin(1)
        fs, fg = self._flat(len(x))
        ok = ad.ravel()[kc + fs] <= tol
        return (np.where(ok, g.ravel()[kc + fg], NONE).astype(np.int64),
                np.where(ok, sy.ravel()[kc + fs], np.nan))

    def place(self, xs, ys, dx=None, dy=None, last=None, last_from=None, climb=None, fly=None) -> Placed:
        """The placement rule for n things in one call (the module's docstring). xs, ys: feet (map px); dx, dy: the
        step since the thing's last frame (both or neither; None: no step); last: its last frame's node, last_from:
        its from_node (None: NONE); climb: can hang on ropes (us, players); fly: a kind that flies (never stands;
        its air is `fly`)."""
        x, y = self._arr(xs), self._arr(ys)
        n = len(x)
        sy, d, g = self._slots(x, y)
        ad = np.abs(d)
        fs, fg = self._flat(n)
        K1 = self._K1
        ok = ad <= g[:, 3 * K1:4 * K1]                  # within its surface's tolerance (3 px flat, 5 px sloped)
        kc = np.where(ok, ad, np.inf).argmin(1)         # the nearest of those
        stand = ok.ravel()[kc + fs]
        if last is not None and np.count_nonzero(g[:, -2]):
            m = ok & (g[:, 2 * K1:3 * K1] == np.asarray(last)[:, None])   # two within: the last frame's node wins
            kc = np.where(m.any(1), m.argmax(1), kc)
        if fly is not None:                             # a kind that flies never stands
            stand &= ~np.asarray(fly, bool)
        gf, df = g.ravel(), d.ravel()
        if dy is not None:                              # the step: the surface's own rise over it, in whole px, + 1
            rise = np.ceil(gf[kc + fg + 2 * K1] * np.abs(dx) - EPS)
            stand &= np.abs(dy) <= self._step + rise
        if stand.all():
            node = gf[kc + fg].astype(np.int64)
            return Placed(np.zeros(n, np.int8), node, node.copy(), df[kc + fs])
        kc = np.where(stand, kc, np.where(d > EPS, np.inf, ad).argmin(1))  # air: the first surface at or under
        node = gf[kc + fg].astype(np.int64)                                # the feet, else the last slot
        off = df[kc + fs]
        off[node == NONE] = np.nan
        loose = ~stand
        place = loose.view(np.int8)                     # STAND 0, AIR 1 (a new array: ~stand)
        if fly is not None:
            place[np.asarray(fly, bool) & loose] = FLY
        if climb is not None and self._nr:
            climb = climb if type(climb) is np.ndarray else np.asarray(climb, bool)
            if np.count_nonzero(g[:, -1][climb]):       # a climber where a rope is within reach (the row's flag)
                ci = np.flatnonzero((g[:, -1] > 0) & climb & ~stand)
                xc, yc = x[ci], y[ci]
                ar = np.abs(xc[:, None] - self.rope_x)
                yc = yc[:, None]
                ok = (ar <= self._rtol) & (yc >= self._rlo) & (yc <= self._rhi)
                if ok.any():
                    np.copyto(ar, np.inf, where=~ok)
                    j = ar.argmin(1)
                    hit = ok.any(1)
                    h, j = ci[hit], j[hit]
                    place[h] = ROPE
                    node[h] = -1 - j
                    off[h] = xc[hit] - self.rope_x[j]
                    stand = stand.copy()
                    stand[h] = True                     # hung on: from_node = this rope
        if last_from is None:
            return Placed(place, node, node * stand, off)
        return Placed(place, node, np.where(stand, node, np.asarray(last_from, np.int64)), off)

    def ix(self, ids) -> np.ndarray:
        """Node ids -> their indices in the node arrays (-1: not a node of this map)."""
        a = np.asarray(ids, np.int64)
        if not len(self.ids):
            return np.full(a.shape, -1, np.int64)
        i = np.clip(np.searchsorted(self._sorted_ids, a), 0, len(self.ids) - 1)
        return np.where(self._sorted_ids[i] == a, self._sorted[i], -1)

    def floor_of(self, ids) -> np.ndarray:
        """The floor number of each node id (-1: a rope, NONE or not a node)."""
        i = self.ix(ids)
        return np.where(i >= 0, self.floor[np.maximum(i, 0)], -1)

    def same_floor(self, a, b) -> np.ndarray:
        fa, fb = self.floor_of(a), self.floor_of(b)
        return (fa == fb) & (fa >= 0)

    def surface_y(self, ids, xs) -> np.ndarray:
        """The surface y of chain `id` at x for each pair (NaN: off it, or not a chain)."""
        x = self._arr(xs)
        sy, _, g = self._slots(x, np.zeros_like(x))
        ids = np.asarray(ids, np.int64).ravel()
        m = (g[:, 2 * self._K1:3 * self._K1] == ids[:, None]) & (ids != NONE)[:, None]
        k = m.argmax(1) + self._flat(len(x))[0]
        return np.where(m.any(1), sy.ravel()[k], np.nan)

    # ---------------------------------------------------------------- edges
    @property
    def nav(self) -> NavMap | None:
        e = self.edges
        return None if e is None else e.nav

    def seconds(self, a: int, b: int) -> float:
        """route()'s seconds from the middle of node a to node b (inf: no way)."""
        return float(self.edges.seconds[self.index[a], self.index[b]])

    def rebuild(self, nav: Nav) -> threading.Thread:
        """New edges and table for changed values, on a worker thread; swapped in whole when built (a newer
        request wins over an older one still building). -> the thread (join() to wait)."""
        with self._lock:
            self._gen += 1
            gen = self._gen
        th = threading.Thread(target=self._rebuild, args=(nav, gen), name=f"graph-edges-{self.map_id}", daemon=True)
        self._thread = th
        th.start()
        return th

    def _rebuild(self, nav: Nav, gen: int):
        e = build_edges(self, nav)
        with self._lock:
            if gen == self._gen:
                self.edges = e

    @property
    def rebuilding(self) -> bool:
        """A rebuild is running (the newest one asked for)."""
        return self._thread is not None and self._thread.is_alive()


def build_edges(g: Graph, nav: Nav) -> Edges:
    """navmap's links over the graph's nodes, then the seconds table from them."""
    t0 = time.perf_counter()
    nm = NavMap(dict(g.platforms), list(g.ropes), list(g.walls), [], nav)
    nm.spawns = list(g._nav_spawns)
    nm.links = nm._find_links()
    t1 = time.perf_counter()
    sec, arr = route_table(nm, g.ids, g.start)
    t2 = time.perf_counter()
    return Edges(nm, sec, arr, nav, t1 - t0, t2 - t1)


def route_table(nm: NavMap, ids, start) -> tuple:
    """route()'s seconds for every pair: NavMap.route's own search (the same moves in the same order, the same
    prices, one position kept per node, the first-found of equal costs), run to the end from each node's start.
    route() stops when it pops its goal; everything popped before is what this run pops, so row i holds route()'s
    answer for every goal. -> (seconds (N, N), arrive (N, N))."""
    ids = [int(v) for v in ids]
    N = len(ids)
    ix = {v: i for i, v in enumerate(ids)}
    out = [[] for _ in range(N)]
    for k in nm.links:
        out[ix[k.src]].append((k, ix[k.dst], k.lo, k.hi, ROUTE_COST[k.kind]))
    c = nm.cfg
    speed = [c.climb_speed if v < 0 else c.walk_speed for v in ids]
    sec = np.full((N, N), np.inf)
    arr = np.full((N, N), np.nan)
    land = {}
    inf = float("inf")
    for s in range(N):
        best = [inf] * N
        best[s] = 0.0
        srow, arow = sec[s], arr[s]
        done = [False] * N
        heap = [(0.0, 0, s, float(start[s]))]
        n = 0
        while heap:
            cost, _, u, p = heapq.heappop(heap)
            if cost > best[u]:
                continue
            if not done[u]:
                done[u] = True
                srow[u], arow[u] = cost, p
            sp = speed[u]
            for k, v, lo, hi, price in out[u]:
                t = lo if p < lo else hi if p > hi else p
                nc = cost + abs(t - p) / sp + price
                if nc < best[v]:
                    key = (id(k), t)
                    q = land.get(key)
                    if q is None:
                        q = land[key] = nm.landing(k, t)
                    best[v] = nc
                    n += 1
                    heapq.heappush(heap, (nc, n, v, q))
    return sec, arr
