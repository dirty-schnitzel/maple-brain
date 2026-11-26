"""Us in the state (docs/state_model.md section 2, "Us"; PLAN-tracker design 7). Nothing here knows the brain. Parts,
each with its own state and events:

OUR TAG AND FEET (step 4b). The feet = our name tag's centre x, its top y - 1, + the camera (map px). The tag is
FrameFacts.tag (perception/selfpos.py: exact) or, when that reader misses it, a box of the tag list (FrameFacts.tags)
taken by our tag's own width and height (constant for our name; the commonest exact size) the way track/players.py
follows a player's tag: a box of our width by its centre, a narrower one (our tag partly hidden by front scenery or
an effect: "Jenk", "sJob") or a wider one (ours run together with a neighbour's) by the edge that kept its place, within
the players' gates of our last place - and only within ours_list_s (2 s) of the last exact tag. The prototype
(proto_players) took any tag overlapping our last place: on the 30-minute capture its 940 such frames held our tag's
pieces, but also other players standing there, pets and mobs' own tags (by eye, 20 cases: 11 ours). No tag: our feet
are not known on this frame (`seen` False; the last values kept). No camera: likewise (cover "blind").

PLACE: the graph's one rule (track/graph.py: stand / rope / air; we climb) with the step since our last sighting.
ROPES NEED A KEY (the user, 2026-11-26: "They are grabbed by pressing up or down"): when our keys are known, a rope the
rule puts us on that we were not on the frame before is a GRAB, taken only with up or down down at it (pressed within
grab_s before the frame); staying on it needs no key; a jump or a fall past a rope without the key is not on it,
whatever the speed (no speed test: try 2's broke 22 grabs from a jump). Our keys unknown (live, until PLAN-tracker step
9 hands them in): the plain rule. Then the stuck cases nav/selfstate.py found live (its docstring; each one a test in
tests/test_track_us.py):
  - hovering: off every surface, not moving (HOVER_V) for HOVER_S, within HOVER_TOL of a rope's x at its height = on
    that rope (ladder 778's tag reads x +10 px, past rope_tol); once on a rope we stay on it within HOVER_TOL while not
    moving sideways;
  - a walk key held on its own STUCK_S without moving, next to a ladder (within HOVER_TOL, spanning our height) =
    hanging on it, whatever the height says; only from ATTACK_FREEZE_S after any other key (a swing holds us still);
    found, it holds until we move HANG_MOVE;
  - off every surface + still HOVER_S, no rope, at a platform's surface height just past its end (within HOVER_TOL,
    LEDGE_TOL in y) = standing on its end (x clamped onto it); it holds until we move HANG_MOVE.
  (SelfState's "tag and minimap both under the floor next to a ladder" needs no rule here: the minimap is not used,
  and an exact tag 13 px under a floor is not standing on it.)
vx, vy: least squares over our last VEL_S of sightings. `facing`: the last left / right key down (-1 / +1; 0 unknown):
a belief, nothing on screen shows it. `act`: climb (rope) / air / walk (standing, |vx| >= HOVER_V) / stand. The swing,
"hit" and "dead" come with the events (PLAN-tracker step 5: a cast = a key-down with no swing running, confirmed by
the MP step). The HUD's numbers as read (hp, mp: [cur, max]; exp points), each held while unreadable.

THE SLOTS (step 7): per key the item / skill / action on it and the item's amount, from FrameFacts `slots` (the hotkey
reader, perception/slots.py: exact or nothing on each frame). A key whose cell is not readable on a frame (a tooltip,
the cursor, a map change's fade) keeps its last exact reading, with `seen` False. Every change of an exact reading is
a `slot` event; an amount's step on the same item carries `d` (a potion drunk = -1, one picked up = +1).
"""
from collections import Counter, deque
from dataclasses import dataclass, field

import numpy as np

from ..config import Track
from .graph import NONE, PLACES, ROPE, STAND

