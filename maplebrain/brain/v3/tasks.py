"""brain v3, layer: TASKS (PLAN-v3.md migration step 2): one interruptible job each, stepped every tick by the
planner (v3/planner.py: the Task contract). The work itself stays in brain v2's parts, moved here unchanged from
BrainV2.step's branches:

    Fight(mob)      fight it from here: Weapon (when to press) + Footwork (where to stand) - the attack logic end to
                    end is v2/combat.py's doc. finishing=True: our swing is still going (its mob died / moved off):
                    stand, the weapon only (it may press at another mob in reach in front).
    Goto(mob)       travel to the target's platform (Trips -> Travel, M1), pressing only while the trip walks.
    Roam            nothing to fight: a weighted spawn elsewhere, linger after arriving (Trips.roam, until M3).
                    Platform mode: spots on the marked platforms only (area).
    Back            Platform mode (step 3): off the marked platforms, nothing to fight -> the nearest marked one.
    Rest            a beat after a fight or a break at a safe spot (Breaks): no keys.

A task holds no per-tick data, only its target's id: it reads this tick's Scene from the goal that made it (Hunt),
so a running task kept by the planner (same kind + target) sees the same as a fresh one. Modes for the ticks log
(LOCAL / TRAVEL / ROAM / IDLE / BREAK / BACK) are written on that goal, as BrainV2 did.
"""
from .planner import Task


class Fight(Task):
    name = "fight"

    def __init__(self, goal, tid, finishing=False):
        super().__init__()
        self.goal, self.tid, self.finishing = goal, tid, finishing

    def key(self):
        return ("finish" if self.finishing else "fight", self.tid)

    def step(self, now, world, hands) -> str:
        g = self.goal
        sc = g.scene
        g.trips.end(hands)
        g.mode = "LOCAL"
        if self.finishing:
            hands.hold(set())
            g.weapon.step(sc, hands, target=self.tid)
            return "run"
        x = sc.get(self.tid)
        g.weapon.step(sc, hands, target=x.id)
        g.footwork.step(sc, x, g.targeting.standoff, hands, swinging=g.weapon.swinging(now))
        return "run"


class Goto(Task):
    name = "goto"

    def __init__(self, goal, tid):
        super().__init__()
        self.goal, self.tid = goal, tid

    def key(self):
        return (self.name, self.tid)

    def step(self, now, world, hands) -> str:
        g = self.goal
        sc, s, tg, trips = g.scene, world.me.s, g.targeting, g.trips
        x = sc.get(self.tid)
        st = trips.go(now, s, hands, ("target", x.id), x.platform, tg.goal_x(x, s))
        if st is not None:
            g.mode = "TRAVEL"
        g.weapon.step(sc, hands, allowed=st == "run" and trips.walking(s) and g.trip_swings, target=x.id)
        trips.settle(now, st)
        if st == "done":
            self.events.append("arrived")
        return st or "run"


class Roam(Task):
    name = "roam"

    def __init__(self, goal, area=None):
        super().__init__()
        self.goal, self.area = goal, area

    def step(self, now, world, hands) -> str:
        g = self.goal
        s, trips = world.me.s, g.trips
        mode, st = trips.roam(now, s, hands, self.area)
        if mode is not None:
            g.mode = mode
        g.weapon.step(g.scene, hands, allowed=trips.travel is None or trips.walking(s))
        trips.settle(now, st)
        if st == "done":
            self.events.append("arrived")
        return "run"


class Back(Task):
    """Platform mode: off the marked platforms with nothing to fight -> travel to (pid, x), the nearest marked
    platform (picked by the goal, kept until we're back). The weapon swings at a mob in reach in front while the
    trip walks, like any trip - until the goal's leash runs out (`trip_swings`)."""
    name = "back"

    def __init__(self, goal, pid, x):
        super().__init__()
        self.goal, self.pid, self.x = goal, pid, x

    def key(self):
        return (self.name, self.pid)

    def step(self, now, world, hands) -> str:
        g = self.goal
        sc, s, trips = g.scene, world.me.s, g.trips
        st = trips.go(now, s, hands, ("area", self.pid), self.pid, self.x)
        if st is not None:
            g.mode = "BACK"
        g.weapon.step(sc, hands, allowed=st == "run" and trips.walking(s) and g.trip_swings)
        trips.settle(now, st)
        if st == "done":
            self.events.append("arrived")
        return st or "run"


class Rest(Task):
    name = "rest"

    def __init__(self, goal):
        super().__init__()
        self.goal = goal

    def step(self, now, world, hands) -> str:
        g = self.goal
        g.trips.end(hands)
        hands.hold(set())
        g.mode = "BREAK"
        return "run"
