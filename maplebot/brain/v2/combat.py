"""brain-v2 combat: Weapon (when to hit, how long) + Footwork (where to stand), side by side on `Hands`.

THE ATTACK LOGIC, END TO END (each step lives in the file named; keep this section true when changing any of them)
  1. reach      (brain/reach.py)    our weapon's attack boxes from the client data vs the mob's body box -> per mob
                                    type a SURE box (every swing stance hits) and a MAYBE box (some stance hits).
  2. scene      (v2/scene.py)       per tick, per live mob: dx/dy from our feet, pdx = dx predicted SWING_LAND_S
                                    ahead (never past us). in_reach = pdx in front up to the sure far edge (start a
                                    hold); in_reach(keep) = ACTUAL dx in front up to the maybe far edge (keep holding).
  3. targeting  (v2/targeting.py)   which mob to go for (score terms); LOCKED on the mob the weapon is engaged on.
  4. brain      (brain_v2.py)       target on our platform, or engaged and in keep reach -> fight here (Weapon +
                                    Footwork); weapon still finishing (reacting to a death) -> stay, no trip;
                                    target elsewhere -> Travel, holding only while walking; nothing -> roam.
  5. Weapon     (here)              press and HOLD the attack key (skill or plain: reflexes.attack_key) on a mob in
                                    reach; let go a human reaction after it dies, or when it got away, or when the
                                    hold does nothing (DRY: we look the other way).
  6. Footwork   (here)              stand while the target is in sure reach, step in when it isn't, turn only with
                                    the attack key up and the swing over (the game ignores direction keys mid-swing).
  7. ledger     (v2/ledger.py)      kills by our last hit, swing outcomes (reach learning).

Weapon - WHEN TO HIT, and how long. States:
    ready     a live mob in reach in front (Scene.in_reach: predicted position, up to the sure far edge) -> pressure,
              ENGAGED on it (our target if it's in reach, else the nearest in reach)
    pressure  HOLD the attack key (skill or plain) until the engaged mob is done - the user: "hold the atk key until
              the death animation is visible, release within a human response time". Every hit knocks it back, the
              game swings at weapon speed, no gaps. Done =
                  it shows its death animation / vanishes   -> react (REACT_S), then: another mob in sure reach in
                                                               front -> engage it, keep holding; else let go
                  it got away (out of keep reach GOT_AWAY_S) -> let go (footwork follows it)
                  DRY: in reach DRY_S, no mob in front reacted  -> let go, Facing.doubt (below)
              NOT done by: knockback into the air (Maple attacks in the air), a mob drifting a little, a new target
              (targeting is locked on the engaged mob, `engaged`). runs/v2 09:21: holds lasted 0.48 s median, 152 of
              330 cut by "air", 80 by trips started mid-fight, 3 ended by a death.
    Let go at once only on a rope/ladder (no attacks there) or when not allowed (a travel move that isn't walking).
    No fresh press while a turn hasn't landed (Scene.turning).
    DRY:      facing is a belief, the game may have dropped the turn (mid-swing, knockback, landing). Swinging at a mob
              in reach makes it react (hit state, or knocked back KNOCK_PX in a tick). No reaction in front for DRY_S =
              two swings -> we look the other way: let go and doubt; Footwork turns us like any mob behind us, the
              weapon presses again. runs/v2 10:19 t=29: 3 s at a mob 54 px "in front" untouched, then a mob 63 px
              "behind" got hit: the user's "stuck pressing attack when monsters are BEHIND it".
    RE-PRESS: the game keeps swinging only while the attack key is the LAST key pressed (a held key's repeat stops
              when another key goes down, like any keyboard; runs/v2 09:53: 0.55 hit reactions/s while the attack
              was the last key, 0.03/s after another key went down). Any other key down during a hold (a potion, a
              turn) -> let go and press it again REPRESS_S later: a real key-up + key-down, as a player does.
              Never fake it (e.g. repeating a key that isn't the last pressed): Nexon watches for input no real
              keyboard can make.
    While holding, a swing is booked every SWING_PERIOD s (kills by last hit, reach learning).

Footwork - where to stand while fighting the target on our platform. One RULE TABLE, first match wins:
    turn      target behind us, close (<= standoff + 15), may turn, attack not held -> tap toward it
              (the game ignores a direction key mid-swing, also for SWING_TAIL_S after the key came up: turning then
              = we THINK we turned - v2c's face-tanking. A mob that walks behind us leaves the keep reach, the weapon
              lets go after GOT_AWAY_S, then we turn. may turn = Facing.can_turn: turn gap passed, swing over)
    brace     target behind us, close, can't turn yet                  -> no keys
    wait      target behind us, far, can't turn yet                    -> no keys (a moment, then turn)
    fight     target in SURE reach in front (predicted) and no turn landing, or the attack is held -> no walk keys:
              stand, the weapon works (a walk key pressed mid-hold would take the key repeat from the attack and stop the swings;
              the game doesn't walk us while attacking anyway. If the mob gets away the weapon lets go, then we
              approach)
    approach  further than standoff + slide, not at the edge           -> hold the walk key toward it
    stand     otherwise                                               -> no keys
"""
from .scene import sign

