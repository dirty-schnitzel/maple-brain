"""brain v3, layer: PLANNER - the goals (PLAN-v3.md migration steps 2-3; the Goal contract: v3/planner.py).

Hunt   (auto mode) always wants to run (the baseline, want 0). Its task each tick = brain v2's decision chain, moved
       here unchanged from BrainV2.step (step 2):
           a beat / break going on, or one starting now (never mid-fight, never in the air)    -> Rest
           target on our platform, or the one we're engaged on and still in keep reach      -> Fight(target)
           our swing still going (its mob died / moved off)                                 -> Fight(finishing)
           target elsewhere                                                                 -> Goto(target)
           nothing to fight                                                                 -> quiet(): Roam
       Before choosing it builds this tick's Scene (the tasks read it) and lets Targeting re-pick (every
       0.22-0.4 s, not in the air, not mid-trip on a rope; locked on the mob the weapon is engaged on).

HuntArea (Platform mode, step 3; the user 2026-11-09) = Hunt bound to the platforms marked before F7 (`area`):
       targets only on marked platforms (Targeting's `area` term); routes may cross unmarked ones.
       OFF THE AREA (we stand on an unmarked platform: fell, knocked off, a route through):
           FIGHT BACK: a mob on our platform within FIGHT_BACK_PX may be the target (never a trip to a mob off the
           area), then back - until the LEASH: LEASH_S (36-44 s, drawn per exit) after we left, nothing off the
           area is fought any more, not even the mob the weapon is engaged on (the lock is cut), and trips press
           no attack (a swing would stop the walk) - until we stand on a marked platform again.
           nothing to fight -> Back: travel to the nearest marked platform (route seconds; picked once per exit).
       ON THE AREA, nothing to fight -> Roam among the marked platforms' spots (ours too; Trips.area_goal).
Later: Rest a goal of its own, Buff, Restock, ... (how goals compete: tiers + scores, to be discussed).
"""
from ..v2.scene import Scene
from .planner import Goal
from .tasks import Back, Fight, Goto, Rest, Roam

LEASH_S = (36.0, 44.0)          # s off the marked platforms before fighting off them stops (the user: 40 s)


class Hunt(Goal):
    name = "hunt"

    def __init__(self, reach, weapon, footwork, targeting, trips, breaks):
        self.reach, self.weapon, self.footwork = reach, weapon, footwork
        self.targeting, self.trips, self.breaks = targeting, trips, breaks
        self.scene = None                                 # this tick's Scene (built in next_task)
        self.mode = "IDLE"                                # LOCAL / TRAVEL / ROAM / IDLE / BREAK / BACK (ticks log)
        self.trip_swings = True                           # trips may press at a mob in reach while walking

    def want(self, world) -> float:
        return 0.0

    def lock(self, sc):
        """The mob targeting must keep (the one the weapon is engaged on), or None."""
        return self.weapon.engaged

    def quiet(self, world):
        """The task when there's nothing to fight."""
        return Roam(self)

    def next_task(self, world):
        now, s, wp, tg = world.now, world.me.s, self.weapon, self.targeting
        sc = self.scene = Scene.of(world, self.reach)
        if self.breaks.resting(sc, wp.busy(now), world.me.hp_now):
            return Rest(self)
        tg.lock = self.lock(sc)                           # None when not engaged (it died / got away / no swing)
        if tg.due(now) and s.state != "air" and (s.state == "ground" or not self.trips.running):
            tg.pick(sc)
        x = tg.current(sc)
        fighting = x is not None and wp.engaged == x.id and sc.in_reach(x, keep=True)
        if x is not None and (x.here or fighting):        # fight it from here (engaged: wherever it stands)
            return Fight(self, x.id)
        if wp.swinging(now):                              # our swing is still going: stay, no trip
            return Fight(self, x.id if x is not None else None, finishing=True)
        if x is not None:                                 # go to it, swinging at whatever is in reach on the way
            return Goto(self, x.id)
        return self.quiet(world)                          # nothing to fight


class HuntArea(Hunt):
    name = "hunt_area"

    def __init__(self, area, world_map, hz, say, *parts):
        super().__init__(*parts)
        self.area = frozenset(area)
        self.map, self.hz, self.say = world_map, hz, say
        self.outside_since = None                         # we left the area then (None = on it)
        self.leash = LEASH_S[0]
        self.leashed = False                              # the leash ran out on this exit (logged once)
        self.back = None                                  # (platform, x) we're going back to

    # ------------------------------------------------------------------ where we are vs the area
    def _where(self, now, me):
        if me.s is None or me.state != "ground":          # on a rope / in the air: as on the last ground
            return
        if me.platform in self.area:
            if self.outside_since is not None:
                self.say(f"back on the marked platforms ({me.platform}) after {now - self.outside_since:.0f} s off")
            self.outside_since, self.back, self.leashed = None, None, False
        elif self.outside_since is None:
            self.outside_since = now
            self.leash = self.hz.between(*LEASH_S)
            self.say(f"off the marked platforms (on {me.platform}): fighting back only, leash {self.leash:.0f} s")

    def fight_back_ok(self, now) -> bool:
        if self.outside_since is None:
            return True
        ok = now - self.outside_since < self.leash
        if not ok and not self.leashed:
            self.leashed = True
            self.say(f"leash: {now - self.outside_since:.0f} s off the marked platforms -> no more fights off them")
        return ok

    # ------------------------------------------------------------------ Hunt's hooks
    def lock(self, sc):
        eng = sc.get(self.weapon.engaged) if self.weapon.engaged is not None else None
        if eng is not None and not self.targeting.allowed(sc, eng):
            return None                                   # the leash ran out: not even the mob we're fighting
        return self.weapon.engaged

    def quiet(self, world):
        if self.outside_since is None:
            return Roam(self, self.area)
        if self.back is None:
            self.back = self._nearest(world)
        if self.back is None:                             # in the air / no route now: coast, try again next tick
            return Roam(self, self.area)
        return Back(self, *self.back)

    def _nearest(self, world):
        """The marked platform with the shortest route from here, at the point nearest us. Platforms a failed trip
        made unreachable count only when all of them are."""
        now, me, tg = world.now, world.me, self.targeting
        best = []
        for pid in sorted(self.area):
            p = self.map.platform(pid)
            if p is None:
                continue
            x = p.clamp(me.x)
            c = self.map.route_seconds(now, me, pid, x)
            if c is not None:
                best.append((tg.unreachable.get(pid, 0.0) > now, c, pid, x))
        return min(best)[2:] if best else None

    def next_task(self, world):
        now, tg = world.now, self.targeting
        self._where(now, world.me)
        tg.area = self.area
        tg.fight_back = self.trip_swings = self.fight_back_ok(now)
        return super().next_task(world)
