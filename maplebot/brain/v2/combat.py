"""brain-v2 combat, two small machines that run side by side, on `Hands` (the keys both of them and Travel hold):

Weapon - WHEN TO HIT. States:
    ready     a live mob in reach in front (Scene.in_reach: predicted position, sure far edge) -> pressure
    pressure  HOLD the attack key: the game swings at weapon speed and every hit knocks the mob back, which keeps it
              at the spear's length (the user, runs/v2b-c: "a player would hold the atk key"; taps left gaps).
              Kept while a mob stays within the wider KEEP reach by its ACTUAL position (a knocked-back mob moves
              away fast: its prediction leaves the reach, the mob doesn't - v2c let go right after hits).
              Ends: nothing within keep reach for a varied 0.15-0.35 s, or not allowed (off the ground / a move
              that isn't walking) -> ready; held 1.5-4 s -> let go briefly (0.08-0.2 s, `cooldown`) and press again.
    While holding, a swing is booked every SWING_PERIOD s (kills by last hit, reach learning).
    Never on a rope / in the air, never facing an unknown way, never at nothing.

Footwork - where to stand while fighting the target on our platform. One RULE TABLE, first match wins:
    turn      target behind us, close (<= standoff + 15), may turn, attack not held -> tap toward it
              (the game ignores a direction key mid-swing: turning while holding = we THINK we turned - v2c's
              face-tanking; the weapon lets go first since nothing is in front)
    hold      target behind us, close                                  -> no keys
    wait      target behind us, far, turned twice lately               -> no keys (no left-right-left-right)
    fight     target in SURE reach in front (predicted)                -> no walk keys: stand, the weapon works
              (only maybe-reach, e.g. knocked back: keep closing in while the weapon keeps holding)
    approach  further than standoff + slide, not at the edge           -> hold the walk key toward it
    stand     otherwise                                               -> no keys
"""
from .scene import sign

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
        """Hold / keep / let go. True = a swing was booked this tick."""
        now = sc.now
        if not allowed or sc.s.state != "ground" or not sc.facing:
            self.release(hands, now)
            return False
        if self.state == "cooldown" and now >= self.until:
            self.state = "ready"
        if self.state == "pressure":
            if now >= self.until:                         # held a while: let go briefly, press again after
                self.release(hands, now, self.hz.between(0.08, 0.2))
                return False
            keep = frozenset(x.id for x in sc.mobs if sc.in_reach(x, keep=True))
            if keep:
                self.clear_t = None
                if now >= self.next_book:
                    self.next_book = now + self.hz.between(*SWING_PERIOD)
                    self._book(sc, keep, self.key)
                    return True
                return False
            if self.clear_t is None:
                self.clear_t = now + self.hz.between(0.15, 0.35)
            elif now >= self.clear_t:
                self.release(hands, now)
            return False
        in_reach = frozenset(x.id for x in sc.mobs if sc.in_reach(x))
        if self.state != "ready" or not in_reach:
            return False
        self.key = self.reflexes.attack_key(obs)
        self.state, self.clear_t = "pressure", None
        self.until = now + self.hz.between(1.5, 4.0)
        self.next_book = now + self.hz.between(*SWING_PERIOD)
        hands.set_extra({self.key})
        self.stats["holds"] += 1
        self._book(sc, in_reach, self.key)
        return True


class Footwork:
    def __init__(self, nav, hz, facing, stats):
        self.nav, self.hz, self.facing, self.stats = nav, hz, facing, stats
        self.state = None
        self.rules = [
            ("turn", lambda c: c["behind"] and c["close"] and c["may_turn"] and not c["holding"]),
            ("hold", lambda c: c["behind"] and c["close"]),
            ("wait", lambda c: c["behind"] and not c["may_turn"]),
            ("fight", lambda c: c["in_reach"]),
            ("approach", lambda c: c["far"] and c["edge_ok"]),
            ("stand", lambda c: True),
        ]

    def facts(self, sc, x, standoff, driver, holding=False) -> dict:
        side = sign(x.pdx) or sc.facing or 1
        dist = abs(x.pdx)
        p = self.nav.platforms.get(sc.s.platform)
        return {"side": side, "behind": side != sc.facing, "close": dist <= standoff + 15,
                "may_turn": self.facing.can_turn(sc.now) and not driver.busy("left") and not driver.busy("right"),
                "holding": holding, "in_reach": sc.in_reach(x),
                "far": dist > standoff + 10 + self.hz.between(0, 8),
                "edge_ok": p is None or (p.left + 6 < sc.s.x + side * 20 < p.right - 6)}

    def step(self, sc, x, standoff, driver, holding=False):
        c = self.facts(sc, x, standoff, driver, holding)
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
