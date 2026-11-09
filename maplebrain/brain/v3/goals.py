"""brain v3, layer: PLANNER - the goals (PLAN-v3.md migration step 2; the Goal contract: v3/planner.py).

Hunt   always wants to run (the baseline, want 0). Its task each tick = brain v2's decision chain, moved here
       unchanged from BrainV2.step:
           a beat / break going on, or one starting now (never mid-fight, never in the air)    -> Rest
           target on our platform, or the one we're engaged on and still in keep reach      -> Fight(target)
           our swing still going (its mob died / moved off)                                 -> Fight(finishing)
           target elsewhere                                                                 -> Goto(target)
           nothing to fight                                                                 -> Roam
       Before choosing it builds this tick's Scene (the tasks read it) and lets Targeting re-pick (every
       0.22-0.4 s, not in the air, not mid-trip on a rope; locked on the mob the weapon is engaged on).

Step 3 adds HuntArea (Platform mode, marked platforms); later Rest becomes a goal of its own, then Buff, Restock, ...
"""
from ..v2.scene import Scene
from .planner import Goal
from .tasks import Fight, Goto, Rest, Roam


class Hunt(Goal):
    name = "hunt"

    def __init__(self, reach, weapon, footwork, targeting, trips, breaks):
        self.reach, self.weapon, self.footwork = reach, weapon, footwork
        self.targeting, self.trips, self.breaks = targeting, trips, breaks
        self.scene = None                                 # this tick's Scene (built in next_task)
        self.mode = "IDLE"                                # LOCAL / TRAVEL / ROAM / IDLE / BREAK (ticks log)

    def want(self, world) -> float:
        return 0.0

    def next_task(self, world):
        now, s, wp, tg = world.now, world.me.s, self.weapon, self.targeting
        sc = self.scene = Scene.of(world, self.reach)
        if self.breaks.resting(sc, wp.busy(now), world.me.hp_now):
            return Rest(self)
        tg.lock = wp.engaged                              # None when not engaged (it died / got away / no swing)
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
        return Roam(self)                                 # nothing to fight
