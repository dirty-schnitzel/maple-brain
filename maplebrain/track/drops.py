"""The drop tracker (PLAN-tracker.md design 5; docs/state_model.md sections 2-4). The reference is the prototype
tools/perc/track/proto_drops.py (measurement 5): its rules and constants (config.Track, the `drop_` / `bob_` /
`hop_` / `look_` / `reach_` / `from_` fields) are ported, not redesigned. The drop finder (perception/drops.py) is not
changed: its sightings (FrameFacts.drops) are this tracker's input. Nothing here knows the brain.

Per frame, `update(facts, evidence, me, keys, mobs)`: the frame's facts (FrameFacts: the camera, the finder's drop
sightings), the evidence of this frame (track/evidence.py: the kept replay's bitmaps or the fit's tensors), our feet
on the map, our key events since the last frame, the mob tracker's records (track/mobs.py: their deaths) -> the drop
records (track/state.Drop) and this frame's events.

1. SIGHTING -> DROP: same item, the SAME map x, feet y inside the drop's resting band (its foothold's y - 5 .. + 6)
   and where its bob says it is now - a cosine of 5 px with a 2.000 s period, fitted per drop by least squares that
   forget with 8 s (trusted after 40 sightings over 1.5 s with an amplitude of 1.2-4.5 px; a sighting within 1.25 px
   of it); before the fit: within 2 px + 8 px/s of its last y; after we were > 1700 px away while it was unsighted
   (the client drops far things, the bob may restart): any height of its band, the fit learnt again. The cheapest
   pairs first (REST before weak), each sighting and drop once. REST and weak both count as sighted.
2. BIRTH: only from a REST sighting no drop took, 4 px above its foothold or lower, over a foothold -> a TENTATIVE
   drop; CONFIRMED (drop_new; born at its first sighting) when sighted at the 0.25 s mark; a tentative one unsighted
   for 0.1 s is dropped without a trace. Two of one item at one x: a second drop (a sighting the first drop's bob
   does not fit); both sighted in one frame = `twin`.
3. GONE, three ways: (a) THE HOP SEEN - an unclaimed sighting of the item 4-24 px over a drop that just lost its
   sighting (<= 0.07 s), then each next one within 8 px sideways, 0.07 s: gone when it rose 12 px; (b) ITS PLACE SEEN
   WITHOUT IT - a look at its place: its picture (every picture of the item: a meso's 4 frames) at every resting
   height it was sighted at +- 7 px, nearest the bob's first; at every one more than 50 % of the WHOLE picture shows
   the scenery (a pixel under front scenery of its layer is cover, not scenery) for 0.15 s without a break; (c) 130 s
   after its birth. Not sighted and none of these: kept, its cover = the look's answer (out of view / edge / ui /
   scenery / covered). The look is one evidence call for every drop looked at on the frame (the first picture's
   heights for all, then the other pictures of those not there on it): the prototype's first-fit order exactly.
4. HOW IT WENT (drop_gone): "we took it" = gone by (a) or (b) within 1.5 s of its last sighting with our pickup key
   DOWN at some moment from 0.75 s before its last resting frame to 0.02 s after it and our feet within 32 px
   sideways, 12 px above .. 36 px below its foothold then. The key's STATE (pressed in that window, or held through
   it), not its last press: the prototype's "a press in the last 0.75 s" missed a key held longer (PLAN-tracker
   measurement 5). Else "gone in view"; unsighted longer: "found gone"; (c): "130 s old".
5. FROM_MOB, at the drop's confirmation: the death (a mob track's first die pose, from the mob tracker's records; a
   death taken back by a live pose is forgotten) 0.6-1.8 s before its first resting sighting, within 110 px sideways,
   100 px above .. 88 px below its foothold; several: the one whose delay is nearest the usual 1.39 s, then the
   nearest in x. `landed` = its place was on screen 0.1-0.25 s and 0.4-0.6 s before its birth (it landed in view).
A frame without a camera (blind) changes nothing: the records keep their values, `seen` False, cover "blind".
Not ported (the prototype's measurement aids, no rule uses them): the flight followed back, the calib counts.
One difference by construction: the prototype took no front scenery for a placement whose on-screen box crossed the
scene canvas's border; here a pixel outside the canvas is simply not front scenery.
"""
import bisect
import json
import math
import time
from collections import Counter, deque
from pathlib import Path

