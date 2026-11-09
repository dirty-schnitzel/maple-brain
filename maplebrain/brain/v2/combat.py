"""brain-v2 combat: Weapon (when to press the attack key) + Footwork (where to stand), side by side on the driver.
v3 layer: tasks (the inside of Fight(mob), PLAN-v3.md: unchanged). Step 1: reads the world model (brain/v3/model.py)
through the Scene: Seen.mob (Mob), sc.me (Character: state, platform, x, HUD for the attack key), the Map's platforms.

THE ATTACK LOGIC, END TO END (each step lives in the file named; keep this section true when changing any of them)
  1. reach      (brain/reach.py)    our weapon's attack boxes from the client data vs the mob's body box -> per mob
                                    type a SURE box (every swing stance hits) and a MAYBE box (some stance hits).
  2. scene      (v2/scene.py)       per tick, per live mob: dx/dy from our feet, pdx = dx predicted SWING_LAND_S
                                    ahead (never past us). in_reach = pdx in front up to the sure far edge (start on a
                                    mob); in_reach(keep) = ACTUAL dx in front up to the maybe far edge (go on with the
                                    mob we're engaged on: our hits knock it back).
  3. targeting  (v2/targeting.py)   which mob to go for (score terms); LOCKED on the mob the weapon is engaged on.
  4. brain      (brain_v2.py)       target on our platform, or engaged and in keep reach -> fight here (Weapon +
                                    Footwork); our swing still going (its mob died) -> stay, no trip; target
                                    elsewhere -> Travel, pressing only while walking; nothing -> roam.
  5. Weapon     (here)              ONE PRESS = ONE SWING. After each swing, on what's on screen then: a live mob in
                                    reach in front -> press again (skill or plain: reflexes.attack_key); else nothing.
  6. Footwork   (here)              stand while the target is in sure reach, step in when it isn't, turn only once
                                    our swing is over (the game drops direction keys mid-swing).
  7. ledger     (v2/ledger.py)      kills by our last hit, swing outcomes (reach learning).

THE GAME'S RULES (measured live, runs/probe/sauna1, polearm; HANDOFF "attack per press", step 1)
    - an attack key-DOWN starts a swing if none is going on. A key-down during a swing is IGNORED (never queued). The
      swing ends Reach.swing_s after the key-down (the client's stance length x the weapon's attack speed; polearm
      0.90 s, live 0.89-0.92; config Combat.attack_speed / --attack-speed for another weapon or a Booster).
    - a held key swings again only through the keyboard's auto-repeat -> we never hold the attack key: we press.
    - any press length works (21 ms did). The hit lands ~0.5 s after the press; the death animation shows ~0.78 s
      after it (median, the user's kills: p10 0.62, p90 0.93) - mostly before the swing is over.
    - a direction key released before our swing ends is dropped; one still down at the end turns us, and so does a
      direction tap just before the attack press (the swing faces the new way).

Weapon - WHEN TO PRESS. States:
    ready  no swing of ours going, and the gap after the last one is over -> decide now, on fresh evidence:
               the mob we're engaged on is still live and in keep reach        -> press (go on with it)
               else a live mob in reach in front (Scene.in_reach, predicted)   -> engage it (our target if it's in
                                                                                  reach, else the nearest) and press
               else                                                            -> nothing, not engaged
           Never on a rope (no attacks there), never while a turn is landing (Scene.turning: the press can eat the
           turn), never when not allowed (a travel move that isn't walking).
    swing  pressed at t: our swing is over at t + swing_s (+ the key's way down); the next decision comes a GAP
           later, drawn from the user's own play (the swing's end -> their next swing, with a mob still in front:
           deciles below, median 0.09 s). Nothing to decide during the swing: the game ignores presses then.
    CLEAN KILLS come from deciding after the swing: by then a mob our swing killed shows its death animation (the
    tracker's `dying`: no longer live) -> no press for it. The user, mashing the key: 64 of 71 kills clean, the
    others ONE swing at nothing. (A mob our hits hide - effects over it - keeps a live track a moment: better
    evidence for that is plan step 3, the HP bars.)
    DRY: facing is a belief, the game may have dropped a turn (mid-swing, knockback, landing). Swinging at a mob in
         reach makes it react (hit state, or knocked back KNOCK_PX in a tick). Engaged and no reaction in front for
         DRY_S = two swings and a bit -> we look the other way: no press, Facing.doubt; Footwork turns us like any
         mob behind us, then we press again.
    Press length: PRESS_S, varied by the driver (the user's taps: deciles 0.074-0.111 s).

Footwork - where to stand while fighting the target on our platform. One RULE TABLE, first match wins:
    turn      target behind us, close (<= standoff + 15), may turn  -> tap toward it (may turn = Facing.can_turn: our
              swing is over - a tap during it is dropped by the game - and the turn gap passed)
    brace     target behind us, close, can't turn yet               -> no keys
    wait      target behind us, far, can't turn yet                 -> no keys (a moment, then turn)
    fight     target in SURE reach in front (predicted) and no turn landing, or our swing going -> no walk keys:
              stand, the weapon works (a walk key down at the swing's end would walk us off; the game doesn't walk us
              during a swing anyway)
    approach  further than standoff + slide, not at the edge        -> hold the walk key toward it
    stand     otherwise                                             -> no keys
"""
from .scene import sign

