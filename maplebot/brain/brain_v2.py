"""brain-v2, M2: the Hunt skill - combat only (no loot, no patrol plan yet: M3).

Every tick `step(now, obs, s, driver)` with obs = the Perceiver's Obs (tracks in obs.mobs: --gpu), s = our SelfState
(nav/selfstate), driver = runtime/keys.KeyDriver (or a fake in tests). It presses the keys itself, like Travel.

  reflexes first:   HP / MP potions (cooldowns varied), HP stop (no potions), out of MP -> the plain attack key
  target:           every ~0.3 s: the live track cheapest to reach - same platform = walking seconds to the standoff,
                    other platforms = NavMap.route seconds; small bonuses for crowds, penalties for mobs someone else
                    is hitting (hit with no swing of ours) and for platforms a trip just failed to reach. The current
                    target is kept unless another is clearly cheaper (0.5 s).
  engage here:      walk toward the target (never away), let go so the slide stops us at a standoff picked per target
                    inside the sure reach; turn at most once per 2.5 s (no left-right-left-right).
  WHEN TO HIT:      a tap of the attack when a live mob's PREDICTED position (its vx over the swing's ~0.45 s) is in
                    front within reach (brain/reach.py: client attack boxes vs the mob's body) - also while walking
                    and while travelling; never at nothing; next swing after the swing cycle (0.72-1.05 s, the user's
                    gaps; now and then a quick re-tap like the user's).
  elsewhere:        Travel(nav, platform, x) toward the target (M1), re-aimed when the target moves away; swings at
                    whatever is in reach on the way.
  nothing tracked:  roam to a spawn platform (weighted by spawns), linger a few s (M3 replaces this).

Learning / stats: each swing logs the mobs in front (dx, dy) and whether they reacted (reach.learned()); kills by LAST
HIT by our weapon (a track turns dying 0.2..1.0 s after our swing that had it in reach).
"""
import collections
import random

from .moves import WALK, node_of
from .reach import SWING_LAND_S, Reach
from .travel import Travel

LIVE = ("live", "hit", "hidden")
KILL_WINDOW = (0.2, 1.0)        # swing press -> its target turns dying (farming example: peak 0.5-0.8 s, few after 1.0)


def _sign(v):
    return (v > 0) - (v < 0)


