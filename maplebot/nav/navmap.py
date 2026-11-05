"""Map geometry from map.json: platforms (walkable foothold chains), ropes, and how to get from one platform to
another (walk across, walk off an edge, drop through, jump, ropes). Pure data + maths, no screen, unit-testable.

Nodes: platforms (id = leftmost foothold id, > 0) and ropes (id = -1 - index in `ropes`). A position on a platform
is an x, on a rope a y (height). Rope moves were measured with the user jumping around Perion
(runs/jump/20261101_234718_2): rope to rope, platform to a rope beside it, rope to platform.

Map coordinates: x right, y DOWN (a higher platform has a smaller y). Footholds are segments `x1,y1 -> x2,y2`
chained by `prev/next`; a walkable one runs left to right (x1 < x2), x1 == x2 is a wall, x1 > x2 a ceiling.
Platforms are one-way: you jump up through them from below and land on top; `down + jump` drops through.
"""
import heapq
import math
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Nav

SAMPLE = 4          # px between sample points when looking for links
SAME = 4            # two surfaces this close at the same x are one floor (walk across)
EDGE_OUT = 8        # walking off an edge we land this far past it


@dataclass(frozen=True)
class Seg:
    x1: float
    y1: float
    x2: float
    y2: float

    def y_at(self, x: float) -> float:
        return self.y1 + (x - self.x1) * (self.y2 - self.y1) / (self.x2 - self.x1)


@dataclass
class Platform:
    id: int                       # the id of its first (leftmost) foothold
    segs: list                    # [Seg] left to right
    open_left: bool = True        # we can walk off that end (False: a wall or the map's edge stops us)
    open_right: bool = True

    @property
    def left(self) -> float:
        return self.segs[0].x1

    @property
    def right(self) -> float:
        return self.segs[-1].x2

    def y_at(self, x: float) -> float | None:
        """The surface's y at x, or None off the platform."""
        if not self.left <= x <= self.right:
            return None
        for s in self.segs:
            if s.x1 <= x <= s.x2:
                return s.y_at(x)
        return None                                     # a gap inside the chain (never seen)

    def clamp(self, x: float) -> float:
        return min(max(x, self.left), self.right)


@dataclass(frozen=True)
class Rope:
    x: float
    top: float                    # smaller y
    bottom: float
    ladder: bool = False


@dataclass(frozen=True)
class Link:
    """One move from platform `src` to `dst`, taken off anywhere in [lo, hi] on src.
    lo/hi are x on a platform, y (height) on a rope.
    kind: walk (surfaces meet), fall (walk off the end, dir = -1/+1), drop (down + jump, straight down),
    jump (dir 0 = straight up through dst; -1/+1 = a walking jump, lands ~jump_reach that way),
    grab (platform -> rope: jump + up, dir 0 straight up / -1/+1 sideways), descend (platform -> rope from its top:
    down), exit (rope -> the platform at its top: climb up), let_go (rope -> what's under its bottom: climb down),
    leap (rope -> rope / platform: jump sideways off the rope, dir -1/+1)."""
    kind: str
    src: int
    dst: int
    lo: float
    hi: float
    dir: int = 0