PRESS_S = 0.088                 # s the attack key stays down (the driver varies it: the user's taps 0.074-0.111 s)
GAP_DECILES = (0.0, 0.015, 0.03, 0.052, 0.068, 0.09, 0.112, 0.15, 0.188, 0.458, 0.98)
                                # s from our swing's end to the next press while a mob is in front: the user's polearm
                                # play (runs/play/20261108_224651_1, 134 swings, probe/human_swings.py)
KEY_WAY_S = 0.02                # s from tap() to the key going down (the driver's reaction pause)
SWING_MARGIN_S = 0.02           # s on top of the client's swing length: live ends 0.89-0.92 s vs 0.90 (polearm). A press
                                # a hair early would be ignored by the game and cost a whole swing
DRY_S = (1.8, 2.4)              # s engaged on a mob in reach with no reaction in front: two swings and a bit
KNOCK_PX = 30                   # px a mob moves away in one tick = knocked back by a hit (the tracker's `hit` misses some)


class Weapon:
    """The attack key, one press per swing: ready -> swing -> ready. See the module doc."""

    def __init__(self, cfg, hz, reflexes, ledger, stats, facing, swing_s):
        self.cfg, self.hz, self.reflexes, self.ledger, self.stats = cfg, hz, reflexes, ledger, stats
        self.facing = facing
        self.swing_s = swing_s + SWING_MARGIN_S           # Reach.swing_s: the client's stance x attack speed
        self.felt, self.dry_s = 0.0, DRY_S[0]             # last reaction in front (or not engaged); DRY after dry_s
        self.prev_dx = {}                                 # track id -> dx last tick (knockback)
        self.engaged = None                               # track id our presses are for
        self.swing_end = -9.0                             # our swing is over then (the game takes keys again)
        self.next_at = -9.0                               # the next decision: swing_end + a gap from the user's play
        self.key = None
        self.last = None                                  # this tick's press, for the ticks log
        self.now = 0.0                                    # the last step's time (for `state`)

    @property
    def state(self) -> str:
        """swing / ready (the ticks log)."""
        return "swing" if self.now < self.swing_end else "ready"

    def swinging(self, now) -> bool:
        return now < self.swing_end

    def busy(self, now) -> bool:
        """Our swing or the gap after it: a fight is going on."""
        return now < self.next_at

    def stop(self):
        """Not engaged any more (a pause, focus lost). A swing under way finishes in the game by itself."""
        self.engaged = None

    def _book(self, sc, in_reach, key):
        near = [(x.id, round(sc.facing * x.dx), round(x.dy)) for x in sc.mobs if sc.near(x)]
        self.ledger.swung(sc.now, near, in_reach)
        self.last = {"key": key, "in_reach": sorted(in_reach), "engaged": self.engaged}
        self.stats["swings"] += 1
        if key != self.cfg.keys.attack:
            self.stats["basic_swings"] += 1

    def _watch(self, sc):
        """DRY (module doc): note any reaction in front (or not being engaged) every tick."""
        reacted = any(sc.near(i) and (i.mob.state == "hit" or abs(i.dx) - abs(self.prev_dx.get(i.id, i.dx)) >= KNOCK_PX)
                      for i in sc.mobs)
        self.prev_dx = {i.id: i.dx for i in sc.mobs}
        if reacted or self.engaged is None:
            self.felt, self.dry_s = sc.now, self.hz.between(*DRY_S)

    def _engage(self, sc, ids, target):
        if target in ids:
            return target
        return min(ids, key=lambda i: abs(sc.get(i).dx))

    def step(self, sc, driver, allowed=True, target=None) -> bool:
        """Decide after each swing whether to press again. True = pressed (a swing booked) this tick."""
        now = self.now = sc.now
        self._watch(sc)
        if now < self.next_at:                            # our swing, or the gap after it
            return False
        if not allowed or sc.me.state == "rope" or not sc.facing or sc.turning:
            self.engaged = None
            return False
        x = sc.get(self.engaged) if self.engaged is not None else None
        in_reach = frozenset(m.id for m in sc.mobs if sc.in_reach(m))
        if x is None or not sc.in_reach(x, keep=True):    # it died / got away: anything else in reach in front?
            if not in_reach:
                self.engaged = None
                return False
            self.engaged = self._engage(sc, in_reach, target)
        if now - self.felt >= self.dry_s:
            self.stats["dry"] += 1
            self.engaged = None
            self.facing.doubt()
            return False
        key = self.reflexes.attack_key(sc.me)
        if not driver.tap(key, PRESS_S):
            return False
        self.key = key
        self.swing_end = now + KEY_WAY_S + self.swing_s
        self.next_at = self.swing_end + self.hz.pick(GAP_DECILES)
        self.facing.swung(self.swing_end)
        self.stats["presses"] += 1
        self._book(sc, in_reach | {self.engaged}, key)
        return True


