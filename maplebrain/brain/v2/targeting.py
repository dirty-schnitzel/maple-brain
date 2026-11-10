"""brain-v2 targeting: which mob to go for. ONE score per mob in seconds (lower = better) = the sum of named TERMS;
a preference is a new term here, never a branch elsewhere. None = can't reach it.

    reach   same platform: walking seconds to the standoff; other platforms: NavMap.route seconds to it
    turn    same platform and behind us: +0.25 s
    crowd   -0.25 s per other live mob within 120 px of it on its platform (max 3)
    others  +1.5 s while someone else is hitting it (hit seen with no swing of ours, last 3 s)
    area    Platform mode only (`area` = the marked platforms, set by the goal HuntArea; None = anywhere): a mob
            off the area can't be a target (None), except FIGHT BACK - on our platform within FIGHT_BACK_PX while
            `fight_back` (the goal's leash) allows it. A mob with no platform next to us (`here`) counts as in the
            area while we stand on a marked platform.

The current target is kept unless another scores KEEP_MARGIN better; the mob the weapon is engaged on is
kept, full stop (`lock`, set by the brain each tick). Re-picked every 0.22-0.4 s (varied), and at once when the
target is gone (dead / lost) - a tick without a target would roam off.
`standoff`: where to stand to fight it, picked per new target: the spear's length (sure far edge - 12..30 px).
A trip that failed makes its platform unreachable for 5-8 s (`unreachable`).
Part of the attack logic described end to end in v2/combat.py.
v3 layer: tasks (Fight / Goto pick their mob here; the planner's goals will score with the same terms). Step 1: reads
the world model (brain/v3/model.py): Map (route seconds, cached there now), Seen.mob (Mob) instead of track dicts.
Step 3: the `area` term (Platform mode).
"""
from ..moves import WALK
from .scene import sign

KEEP_MARGIN = 0.5
FIGHT_BACK_PX = 150             # Platform mode, off the marked platforms: a mob on our platform this close may be
                                # fought (it's at us; the user 2026-11-09: option B, never chase one off the area)


class Targeting:
    def __init__(self, map_, hz, ledger, stats, say):
        self.map, self.hz, self.ledger, self.stats, self.say = map_, hz, ledger, stats, say
        self.target, self.cost, self.standoff = None, None, 90.0
        self.next_pick = 0.0
        self.unreachable = {}                             # platform -> until
        self.terms = [self.t_area, self.t_reach, self.t_turn, self.t_crowd, self.t_others]
        self.lock = None                                  # the mob the weapon is engaged on: never switch mid-fight
        self.area = None                                  # Platform mode: the marked platform ids (None = anywhere)
        self.fight_back = True                            # Platform mode: off the area, may we fight back (leash)

    # ------------------------------------------------------------------ geometry
    def goal_x(self, x, me):
        """Where to stand to fight this mob from its platform: the standoff on our side of it."""
        p = self.map.platform(x.platform)
        side = sign(x.mob.x - me.x) or 1
        gx = x.mob.x - side * self.standoff
        return p.clamp(gx) if p is not None else gx

    # ------------------------------------------------------------------ the score
    def allowed(self, sc, x) -> bool:
        """Platform mode's fence (the `area` term): may this mob be a target at all?"""
        a = self.area
        if a is None or x.platform in a:
            return True
        if x.platform is None and x.here and sc.me.platform in a:
            return True
        return self.fight_back and x.here and abs(x.dx) <= FIGHT_BACK_PX

    def t_area(self, sc, x):
        return 0.0 if self.allowed(sc, x) else None

    def t_reach(self, sc, x):
        if x.here:
            return max(0.0, abs(x.dx) - self.standoff) / WALK
        pid = x.platform
        if pid is None or pid not in self.map.platforms or sc.now < self.unreachable.get(pid, 0.0):
            return None
        return self.map.route_seconds(sc.now, sc.me, pid, self.goal_x(x, sc.me))

    def t_turn(self, sc, x):
        return 0.25 if x.here and sc.facing and sign(x.dx) != sc.facing else 0.0

    def t_crowd(self, sc, x):
        n = sum(1 for o in sc.mobs if o is not x and o.platform == x.platform and abs(o.mob.x - x.mob.x) <= 120)
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
        locked = sc.get(self.lock) if self.lock is not None else None
        if locked is not None:                            # mid-fight: it stays the target until it's done
            if locked.id != self.target:
                self.stats["targets"] += 1
                self.say(f"target {locked.mob.type} id {locked.id} (the one we're fighting)")
            self.target, self.cost = locked.id, 0.0
            self.next_pick = sc.now + self.hz.between(0.22, 0.4)
            return
        cur = sc.get(self.target)
        cur_cost = self.score(sc, cur) if cur is not None else None
        best, best_cost = cur, cur_cost
        for x in sc.mobs:
            if x is cur or x.mob.state == "hidden" and x.mob.unseen > 0.5:
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
                self.standoff = self.hz.between(best.sure.hi - 30, best.sure.hi - 12)  # spear's length
                self.stats["targets"] += 1
                self.say(f"target {best.mob.type} id {best.id} on {best.platform} dx {best.dx:.0f} "
                         f"dy {best.dy:.0f}, cost {best_cost:.1f}s, standoff {self.standoff:.0f}")
            self.target, self.cost = best.id, best_cost
        self.next_pick = sc.now + self.hz.between(0.22, 0.4)

    def current(self, sc):
        """The target's Seen this tick; gone (dead / lost) -> re-pick NOW (not next tick: a tick without a target
        roams off elsewhere - the flapping after kills in runs/v2b-c)."""
        x = sc.get(self.target)
        if x is None and self.target is not None:
            self.target = None
            if sc.me.state != "air":
                self.pick(sc)
                x = sc.get(self.target)
            else:
                self.next_pick = sc.now
        return x
