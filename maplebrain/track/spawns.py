"""Spawn points as tracked things (PLAN-tracker step 3b; docs/state_model.md section 3). Memory, not prediction - the
user, 2026-11-25: "keeping track of the time since last spawn (on spawn point) is a valid tracking object. It would
not be trying to add predictive abilities to the tracking behavior ... it is a part of tracking's memory".

Per frame, after the mob tracker: `update(t, C, records, events, tags, drops, ui)`.
1. FIRST SIGHTINGS: a track id seen for the first time in the mob tracker's records (tentative ones included) leaves
   its first feet, node, opacity and time here.
2. A SPAWN SEEN = the mob tracker's `mob_new` event (a confirmed mob; it waits until "how it came into sight" is
   settled) with how "faded in", traced back to its point - rule (c), the user's answer of 2026-11-25: a point of its
   kind could have put the mob where it was first seen in the time it has existed: that time = its first opacity x
   spawn_fade_s (the fade-in measured on Classic World: 0.82 s, a straight line); a walker: the point on the first
   sighting's node, |dx| <= its kind's speed (kinds.py) x the time + spawn_slack, the feet within spawn_slack of the
   node's surface or up to one hop (spawn_hop) over it when its kind jumps; a flyer: the point's (x, spriteY) within
   its speed x the time + spawn_slack. Exactly one candidate -> that point's spawn: last_spawn_t = the mob's first
   sighting, last_mob = its id, spawns + 1. Two or more -> none (never a guess); none -> none. A mob born another way
   (came into view, uncovered, there at entry) is never a spawn.
3. IN VIEW: the point's body box (its kind's, at the point; a flyer at spriteY) has its centre on the play area, not
   in a UI rectangle and not in a box the trackers hold (us, other players - the sorted tags' -, the mobs seen, the
   drops). On the CPU, no GPU call.
A blind frame (no camera) changes nothing. No respawn rule, no timer, no guess about spawns not seen; the brain does
not read it (the 10 s round of game_rules E2 is ~7.1 s measured: not tracked here).
"""
import numpy as np

from ..config import Track
from .graph import NONE
from .state import SpawnPoint

SW, PLAY_H = 1366, 700


class Spawns:
    """`graph`: the map's track/graph.Graph (its spawn points: kind, x, y, spriteY, node, mobTime); `kinds`:
    track/kinds.kinds() of the map; `cfg`: config.Track."""

    def __init__(self, graph, kinds: dict, cfg: Track | None = None):
        self.g, self.kinds, self.cfg = graph, kinds, cfg or Track()
        g = graph
        self.points = [SpawnPoint(int(g.spawn_index[i]), int(g.spawn_kind[i]), float(g.spawn_x[i]),
                                  float(g.spawn_y[i]), float(g.spawn_sy[i]), int(g.spawn_node[i]),
                                  int(g.spawn_time[i])) for i in range(len(g.spawn_kind))]
        # each point's body-box centre in map px (its kind's box at the point; a flyer at spriteY): in_view tests it
        cx, cy = [], []
        for p in self.points:
            k = kinds.get(p.kind)
            lt, rb = (k.lt, k.rb) if k is not None else ((0, 0), (0, 0))
            cx.append(p.x + (lt[0] + rb[0]) / 2)
            cy.append((p.sy if k is not None and k.fly else p.y) + (lt[1] + rb[1]) / 2)
        self.cx, self.cy = np.array(cx, np.float64), np.array(cy, np.float64)
        self.first = {}                                 # track id -> (t, x, y, node, opacity) of its first sighting
        self.events = []                                # this frame's spawns seen: {"ev": "spawn_seen", ...}
        self.stats = {"matched": 0, "two or more points": 0, "no point": 0}

    # ------------------------------------------------------------------ one frame
    def update(self, t, C, records, events, tags=None, drops=None, ui=()) -> list:
        """-> this frame's spawns seen; `points` = the SpawnPoint records. records / events: the mob tracker's
        (records with tentative tracks); tags: the sorted tags' boxes ({"us": [...], "player": [...]}, screen px);
        drops: facts.drops; ui: the UI rectangles (x0, y0, x1, y1) on the screen."""
        self.events = []
        if C is None:                                   # blind: nothing changes
            return self.events
        for m in records:
            if m.id not in self.first and m.seen:
                self.first[m.id] = (m.born_t, m.x, m.y, m.from_node, m.opacity)
        for e in events:
            if e.get("ev") != "mob_new" or e.get("how") != "faded in" or e["id"] not in self.first:
                continue
            idx = self.trace(e["kind"], *self.first[e["id"]])
            if len(idx) == 1:
                p = self.points[idx[0]]
                p.last_spawn_t, p.last_mob = self.first[e["id"]][0], e["id"]
                p.spawns += 1
                self.stats["matched"] += 1
                self.events.append({"ev": "spawn_seen", "t": t, "point": p.index, "id": e["id"], "kind": p.kind})
            else:
                self.stats["two or more points" if idx else "no point"] += 1
        if len(self.first) > len(records):              # a track ended: its first sighting is not needed
            live = {m.id for m in records}
            for i in [i for i in self.first if i not in live]:
                del self.first[i]
        self._in_view(C, records, tags, drops, ui)
        return self.events

    def trace(self, kind: int, t0: float, x: float, y: float, node: int, o: float) -> list:
        """Rule (c): the indices (into `points`) of the points of `kind` that could have put a mob first seen at
        (x, y) over `node` with opacity `o` there in the time it has existed."""
        c, k = self.cfg, self.kinds.get(kind)
        if k is None:
            return []
        reach = k.v * o * c.spawn_fade_s + c.spawn_slack
        out = []
        surf = None
        for i, p in enumerate(self.points):
            if p.kind != kind:
                continue
            if k.fly:
                if np.hypot(p.x - x, p.sy - y) <= reach:
                    out.append(i)
                continue
            if node == NONE or p.node != node or abs(p.x - x) > reach:
                continue
            if surf is None:
                s = float(self.g.surface_y([node], [x])[0])
                surf = s if np.isfinite(s) else p.y
            up = surf - y                               # the feet this far over the node's surface
            if -c.spawn_slack <= up <= (c.spawn_hop + c.spawn_slack if k.jump else c.spawn_slack):
                out.append(i)
        return out

    def _in_view(self, C, records, tags, drops, ui):
        boxes = [tuple(b) for k in ("us", "player") for b in ((tags or {}).get(k) or [])]
        for m in records:
            if m.seen:
                k = self.kinds.get(m.kind)
                if k is not None:
                    boxes.append((m.sx + k.lt[0], m.sy + k.lt[1], m.sx + k.rb[0], m.sy + k.rb[1]))
        for d in drops or []:
            x, y, w, h = d["box"]
            boxes.append((x, y, x + w, y + h))
        boxes += [tuple(r) for r in ui]
        B = np.array(boxes, np.float64).reshape(-1, 4)
        cx, cy = self.cx - C[0], self.cy - C[1]
        on = (cx >= 0) & (cx < SW) & (cy >= 0) & (cy < PLAY_H)
        if len(B) and on.any():
            on &= ~((B[None, :, 0] <= cx[:, None]) & (cx[:, None] < B[None, :, 2]) & (B[None, :, 1] <= cy[:, None])
                    & (cy[:, None] < B[None, :, 3])).any(1)
        for p, v in zip(self.points, on.tolist()):
            p.in_view = v