HOVER_S = 0.25                    # s off every surface without moving = holding on to something (nav/selfstate.py)
HOVER_V = 30.0                    # px/s: "not moving" on both axes
HOVER_TOL = 16.0                  # px from a rope's x for a hovering body to count as on it
STUCK_S = 0.4                     # s a walk key is held without moving: we aren't on a floor
STUCK_V = 5.0                     # px/s
HANG_MOVE = 4.0                   # px: a found hang / ledge lasts until we move this far
ATTACK_FREEZE_S = 0.9             # s after any other key in which standing still proves nothing (a swing ~0.8 s)
LEDGE_TOL = 9.0                   # px: our feet at a platform end's surface height (SelfTracker's ground_tol)
LEDGE_REACH = 20.0                # px: a ladder "spans our height" within this of its ends (SelfTracker._ladder_near)
VEL_S = 0.2                       # s of sightings for vx, vy
WALK = ("left", "right")
GRAB = {"up", "down"}                     # a rope is grabbed with one of these down (the user, 2026-11-26)
MOVE = ("left", "right", "up", "down")


@dataclass
class Slot:
    """One hotkey as the state holds it. `kind` "item" / "skill" / "skill_disabled" / "skill_mouseover" / "action" /
    "empty" (perception/slots.Read); `id` the item's / skill's / action's id, `amount` the number drawn (None: none
    drawn). `seen`: read exactly on this frame (False: held from `seen_t`). `since`: when it last changed."""
    kind: str
    id: int | None
    amount: int | None
    seen: bool = True
    seen_t: float = 0.0
    since: float = 0.0

    def reading(self) -> list:
        return [self.kind, self.id, self.amount]


class Slots:
    """`update(slots, t)` per frame with FrameFacts `slots` ({key: [kind, id, amount] or None}) -> this frame's
    events. `keys` = {key: Slot}: every key ever read (a key never read exactly is not in it)."""

    def __init__(self):
        self.keys: dict[str, Slot] = {}

    def update(self, slots: dict, t: float) -> list:
        events = []
        for s in self.keys.values():
            s.seen = False
        for key, r in (slots or {}).items():
            if r is None:
                continue
            kind, cid, amount = r
            s = self.keys.get(key)
            if s is None:
                self.keys[key] = Slot(kind, cid, amount, True, t, t)
                continue
            if [kind, cid, amount] != s.reading():
                same = (kind, cid) == (s.kind, s.id) and amount is not None and s.amount is not None
                events.append({"ev": "slot", "t": t, "key": key, "was": s.reading(), "now": [kind, cid, amount],
                               "d": amount - s.amount if same else None})
                s.kind, s.id, s.amount, s.since = kind, cid, amount, t
            s.seen, s.seen_t = True, t
        return events

    def state(self) -> dict:
        """{key: {kind, id, amount, seen, seen_t, since}} - the state's `slots`."""
        return {k: {"kind": s.kind, "id": s.id, "amount": s.amount, "seen": s.seen, "seen_t": s.seen_t,
                    "since": s.since} for k, s in self.keys.items()}