class BrainV2:
    def __init__(self, cfg, nav, hz, reach: Reach | None = None, log=None):
        self.cfg, self.nav, self.hz = cfg, nav, hz
        self.reach = reach or Reach(cfg.combat.weapon)
        self.say = log or (lambda msg: None)
        self.keymap = {"jump": cfg.keys.jump}
        self.mode = "IDLE"                                # LOCAL / TRAVEL / ROAM / IDLE
        self.target, self.target_cost, self.standoff = None, None, 90.0
        self.next_pick = 0.0
        self.travel, self.travel_for = None, None         # Travel + what it's for: ("target", id) / ("roam", pid)
        self.facing = 0                                   # +1 right / -1 left / 0 unknown
        self.flips = collections.deque()                  # times we turned (no back-and-forth)
        self.next_swing, self.swing_t = 0.0, -9.0
        self.potion_t = {"hp": 0.0, "mp": 0.0}
        self.hist = {}                                    # track id -> deque[(t, state)]
        self.contested = {}                               # track id -> t someone else's hit was seen
        self.unreachable = {}                             # platform -> until
        self.route_cache = {}
        self.roam_wait = 0.0
        self.stats = collections.Counter()
        self.kill_t = []
        self.strikes = collections.deque()                # (t, ids in our weapon's reach at that swing)
        self.tick_swing = None

    # ------------------------------------------------------------------ helpers
    def _hold(self, driver, keys):
        driver.hold(keys)
        d = (1 if "right" in keys else 0) - (1 if "left" in keys else 0)
        if d:
            self._face(d)

    def _face(self, d):
        if d and d != self.facing:
            if self.facing:
                self.flips.append(self._now)
            self.facing = d

    def _can_turn(self, now):
        while self.flips and now - self.flips[0] > 2.5:
            self.flips.popleft()
        return len(self.flips) < 2

    def _rel(self, m, obs, s):
        """(dx, dy) of a track from our feet: screen px when both were seen this frame (no camera error), else map."""
        if obs.me is not None and m.get("src") != "none" and m.get("sx") is not None:
            return m["sx"] - obs.me[0], m["sy"] - obs.me[1]
        return m["x"] - s.x, m["y"] - s.y

    def _pred(self, m, dx):
        return dx + (m.get("vx") or 0.0) * SWING_LAND_S

    def _live(self, obs):
        return [m for m in obs.mobs if m.get("kind", "mob") == "mob" and m["state"] in LIVE
                and m.get("unseen", 0) <= 1.5]

    def _here(self, m, s, dy):
        return s.state == "ground" and (m.get("platform") == s.platform or (m.get("platform") is None and abs(dy) <= 40))

    # ------------------------------------------------------------------ bookkeeping: outcomes, kills, contested
    def _book(self, now, obs, s):
        for m in obs.mobs:
            h = self.hist.setdefault(m["id"], collections.deque())
            prev = h[-1][1] if h else None
            h.append((now, m["state"]))
            while h and now - h[0][0] > 3.0:
                h.popleft()
            if m["state"] == prev:
                continue
            ours = [n for t, n in self.reach.swings if now - t <= 1.0]
            had = any(tid == m["id"] for near in ours for tid, dx, dy in near)
            if m["state"] == "dying" and prev in LIVE:
                if self._our_kill(now, m["id"]):
                    self.stats["kills"] += 1
                    self.kill_t.append(now)
                    self.say(f"kill #{self.stats['kills']} (last hit): {m.get('mob')} id {m['id']}")
                else:
                    self.stats["deaths_not_ours"] += 1
            elif m["state"] == "hit" and prev in ("live", "hidden") and not had and now - self.swing_t > 1.0:
                self.contested[m["id"]] = now
        for i in [i for i, h in self.hist.items() if h and now - h[-1][0] > 3.0]:
            del self.hist[i]

        def state_of(tid, t0, t1):
            return [st for t, st in self.hist.get(tid, ()) if t0 <= t <= t1]
        for dx, dy, hit in self.reach.outcome(now, state_of):
            self.stats["reach_hit" if hit else "reach_nohit"] += 1

    def _our_kill(self, now, tid) -> bool:
        """Last hit by OUR weapon: it turns dying KILL_WINDOW after a swing that had it inside our reach (predicted,
        like the strike rule). Kills others make on mobs we never had in reach aren't counted; a few we finish off
        for others are (the user, 2026-11-05: fine)."""
        lo, hi = KILL_WINDOW
        return any(lo <= now - t <= hi and tid in ids for t, ids in self.strikes)

    # ------------------------------------------------------------------ reflexes
    def _reflexes(self, now, obs, driver):
        c, k = self.cfg.safety, self.cfg.keys
        if obs.hp_now is not None and obs.hp < c.hp_stop and not obs.hp_potions:
            return f"HP {obs.hp:.0%} and no HP potions"
        if obs.hp_now is not None and obs.hp < c.hp_potion_at and obs.hp_potions and now >= self.potion_t["hp"]:
            driver.tap(k.hp_potion, self.hz.between(0.06, 0.12))
            self.potion_t["hp"] = now + self.hz.between(1.5, 3.0)
            self.stats["hp_potions"] += 1
            self.say(f"HP {obs.hp:.0%} -> HP potion ({k.hp_potion})")
        if obs.mp_now is not None and obs.mp < c.mp_potion_at and obs.mp_potions and now >= self.potion_t["mp"]:
            driver.tap(k.mp_potion, self.hz.between(0.06, 0.12))
            self.potion_t["mp"] = now + self.hz.between(1.5, 3.0)
            self.stats["mp_potions"] += 1
            self.say(f"MP {obs.mp:.0%} -> MP potion ({k.mp_potion})")
        return None

    def _attack_key(self, obs):
        if obs.mp_now is not None and obs.mp_now < self.cfg.combat.skill_mp and not obs.mp_potions:
            return self.cfg.keys.basic_attack
        return self.cfg.keys.attack

    # ------------------------------------------------------------------ WHEN TO HIT
    def _try_swing(self, now, obs, s, driver, live) -> bool:
        """Tap the attack if a live mob's predicted position is in front within reach."""
        if now < self.next_swing or s.state != "ground" or not self.facing:
            return False
        near, inreach = [], set()
        for m in live:
            dx, dy = self._rel(m, obs, s)
            f = self.facing * self._pred(m, dx)
            sure, maybe = self.reach.vs(m.get("mob"))
            if -10 <= f <= 200 and abs(dy) <= 60:
                near.append((m["id"], round(self.facing * dx), round(dy)))
            if maybe.lo + 4 <= f <= sure.hi - 4 and sure.ylo <= dy <= sure.yhi:
                inreach.add(m["id"])
        if not inreach:
            return False
        frozen = frozenset(inreach)
        key = self._attack_key(obs)
        secs = self.hz.between(0.07, 0.18) if not self.hz.chance(0.15) else self.hz.between(0.2, 0.45)
        if not driver.tap(key, secs):
            return False
        self.reach.swing(now, near)
        self.strikes.append((now, frozen))
        while self.strikes and now - self.strikes[0][0] > 2.0:
            self.strikes.popleft()
        self.tick_swing = {"key": key, "in_reach": sorted(frozen)}
        self.swing_t = now
        self.stats["swings"] += 1
        if key != self.cfg.keys.attack:
            self.stats["basic_swings"] += 1
        quick = self.hz.chance(0.1)                       # the user re-taps quickly now and then (gaps 0.17-0.19 s)
        self.next_swing = now + (self.hz.between(0.18, 0.3) if quick else self.hz.between(0.72, 1.05))
        return True

    # ------------------------------------------------------------------ targets
    def _route_cost(self, now, s, pid, x):
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

    def _goal_x(self, m, s):
        p = self.nav.platforms.get(m.get("platform"))
        side = _sign(m["x"] - s.x) or 1
        x = m["x"] - side * self.standoff
        return p.clamp(x) if p is not None else x

    def _cost(self, now, m, obs, s, live):
        dx, dy = self._rel(m, obs, s)
        crowd = sum(1 for o in live if o is not m and o.get("platform") == m.get("platform")
                    and abs(o["x"] - m["x"]) <= 120)
        extra = -0.25 * min(crowd, 3) + (1.5 if now - self.contested.get(m["id"], -9) < 3.0 else 0.0)
        if self._here(m, s, dy):
            turn = 0.25 if self.facing and _sign(dx) != self.facing else 0.0
            return max(0.0, abs(dx) - self.standoff) / WALK + turn + extra
        pid = m.get("platform")
        if pid is None or pid not in self.nav.platforms or now < self.unreachable.get(pid, 0.0):
            return None
        c = self._route_cost(now, s, pid, self._goal_x(m, s))
        return None if c is None else c + extra

    def _pick(self, now, obs, s, live):
        cur = next((m for m in live if m["id"] == self.target), None)
        cur_cost = self._cost(now, cur, obs, s, live) if cur is not None else None
        best, best_cost = cur, cur_cost
        for m in live:
            if m is cur or m["state"] == "hidden" and m.get("unseen", 0) > 0.5:
                continue
            c = self._cost(now, m, obs, s, live)
            if c is not None and (best_cost is None or c < best_cost - (0.5 if best is cur and cur is not None else 0)):
                best, best_cost = m, c
        if best is None or best_cost is None:
            if self.target is not None:
                self.say("no target")
            self.target, self.target_cost = None, None
            return
        if best["id"] != self.target:
            sure, _ = self.reach.vs(best.get("mob"))
            self.standoff = self.hz.between(sure.lo + 25, sure.hi - 20)
            self.stats["targets"] += 1
            dx, dy = self._rel(best, obs, s)
            self.say(f"target {best.get('mob')} id {best['id']} on {best.get('platform')} dx {dx:.0f} dy {dy:.0f}, "
                     f"cost {best_cost:.1f}s, standoff {self.standoff:.0f}")
        self.target, self.target_cost = best["id"], best_cost

    # ------------------------------------------------------------------ the tick
    def step(self, now, obs, s, driver) -> str | None:
        """One tick. Returns a stop reason (safety) or None."""
        self._now = now
        self.tick_swing = None
        stop = self._reflexes(now, obs, driver)
        if stop:
            driver.release_all()
            return stop
        if s is None:
            driver.hold(set())
            return None
        self._book(now, obs, s)
        live = self._live(obs)
        held = getattr(driver, "want", None) or set()
        d = (1 if "right" in held else 0) - (1 if "left" in held else 0)
        if d:
            self._face(d)
        travelling = self.travel is not None and self.travel.status == "run"
        if now >= self.next_pick and s.state != "air" and (s.state == "ground" or not travelling):
            self._pick(now, obs, s, live)
            self.next_pick = now + self.hz.between(0.22, 0.4)
        tgt = next((m for m in live if m["id"] == self.target), None)
        if tgt is None and self.target is not None:
            self.target = None
            self.next_pick = now
        if tgt is not None:
            dx, dy = self._rel(tgt, obs, s)
            if self._here(tgt, s, dy):
                return self._local(now, obs, s, driver, live, tgt, dx, dy)
            return self._travel(now, obs, s, driver, live, ("target", tgt["id"]), tgt.get("platform"),
                                self._goal_x(tgt, s))
        return self._roam(now, obs, s, driver, live)

    def _end_travel(self, driver):
        if self.travel is not None:
            self.travel = self.travel_for = None
            if hasattr(driver, "cancel_taps"):
                driver.cancel_taps(self.cfg.keys.jump)

    def _local(self, now, obs, s, driver, live, tgt, dx, dy):
        if self.travel is not None:
            if s.state != "ground":                       # mid-move: let it land first
                self.travel.step(now, s, driver)
                return None
            self._end_travel(driver)
        self.mode = "LOCAL"
        if self._try_swing(now, obs, s, driver, live):
            pass
        pdx = self._pred(tgt, dx)
        side = _sign(pdx) or self.facing or 1
        sure, maybe = self.reach.vs(tgt.get("mob"))
        dist = abs(pdx)
        p = self.nav.platforms.get(s.platform)
        if side != self.facing:                           # the target is behind us
            if dist <= self.standoff + 15:                # close: turn on the spot (a short tap), then swing
                if self._can_turn(now) and not driver.busy("left") and not driver.busy("right"):
                    driver.hold(set())
                    k = "right" if side > 0 else "left"
                    if driver.tap(k, self.hz.between(0.04, 0.08)):
                        self._face(side)
                        self.stats["turns"] += 1
                else:
                    driver.hold(set())
                return None
            if not self._can_turn(now):                   # just turned twice: don't pendulum, wait a moment
                driver.hold(set())
                return None
        slide = 10 + self.hz.between(0, 8)
        edge_ok = p is None or (p.left + 6 < s.x + side * 20 < p.right - 6)
        if dist > self.standoff + slide and edge_ok:
            self._hold(driver, {"right" if side > 0 else "left"})
        else:
            driver.hold(set())
        return None

    def _travel(self, now, obs, s, driver, live, why, pid, x):
        tr = self.travel
        if tr is not None and tr.status == "run":
            same = self.travel_for == why and tr.dst == pid and (tr.dst_x is None or abs(tr.dst_x - x) < 80)
            if not same and s.state == "ground" and (tr.move is None or tr.move.phase == "approach"):
                self._end_travel(driver)
                tr = None
        if tr is None or tr.status != "run":
            if tr is not None and tr.status == "failed":
                self.unreachable[tr.dst] = now + self.hz.between(5, 8)
                self.say(f"trip to {tr.dst} failed ({tr.reason}): skipping it for a few s")
                self._end_travel(driver)
                self.next_pick = now
                driver.hold(set())
                return None
            if s.state == "air" or pid is None:          # a trip starts on the ground or on a rope
                if s.state == "ground":
                    driver.hold(set())
                return None
            self.travel = Travel(self.nav, pid, x, self.hz, self.keymap)
            self.travel_for = why
            self.stats["trips"] += 1
            self.say(f"travel {node_of(s)} x {s.x:.0f} -> {pid} x {x:.0f} ({why[0]})")
        self.mode = "TRAVEL" if why[0] == "target" else "ROAM"
        st = self.travel.step(now, s, driver)
        mv = self.travel.move
        if st == "run" and s.state == "ground" and (mv is None or mv.kind in ("walk_to", "walk")
                                                    or mv.phase == "approach"):
            self._try_swing(now, obs, s, driver, live)     # whatever is in reach on the way
        if st == "done":
            self.travel = None
            if why[0] == "roam":
                self.roam_wait = now + self.hz.between(1.0, 3.5)
        return None

    def _roam(self, now, obs, s, driver, live):
        self._try_swing(now, obs, s, driver, live)
        if self.travel is not None and self.travel_for and self.travel_for[0] == "roam":
            return self._travel(now, obs, s, driver, live, self.travel_for, self.travel.dst, self.travel.dst_x)
        if self.travel is not None and s.state == "air":
            self.travel.step(now, s, driver)
            return None
        self._end_travel(driver)
        driver.hold(set())
        self.mode = "IDLE"
        if s.state == "rope":                             # never linger on a rope: roam off it now
            self.roam_wait = min(self.roam_wait, now)
        if now < self.roam_wait or s.state == "air":
            return None
        g = self._roam_goal(s)
        if g is None:
            self.roam_wait = now + self.hz.between(1.0, 2.0)
            return None
        return self._travel(now, obs, s, driver, live, ("roam", g[0]), g[0], g[1])

    def _roam_goal(self, s):
        """A spawn point on another platform, weighted by how many spawns its platform has (M3 replaces this)."""
        by = collections.defaultdict(list)
        for x, y in self.nav.spawns:
            p = self.nav.platform_at(x, y, tol=12)
            if p is not None and p.id != s.platform and self.unreachable.get(p.id, 0) <= self._now:
                by[p.id].append(x)
        rng = getattr(self.hz, "rng", random)
        for _ in range(8):
            if not by:
                return None
            pid = rng.choices(list(by), weights=[len(v) for v in by.values()])[0]
            x = rng.choice(by[pid]) + rng.uniform(-40, 40)
            x = self.nav.platforms[pid].clamp(x)
            if self._route_cost(self._now, s, pid, x) is not None:
                return pid, x
            del by[pid]
        return None

    def snapshot(self) -> dict:
        """Per tick, for ticks.jsonl."""
        tr = self.travel
        return {"mode": self.mode, "target": self.target, "swing": self.tick_swing, "cost": None if self.target_cost is None
                else round(self.target_cost, 2), "standoff": round(self.standoff), "facing": self.facing,
                "travel": None if tr is None else {"dst": tr.dst, "move": tr.move.kind if tr.move else None,
                                                   "phase": tr.move.phase if tr.move else None}}