SWING_PERIOD = (0.55, 0.7)      # s per swing while held - a guess from the press -> hit timing; measure live
REACT_S = (0.18, 0.32)          # s from the death animation to letting go: a human's response (uniform)
GOT_AWAY_S = (0.3, 0.5)         # s the engaged mob may be out of keep reach before we let go and follow
REPRESS_S = (0.12, 0.25)        # s between letting go and pressing the attack key again (another key took the repeat)
SWING_TAIL_S = (0.6, 0.8)       # s a swing goes on after the key came up: direction keys are ignored until then (live
                                # period ~0.81 s: a mob's knockbacks during a hold, runs/v2 10:19 t=34-35.6)
DRY_S = (1.8, 2.4)              # s holding at a mob in reach with no reaction in front: two swings and a bit
KNOCK_PX = 30                   # px a mob moves away in one tick = knocked back by a hit (the tracker's `hit` misses some)


class Hands:
    """The driver as the parts see it: `hold(keys)` from footwork / Travel keeps the weapon's held keys (`extra`).
    `stolen`: another key went down while the weapon's key was held - the game stopped repeating the attack (see
    RE-PRESS in the module doc); cleared by the next fresh press of the weapon's key."""

    def __init__(self, driver):
        self.real = driver
        self.base, self.extra = set(), set()
        self.stolen = False

    @property
    def want(self):
        return self.base

    def hold(self, keys):
        keys = set(keys)
        if self.extra and keys - self.base - self.extra:
            self.stolen = True
        self.base = keys
        self.real.hold(self.base | self.extra)

    def set_extra(self, keys):
        keys = set(keys)
        if keys != self.extra:
            if keys - self.extra:                         # a fresh press: it's the last key down again
                self.stolen = False
            self.extra = keys
            self.real.hold(self.base | self.extra)

    def tap(self, key, secs, after=0.0):
        ok = self.real.tap(key, secs, after)
        if ok and self.extra and key not in self.extra:
            self.stolen = True
        return ok

    def busy(self, key=None):
        return self.real.busy(key)

    def cancel_taps(self, key=None):
        return self.real.cancel_taps(key) if hasattr(self.real, "cancel_taps") else 0

    def release_all(self):
        self.base, self.extra, self.stolen = set(), set(), False
        self.real.release_all()