class OurTag:
    """Our name tag on the screen this frame: FrameFacts.tag, else a box of the tag list (the module's docstring).
    `find(facts)` -> (x, y, w, h, list index or None) or None; `src` "tag" / "list" / None."""

    def __init__(self, cfg: Track):
        self.cfg = cfg
        self.size = Counter()                # the exact tag's (w, h)
        self.wh = None
        self.last = None                     # (left, top) map px of our tag's last sighting, its t
        self.last_t = None
        self.exact_t = None                  # the last exact tag's t
        self.src = None
        self.stats = Counter()

    def find(self, facts):
        c = self.cfg
        t, C = facts.t, facts.scene_cam
        self.src = None
        tag = facts.tag
        if tag is not None:
            x, y, w, h = (int(v) for v in tag[:4])
            k = self.size[(w, h)] = self.size[(w, h)] + 1
            if self.wh is None or k > self.size[self.wh]:
                self.wh = (w, h)
            if C is not None:
                self.last, self.last_t = (x + C[0], y + C[1]), t
            self.exact_t, self.src = t, "tag"
            self.stats["tag"] += 1
            return (x, y, w, h, None)
        if C is None or self.wh is None or self.last is None or t - self.exact_t > c.ours_list_s:
            self.stats["none"] += 1
            return None
        ow, oh = self.wh
        u = t - self.last_t
        G0, WT = c.tag_gate, c.tag_w_tol
        pl, pt = self.last
        pr = pl + ow
        best = None
        for i, tg in enumerate(facts.tags or []):
            x, y, w, h = (int(v) for v in tg[:4])
            L, T = x + C[0], y + C[1]
            R = L + w
            ey = min(abs(T - pt), abs(T + h - pt - oh))
            if ey > G0 + c.tag_vy * u or abs(h - oh) > WT and w <= ow + WT:
                continue                     # a piece or a whole tag of ours has our height
            dw = w - ow
            if abs(dw) <= WT:                # our width: by the centre
                ex = abs(L + w / 2.0 - pl - ow / 2.0)
                if ex > G0 + c.tag_vx * u:
                    continue
                cost, nl = ex + ey, L + (w - ow) / 2.0
            else:                            # a piece of ours / a wider box we are in: by the edge that kept its place
                el, er = abs(L - pl), abs(R - pr)
                ex = min(el, er)
                if ex > G0 + 60.0 * u:
                    continue
                cost, nl = ex + ey + 8.0, (L if el <= er else R - ow)
            ny = T if abs(T - pt) <= abs(T + h - pt - oh) else T + h - oh
            if best is None or cost < best[0]:
                best = (cost, i, nl, ny)
        if best is None:
            self.stats["none"] += 1
            return None
        _, i, nl, ny = best
        self.last, self.last_t, self.src = (nl, ny), t, "list"
        self.stats["list"] += 1
        return (nl - C[0], ny - C[1], ow, oh, i)


