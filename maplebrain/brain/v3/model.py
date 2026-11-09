"""brain v3, layer: WORLD MODEL (PLAN-v3.md migration step 1: objects over today's parts).

One object per thing in the game, updated once per tick from perception (`World.update`); every part of the brain
reads these instead of raw dicts / tuples. Thin wrappers: nothing here decides anything, no rule lives here.

    Map        NavMap (platforms, ropes, links, routes) + its spawns as Spawn objects + route seconds (cached)
    Platform   navmap.Platform as it is (ends, footholds, y at x, open ends)
    Spawn      x, y and the platform it stands on
    Mob        one tracked mob this tick (world.Track.as_dict, typed): id, type, state, map / screen feet, vx, ...
    Character  us: SelfState (where, ground / rope / air) + Facing (which way we believe we look) + our HUD numbers
               + the keys (`hands` = the KeyDriver)

Step 1 changes no behaviour: tools/v3/gate.py (sim 8 seeds x 3 min + agree.py) matches the baseline exactly.
Added later (PLAN-v3.md): marks per session on the Map (step 3), memory - respawn per spawn, last cleared per platform,
players over time (step 4).
"""
from dataclasses import dataclass

from ..moves import node_of

LIVE = ("live", "hit", "hidden")    # track states that count as a live mob
ROUTE_TTL_S = 1.0                   # s a route's seconds stay cached
ROUTE_CACHE_MAX = 400               # entries before the stale ones are dropped


class Mob:
    """One tracked mob this tick: perception's track dict (world.Track.as_dict), typed. `type` = the mob id in the
    game data (the dict's "mob"); sx / sy = screen feet (None when the dict has none)."""
    __slots__ = ("id", "type", "kind", "state", "x", "y", "sx", "sy", "vx", "platform", "unseen", "src")

    def __init__(self, d: dict):
        self.id = d["id"]
        self.type = d.get("mob")
        self.kind = d.get("kind", "mob")
        self.state = d["state"]
        self.x, self.y = d["x"], d["y"]
        self.sx, self.sy = d.get("sx"), d.get("sy")
        self.vx = d.get("vx") or 0.0
        self.platform = d.get("platform")
        self.unseen = d.get("unseen", 0)
        self.src = d.get("src")

    @property
    def live(self) -> bool:
        return self.state in LIVE

    @property
    def dying(self) -> bool:
        return self.state == "dying"

    def __repr__(self):
        return f"Mob({self.id} {self.type} {self.state} x {self.x} y {self.y} on {self.platform})"


@dataclass(frozen=True)
class Spawn:
    x: float
    y: float
    platform: int | None            # the platform it stands on (within 12 px), None = none


class Map:
    """The map: NavMap's geometry and routes, its spawns, and route seconds cached for ROUTE_TTL_S (the targeting
    score and roam ask the same few routes many times a second). `nav` = the NavMap itself (Travel takes it)."""

    def __init__(self, nav):
        self.nav = nav
        self.platforms = nav.platforms if nav is not None else {}
        self.spawns = [] if nav is None else [Spawn(x, y, _pid(nav.platform_at(x, y, tol=12)))
                                              for x, y in nav.spawns]
        self._routes = {}

    def platform(self, pid):
        return self.platforms.get(pid)

    def rope(self, node):
        return self.nav.rope(node)

    def route_seconds(self, now, me, pid, x):
        """Seconds from where we are (`me`: Character or SelfState) to x on platform pid; None = no route / in the
        air (no node to route from)."""
        n = node_of(me)
        if n is None:
            return None
        key = (n, round(me.x / 40), pid, round(x / 40))
        c = self._routes.get(key)
        if c is None or now - c[0] > ROUTE_TTL_S:
            r = self.nav.route(n, me.y if self.nav.is_rope(n) else me.x, pid, x, with_cost=True)
            c = (now, r[1] if r is not None else None)
            self._routes[key] = c
            if len(self._routes) > ROUTE_CACHE_MAX:
                self._routes = {k: v for k, v in self._routes.items() if now - v[0] <= ROUTE_TTL_S}
        return c[1]


def _pid(p):
    return p.id if p is not None else None


TURN_GAP = (0.6, 0.9)             # s between two turns (varied)
TURN_SETTLE = (0.12, 0.2)         # s after a turn before the attack goes down: pressed on top of the walk key, it can
                                  # eat the turn (runs/v2 10:19 t=256: walk key 0.07 s, then 5.9 s of swings at nothing)


