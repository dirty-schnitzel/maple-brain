"""brain-v2: the per-tick picture every part reads (M0's obs.state): us + every live mob relative to us, computed ONCE.
v3 layer: tasks (Fight's view of the world model). Step 1: built from the world model's objects (brain/v3/model.py:
Mob, Character) instead of the track dicts; Facing moved there (part of Character).

Nothing here decides anything. Facing (brain/v3/model.py) is the one place that knows which way we think we look.

Reach tests (step 2 of the attack logic, described end to end in v2/combat.py):
    in_reach(x)        start on a mob: the PREDICTED position (pdx) in front, from the stab's near edge to the SURE
                       far edge, at a height every stance reaches
    in_reach(x, keep)  go on with the mob we're engaged on: the ACTUAL position (dx) in front, up to keep_hi (the
                       MAYBE far edge) - a mob our hits knock back moves away fast; its prediction leaves the reach
                       long before it does
"""
from dataclasses import dataclass, field

from ..reach import SWING_LAND_S, Box
from ..v3.model import LIVE, Character, Mob

UNSEEN_MAX = 1.5                  # s a track may go unseen and still count as there


def sign(v):
    return (v > 0) - (v < 0)


def keep_hi(x) -> float:
    """How far out we go on pressing at the engaged mob: the maybe far edge (live, v2 08:40: swings still hit 42 % at
    150-180 px; halfway (~147) lost kills in the sim, 12.4 vs 13.7)."""
    return x.maybe.hi


@dataclass
class Seen:
    """One live mob, relative to our feet."""
    mob: Mob                      # the world model's Mob
    dx: float                     # px, + = right of us (screen px when both were seen this frame, else map)
    dy: float                     # px, + = below our feet
    pdx: float                    # dx predicted at the moment a swing pressed now would land - up to us, never
                                  # past us (a mob walking into us was predicted behind: wrong side, v2 08:40)
    sure: Box                     # our reach vs this mob type (brain/reach.py)
    maybe: Box
    here: bool                    # on our platform (we're standing): reachable by walking

    @property
    def id(self):
        return self.mob.id

    @property
    def platform(self):
        return self.mob.platform


@dataclass
class Scene:
    now: float
    me: Character                 # us (SelfState + Facing + HUD)
    facing: int
    mobs: list = field(default_factory=list)          # [Seen], in the tracker's order
    turning: bool = False                             # a turn hasn't landed yet: no fresh attack press

    @property
    def s(self):
        """Our SelfState (Travel / moves take it)."""
        return self.me.s

    @classmethod
    def of(cls, world, reach) -> "Scene":
        """This tick's scene from the world model (after World.update)."""
        me = world.me
        return cls.build(world.now, world.mobs, me, reach, me.face.turning(world.now))

    @classmethod
    def build(cls, now, mobs, me: Character, reach, turning: bool = False) -> "Scene":
        """`mobs`: [Mob] (every kind / state: only live mobs seen lately make it in)."""
        out = []
        feet = me.screen
        for m in mobs:
            if m.kind != "mob" or m.state not in LIVE or m.unseen > UNSEEN_MAX:
                continue
            if feet is not None and m.src != "none" and m.sx is not None:
                dx, dy = m.sx - feet[0], m.sy - feet[1]
            else:
                dx, dy = m.x - me.x, m.y - me.y
            sure, maybe = reach.vs(m.type)
            here = me.state == "ground" and (m.platform == me.platform
                                             or (m.platform is None and abs(dy) <= 40))
            pdx = dx + m.vx * SWING_LAND_S
            if sign(pdx) != sign(dx):
                pdx = 0.0
            out.append(Seen(m, dx, dy, pdx, sure, maybe, here))
        return cls(now, me, me.facing, out, turning)

    def get(self, tid):
        return next((x for x in self.mobs if x.id == tid), None)

    def front(self, x: Seen) -> float:
        """Predicted px in front of us (negative = behind)."""
        return self.facing * x.pdx

    def in_reach(self, x: Seen, keep: bool = False) -> bool:
        """WHEN TO HIT: predicted in front between the stab's near edge and the sure far edge, at a height every
        stance reaches. keep=True (the mob we're engaged on): the ACTUAL position within the maybe reach - a mob
        our hits knock back moves away fast, its prediction leaves the reach long before it does."""
        if keep:
            return x.maybe.lo - 6 <= self.facing * x.dx <= keep_hi(x) and x.sure.ylo <= x.dy <= x.sure.yhi
        f = self.front(x)
        return x.maybe.lo - 6 <= f <= x.sure.hi - 4 and x.sure.ylo <= x.dy <= x.sure.yhi

    def near(self, x: Seen) -> bool:
        """Close enough in front to log a swing's outcome for (reach learning)."""
        return -10 <= self.front(x) <= 200 and abs(x.dy) <= 60