class Place:
    """Our place by the graph's one rule + the stuck cases (the module's docstring). `update(t, feet, held)`."""

    def __init__(self, graph, cfg: Track):
        self.g, self.cfg = graph, cfg
        self.hist = deque()                  # (t, x, y)
        self.x = self.y = None
        self.t = None                        # our last sighting
        self.place, self.node, self.from_node, self.off = 1, NONE, NONE, float("nan")
        self.vx = self.vy = 0.0
        self.hover_since = None
        self.walk_since = None               # a walk key held on its own continuously since
        self.frozen_until = -9.0             # standing still proves nothing until then (a swing)
        self.hang = None                     # (rope index, x, y): found hanging there
        self.ledge = None                    # (node, x, y): found standing past its end
        self.why = ""                        # the rule that decided this frame's place (a tool reads it)
        self.grab_t = -9.0                   # the last time up or down was down
        g = graph
        self._ropes = [(i, float(g.rope_x[i]), float(g.rope_top[i]), float(g.rope_bottom[i]))
                       for i in range(len(g.rope_x))]

    def _velocity(self, t):
        pts = [p for p in self.hist if t - p[0] <= VEL_S]
        if len(pts) < 2 or pts[-1][0] - pts[0][0] < 0.05:
            return 0.0, 0.0
        a = np.array(pts)
        tt = a[:, 0] - a[:, 0].mean()
        den = float((tt * tt).sum()) or 1e-9
        return float((tt * a[:, 1]).sum() / den), float((tt * a[:, 2]).sum() / den)

    def _ladder_near(self, x, y, tol=HOVER_TOL, reach=LEDGE_REACH):
        best = None
        for i, rx, top, bot in self._ropes:
            if abs(rx - x) <= tol and top - reach <= y <= bot + reach and (best is None or abs(rx - x) < best[0]):
                best = (abs(rx - x), i)
        return None if best is None else best[1]

    def _ledge_under(self, x, y):
        """The node whose end we stand just past: x within HOVER_TOL beyond it, feet at its surface (LEDGE_TOL)."""
        g = self.g
        best = None
        for k, nid in enumerate(g.ids):
            if nid <= 0:
                continue
            lo, hi = float(g.left[k]), float(g.right[k])
            cx = min(max(x, lo), hi)
            if cx == x or abs(cx - x) > HOVER_TOL:
                continue
            yp = float(g.surface_y(np.array([nid], np.int64), np.array([cx]))[0])
            if not np.isnan(yp) and abs(yp - y) <= LEDGE_TOL and (best is None or abs(yp - y) < best[0]):
                best = (abs(yp - y), int(nid), cx, yp)
        return best

    def update(self, t, feet, held, keys_known: bool = False) -> bool:
        """feet (map px) or None (not known: nothing changes) -> True when placed. `held`: the keys down now;
        `keys_known`: our keys are known (else a rope needs no key: the plain rule)."""
        keys = set(held or ())
        if keys & GRAB:
            self.grab_t = t
        if feet is None:
            return False
        x, y = float(feet[0]), float(feet[1])
        c = self.cfg
        recent = self.t is not None and 0 < t - self.t < c.ballistic_s
        dx, dy = (x - self.x, y - self.y) if recent else (0.0, 0.0)
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > VEL_S:
            self.hist.popleft()
        self.vx, self.vy = self._velocity(t)
        args = (np.array([x]), np.array([y]), np.array([dx]), np.array([dy]), np.array([self.node]),
                np.array([self.from_node]))
        P = self.g.place(*args, climb=np.array([True]))
        place, node, off = int(P.place[0]), int(P.node[0]), float(P.off[0])
        self.why = "rule"
        grab = place == ROPE and not (self.place == ROPE and self.node == node)   # a rope we were not on
        if grab and keys_known and t - self.grab_t > c.grab_s:   # ... without up / down: past it, not on it
            P = self.g.place(*args, climb=np.array([False]))
            place, node, off = int(P.place[0]), int(P.node[0]), float(P.off[0])
            self.why = "no grab"
        if keys - set(MOVE):
            self.frozen_until = t + ATTACK_FREEZE_S
        walking = bool(set(WALK) & keys) and t >= self.frozen_until
        self.walk_since = (self.walk_since if self.walk_since is not None else t) if walking else None
        if self.hang is not None and (abs(x - self.hang[1]) > HANG_MOVE or abs(y - self.hang[2]) > HANG_MOVE):
            self.hang = None
        if self.ledge is not None and (abs(x - self.ledge[1]) > HANG_MOVE or abs(y - self.ledge[2]) > HANG_MOVE):
            self.ledge = None
        if self.hang is None and place == STAND and walking and abs(self.vx) < STUCK_V \
                and t - self.walk_since >= STUCK_S:
            i = self._ladder_near(x, y)
            if i is not None:                               # walking does nothing: we hang on the ladder
                self.hang = (i, x, y)
        still = abs(self.vx) < HOVER_V and abs(self.vy) < HOVER_V
        if place == STAND or place == ROPE or self.hang is not None:
            self.hover_since = None
        else:
            self.hover_since = (self.hover_since if self.hover_since is not None else t) if still else None
        hovering = self.hover_since is not None and t - self.hover_since >= HOVER_S
        if self.hang is not None:
            place, node, off, self.why = ROPE, -1 - self.hang[0], x - float(self.g.rope_x[self.hang[0]]), "hang"
        elif place != STAND:
            was = -1 - node if place == ROPE else (-1 - self.node if self.place == ROPE else None)
            best = None
            for i, rx, top, bot in self._ropes:
                stays = was == i and abs(self.vx) < HOVER_V     # climbing on it, not leaving sideways
                if not (hovering or stays):             # the plain rope_tol case is the graph's rule (and the
                    continue                            # grab's key); here only the stuck cases' wider reach
                tol = max(c.rope_tol, HOVER_TOL)
                if abs(rx - x) <= tol and top - c.rope_tol <= y <= bot + c.rope_tol \
                        and (best is None or abs(rx - x) < best[0]):
                    best = (abs(rx - x), i)
            if best is not None and place != ROPE:
                i = best[1]
                place, node, off, self.why = ROPE, -1 - i, x - float(self.g.rope_x[i]), "hover" if hovering else "stays"
            elif best is None and place != ROPE and (hovering or self.ledge is not None):
                lg = self._ledge_under(x, y)
                if lg is not None:                          # nothing hovers: we stand on its end
                    self.ledge = (lg[1], x, y)
                    place, node, off, self.why = STAND, lg[1], y - lg[3], "ledge"
                    x = lg[2]
        if place == STAND:
            self.hover_since = None
        self.from_node = node if place in (STAND, ROPE) else self.from_node
        self.place, self.node, self.off = place, node, off
        self.x, self.y, self.t = x, y, t
        return True


