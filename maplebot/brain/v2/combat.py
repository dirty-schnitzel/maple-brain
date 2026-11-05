"""brain-v2 combat, two small machines that run side by side:

Weapon - WHEN TO HIT. States: ready -> (a live mob in reach in front: Scene.in_reach) swing -> cooldown -> ready.
    A swing is a tap (length from the user's taps); the cooldown is the swing cycle (0.72-1.05 s; 10 % quick re-taps
    0.18-0.3 s like the user's). Only on the ground, only facing a known way, never at nothing.

Footwork - where to stand while fighting the target on our platform. One RULE TABLE, first match wins:
    turn      target behind us, close (<= standoff + 15), may turn  -> tap toward it (a turn on the spot)
    hold      target behind us, close, may not turn (yet)          -> no keys
    wait      target behind us, far, turned twice lately           -> no keys (no left-right-left-right)
    approach  further than standoff + slide, not at the edge       -> hold the walk key toward it
    stand     otherwise                                           -> no keys (the slide stops us at the standoff)
"""
from .scene import sign


class Weapon:
    def __init__(self, cfg, hz, reflexes, ledger, stats):
        self.cfg, self.hz, self.reflexes, self.ledger, self.stats = cfg, hz, reflexes, ledger, stats
        self.state = "ready"
        self.until = 0.0
        self.last = None                                  # this tick's swing, for the ticks log

    def step(self, sc, obs, driver) -> bool:
        """Swing if a mob is in reach. True = swung this tick."""
        if self.state == "cooldown" and sc.now >= self.until:
            self.state = "ready"
        if self.state != "ready" or sc.s.state != "ground" or not sc.facing:
            return False
        in_reach = frozenset(x.id for x in sc.mobs if sc.in_reach(x))
        if not in_reach:
            return False
        key = self.reflexes.attack_key(obs)
        secs = self.hz.between(0.07, 0.18) if not self.hz.chance(0.15) else self.hz.between(0.2, 0.45)
        if not driver.tap(key, secs):
            return False
        near = [(x.id, round(sc.facing * x.dx), round(x.dy)) for x in sc.mobs if sc.near(x)]
        self.ledger.swung(sc.now, near, in_reach)
        self.last = {"key": key, "in_reach": sorted(in_reach)}
        self.stats["swings"] += 1
        if key != self.cfg.keys.attack:
            self.stats["basic_swings"] += 1
        quick = self.hz.chance(0.1)                       # the user re-taps quickly now and then (gaps 0.17-0.19 s)
        self.state, self.until = "cooldown", sc.now + (self.hz.between(0.18, 0.3) if quick
                                                       else self.hz.between(0.72, 1.05))
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
