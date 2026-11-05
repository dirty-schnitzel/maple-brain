"""brain-v2 (M2: combat; no loot / patrol plan yet). This file only WIRES the parts; no rules live here.

Every tick `step(now, obs, s, driver)` (obs = the Perceiver's Obs with tracks in obs.mobs, s = our SelfState,
driver = runtime/keys.KeyDriver or a fake):

    reflexes   (v2/reflexes.py)   potions, HP stop, which attack key
    ledger     (v2/ledger.py)     track history, kills by our last hit, contested mobs, swing outcomes
    scene      (v2/scene.py)      us + every live mob relative to us, once per tick; Facing
    targeting  (v2/targeting.py)  one score per mob = a sum of named terms; keep / switch / none; locked mid-fight
    weapon     (v2/combat.py)     WHEN TO HIT: ready -> pressure (hold until the engaged mob dies) -> let go
    footwork   (v2/combat.py)     fighting here: a rule table (turn / brace / wait / fight / approach / stand)
    trips      (v2/trips.py)      target elsewhere: Travel (M1); nothing to fight: roam (until M3)

The attack logic end to end (reach -> scene -> targeting -> here -> weapon/footwork -> ledger): v2/combat.py's doc.

The decision each tick, in order (step):
    target on our platform, or the one we're engaged on and still in keep reach  -> LOCAL: weapon + footwork
    the weapon still finishing a fight (reacting to a death)                     -> LOCAL: stand, weapon only
    target elsewhere                                                            -> TRAVEL; hold the attack only while
                                                                                   the trip is walking
    nothing to fight                                                            -> ROAM / IDLE

Modes (ticks log): LOCAL (fighting here) / TRAVEL (going to the target) / ROAM / IDLE.
How to change behaviour: a score term, a rule in a table, a state, or a parameter with its data source - never a
special case in here.
"""
import collections

from .reach import Reach
from .v2.combat import Footwork, Hands, Weapon
from .v2.ledger import Ledger
from .v2.reflexes import Reflexes
from .v2.scene import Facing, Scene
from .v2.targeting import Targeting
from .v2.trips import Trips


class BrainV2:
    def __init__(self, cfg, nav, hz, reach: Reach | None = None, log=None):
        self.cfg, self.nav, self.hz = cfg, nav, hz
        self.reach = reach or Reach(cfg.combat.weapon)
        self.say = log or (lambda msg: None)
        self.stats = collections.Counter()
        self.face = Facing(hz)
        self.reflexes = Reflexes(cfg, hz, self.stats, self.say)
        self.ledger = Ledger(self.reach, self.stats, self.say)
        self.targeting = Targeting(nav, hz, self.ledger, self.stats, self.say)
        self.weapon = Weapon(cfg, hz, self.reflexes, self.ledger, self.stats)
        self.footwork = Footwork(nav, hz, self.face, self.stats)
        self.trips = Trips(nav, hz, {"jump": cfg.keys.jump}, cfg.keys.jump, self.targeting, self.stats, self.say)
        self.mode = "IDLE"
        self.scene = None
        self.hands = None

    # the parts' state, by the names the tests / tools / logs use
    @property
    def facing(self):
        return self.face.dir

    @facing.setter
    def facing(self, d):
        self.face.dir = d

    @property
    def target(self):
        return self.targeting.target

    @property
    def travel(self):
        return self.trips.travel

    def reset(self, driver):
        """After a pause (focus lost): no trip, no target, attack let go; pick afresh."""
        hands = self._hands(driver)
        self.weapon.release(hands)
        self.trips.end(hands)
        self.targeting.target = None

    def _hands(self, driver):
        if self.hands is None or self.hands.real is not driver:
            self.hands = Hands(driver)
        return self.hands

    def step(self, now, obs, s, driver) -> str | None:
        """One tick. Returns a stop reason (safety) or None."""
        driver = self._hands(driver)                     # every part holds keys through Hands (weapon + walk)
        self.weapon.last = None
        stop = self.reflexes.step(now, obs, driver)
        if stop:
            driver.release_all()
            return stop
        if s is None:
            self.weapon.release(driver)
            driver.hold(set())
            return None
        self.ledger.update(now, obs)
        self.face.from_keys(getattr(driver, "want", None) or set(), now)
        sc = self.scene = Scene.build(now, obs, s, self.face.dir, self.reach)
        tg = self.targeting
        tg.lock = self.weapon.engaged if self.weapon.state == "pressure" else None
        if tg.due(now) and s.state != "air" and (s.state == "ground" or not self.trips.running):
            tg.pick(sc)
        x = tg.current(sc)
        fighting = x is not None and self.weapon.engaged == x.id and sc.in_reach(x, keep=True)
        if x is not None and (x.here or fighting):       # fight it from here (engaged: wherever it stands)
            self.trips.end(driver)
            self.mode = "LOCAL"
            self.weapon.step(sc, obs, driver, target=x.id)
            self.footwork.step(sc, x, tg.standoff, driver, holding=self.weapon.state == "pressure")
        elif self.weapon.state == "pressure":            # finishing a fight (reacting to a death): stay, no trip
            self.trips.end(driver)
            self.mode = "LOCAL"
            driver.hold(set())
            self.weapon.step(sc, obs, driver, target=x.id if x is not None else None)
        elif x is not None:                              # go to it, swinging at whatever is in reach on the way
            st = self.trips.go(now, s, driver, ("target", x.id), x.platform, tg.goal_x(x, s))
            if st is not None:
                self.mode = "TRAVEL"
            self.weapon.step(sc, obs, driver, allowed=st == "run" and self.trips.walking(s), target=x.id)
            self.trips.settle(now, st)
        else:                                            # nothing to fight: roam
            mode, st = self.trips.roam(now, s, driver)
            if mode is not None:
                self.mode = mode
            self.weapon.step(sc, obs, driver, allowed=self.trips.travel is None or self.trips.walking(s))
            self.trips.settle(now, st)
        return None

    def snapshot(self) -> dict:
        """Per tick, for ticks.jsonl."""
        tr, tg = self.trips.travel, self.targeting
        return {"mode": self.mode, "target": tg.target, "swing": self.weapon.last,
                "cost": None if tg.cost is None else round(tg.cost, 2), "standoff": round(tg.standoff),
                "facing": self.face.dir, "weapon": self.weapon.state, "footwork": self.footwork.state,
                "travel": None if tr is None else {"dst": tr.dst, "move": tr.move.kind if tr.move else None,
                                                   "phase": tr.move.phase if tr.move else None}}