class Footwork:
    """Walk keys while fighting the target on our platform: the rule table in the module doc, first match wins."""

    def __init__(self, map_, hz, facing, stats):
        self.map, self.hz, self.facing, self.stats = map_, hz, facing, stats
        self.state = None
        self.rules = [
            ("turn", lambda c: c["behind"] and c["close"] and c["may_turn"]),
            ("brace", lambda c: c["behind"] and c["close"]),
            ("wait", lambda c: c["behind"] and not c["may_turn"]),
            ("fight", lambda c: c["in_reach"] or c["swinging"]),
            ("approach", lambda c: c["far"] and c["edge_ok"]),
            ("stand", lambda c: True),
        ]

    def facts(self, sc, x, standoff, driver, swinging=False) -> dict:
        side = sign(x.pdx) or sc.facing or 1
        dist = abs(x.pdx)
        p = self.map.platform(sc.me.platform)
        return {"side": side, "behind": side != sc.facing, "close": dist <= standoff + 15,
                "may_turn": self.facing.can_turn(sc.now) and not driver.busy("left") and not driver.busy("right"),
                "swinging": swinging, "in_reach": sc.in_reach(x) and not sc.turning,
                "far": dist > standoff + 10 + self.hz.between(0, 8),
                "edge_ok": p is None or (p.left + 6 < sc.me.x + side * 20 < p.right - 6)}

    def step(self, sc, x, standoff, driver, swinging=False):
        c = self.facts(sc, x, standoff, driver, swinging)
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
