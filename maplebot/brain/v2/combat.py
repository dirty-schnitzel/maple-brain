"""brain-v2 combat, two small machines that run side by side, on `Hands` (the keys both of them and Travel hold):

Weapon - WHEN TO HIT. States:
    ready     a live mob in reach in front (Scene.in_reach) ->
                  the fight goes on (2+ mobs in reach, or we swung in the last FIGHT_S) -> pressure
                  else a lone mob -> tap (the user's tap lengths) -> cooldown
    cooldown  0.5-0.65 s after a tap (10 % quick re-taps 0.18-0.3 s like the user's) -> ready
    pressure  HOLD the attack key: the game swings at weapon speed, no gap to think in (the user, runs/v2b: "a player
              would hold the atk key"; v2 tapped with gaps of median 1.02 s). Ends: nothing in reach for a varied
              0.15-0.35 s, or not allowed (off the ground / a move that isn't walking) -> ready; held 1.5-4 s ->
              let go briefly (0.08-0.2 s) and press again, like a person.
    While holding, a swing is booked every SWING_PERIOD s in reach (kills by last hit, reach learning).
    Never on a rope / in the air, never facing an unknown way, never at nothing.

Footwork - where to stand while fighting the target on our platform. One RULE TABLE, first match wins:
    turn      target behind us, close (<= standoff + 15), may turn  -> tap toward it (a turn on the spot)
    hold      target behind us, close, may not turn (yet)          -> no keys
    wait      target behind us, far, turned twice lately           -> no keys (no left-right-left-right)
    approach  further than standoff + slide, not at the edge       -> hold the walk key toward it
    stand     otherwise                                           -> no keys (the slide stops us at the standoff)
"""
from .scene import sign

FIGHT_S = 1.3                   # a swing this recent + something in reach = the fight goes on: hold
SWING_PERIOD = (0.55, 0.7)      # s per swing while held - a guess from the press -> hit timing; measure live


class Hands:
    """The driver as the parts see it: `hold(keys)` from footwork / Travel keeps the weapon's held keys (`extra`)."""

    def __init__(self, driver):
        self.real = driver
        self.base, self.extra = set(), set()

    @property
    def want(self):
        return self.base

    def hold(self, keys):
        self.base = set(keys)
        self.real.hold(self.base | self.extra)

    def set_extra(self, keys):
        keys = set(keys)
        if keys != self.extra:
            self.extra = keys
            self.real.hold(self.base | self.extra)

    def tap(self, key, secs, after=0.0):
        return self.real.tap(key, secs, after)

    def busy(self, key=None):
        return self.real.busy(key)

    def cancel_taps(self, key=None):
        return self.real.cancel_taps(key) if hasattr(self.real, "cancel_taps") else 0

    def release_all(self):
        self.base, self.extra = set(), set()
        self.real.release_all()


