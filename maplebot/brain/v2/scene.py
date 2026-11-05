"""brain-v2: the per-tick picture every part reads (M0's obs.state): us + every live mob relative to us, computed ONCE.

Nothing here decides anything. `Facing` is the one place that knows which way we look (from the walk keys we hold or
tap) and how often we turned lately (no left-right-left-right).
"""
import collections
from dataclasses import dataclass, field

from ..reach import SWING_LAND_S, Box

LIVE = ("live", "hit", "hidden")
UNSEEN_MAX = 1.5                  # s a track may go unseen and still count as there


def sign(v):
    return (v > 0) - (v < 0)


@dataclass
class Seen:
    """One live mob, relative to our feet."""
    m: dict                       # the track (world.Track.as_dict)
    dx: float                     # px, + = right of us (screen px when both were seen this frame, else map)
    dy: float                     # px, + = below our feet
    pdx: float                    # dx predicted at the moment a swing pressed now would land
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
    def __init__(self, window: float = 2.5, max_turns: int = 2):
        self.dir = 0                                      # +1 right / -1 left / 0 unknown
        self.turns = collections.deque()
        self.window, self.max_turns = window, max_turns

    def face(self, d, now):
        if d and d != self.dir:
            if self.dir:
                self.turns.append(now)
            self.dir = d

    def from_keys(self, keys, now):
        self.face(("right" in keys) - ("left" in keys), now)

    def can_turn(self, now) -> bool:
        while self.turns and now - self.turns[0] > self.window:
            self.turns.popleft()
        return len(self.turns) < self.max_turns


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
            out.append(Seen(m, dx, dy, dx + (m.get("vx") or 0.0) * SWING_LAND_S, sure, maybe, here))
        return cls(now, s, facing, out)

    def get(self, tid):
        return next((x for x in self.mobs if x.id == tid), None)

    def front(self, x: Seen) -> float:
        """Predicted px in front of us (negative = behind)."""
        return self.facing * x.pdx

    def in_reach(self, x: Seen) -> bool:
        """WHEN TO HIT: predicted in front between the stab's near edge and the sure far edge, at a height every
        stance reaches."""
        f = self.front(x)
        return x.maybe.lo + 4 <= f <= x.sure.hi - 4 and x.sure.ylo <= x.dy <= x.sure.yhi

    def near(self, x: Seen) -> bool:
        """Close enough in front to log a swing's outcome for (reach learning)."""
        return -10 <= self.front(x) <= 200 and abs(x.dy) <= 60
