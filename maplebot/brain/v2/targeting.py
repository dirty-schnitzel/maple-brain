"""brain-v2 targeting: which mob to go for. ONE score per mob in seconds (lower = better) = the sum of named TERMS;
a preference is a new term here, never a branch elsewhere. None = can't reach it.

    reach   same platform: walking seconds to the standoff; other platforms: NavMap.route seconds to it
    turn    same platform and behind us: +0.25 s
    crowd   -0.25 s per other live mob within 120 px of it on its platform (max 3)
    others  +1.5 s while someone else is hitting it (hit seen with no swing of ours, last 3 s)

The current target is kept unless another scores KEEP_MARGIN better. Re-picked every 0.22-0.4 s (varied).
A trip that failed makes its platform unreachable for 5-8 s (`unreachable`).
"""
from ..moves import WALK, node_of
from .scene import sign

KEEP_MARGIN = 0.5


class Targeting:
    def __init__(self, nav, hz, ledger, stats, say):
        self.nav, self.hz, self.ledger, self.stats, self.say = nav, hz, ledger, stats, say
        self.target, self.cost, self.standoff = None, None, 90.0
        self.next_pick = 0.0
        self.unreachable = {}                             # platform -> until
        self.route_cache = {}
        self.terms = [self.t_reach, self.t_turn, self.t_crowd, self.t_others]

    # ------------------------------------------------------------------ geometry
    def route_cost(self, now, s, pid, x):
        n = node_of(s)
        if n is None:                                     # in the air: no node to route from
            return None
        key = (n, round(s.x / 40), pid, round(x / 40))
        c = self.route_cache.get(key)
        if c is None or now - c[0] > 1.0:
            r = self.nav.route(n, s.y if self.nav.is_rope(n) else s.x, pid, x, with_cost=True)
            c = (now, r[1] if r is not None else None)
            self.route_cache[key] = c
            if len(self.route_cache) > 400:
                self.route_cache = {k: v for k, v in self.route_cache.items() if now - v[0] <= 1.0}
        return c[1]

    def goal_x(self, x, s):
        """Where to stand to fight this mob from its platform: the standoff on our side of it."""
        p = self.nav.platforms.get(x.platform)
        side = sign(x.m["x"] - s.x) or 1
        gx = x.m["x"] - side * self.standoff
        return p.clamp(gx) if p is not None else gx

    # ------------------------------------------------------------------ the score
    def t_reach(self, sc, x):
        if x.here:
            return max(0.0, abs(x.dx) - self.standoff) / WALK
        pid = x.platform
        if pid is None or pid not in self.nav.platforms or sc.now < self.unreachable.get(pid, 0.0):
            return None
        return self.route_cost(sc.now, sc.s, pid, self.goal_x(x, sc.s))

    def t_turn(self, sc, x):
        return 0.25 if x.here and sc.facing and sign(x.dx) != sc.facing else 0.0

    def t_crowd(self, sc, x):
        n = sum(1 for o in sc.mobs if o is not x and o.platform == x.platform and abs(o.m["x"] - x.m["x"]) <= 120)
        return -0.25 * min(n, 3)

    def t_others(self, sc, x):
        return 1.5 if self.ledger.contested_recently(x.id, sc.now) else 0.0

    def score(self, sc, x):
        total = 0.0
        for term in self.terms:
            v = term(sc, x)
            if v is None:
                return None
            total += v
        return total

    # ------------------------------------------------------------------ the pick
    def due(self, now) -> bool:
        return now >= self.next_pick

    def pick(self, sc):
        cur = sc.get(self.target)
        cur_cost = self.score(sc, cur) if cur is not None else None
        best, best_cost = cur, cur_cost
        for x in sc.mobs:
            if x is cur or x.m["state"] == "hidden" and x.m.get("unseen", 0) > 0.5:
                continue
            c = self.score(sc, x)
            margin = KEEP_MARGIN if best is cur and cur is not None else 0.0
            if c is not None and (best_cost is None or c < best_cost - margin):
                best, best_cost = x, c
        if best is None or best_cost is None:
            if self.target is not None:
                self.say("no target")
            self.target, self.cost = None, None
        else:
            if best.id != self.target:
                self.standoff = self.hz.between(best.sure.lo + 25, best.sure.hi - 20)
                self.stats["targets"] += 1
                self.say(f"target {best.m.get('mob')} id {best.id} on {best.platform} dx {best.dx:.0f} "
                         f"dy {best.dy:.0f}, cost {best_cost:.1f}s, standoff {self.standoff:.0f}")
            self.target, self.cost = best.id, best_cost
        self.next_pick = sc.now + self.hz.between(0.22, 0.4)

    def current(self, sc):
        """The target's Seen this tick; gone (dead / lost) -> forget it and re-pick at once."""
        x = sc.get(self.target)
        if x is None and self.target is not None:
            self.target = None
            self.next_pick = sc.now
        return x
