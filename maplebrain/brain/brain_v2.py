"""brain-v2 (M2: combat; no loot / patrol plan yet), migrating to brain v3 (PLAN-v3.md). This file only WIRES the
layers and parts; no rules live here.
    step 1 (objects): the parts read the WORLD MODEL (v3/model.py: Map, Mob, Character), updated once per tick here.
    step 2 (planner): the decision chain moved into the PLANNER (v3/planner.py): one goal, Hunt (v3/goals.py), names
           a TASK every tick (v3/tasks.py: Fight / Goto / Roam / Rest). Behaviour identical (tools/v3/gate.py).

Every tick `step(now, obs, s, driver)` (obs = the Perceiver's Obs with tracks in obs.mobs, s = our SelfState,
driver = runtime/keys.KeyDriver or a fake):

    REFLEXES   (v2/reflexes.py)   first: potions, HP stop (which attack key: the weapon asks it)
    WORLD      (v3/model.py)      the world model: Map (+ spawns, route seconds), Mob per track, Character (us)
               (v2/ledger.py)     its short memory: track history, kills by our last hit, contested mobs, swing outcomes
    PLANNER    (v3/planner.py)    which goal runs (~1x/s + on task events); the goal names this tick's task
               (v3/goals.py)      Hunt = the chain: Rest / Fight / Fight(finishing) / Goto / Roam
    TASKS      (v3/tasks.py)      run on brain v2's parts:
        scene      (v2/scene.py)      us + every live mob relative to us, once per tick (Facing: v3/model.py)
        breaks     (v2/breaks.py)     short beats after a fight, a real break every few minutes at a safe spot
        targeting  (v2/targeting.py)  one score per mob = a sum of named terms; keep / switch / none; locked mid-fight
        weapon     (v2/combat.py)     WHEN TO HIT: one press per swing, the next decided after the swing
        footwork   (v2/combat.py)     fighting here: a rule table (turn / brace / wait / fight / approach / stand)
        trips      (v2/trips.py)      target elsewhere: Travel (M1); nothing to fight: roam (until M3)

The attack logic end to end (reach -> scene -> targeting -> Hunt -> weapon/footwork -> ledger): v2/combat.py's doc.

Modes (ticks log): LOCAL (fighting here) / TRAVEL (going to the target) / ROAM / IDLE / BREAK.
How to change behaviour: a score term, a rule in a table, a state, a parameter with its data source, or a goal whose
terms say when it matters - never a special case in here.
"""
import collections

from .reach import Reach
from .v2.breaks import Breaks
from .v2.combat import Footwork, Weapon
from .v2.ledger import Ledger
from .v2.reflexes import Reflexes
from .v2.targeting import Targeting
from .v2.trips import Trips
from .v3.goals import Hunt
from .v3.model import World
from .v3.planner import Planner


class BrainV2:
    def __init__(self, cfg, nav, hz, reach: Reach | None = None, log=None):
        self.cfg, self.nav, self.hz = cfg, nav, hz
        self.reach = reach or Reach(cfg.combat.weapon, attack_speed=cfg.combat.attack_speed)
        self.say = log or (lambda msg: None)
        self.stats = collections.Counter()
        self.world = World(nav, hz)
        self.face = self.world.me.face
        mp = self.world.map
        self.reflexes = Reflexes(cfg, hz, self.stats, self.say)
        self.ledger = Ledger(self.reach, self.stats, self.say)
        self.targeting = Targeting(mp, hz, self.ledger, self.stats, self.say)
        self.weapon = Weapon(cfg, hz, self.reflexes, self.ledger, self.stats, self.face, self.reach.swing_s)
        self.footwork = Footwork(mp, hz, self.face, self.stats)
        self.trips = Trips(mp, hz, {"jump": cfg.keys.jump}, cfg.keys.jump, self.targeting, self.stats, self.say)
        self.breaks = Breaks(mp, hz, self.stats, self.say)
        self.hunt = Hunt(self.reach, self.weapon, self.footwork, self.targeting, self.trips, self.breaks)
        self.planner = Planner([self.hunt], hz, self.say)

    # the parts' state, by the names the tests / tools / logs use
    @property
    def mode(self):
        return self.hunt.mode

    @property
    def scene(self):
        return self.hunt.scene

    @property
    def task(self):
        return self.planner.task

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
        """After a pause (focus lost): no trip, no target, not engaged; pick afresh."""
        self.weapon.stop()
        self.trips.end(driver)
        self.targeting.target = None
        self.planner.task = None

    def step(self, now, obs, s, driver) -> str | None:
        """One tick. Returns a stop reason (safety) or None."""
        self.weapon.last = None
        stop = self.reflexes.step(now, obs, driver)
        if stop:
            driver.release_all()
            return stop
        if s is None:
            self.weapon.stop()
            driver.hold(set())
            return None
        w = self.world
        w.update(now, obs, s, driver)                    # mobs, us (Facing from the walk keys we hold)
        self.ledger.update(now, w.mobs)
        self.planner.step(now, w, driver)                # the goal names its task, the task moves us
        return None

    def snapshot(self) -> dict:
        """Per tick, for ticks.jsonl."""
        tr, tg = self.trips.travel, self.targeting
        return {"mode": self.mode, "target": tg.target, "swing": self.weapon.last,
                "cost": None if tg.cost is None else round(tg.cost, 2), "standoff": round(tg.standoff),
                "facing": self.face.dir, "weapon": self.weapon.state, "footwork": self.footwork.state,
                "rest": self.breaks.kind,
                "travel": None if tr is None else {"dst": tr.dst, "move": tr.move.kind if tr.move else None,
                                                   "phase": tr.move.phase if tr.move else None}}
