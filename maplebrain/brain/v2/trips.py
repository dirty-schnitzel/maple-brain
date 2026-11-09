"""brain-v2 trips: one Travel (M1) at a time and what it's for - ("target", track id) or ("roam", platform).

`go(why, pid, x)` keeps the running trip if it's for the same thing (same platform, goal within 80 px), else replaces
it - only on the ground at a move boundary (never mid-jump). A trip starts on the ground or on a rope, never in the
air. A failed trip makes its platform unreachable for 5-8 s (targeting skips it).

Roam (placeholder until M3's patrol): nothing worth fighting tracked -> a spawn point on another platform, weighted by
the platform's spawns; linger 1-3.5 s after arriving; never linger on a rope.

v3 layer: tasks (Goto = a Travel; roam = today's Hunt goal's quiet-time task). Step 1: reads the world model's Map
(spawns as Spawn objects, route seconds) instead of NavMap tuples.
"""
import collections
import random

from ..moves import node_of
from ..travel import Travel


class Trips:
    def __init__(self, map_, hz, keymap, jump_key, targeting, stats, say):
        self.map, self.hz, self.keymap, self.jump_key = map_, hz, keymap, jump_key
        self.targeting, self.stats, self.say = targeting, stats, say
        self.travel, self.why = None, None
        self.roam_wait = 0.0

    @property
    def running(self) -> bool:
        return self.travel is not None and self.travel.status == "run"

    def end(self, driver):
        if self.travel is not None:
            self.travel = self.why = None
            if hasattr(driver, "cancel_taps"):
                driver.cancel_taps(self.jump_key)

    def coast(self, now, s, driver) -> bool:
        """In the air with a trip: let its move finish (land first). True = handled."""
        if self.travel is not None and s.state == "air":
            self.travel.step(now, s, driver)
            return True
        return False

    def go(self, now, s, driver, why, pid, x) -> str | None:
        """Travel toward (pid, x) for `why`. Returns the trip's status this tick, None = no trip running. Call
        `settle(now, status)` after anything else this tick (a swing on the way)."""
        tr = self.travel
        if tr is not None and tr.status == "run":
            same = self.why == why and tr.dst == pid and (tr.dst_x is None or abs(tr.dst_x - x) < 80)
            if not same and s.state == "ground" and (tr.move is None or tr.move.phase == "approach"):
                self.end(driver)
                tr = None
        if tr is None or tr.status != "run":
            if tr is not None and tr.status == "failed":
                self.targeting.unreachable[tr.dst] = now + self.hz.between(5, 8)
                self.say(f"trip to {tr.dst} failed ({tr.reason}): skipping it for a few s")
                self.end(driver)
                self.targeting.next_pick = now
                driver.hold(set())
                return None
            if s.state == "air" or pid is None:          # a trip starts on the ground or on a rope
                if s.state == "ground":
                    driver.hold(set())
                return None
            self.travel = Travel(self.map.nav, pid, x, self.hz, self.keymap)
            self.why = why
            self.stats["trips"] += 1
            self.say(f"travel {node_of(s)} x {s.x:.0f} -> {pid} x {x:.0f} ({why[0]})")
        return self.travel.step(now, s, driver)

    def settle(self, now, st):
        """A trip that arrived: forget it; after a roam trip, linger a moment."""
        if st == "done" and self.travel is not None:
            if self.why[0] == "roam":
                self.roam_wait = now + self.hz.between(1.0, 3.5)
            self.travel = self.why = None

    def walking(self, s) -> bool:
        """On the ground in a part of the trip where a swing doesn't spoil a move (walking / before a take-off)."""
        mv = self.travel.move if self.travel is not None else None
        return s.state == "ground" and (mv is None or mv.kind in ("walk_to", "walk") or mv.phase == "approach")

    # ------------------------------------------------------------------ roam (M3 replaces this)
    def roam(self, now, s, driver):
        """(mode, trip status): ROAM on a roam trip / IDLE lingering / None coasting in the air."""
        if self.travel is not None and self.why and self.why[0] == "roam":
            return "ROAM", self.go(now, s, driver, self.why, self.travel.dst, self.travel.dst_x)
        if self.coast(now, s, driver):
            return None, None
        self.end(driver)
        driver.hold(set())
        if s.state == "rope":                             # never linger on a rope: roam off it now
            self.roam_wait = min(self.roam_wait, now)
        if now < self.roam_wait or s.state == "air":
            return "IDLE", None
        g = self.roam_goal(now, s)
        if g is None:
            self.roam_wait = now + self.hz.between(1.0, 2.0)
            return "IDLE", None
        return "ROAM", self.go(now, s, driver, ("roam", g[0]), g[0], g[1])

    def roam_goal(self, now, s):
        """A spawn point on another platform, weighted by how many spawns its platform has."""
        by = collections.defaultdict(list)
        for sp in self.map.spawns:
            pid = sp.platform
            if pid is not None and pid != s.platform and self.targeting.unreachable.get(pid, 0) <= now:
                by[pid].append(sp.x)
        rng = getattr(self.hz, "rng", random)
        for _ in range(8):
            if not by:
                return None
            pid = rng.choices(list(by), weights=[len(v) for v in by.values()])[0]
            x = rng.choice(by[pid]) + rng.uniform(-40, 40)
            x = self.map.platforms[pid].clamp(x)
            if self.map.route_seconds(now, s, pid, x) is not None:
                return pid, x
            del by[pid]
        return None