class Facing:
    """Which way we believe we look, and when we may turn again: a varied TURN_GAP after the last turn (was max 2
    turns per 2.5 s: runs/v2 08:40 stood ~14 s in all with the target behind; the user: turning looked fine, don't
    overfit) and not before the last swing is over (`swung`). `doubt`: the evidence says we look the other way.
    It's a BELIEF: nothing on screen confirms it, the game drops direction keys mid-swing / in knockback."""

    def __init__(self, hz=None):
        self.dir = 0                                      # +1 right / -1 left / 0 unknown
        self.hz = hz
        self.last_turn, self.gap = -9.0, TURN_GAP[0]
        self.settled_at = 0.0                             # a turn has landed from then on
        self.swing_over = 0.0                             # the game takes direction keys again from then on

    def face(self, d, now):
        if d and d != self.dir:
            if self.dir:
                self.last_turn = now
                self.gap = self.hz.between(*TURN_GAP) if self.hz is not None else TURN_GAP[0]
                settle = self.hz.between(*TURN_SETTLE) if self.hz is not None else TURN_SETTLE[0]
                self.settled_at = max(now, self.swing_over) + settle
            self.dir = d

    def from_keys(self, keys, now):
        self.face(("right" in keys) - ("left" in keys), now)

    def swung(self, over):
        """We pressed the attack key: our swing ends at `over` (Weapon: key-down + swing_s)."""
        self.swing_over = over

    def doubt(self):
        """We look the other way after all. Footwork's rules then turn us toward the target like any mob behind us
        (if we were right, that tap only points us where we already look)."""
        self.dir = -self.dir

    def can_turn(self, now) -> bool:
        return now - self.last_turn >= self.gap and now >= self.swing_over

    def turning(self, now) -> bool:
        return now < self.settled_at


class Character:
    """Us. Where: SelfState `s` (x / y, ground / rope / air, platform, rope, vx / vy). Facing `face`. HUD numbers
    (hp / mp shares, hp_now / mp_now points or None, potions left). `screen` = our feet on screen (the tag; None
    unseen). `hands` = the key driver this tick."""

    def __init__(self, hz=None):
        self.face = Facing(hz)
        self.s = None
        self.hands = None
        self.screen = None
        self.hp = self.mp = self.hp_now = self.mp_now = None
        self.hp_potions = self.mp_potions = True

    @classmethod
    def of(cls, s, facing: int = 0, obs=None) -> "Character":
        """A Character standing at SelfState s, looking `facing`, HUD from obs (tests, replay tools)."""
        me = cls()
        me.face.dir = facing
        me.s = s
        me._hud(obs)
        return me

    def _hud(self, obs):
        if obs is None:
            return
        self.screen = getattr(obs, "me", None)
        for k in ("hp", "mp", "hp_now", "mp_now", "hp_potions", "mp_potions"):
            if hasattr(obs, k):
                setattr(self, k, getattr(obs, k))

    def update(self, now, obs, s, hands):
        self.s, self.hands = s, hands
        self._hud(obs)
        self.face.from_keys(getattr(hands, "want", None) or set(), now)

    # where we are (SelfState's fields)
    x = property(lambda self: self.s.x)
    y = property(lambda self: self.s.y)
    state = property(lambda self: self.s.state)
    platform = property(lambda self: self.s.platform)
    rope = property(lambda self: self.s.rope)
    vx = property(lambda self: self.s.vx)
    vy = property(lambda self: self.s.vy)

    @property
    def facing(self) -> int:
        return self.face.dir

    @property
    def node(self):
        """The navmap node we're on: platform id (ground), rope node (< 0), None in the air."""
        return node_of(self.s)


class World:
    """The world model: the Map, us (Character), the mobs this tick. `update` once per tick, before any part reads it."""

    def __init__(self, nav, hz=None):
        self.map = Map(nav)
        self.me = Character(hz)
        self.mobs = []                                    # [Mob], in the tracker's order (every kind and state)
        self.now = 0.0

    def update(self, now, obs, s, hands):
        self.now = now
        self.mobs = [Mob(d) for d in obs.mobs]
        self.me.update(now, obs, s, hands)