@dataclass
class NavMap:
    platforms: dict                                   # id -> Platform
    ropes: list = field(default_factory=list)         # [Rope]
    walls: list = field(default_factory=list)         # [Seg] vertical
    links: list = field(default_factory=list)         # [Link]
    cfg: Nav = field(default_factory=Nav)
    spawns: list = field(default_factory=list)        # [(x, y)] the map's mob spawn points (map.json 'mobs')

    # ---------------------------------------------------------------- building
    @classmethod
    def from_json(cls, m: dict, cfg: Nav | None = None) -> "NavMap":
        cfg = cfg or Nav()
        fh = {int(k): v for k, v in m["footholds"].items()}
        floor = {i for i, f in fh.items() if f["x1"] < f["x2"]}
        walls = [Seg(f["x1"], min(f["y1"], f["y2"]), f["x2"], max(f["y1"], f["y2"]))
                 for f in fh.values() if f["x1"] == f["x2"]]
        plats, seen = {}, set()
        for i in sorted(floor):
            if i in seen or fh[i]["prev"] in floor:   # not the left end of a walkable chain
                continue
            segs, j = [], i
            while j in floor and j not in seen:
                seen.add(j)
                f = fh[j]
                segs.append(Seg(f["x1"], f["y1"], f["x2"], f["y2"]))
                j = f["next"]
            plats[i] = Platform(i, segs)
        for i in sorted(floor - seen):                  # chains with no left end (a loop): never seen, keep them
            f = fh[i]
            plats[i] = Platform(i, [Seg(f["x1"], f["y1"], f["x2"], f["y2"])])
        xs = [v for f in fh.values() for v in (f["x1"], f["x2"])]
        x_min, x_max = min(xs), max(xs)
        for p in plats.values():
            p.open_left = not (p.left <= x_min + 1 or _walled(walls, p.left, p.segs[0].y1))
            p.open_right = not (p.right >= x_max - 1 or _walled(walls, p.right, p.segs[-1].y2))
        ropes = [Rope(r["x"], min(r["y1"], r["y2"]), max(r["y1"], r["y2"]), bool(r.get("isLadder")))
                 for r in m.get("ladderRopes") or []]
        nm = cls(plats, ropes, walls, [], cfg)
        nm.spawns = [(float(v["x"]), float(v["y"])) for v in m.get("mobs") or [] if not v.get("hidden")]
        nm.links = nm._find_links()
        return nm

    @classmethod
    def for_map(cls, map_id: int, root: Path, cfg: Nav | None = None) -> "NavMap":
        m = json.loads((root / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
        return cls.from_json(m, cfg)

    def _find_links(self) -> list:
        h, reach = self.cfg.jump_height, self.cfg.jump_reach
        raw = []                                         # (kind, src, dst, x, dir) per sample point
        for a in self.platforms.values():
            for x in _samples(a.left, a.right):
                ya = a.y_at(x)
                for b, yb in self.surfaces(x):
                    if b is not a and abs(yb - ya) <= SAME:
                        raw.append(("walk", a.id, b.id, x, 0))
                down = self.below(x, ya + SAME)
                if down is not None:
                    raw.append(("drop", a.id, down.id, x, 0))
                up = self._landing_above(x, ya, h, a)
                if up is not None:
                    raw.append(("jump", a.id, up.id, x, 0))
                for d in (-1, 1):                        # a walking jump: where the arc comes down first
                    hit = self.arc(x, ya, d)
                    # down to 2 jump heights lower (the user, runs/jump: 130 -> 191 78 px down, 113 -> 127 82 px)
                    if hit is not None and hit[1] is not a and ya - h <= hit[1].y_at(hit[2]) <= ya + 2 * h:
                        raw.append(("jump", a.id, hit[1].id, x, d))
            for d, open_, x in ((-1, a.open_left, a.left), (1, a.open_right, a.right)):
                if open_:
                    land = self.below(x + d * EDGE_OUT, (a.y_at(x) or 0) - SAME)
                    if land is not None and land is not a:
                        raw.append(("fall", a.id, land.id, x, d))
        return _merge(raw) + self._rope_links()

    # ---------------------------------------------------------------- ropes
    def rope_id(self, i: int) -> int:
        return -1 - i

    def rope(self, node: int) -> Rope:
        return self.ropes[-1 - node]

    @staticmethod
    def is_rope(node: int) -> bool:
        return node < 0

    def _top_platform(self, r: Rope):
        """The platform a rope leads up to: its top end sits 0-10 px under that surface (Perion -124 / -492 / 764)."""
        top = [(abs(y - r.top), p.id, p) for p, y in self.surfaces(r.x) if abs(y - r.top) <= 15]
        return min(top)[2] if top else None

    def _rope_links(self) -> list:
        c = self.cfg
        raw = []
        for i, r in enumerate(self.ropes):
            rid = self.rope_id(i)
            top = self._top_platform(r)
            if top is not None:
                raw.append(("exit", rid, top.id, r.top, 0))
                raw.append(("descend", top.id, rid, r.x, 0))
            under = self.below(r.x, r.bottom)
            if under is not None and under is not top:
                raw.append(("let_go", rid, under.id, r.bottom, 0))
            for a in self.platforms.values():               # jump + up from a platform: straight or sideways
                lo, hi = max(a.left, r.x - c.jump_reach), min(a.right, r.x + c.jump_reach)
                if lo > hi:
                    continue
                for x in _samples(lo, hi):
                    ya = a.y_at(x)
                    if ya is None or (a is top and abs(x - r.x) < 15):
                        continue
                    if r.bottom >= ya - c.rope_grab and r.top <= ya - 10:
                        d = 0 if abs(r.x - x) <= 10 else (1 if r.x > x else -1)
                        raw.append(("grab", a.id, rid, x, d))
            for d in (-1, 1):                                # jump sideways off the rope
                nxt = sorted((abs(q.x - r.x), j) for j, q in enumerate(self.ropes)
                             if 0 < d * (q.x - r.x) <= c.rope_leap)
                for y in _samples(r.top, r.bottom):
                    caught = [j for _, j in nxt if self.ropes[j].top <= y + c.leap_drop <= self.ropes[j].bottom]
                    if caught:                               # holding up: the nearest rope on the way catches us
                        raw.append(("leap", rid, self.rope_id(caught[0]), y, d))
                    lands = [(p.y_at(r.x + d * off), p.id, p) for off in _leap_offsets(c)   # seen 48-80 px out
                             if (p := self.below(r.x + d * off, y - 15)) is not None]
                    if lands:                                # the arc meets the highest surface first
                        raw.append(("leap", rid, min(lands)[2].id, y, d))
        return _merge(raw)

    def arc(self, x: float, y: float, d: int):
        """A walking jump from feet (x, y) toward d: the first surface the arc comes down on, as (secs, platform,
        x there), or None (nothing within 2 jump heights below... or more: the caller decides). Physics.img: jump
        555 px/s, gravity 2000; horizontal cfg.jump_vx. One-way platforms: only crossings on the way DOWN count,
        so the highest surface under the descending arc wins. Reach depends on the height: landing 60 px up
        comes down after ~0.43 s (~67 px), level after ~0.56 s (~86 px), 70 px down after ~0.65 s."""
        c = self.cfg
        v, g, vx = c.jump_speed, c.gravity, c.jump_vx
        best = None
        for p in self.platforms.values():
            yb = p.y_at(min(max(x + d * vx * v / g * 2, p.left), p.right))
            for _ in range(3):                           # the surface's y where we come down (slopes): iterate
                rise = y - yb
                disc = v * v - 2 * g * rise
                if disc < 0:
                    break
                t = (v + math.sqrt(disc)) / g
                xl = x + d * vx * t
                y2 = p.y_at(xl)
                if y2 is None:
                    break
                if abs(y2 - yb) < 0.5:
                    if best is None or t < best[0]:
                        best = (t, p, xl)
                    break
                yb = y2
        return best

    def _landing_above(self, x, y, h, not_this):
        """Jumping at x from feet y: the highest surface in (y - h, y - SAME) we can land on (one-way platforms)."""
        best = None
        for p, yp in self.surfaces(x):
            if p is not not_this and y - h <= yp < y - SAME and (best is None or yp < best[1]):
                best = (p, yp)
        return best and best[0]

    # ---------------------------------------------------------------- queries
    def surfaces(self, x: float):
        """[(platform, y)] for every platform over x."""
        out = []
        for p in self.platforms.values():
            y = p.y_at(x)
            if y is not None:
                out.append((p, y))
        return out

    def platform_at(self, x: float, y: float, tol: float | None = None) -> Platform | None:
        """The platform whose surface at x is nearest our feet y (within tol), or None (in the air, on a rope).
        Nothing at x: one minimap px (16 map px) either side is tried - our x is that coarse, and next to a wall it
        lands on the wrong side (rain1: in the pit at its wall, read as x 238 beyond the wall at 231)."""
        tol = self.cfg.surface_tol if tol is None else tol
        for dx in (0, -8, 8, -16, 16):
            best = min(((abs(yp - y), p.id, p) for p, yp in self.surfaces(x + dx) if abs(yp - y) <= tol),
                       default=None)
            if best is not None:
                return best[2]
        return None

    def below(self, x: float, y: float) -> Platform | None:
        """The first surface lower than y at x (where a drop or a fall lands), or None (nothing below)."""
        best = min(((yp, p.id, p) for p, yp in self.surfaces(x) if yp > y), default=None)
        return best and best[2]

    def rope_at(self, x: float, y: float, tol: float | None = None) -> Rope | None:
        tol = self.cfg.rope_tol if tol is None else tol
        for r in self.ropes:
            if abs(r.x - x) <= tol and r.top - tol <= y <= r.bottom + tol:
                return r
        return None

    def step_ahead(self, pid: int, x: float, d: int):
        """Walking on platform pid at x in direction d (-1 left / +1 right): the barrier at its end, if any, as
        (distance to it, rise = how far the floor beyond is above ours). None: that end is open (we'd walk off /
        step down). rise = inf: the map ends there or nothing is beyond the wall."""
        p = self.platforms.get(pid)
        if p is None:
            return None
        end = p.right if d > 0 else p.left
        if p.open_right if d > 0 else p.open_left:
            return None
        ye = p.y_at(end)
        higher = [ye - yq for q, yq in self.surfaces(end + d * 6) if q is not p and yq < ye - SAME]
        return (d * (end - x), min(higher) if higher else float("inf"))

    def spawn_center(self, y: float | None = None) -> float | None:
        """The x where mobs spawn densest (a gaussian of cfg.spawn_bw around each spawn point, sampled every 10 px),
        counting only spawns within cfg.spawn_level of height y (our floor) - all of them if none / y unknown.
        None: the map spawns nothing."""
        c = self.cfg
        pts = [sx for sx, sy in self.spawns if y is None or abs(sy - y) <= c.spawn_level] or               [sx for sx, _ in self.spawns]
        if not pts:
            return None
        key = tuple(pts)
        cache = self.__dict__.setdefault("_spawn_cache", {})
        if key not in cache:
            lo, hi = min(pts), max(pts)
            xs = [lo + i * 10 for i in range(int((hi - lo) // 10) + 1)] + [hi]
            w = 2 * c.spawn_bw ** 2
            cache[key] = max(xs, key=lambda x: sum(math.exp(-(x - p) ** 2 / w) for p in pts))
        return cache[key]

    def links_from(self, pid: int) -> list:
        return [k for k in self.links if k.src == pid]

    # ---------------------------------------------------------------- routes
    def route(self, src: int, pos: float, dst: int, dst_x: float | None = None, avoid=()) -> list | None:
        """Cheapest list of Links from node src at pos (x on a platform, y on a rope) to node dst (and, if given,
        then to dst_x on that platform). Cost = seconds: walking/climbing to each take-off point + a fixed price
        per move. `avoid`: links not to use (they failed). None if there's no way."""
        cost = {"walk": 0.0, "fall": 0.5, "drop": 0.8, "jump": 0.7, "grab": 0.7, "descend": 0.4, "exit": 0.4,
                "let_go": 0.5, "leap": 0.7}
        best = {src: 0.0}
        heap = [(0.0, 0, src, pos, [])]
        n = 0
        while heap:
            c, _, node, p, path = heapq.heappop(heap)
            if c > best.get(node, float("inf")):
                continue
            if node == dst:
                return path
            speed = self.cfg.climb_speed if self.is_rope(node) else self.cfg.walk_speed
            for k in self.links_from(node):
                if k in avoid:
                    continue
                t = min(max(p, k.lo), k.hi)                           # nearest take-off point
                land = self.landing(k, t)
                nc = c + abs(t - p) / speed + cost[k.kind]
                if dst_x is not None and k.dst == dst and not self.is_rope(dst):
                    nc += abs(land - dst_x) / self.cfg.walk_speed
                if nc < best.get(k.dst, float("inf")):
                    best[k.dst] = nc
                    n += 1
                    heapq.heappush(heap, (nc, n, k.dst, land, path + [k]))
        return None

    def landing(self, k: Link, t: float) -> float:
        """Where taking link k off at t (x on a platform, y on a rope) puts us: x on a platform, y on a rope."""
        c = self.cfg
        if k.kind == "fall":
            return t + k.dir * EDGE_OUT
        if k.kind == "jump" and k.dir:
            src = self.platforms.get(k.src)
            hit = self.arc(t, src.y_at(src.clamp(t)), k.dir) if src is not None else None
            if hit is not None and hit[1].id == k.dst:
                return hit[2]
            return self.platforms[k.dst].clamp(t + k.dir * c.jump_reach)
        if k.kind == "grab":
            r = self.rope(k.dst)
            return min(max(self.platforms[k.src].y_at(t) - c.grab_body, r.top), r.bottom)
        if k.kind == "descend":
            return self.rope(k.dst).top + 20
        if k.kind in ("exit", "let_go"):
            return self.rope(k.src).x
        if k.kind == "leap":
            if self.is_rope(k.dst):
                r = self.rope(k.dst)
                return min(max(t + c.leap_drop, r.top), r.bottom)
            p, x = self.platforms[k.dst], self.rope(k.src).x
            return next((x + k.dir * o for o in _leap_offsets(c) if p.y_at(x + k.dir * o) is not None),
                        p.clamp(x + k.dir * c.leap_land))
        return t


def _leap_offsets(c: Nav) -> tuple:
    """How far out a leap off a rope may land (the user: 48-80 px), most likely first."""
    return (c.leap_land, c.leap_land + 20, c.leap_land - 20)


def _walled(walls, x, y) -> bool:
    """A wall at x rising above the surface y stops us there (a stub hanging below a platform doesn't)."""
    return any(abs(w.x1 - x) <= 2 and w.y1 < y - 2 <= w.y2 for w in walls)


def _samples(lo, hi):
    lo, hi = lo + 1, hi - 1
    n = max(1, int((hi - lo) // SAMPLE))
    return [lo + (hi - lo) * i / n for i in range(n + 1)]


def _merge(raw) -> list:
    """Consecutive sample points with the same (kind, src, dst, dir) -> one Link over [lo, hi]."""
    groups = {}
    for kind, s, d, x, dr in raw:
        groups.setdefault((kind, s, d, dr), []).append(x)
    out = []
    for (kind, s, d, dr), xs in groups.items():
        xs.sort()
        lo = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is None or x - prev > SAMPLE * 1.5:
                out.append(Link(kind, s, d, lo, prev, dr))
                lo = x
            prev = x if x is not None else prev
    return sorted(out, key=lambda k: (k.src, k.kind, k.lo))