class Weapon:
    """The attack key: ready -> pressure (held, engaged on one mob) -> ready. See the module doc."""

    def __init__(self, cfg, hz, reflexes, ledger, stats, facing):
        self.cfg, self.hz, self.reflexes, self.ledger, self.stats = cfg, hz, reflexes, ledger, stats
        self.facing = facing
        self.felt, self.dry_s = 0.0, DRY_S[0]             # last reaction in front (or not in reach); DRY after dry_s
        self.prev_dx = {}                                 # track id -> dx last tick (knockback)
        self.state = "ready"
        self.engaged = None                               # track id we hold the attack for
        self.release_at = None                            # engaged mob done: let go (or move on) at this time
        self.away_since = None                            # engaged mob out of keep reach since
        self.away_s = 0.0
        self.repress_at = None                            # let go because another key took the repeat: press again then
        self.next_book = 0.0
        self.key = None
        self.last = None                                  # this tick's swing, for the ticks log

    def _book(self, sc, in_reach, key):
        near = [(x.id, round(sc.facing * x.dx), round(x.dy)) for x in sc.mobs if sc.near(x)]
        self.ledger.swung(sc.now, near, in_reach)
        self.last = {"key": key, "in_reach": sorted(in_reach), "engaged": self.engaged}
        self.stats["swings"] += 1
        if key != self.cfg.keys.attack:
            self.stats["basic_swings"] += 1

    def release(self, hands, now=0.0):
        """Attack key up now, engagement over."""
        if self.state == "pressure":
            hands.set_extra(set())
            self.facing.swung(now + self.hz.between(*SWING_TAIL_S))
        self.state, self.engaged, self.release_at, self.away_since, self.repress_at = "ready", None, None, None, None

    def _repress(self, now, hands) -> bool:
        """RE-PRESS (module doc): another key went down mid-hold -> key up now, down again REPRESS_S later.
        True while the key is up for it (no swings then)."""
        if self.repress_at is not None:
            if now < self.repress_at:
                return True
            self.repress_at = None
            hands.set_extra({self.key})
            self.stats["represses"] += 1
            return False
        if hands.stolen:
            hands.set_extra(set())
            hands.stolen = False
            self.repress_at = now + self.hz.between(*REPRESS_S)
            return True
        return False

    def _feel(self, now):
        self.felt, self.dry_s = now, self.hz.between(*DRY_S)

    def _dry(self, sc, x, repressing) -> bool:
        """DRY (module doc): True = holding at a mob in reach and nothing in front reacts."""
        reacted = any(sc.near(i) and (i.m["state"] == "hit" or abs(i.dx) - abs(self.prev_dx.get(i.id, i.dx)) >= KNOCK_PX)
                      for i in sc.mobs)
        self.prev_dx = {i.id: i.dx for i in sc.mobs}
        if reacted or repressing or not sc.in_reach(x):
            self._feel(sc.now)
        return sc.now - self.felt >= self.dry_s

    def _engage(self, sc, ids, target):
        if target in ids:
            return target
        return min(ids, key=lambda i: abs(sc.get(i).dx))

    def step(self, sc, obs, hands, allowed=True, target=None) -> bool:
        """Hold / keep / let go. True = a swing was booked this tick."""
        now = sc.now
        if not allowed or sc.s.state == "rope" or not sc.facing:
            self.release(hands, now)
            return False
        in_reach = frozenset(x.id for x in sc.mobs if sc.in_reach(x))
        if self.state == "ready":
            if not in_reach or sc.s.state != "ground" or sc.turning:   # press on the ground; once pressed, the air is fine
                return False
            self.key = self.reflexes.attack_key(obs)
            self.state, self.engaged = "pressure", self._engage(sc, in_reach, target)
            self.release_at = self.away_since = None
            self.prev_dx = {}
            self._feel(now)
            self.next_book = now + self.hz.between(*SWING_PERIOD)
            hands.set_extra({self.key})
            self.stats["holds"] += 1
            self._book(sc, in_reach, self.key)
            return True
        repressing = self._repress(now, hands)
        x = sc.get(self.engaged)
        if self.release_at is not None:                   # it's done: a human's reaction later, move on or let go
            if now < self.release_at:
                return False
            if in_reach:
                self.engaged, self.release_at, self.away_since = self._engage(sc, in_reach, target), None, None
                self._feel(now)
                self.stats["held_on"] += 1
                return False
            self.release(hands, now)
            return False
        if x is None:                                     # death animation (no longer live) or gone
            self.release_at = now + self.hz.between(*REACT_S)
            return False
        if not sc.in_reach(x, keep=True):
            if self.away_since is None:
                self.away_since, self.away_s = now, self.hz.between(*GOT_AWAY_S)
            elif now - self.away_since >= self.away_s:
                self.stats["got_away"] += 1
                self.release(hands, now)
            return False
        self.away_since = None
        if self._dry(sc, x, repressing):
            self.stats["dry"] += 1
            self.release(hands, now)
            self.facing.doubt()
            return False
        if not repressing and now >= self.next_book:
            self.next_book = now + self.hz.between(*SWING_PERIOD)
            self._book(sc, frozenset(i.id for i in sc.mobs if sc.in_reach(i, keep=True)), self.key)
            return True
        return False


class Footwork:
    """Walk keys while fighting the target on our platform: the rule table in the module doc, first match wins."""

    def __init__(self, nav, hz, facing, stats):
        self.nav, self.hz, self.facing, self.stats = nav, hz, facing, stats
        self.state = None
        self.rules = [
            ("turn", lambda c: c["behind"] and c["close"] and c["may_turn"] and not c["holding"]),
            ("brace", lambda c: c["behind"] and c["close"]),
            ("wait", lambda c: c["behind"] and not c["may_turn"]),
            ("fight", lambda c: c["in_reach"] or c["holding"]),
            ("approach", lambda c: c["far"] and c["edge_ok"]),
            ("stand", lambda c: True),
        ]

    def facts(self, sc, x, standoff, driver, holding=False) -> dict:
        side = sign(x.pdx) or sc.facing or 1
        dist = abs(x.pdx)
        p = self.nav.platforms.get(sc.s.platform)
        return {"side": side, "behind": side != sc.facing, "close": dist <= standoff + 15,
                "may_turn": self.facing.can_turn(sc.now) and not driver.busy("left") and not driver.busy("right"),
                "holding": holding, "in_reach": sc.in_reach(x) and not sc.turning,
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