class Weapon:
    def __init__(self, cfg, hz, reflexes, ledger, stats):
        self.cfg, self.hz, self.reflexes, self.ledger, self.stats = cfg, hz, reflexes, ledger, stats
        self.state = "ready"
        self.until = 0.0                                  # cooldown end / pressure: when to let go briefly
        self.clear_t = None                               # pressure: nothing in reach since then
        self.next_book = 0.0
        self.key = None
        self.last = None                                  # this tick's swing, for the ticks log

    def _book(self, sc, in_reach, key):
        near = [(x.id, round(sc.facing * x.dx), round(x.dy)) for x in sc.mobs if sc.near(x)]
        self.ledger.swung(sc.now, near, in_reach)
        self.last = {"key": key, "in_reach": sorted(in_reach), "held": self.state == "pressure"}
        self.stats["swings"] += 1
        if key != self.cfg.keys.attack:
            self.stats["basic_swings"] += 1

    def release(self, hands, now, pause=None):
        if self.state == "pressure":
            hands.set_extra(set())
            self.state, self.until = ("cooldown", now + pause) if pause else ("ready", 0.0)
            self.clear_t = None

    def step(self, sc, obs, hands, allowed=True) -> bool:
        """Swing / hold / let go. True = a swing was booked this tick."""
        now = sc.now
        if not allowed or sc.s.state != "ground" or not sc.facing:
            self.release(hands, now)
            return False
        if self.state == "cooldown" and now >= self.until:
            self.state = "ready"
        in_reach = frozenset(x.id for x in sc.mobs if sc.in_reach(x))
        if self.state == "pressure":
            if now >= self.until:                         # held a while: let go briefly, press again after
                self.release(hands, now, self.hz.between(0.08, 0.2))
                return False
            if in_reach:
                self.clear_t = None
                if now >= self.next_book:
                    self.next_book = now + self.hz.between(*SWING_PERIOD)
                    self._book(sc, in_reach, self.key)
                    return True
                return False
            if self.clear_t is None:
                self.clear_t = now + self.hz.between(0.15, 0.35)
            elif now >= self.clear_t:
                self.release(hands, now)
            return False
        if self.state != "ready" or not in_reach:
            return False
        key = self.reflexes.attack_key(obs)
        if len(in_reach) >= 2 or now - self.ledger.swing_t <= FIGHT_S:
            self.state, self.key, self.clear_t = "pressure", key, None
            self.until = now + self.hz.between(1.5, 4.0)
            self.next_book = now + self.hz.between(*SWING_PERIOD)
            hands.set_extra({key})
            self.stats["holds"] += 1
            self._book(sc, in_reach, key)
            return True
        secs = self.hz.between(0.07, 0.18) if not self.hz.chance(0.15) else self.hz.between(0.2, 0.45)
        if not hands.tap(key, secs):
            return False
        self._book(sc, in_reach, key)
        quick = self.hz.chance(0.1)                       # the user re-taps quickly now and then (gaps 0.17-0.19 s)
        self.state, self.until = "cooldown", now + (self.hz.between(0.18, 0.3) if quick
                                                    else self.hz.between(0.5, 0.65))
        return True


class Footwork:
    def __init__(self, nav, hz, facing, stats):
        self.nav, self.hz, self.facing, self.stats = nav, hz, facing, stats
        self.state = None
        self.rules = [
            ("turn", lambda c: c["behind"] and c["close"] and c["may_turn"]),
            ("hold", lambda c: c["behind"] and c["close"]),
            ("wait", lambda c: c["behind"] and not c["may_turn"]),
            ("approach", lambda c: c["far"] and c["edge_ok"]),
            ("stand", lambda c: True),
        ]

    def facts(self, sc, x, standoff, driver) -> dict:
        side = sign(x.pdx) or sc.facing or 1
        dist = abs(x.pdx)
        behind = side != sc.facing
        f = {"side": side, "behind": behind, "close": dist <= standoff + 15,
             "may_turn": self.facing.can_turn(sc.now) and not driver.busy("left") and not driver.busy("right")}
        if behind and f["close"]:
            return f                                      # the turn rules decide; no slide needed
        if behind:
            f["may_turn"] = self.facing.can_turn(sc.now)
            if not f["may_turn"]:
                return f
        p = self.nav.platforms.get(sc.s.platform)
        slide = 10 + self.hz.between(0, 8)
        f["far"] = dist > standoff + slide
        f["edge_ok"] = p is None or (p.left + 6 < sc.s.x + side * 20 < p.right - 6)
        return f

    def step(self, sc, x, standoff, driver):
        c = self.facts(sc, x, standoff, driver)
        self.state = next(name for name, cond in self.rules if cond(c))
        walk = "right" if c["side"] > 0 else "left"
        if self.state == "turn":
            driver.hold(set())
            if driver.tap(walk, self.hz.between(0.04, 0.08)):
                self.facing.face(c["side"], sc.now)
                self.stats["turns"] += 1
        elif self.state == "approach":
            driver.hold({walk})
            self.facing.face(c["side"], sc.now)
        else:
            driver.hold(set())