import numpy as np

from ..config import Track
from .graph import NONE
from .state import Drop

SW, PLAY_H = 1366, 700
MESO = {9000000: "meso bronze", 9000001: "meso gold", 9000002: "meso bundle", 9000003: "meso sack"}
KIND = {"Consume": "use", "Etc": "etc", "Install": "setup"}


class Pictures:
    """The item pictures the look needs, on the CPU: per item its opaque pictures in the finder's order (a meso: one
    per frame), each as its pixels' offsets from the bottom-centre (the drop's feet) and its opaque count; the item's
    name and class. `Pictures.load()` reads assets/mcw/items (gamedata.load_items; weak and cash-only pictures are
    never searched by the finder, so never looked for); `Pictures(masks, meta)` takes {item: [(f, bool mask)]}."""

    def __init__(self, masks: dict, meta: dict | None = None):
        self.meta = meta or {}
        self.cores = {}
        for item, lst in masks.items():
            out = []
            for f, mk in lst:
                h, w = mk.shape
                rr, cc = np.nonzero(mk)
                out.append((int(f), (cc - w // 2).astype(np.int64), (rr - h).astype(np.int64), int(mk.sum())))
            self.cores[int(item)] = out

    @classmethod
    def load(cls, root: Path | None = None) -> "Pictures":
        from .. import gamedata
        it = gamedata.load_items(root)
        masks = {}
        for g, pic in enumerate(it.pics):
            if it.weak[g] or it.cash[g]:
                continue
            masks.setdefault(int(it.item[g]), []).append((int(it.f[g]), np.ascontiguousarray(pic[..., 3] == 255)))
        return cls(masks, it.meta)

    def name(self, item) -> str:
        return (self.meta.get(str(int(item))) or {}).get("name") or str(int(item))

    def cls(self, item) -> str:
        if int(item) in MESO:
            return MESO[int(item)]
        return KIND.get((self.meta.get(str(int(item))) or {}).get("kind"), "equip")


class Fronts:
    """A map's front planes (assets/scene/<map>/layers/front_<L>.png: the tiles / objects drawn OVER the things of
    foothold layer L), bool in canvas px; the canvas's map corner x0, y0. `Fronts.load(map_id)`; `Fronts({}, 0, 0)`:
    none."""

    def __init__(self, planes: dict, x0: int, y0: int):
        self.planes = {int(L): np.asarray(p, bool) for L, p in planes.items()}
        self.x0, self.y0 = int(x0), int(y0)

    @classmethod
    def load(cls, map_id: int, scene_root: Path | None = None) -> "Fronts":
        import cv2
        d = Path(scene_root or Path(__file__).resolve().parents[2] / "assets" / "scene") / str(map_id)
        sc = json.loads((d / "scene.json").read_text(encoding="utf-8"))
        planes = {}
        for L in sc.get("layers") or []:
            p = d / "layers" / f"front_{L}.png"
            if p.exists():
                planes[int(L)] = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)[..., 3] >= 128
        return cls(planes, sc["x0"], sc["y0"])

    def at(self, layer, mx, my) -> np.ndarray | None:
        """bool per map pixel (mx, my arrays): under front scenery of `layer` (None: that layer has no plane)."""
        P = self.planes.get(layer) if layer is not None else None
        if P is None:
            return None
        ax, ay = mx - self.x0, my - self.y0
        ok = (ax >= 0) & (ay >= 0) & (ax < P.shape[1]) & (ay < P.shape[0])
        out = np.zeros(ax.shape, bool)
        out[ok] = P[ay[ok], ax[ok]]
        return out


class _Drop:
    """One drop (the prototype's Drop)."""
    __slots__ = ("id", "item", "x", "yf", "fh", "layer", "node", "born_t", "born_n", "conf", "y", "y_t", "y_lo", "y_hi",
                 "last_t", "last_n", "last_rest_t", "n_rest", "n_weak", "seen", "cover", "unseen_s", "absent", "hop",
                 "hop_from", "sums", "sum_t", "fit", "fit_t0", "n_fit", "far", "from_mob", "n_from", "end", "cov_n",
                 "twin", "first", "seen_last", "lost", "landed", "near", "fronts", "cls")

    def __init__(self, i, item, x, yf, fh, layer, t, n, y):
        self.id, self.item, self.x, self.yf, self.fh, self.layer = i, item, x, yf, fh, layer
        self.node = NONE
        self.born_t, self.born_n, self.conf = t, n, False
        self.y = self.y_lo = self.y_hi = y
        self.y_t = self.last_t = self.last_rest_t = t
        self.last_n = n
        self.n_rest = self.n_weak = 0
        self.seen, self.cover, self.unseen_s, self.absent = True, "none", 0.0, None
        self.hop, self.hop_from = None, None
        self.sums, self.sum_t, self.fit, self.fit_t0, self.n_fit = np.zeros(9), t, None, t, 0
        self.far, self.from_mob, self.n_from, self.end = 0.0, None, 0, None
        self.cov_n, self.twin, self.first, self.seen_last = Counter(), False, [], None
        self.lost, self.landed, self.near, self.fronts, self.cls = None, False, None, None, None

    # the bob: y(t) = c0 + c1 cos(wt) + c2 sin(wt), least squares over this drop's sightings, forgetting with bob_tau
    def learn(self, t, y, c: Track):
        s = self.sums
        s *= math.exp(-(t - self.sum_t) / c.bob_tau)
        self.sum_t = t
        w = 2 * math.pi * t / c.bob_t
        cs, sn = math.cos(w), math.sin(w)
        s += (1.0, cs, sn, cs * cs, cs * sn, sn * sn, y, y * cs, y * sn)
        self.n_fit += 1
        self.fit = None

    def expect(self, t, c: Track):
        """Where the bob puts the feet at t (None: no trusted fit yet)."""
        if self.n_fit < c.bob_min_n or self.sum_t - self.fit_t0 < c.bob_min_s:
            return None
        if self.fit is None:
            s = self.sums
            A = np.array([[s[0], s[1], s[2]], [s[1], s[3], s[4]], [s[2], s[4], s[5]]])
            try:
                self.fit = np.linalg.solve(A, s[6:9])
            except np.linalg.LinAlgError:
                return None
            if not c.bob_amp[0] <= math.hypot(self.fit[1], self.fit[2]) <= c.bob_amp[1]:
                self.fit = False                        # not a bob (yet): don't trust it
        if self.fit is False:
            return None
        w = 2 * math.pi * t / c.bob_t
        return float(self.fit[0] + self.fit[1] * math.cos(w) + self.fit[2] * math.sin(w))


_COVER = {"out": "out of view", "absent": "empty"}


class DropTracker:
    """`pics`: Pictures; `fronts`: Fronts (None: no front scenery); `graph`: the map's track/graph.Graph (the node a
    drop lies on; None: not placed); `pickup`: our pickup key's name (config Keys.pickup); `cfg`: config.Track.
    `keep` True: the tools' diagnostics are kept (`done` = the ended drops, the key's presses, each life's end).
    `deaths` [(t, x, y, mob id)] by t: the mob deaths known so far (from the `mobs` records each frame; a tool may
    fill it with `add_death`)."""

    def __init__(self, pics: Pictures, fronts: Fronts | None = None, graph=None, pickup: str = "z",
                 cfg: Track | None = None, keep: bool = False):
        self.pics, self.fronts, self.g, self.pickup = pics, fronts, graph, pickup
        self.cfg = cfg or Track()
        self.keep = keep
        self.live = {}                                  # (item, x) -> [_Drop] (tentative and confirmed)
        self.done, self.next_id = [], 1
        self.deaths, self.death_t, self._dead = [], [], {}  # the deaths: (t, x, y, id) by t; id -> its entry
        self.down, self.down_t = False, None            # the pickup key: held now, since when
        self.spans = deque()                            # (from, to, our feet): the key down during a frame
        self._pending = []                              # ... its spans on blind frames, waiting for our feet
        self.presses, self.press_me = [], []            # keep: every key-down's time, our feet at its first frame
        self.cams = deque()                             # the cameras of the last 0.7 s: (t, C)
        self.t_prev, self.me_last = None, None
        self.stats = Counter()
        self.looks = 0                                  # drops looked at on the last frame
        self.records: list = []
        self._ev = []

    # ------------------------------------------------------------------ inputs: deaths, our key
    def add_death(self, t, x, y, key):
        i = bisect.bisect_right(self.death_t, t)
        self.deaths.insert(i, (t, x, y, key))
        self.death_t.insert(i, t)

    def _mob_deaths(self, mobs, t):
        """A mob record's first die pose = a death (t, where it was seen, its id); taken back by a live pose
        (track/mobs.py: within 0.2 s) = forgotten (a later die pose of it is a new death)."""
        for m in mobs:
            if m.life == "dying":
                if m.id not in self._dead:
                    e = (t, float(m.x_seen), float(m.y_seen), m.id)
                    self._dead[m.id] = e
                    self.add_death(*e)
            elif m.id in self._dead:
                i = self.deaths.index(self._dead.pop(m.id))
                del self.deaths[i], self.death_t[i]
                self.stats["death taken back"] += 1

    def _key(self, keys, t):
        """Our key events since the last frame -> the stretches of this frame the pickup key was down (pending until a
        frame with a camera gives our feet)."""
        t0 = -math.inf if self.t_prev is None else self.t_prev
        a = t0 if self.down else None
        for e in keys or ():
            k, down, te = (e["key"], e["down"], e["t"]) if isinstance(e, dict) else (e[1], e[2], e[0])
            if k != self.pickup:
                continue
            if down and self.keep:
                self.presses.append(te)
            if down and not self.down:
                self.down, self.down_t, a = True, te, te
            elif not down and self.down:
                self.down = False
                self._pending.append((a, te))
                a = None
        if self.down:
            self._pending.append((a, t))

    # ------------------------------------------------------------------ one frame
    def update(self, facts, evidence, me=None, keys=(), mobs=None, n=None) -> list:
        """-> this frame's events; `records` = the drop records (track/state.Drop), tentative drops included."""
        c = self.cfg
        t, C = facts.t, facts.scene_cam
        self._ev, self.looks = [], 0
        self._key(keys, t)
        self.t_prev = t
        if mobs:
            self._mob_deaths(mobs, t)
        sightings = facts.drops
        if C is None or sightings is None:              # blind: nothing changes
            self.stats["blind"] += 1
            self.records = self._records(t, blind=True)
            return self._ev
        if me is not None:
            self.me_last = (me, t)
        elif self.me_last is not None and t - self.me_last[1] <= c.me_hold_s:
            me = self.me_last[0]                        # our tag is missed on some frames: where we just were
        for a, b in self._pending:                      # where we stood while the pickup key was down
            self.spans.append((a, b, me))
        if self.keep:
            while len(self.press_me) < len(self.presses):
                self.press_me.append(me)
        self._pending = []
        while self.spans and t - self.spans[0][1] > 3.0:
            self.spans.popleft()
        self._pair(t, n, C, sightings, me)
        self.cams.append((t, C))
        while self.cams and t - self.cams[0][0] > 0.7:
            self.cams.popleft()
        self._each(t, n, C, evidence, me)
        self.records = self._records(t)
        return self._ev

    def _pair(self, t, n, C, sightings, me):
        """1-2: sightings -> drops (the cheapest pairs first, one each), then the hops and the births."""
        c = self.cfg
        S = []
        for s in sightings:
            S.append((s["item"], s["feet"][0] + C[0], s["feet"][1] + C[1], s["kind"] == "rest", s))
        pairs = []
        for j, (item, mx, my, rest, s) in enumerate(S):
            for d in self.live.get((item, mx), ()):
                k = self._fits(d, t, my)
                if k is not None:
                    pairs.append((k, not rest, j, d))
        pairs.sort(key=lambda p: (p[0], p[1], p[2]))
        got, used = {}, set()
        for _, _, j, d in pairs:
            if j in used or d.id in got:
                continue
            used.add(j)
            got[d.id] = j
        for lst in self.live.values():
            for d in lst:
                j = got.get(d.id)
                if j is None:
                    d.seen = False
                    continue
                item, mx, my, rest, s = S[j]
                if d.far > c.bob_far:                   # back from far away: its bob is learnt again
                    d.sums[:], d.n_fit, d.fit, d.fit_t0, d.sum_t = 0.0, 0, None, t, t
                    self.stats["bob redone"] += 1
                d.far = 0.0
                d.seen, d.y, d.y_t, d.last_t, d.last_n, d.unseen_s, d.absent = True, my, t, t, n, 0.0, None
                d.y_lo, d.y_hi = min(d.y_lo, my), max(d.y_hi, my)
                d.hop, d.seen_last = None, me
                d.learn(t, my, c)
                if self.keep and t - d.born_t <= 2.0:
                    d.first.append((t, my))
                if rest:
                    d.n_rest, d.last_rest_t = d.n_rest + 1, t
                    d.cover = "none" if s["seen"] >= 0.95 * s["n_op"] else "drop" if s["under"] else \
                        "scenery" if s["front"] else "partly"
                else:
                    d.n_weak += 1
                    d.cover = "partly"
            if len(lst) > 1:
                both = [x for x in lst if x.conf and x.seen]
                if len(both) > 1:                       # two of one item at one x, both sighted this frame
                    for x in both:
                        x.twin = True
        # the sightings no drop took: a hop of a drop that just lost its sighting, else (REST) a tentative drop
        lost = [d for lst in self.live.values() for d in lst if d.conf and not d.seen
                and (d.hop is not None or t - d.last_t <= c.hop_gap)]
        for j, (item, mx, my, rest, s) in enumerate(S):
            if j in used:
                continue
            hopped = False
            for d in lost:
                if d.item != item:
                    continue
                if d.hop is None:
                    if abs(mx - d.x) <= c.hop_dx and 4 <= d.y - my <= c.hop_up:
                        d.hop, d.hop_from, hopped = [(t, mx, my)], d.y, True
                else:
                    ht, hx, hy = d.hop[-1]
                    if 0 < t - ht <= c.hop_gap and abs(mx - hx) <= c.hop_dx and -2 <= hy - my <= c.hop_up:
                        d.hop.append((t, mx, my))
                        hopped = True
                if hopped:
                    break
            if hopped:
                continue
            if rest and s["dy"] is not None and s["dy"] >= c.drop_new_lo and s["fh"] is not None:
                d = _Drop(self.next_id, item, mx, my - s["dy"], s["fh"], s["layer"], t, n, my)
                self.next_id += 1
                d.n_rest, d.seen_last = 1, me
                d.learn(t, my, c)
                if self.keep:
                    d.first.append((t, my))
                L, T, B = c.landed_px                   # was its place on screen before it lay there?
                d.landed = all(any(a <= t - tc <= b and L <= mx - cc[0] <= SW - L and T <= d.yf - cc[1] <= PLAY_H - B
                                   for tc, cc in self.cams) for a, b in c.landed_s)
                self.live.setdefault((item, mx), []).append(d)

    def _fits(self, d, t, my):
        """The cost of sighting y `my` for drop d at t (None: not this drop)."""
        c = self.cfg
        if not d.yf + c.drop_band[0] <= my <= d.yf + c.drop_band[1]:
            return None
        if d.far > c.bob_far:                           # its bob may have begun anew: any height of the band
            return 0.5 + 0.01 * abs(my - d.y)
        e = d.expect(t, c)
        if e is not None:
            k = abs(my - e)
            return k if k <= c.bob_tol else None
        k = abs(my - d.y)
        return k if k <= c.drop_y_step + c.drop_y_rate * (t - d.y_t) else None

    def _each(self, t, n, C, evidence, me):
        """3-4: every drop - confirm, forget, 130 s, the hop, the look (one evidence call for all looked at)."""
        c = self.cfg
        look = []
        for d in [x for lst in self.live.values() for x in lst]:
            if not d.conf:
                if d.seen and t - d.born_t >= c.drop_confirm_s:
                    d.conf = True
                    d.from_mob, d.n_from = self._from_mob(d)
                    if self.g is not None:
                        d.node = int(self.g.nearest(np.array([float(d.x)]), np.array([float(d.yf)]), c.stand_tol)[0][0])
                    self.stats["confirmed"] += 1
                    self._ev.append({"ev": "drop_new", "t": t, "id": d.id, "item": d.item, "from_mob": d.from_mob,
                                     "born_t": d.born_t})
                elif not d.seen and t - d.last_t > c.drop_tentative_s:
                    self._remove(d)
                    self.stats["tentative dropped"] += 1
                continue
            if t - d.born_t >= c.drop_life_s:
                self._gone(d, n, t, "130 s old" if not d.seen else "130 s old (still seen)")
                continue
            if d.seen:
                d.lost = None
                continue
            d.unseen_s = t - d.last_t
            if d.lost is None:
                d.lost = (t, n)                         # the first frame without it
            if me is not None:
                d.far = max(d.far, math.hypot(me[0] - d.x, me[1] - d.yf))
            if d.hop is not None:
                if d.hop_from - d.hop[-1][2] >= c.hop_gone:
                    self._gone(d, n, t, self._cause(d, t))
                    continue
                if t - d.hop[-1][0] > c.hop_gap:
                    d.hop = None                        # it did not go on: no hop
            sx, sy = d.x - C[0], d.yf - C[1]
            o = c.look_out
            if sx < -o[0] or sx > SW + o[0] or sy < -o[1] or sy > PLAY_H + o[2]:
                self._seen_as(d, "out", n, t)
                continue
            look.append(d)
        if look:
            for d, v in zip(look, self._look(look, C, evidence, t)):
                self._seen_as(d, v, n, t)

    def _seen_as(self, d, v, n, t):
        """The look's answer for an unsighted drop."""
        d.cover = _COVER.get(v, v)
        d.cov_n[v] += 1
        if v == "absent":
            if d.absent is None:
                d.absent = (t, n)                       # the first frame its place showed without it
            if t - d.absent[0] >= self.cfg.absent_s:
                self._gone(d, n, t, self._cause(d, t))
        else:
            d.absent = None

    # ------------------------------------------------------------------ the look
    def _front_cores(self, d):
        """Per picture of the item, per height of its band: the offsets of its pixels under front scenery of its
        layer (None: none at any height) - map-fixed, made once per drop."""
        c = self.cfg
        out = []
        for _f, dx, dy, _n in self.pics.cores[d.item]:
            per = {}
            if self.fronts is not None:
                for y in range(d.yf + c.drop_band[0], d.yf + c.drop_band[1] + 1):
                    fr = self.fronts.at(d.layer, d.x + dx, y + dy)
                    if fr is not None and fr.any():
                        per[y] = (dx[fr], dy[fr])
            out.append(per or None)
        return out

    def _look(self, drops, C, evidence, t) -> list:
        """Is each drop's place seen without it? -> per drop: 'out' (off screen), 'edge' (too little of it on screen),
        'ui' (under the UI / unknown scenery), 'scenery' (behind front scenery), 'covered' (something is drawn
        there), 'absent' (the scenery shows where it would be, at every resting height and picture). The prototype's
        order: per picture, per height nearest the bob's first; the first placement where at most look_abs of the
        whole picture shows the scenery decides. Its first picture for every drop, then the rest where needed."""
        c = self.cfg
        if not evidence.ready:
            return ["ui"] * len(drops)
        C0, C1 = int(C[0]), int(C[1])
        self.looks = len(drops)
        jobs = []
        for d in drops:
            e = d.expect(t, c)
            y0 = int(round(e)) if e is not None else d.y
            lo, hi = d.yf + c.drop_band[0], d.yf + c.drop_band[1]
            ys = sorted(range(max(lo + 1, d.y_hi - c.look_dy), min(hi - 1, d.y_lo + c.look_dy) + 1),
                        key=lambda y: abs(y - y0))
            if d.fronts is None:
                d.fronts = self._front_cores(d)
            jobs.append({"d": d, "ys": np.array(ys, np.int64), "rows": [], "best": None, "any_on": False})
        cores = [self.pics.cores[j["d"].item] for j in jobs]
        todo = list(range(len(jobs)))
        k = 0
        while todo:                                     # stage k: picture k of the drops still undecided
            groups, back = [], []
            for i in todo:
                j, (f, dx, dy, n_op) = jobs[i], cores[i][k]
                d, ys = j["d"], j["ys"]
                groups.append((np.full(len(ys), d.x - C0, np.int64), ys - C1, dx, dy))
                fr = d.fronts[k]
                fg = []
                if fr is not None:
                    for q, y in enumerate(ys.tolist()):
                        if y in fr:
                            groups.append((np.array([d.x - C0], np.int64), np.array([y - C1], np.int64), *fr[y]))
                            fg.append((q, len(groups) - 1))
                back.append((i, len(groups) - 1 - len(fg), fg, n_op))
            res = evidence.count(groups)
            nxt = []
            for i, g0, fg, n_op in back:
                j = jobs[i]
                sh, n_on, wo = (np.asarray(a, np.int64) for a in res[g0])
                sh_fr = np.zeros(len(sh), np.int64)
                for q, gi in fg:
                    sh_fr[q] = int(res[gi][0][0])
                n_abs = sh - sh_fr
                ok = np.flatnonzero(n_abs <= c.look_abs * n_op)
                if len(ok):
                    q = int(ok[0])
                    j["any_on"] = j["any_on"] or bool((n_on[:q + 1] > 0).any())
                    n_unk = n_on[q] - wo[q]
                    j["best"] = (n_op, int(n_on[q]), int(n_abs[q]), int(sh_fr[q]), int(n_unk))
                    continue
                j["any_on"] = j["any_on"] or bool((n_on > 0).any())
                if k + 1 < len(cores[i]):
                    nxt.append(i)
            todo, k = nxt, k + 1
        out = []
        for j in jobs:
            if not j["any_on"]:
                out.append("out")
                continue
            if j["best"] is None:
                out.append("absent")
                continue
            n_op, n_on, n_abs, n_front, n_unk = j["best"]
            out.append("edge" if n_on < c.look_edge * n_op else "ui" if n_unk >= c.look_ui * n_op
                       else "scenery" if n_front >= c.look_front * n_op else "covered")
        return out

    # ------------------------------------------------------------------ how it went, which mob
    def _from_mob(self, d):
        """-> (the mob id or None, how many deaths fit the rule)."""
        c = self.cfg
        i0 = bisect.bisect_left(self.death_t, d.born_t - c.from_s[1] - 0.001)
        i1 = bisect.bisect_right(self.death_t, d.born_t - c.from_s[0] + 0.001)
        fit = []
        for dt, x, y, key in self.deaths[i0:i1]:
            s = round(d.born_t - dt, 4)                 # (the prototype's delays: to 0.1 ms)
            if c.from_s[0] <= s <= c.from_s[1] and abs(x - d.x) <= c.from_dx and -c.from_up <= y - d.yf <= c.from_down:
                fit.append((round(abs(s - c.from_mid_s), 1), abs(x - d.x), key))
        if self.keep:                                   # the tools: every death in a generous window
            j0 = bisect.bisect_left(self.death_t, d.born_t - 5.0)
            j1 = bisect.bisect_right(self.death_t, d.born_t + 0.5)
            d.near = [(round(d.born_t - dt, 4), x - d.x, y - d.yf, key) for dt, x, y, key in self.deaths[j0:j1]
                      if abs(x - d.x) <= 300 and abs(y - d.yf) <= 200]
        if not fit:
            return None, 0
        return min(fit, key=lambda m: (m[0], m[1]))[2], len(fit)

    def _taken(self, d) -> tuple | None:
        """Our pickup key down at some moment of [last resting frame - pick_s, + pick_after_s] with our feet within
        reach then -> that stretch (from, to, our feet), else None."""
        c = self.cfg
        lo, hi = d.last_t - c.pick_s, d.last_t + c.pick_after_s
        for a, b, me in self.spans:
            if a <= hi and b >= lo and me is not None and abs(me[0] - d.x) <= c.reach_x \
                    and -c.reach_up <= me[1] - d.yf <= c.reach_down:
                return a, b, me
        return None

    def _cause(self, d, t) -> str:
        """How a drop seen leaving / whose place shows without it went."""
        if t - d.last_t > self.cfg.in_view_s:
            return "found gone"
        return "we took it" if self._taken(d) is not None else "gone in view"

    def _remove(self, d):
        lst = self.live[(d.item, d.x)]
        lst.remove(d)
        if not lst:
            del self.live[(d.item, d.x)]

    def _gone(self, d, n, t, how):
        if self.keep:
            z, zm = self.presses, self.press_me
            i = bisect.bisect_right(z, d.last_t + 0.02) - 1
            lo = bisect.bisect_left(z, d.last_t - 1.5)
            hi = min(bisect.bisect_right(z, d.last_t + 0.02), len(zm))
            tk = self._taken(d)
            d.end = {"n": n, "t": t, "how": how, "last_n": d.last_n, "last_t": d.last_t,
                     "unseen_s": round(t - d.last_t, 4), "hop": 0 if d.hop is None else len(d.hop),
                     "age": round(t - d.born_t, 3), "me": d.seen_last,
                     "absent_t": None if d.absent is None else d.absent[0],
                     "absent_n": None if d.absent is None else d.absent[1],
                     "lost_t": None if d.lost is None else d.lost[0], "lost_n": None if d.lost is None else d.lost[1],
                     "hop_dx": None if not d.hop else d.hop[-1][1] - d.x,
                     "z_before": None if i < 0 else round(d.last_t - z[i], 4),
                     "z_after": None if i + 1 >= len(z) else round(z[i + 1] - d.last_t, 4),
                     "z": [(round(d.last_t - z[k], 4), None if zm[k] is None else zm[k][0] - d.x,
                            None if zm[k] is None else zm[k][1] - d.yf) for k in range(lo, hi)],
                     "key": None if tk is None else (round(d.last_t - tk[0], 4), round(d.last_t - tk[1], 4),
                                                     tk[2][0] - d.x, tk[2][1] - d.yf)}
        self._remove(d)
        if self.keep:
            self.done.append(d)
        self.stats["gone: " + how] += 1
        self._ev.append({"ev": "drop_gone", "t": t, "id": d.id, "item": d.item, "how": how})

    def finish(self, n, t):
        """The tools: every confirmed drop ends with the capture."""
        for d in [x for lst in self.live.values() for x in lst if x.conf]:
            self._gone(d, n, t, "capture ended")

    # ------------------------------------------------------------------ the records
    def _records(self, t: float, blind: bool = False) -> list:
        out = []
        for lst in self.live.values():
            for d in lst:
                if d.cls is None:
                    d.cls = self.pics.cls(d.item)
                out.append(Drop(d.id, d.item, d.cls, d.conf, d.x, d.yf, d.fh, d.layer, d.node,
                                d.born_t, d.landed, d.from_mob, d.seen and not blind, "blind" if blind else d.cover,
                                round(t - d.last_t, 4)))
        return out

    def drops(self) -> list:
        """The drops of the state: the confirmed records."""
        return [r for r in self.records if r.confirmed]