@dataclass
class Us:
    """Our character in the state. `update(facts, keys)` per frame (perception/facts.FrameFacts; `keys` = our key
    events since the last frame [{"t", "key", "down"}], None: not known) -> this frame's events; `state()` the
    fields. `graph` None: the slots only (no camera work)."""
    graph: object = None
    cfg: Track = field(default_factory=Track)
    slots: Slots = field(default_factory=Slots)

    def __post_init__(self):
        self.tag = OurTag(self.cfg)
        self.place = Place(self.graph, self.cfg) if self.graph is not None else None
        self.held = set()
        self.keys_known = False              # our keys were ever handed in (live: not until PLAN-tracker step 9)
        self.facing = 0
        self.seen = False
        self.box = None                      # our tag on the screen this frame (x, y, w, h, list index or None)
        self.sx = self.sy = None
        self.hp = self.mp = None
        self.exp = None
        self.cover = "none"
        self.t = None

    def update(self, facts, keys=None) -> list:
        events = self.slots.update(facts.slots, facts.t)
        t, C = facts.t, facts.scene_cam
        self.t = t
        self.keys_known |= keys is not None
        for k in keys or ():
            if k["down"]:
                self.held.add(k["key"])
                if k["key"] in GRAB and self.place is not None:     # pressed and let go between two frames counts
                    self.place.grab_t = max(self.place.grab_t, k.get("t", t))
                if k["key"] in WALK:
                    self.facing = -1 if k["key"] == "left" else 1
            else:
                self.held.discard(k["key"])
        if facts.hp is not None:
            self.hp = list(facts.hp)
        if facts.mp is not None:
            self.mp = list(facts.mp)
        if facts.exp_points is not None:
            self.exp = facts.exp_points
        self.box = self.tag.find(facts)
        self.seen, self.cover = False, "blind" if C is None else "none"
        if self.place is None or C is None:
            return events
        if self.box is not None:
            x, y, w, h, _ = self.box
            self.sx, self.sy = x + w / 2.0, y - 1.0
            self.seen = self.place.update(t, (self.sx + C[0], self.sy + C[1]), self.held, self.keys_known)
        else:
            self.cover = "unseen"
        return events

    def act(self) -> str:
        p = self.place
        if p is None or p.x is None:
            return "unknown"
        if p.place == ROPE:
            return "climb"
        if p.place != STAND:
            return "air"
        return "walk" if abs(p.vx) >= HOVER_V else "stand"

    def state(self) -> dict:
        out = {"slots": self.slots.state(), "facing": self.facing, "hp": self.hp, "mp": self.mp, "exp": self.exp}
        p = self.place
        if p is not None:
            out.update({"x": p.x, "y": p.y, "seen": self.seen, "src": self.tag.src, "cover": self.cover,
                        "place": PLACES[p.place], "node": p.node, "from_node": p.from_node, "off": p.off,
                        "vx": p.vx, "vy": p.vy, "act": self.act(),
                        "unseen_s": None if p.t is None else round(self.t - p.t, 4)})
        return out
