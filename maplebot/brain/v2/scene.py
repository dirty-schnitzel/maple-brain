"""brain-v2: the per-tick picture every part reads (M0's obs.state): us + every live mob relative to us, computed ONCE.

Nothing here decides anything. `Facing` is the one place that knows which way we look (from the walk keys we hold or
tap) and how often we turned lately (no left-right-left-right).
"""
from dataclasses import dataclass, field

from ..reach import SWING_LAND_S, Box

LIVE = ("live", "hit", "hidden")
UNSEEN_MAX = 1.5                  # s a track may go unseen and still count as there
TURN_GAP = (0.6, 0.9)             # s between two turns (varied)


def sign(v):
    return (v > 0) - (v < 0)


def keep_hi(x) -> float:
    """How far out a held attack is kept going: the maybe far edge (live, v2 08:40: swings still hit 42 % at
    150-180 px; holding on costs nothing, a re-press does - halfway (~147) lost kills in the sim, 12.4 vs 13.7)."""
    return x.maybe.hi


@dataclass
class Seen:
    """One live mob, relative to our feet."""
    m: dict                       # the track (world.Track.as_dict)
    dx: float                     # px, + = right of us (screen px when both were seen this frame, else map)
    dy: float                     # px, + = below our feet
    pdx: float                    # dx predicted at the moment a swing pressed now would land - up to us, never
                                  # past us (a mob walking into us was predicted behind: wrong side, v2 08:40)
    sure: Box                     # our reach vs this mob type (brain/reach.py)
    maybe: Box
    here: bool                    # on our platform (we're standing): reachable by walking

    @property
    def id(self):
        return self.m["id"]

    @property
    def platform(self):
        return self.m.get("platform")


class Facing:
    """Which way we look, and when we may turn again: a varied TURN_GAP after the last turn (was max 2 turns per
    2.5 s: runs/v2 08:40 stood ~14 s in all with the target behind; the user: turning looked fine, don't overfit)."""

    def __init__(self, hz=None):
        self.dir = 0                                      # +1 right / -1 left / 0 unknown
        self.hz = hz
        self.last_turn, self.gap = -9.0, TURN_GAP[0]

    def face(self, d, now):
        if d and d != self.dir:
            if self.dir:
                self.last_turn = now
                self.gap = self.hz.between(*TURN_GAP) if self.hz is not None else TURN_GAP[0]
            self.dir = d

    def from_keys(self, keys, now):
        self.face(("right" in keys) - ("left" in keys), now)

    def can_turn(self, now) -> bool:
        return now - self.last_turn >= self.gap


@dataclass
class Scene:
    now: float
    s: object                     # SelfState
    facing: int
    mobs: list = field(default_factory=list)          # [Seen], in the tracker's order

    @classmethod
    def build(cls, now, obs, s, facing: int, reach) -> "Scene":
        out = []
        for m in obs.mobs:
            if m.get("kind", "mob") != "mob" or m["state"] not in LIVE or m.get("unseen", 0) > UNSEEN_MAX:
                continue
            if obs.me is not None and m.get("src") != "none" and m.get("sx") is not None:
                dx, dy = m["sx"] - obs.me[0], m["sy"] - obs.me[1]
            else:
                dx, dy = m["x"] - s.x, m["y"] - s.y
            sure, maybe = reach.vs(m.get("mob"))
            here = s.state == "ground" and (m.get("platform") == s.platform
                                            or (m.get("platform") is None and abs(dy) <= 40))
            pdx = dx + (m.get("vx") or 0.0) * SWING_LAND_S
            if sign(pdx) != sign(dx):
                pdx = 0.0
            out.append(Seen(m, dx, dy, pdx, sure, maybe, here))
        return cls(now, s, facing, out)

    def get(self, tid):
        return next((x for x in self.mobs if x.id == tid), None)

    def front(self, x: Seen) -> float:
        """Predicted px in front of us (negative = behind)."""
        return self.facing * x.pdx

    def in_reach(self, x: Seen, keep: bool = False) -> bool:
        """WHEN TO HIT: predicted in front between the stab's near edge and the sure far edge, at a height every
        stance reaches. keep=True (already holding the attack): the ACTUAL position within the maybe reach - a mob
        our hits knock back moves away fast, its prediction leaves the reach long before it does."""
        if keep:
            return x.maybe.lo - 6 <= self.facing * x.dx <= keep_hi(x) and x.sure.ylo <= x.dy <= x.sure.yhi
        f = self.front(x)
        return x.maybe.lo - 6 <= f <= x.sure.hi - 4 and x.sure.ylo <= x.dy <= x.sure.yhi

    def near(self, x: Seen) -> bool:
        """Close enough in front to log a swing's outcome for (reach learning)."""
        return -10 <= self.front(x) <= 200 and abs(x.dy) <= 60
