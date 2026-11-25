"""Tracker plan, Part 2 (an experiment, nothing of the product): a PROTOTYPE DROP TRACKER that runs from the kept
replay only (dump.py: the finder's per-frame sightings + the two bitmaps), no GPU, no frames - and the numbers the
plan needs of it. The by-eye sheets alone read frames.

    python tools/perc/track/proto_drops.py run CAP [CAP ...] | --sound     track, keep the result (work/track-plan/drops)
    python tools/perc/track/proto_drops.py numbers CAP [CAP ...] | --sound  the numbers 1-6 of the kept results
    python tools/perc/track/proto_drops.py sheets CAP [--n 20] [--seed 1]   by-eye sheets: random births and ends
    python tools/perc/track/proto_drops.py calib CAP [--every 10]           the bitmap look against the finder's counts

THE RULES (each constant below says what measured it; the 30-minute capture 20261121_000219_2#0 unless said):
  sighting -> drop   same item, the SAME map x, feet y inside the drop's resting band (its foothold's y - 5 .. + 6:
                     every resting sighting of 11 items lay in -4 .. +5) and where its bob says it is now: the bob
                     is a cosine of 5 px, period 2.000 s (147 drops fitted, rounding noise 0.29 px), so a drop's y is
                     known from its own sightings (a least-squares fit that forgets with 8 s); before the fit exists:
                     within 2 px + 8 px/s of its last y (frame to frame the y moved 0-1 px on 99.99 %). REST and
                     weak sightings both count as "seen" (weak at a known drop = it is partly covered).
  birth              only from a REST sighting no drop takes -> a TENTATIVE drop; CONFIRMED (drop_new, born at its
                     first sighting) when it was sighted over 0.25 s; a tentative one unsighted for 0.1 s is dropped
                     without a trace (a flying meso passing a foothold's height, a pickup hop's first frame).
  two at one x       two sightings of one item at one x in one frame, or a sighting the first drop's bob does not
                     fit, make a second drop there (a twin: two kills at one platform end).
  gone               (a) LEAVING SEEN: the frame after its last resting sighting shows the item 4-24 px up, then
                     higher: the pickup hop (it rises ~8 px a game frame) - gone when it rose 12 px;
                     (b) PLACE SEEN WITHOUT IT: a look at its place from the two bitmaps - its picture at every
                     resting height (x every meso frame): gone when at every one more than LOOK_ABS of the picture's
                     pixels show the scenery (front scenery of its layer = cover, not scenery);
                     (c) 130 s after its birth.
                     Not seen, and not (a) / (b): kept (covered, at the screen's edge, under the UI, out of view).
  how it went        "we took it" = gone in view (a) / (b) with our pickup key down at most Z_FIT_S before its last
                     resting frame and our feet within REACH of it; else "gone in view" (seen <= IN_VIEW_S ago),
                     "found gone" (its place came back without it), "130 s old", "capture ended".
  from_mob           the death (a chain's first die pose) BORN_LO..BORN_HI s before the drop's first resting
                     sighting, within MOB_DX px of its x on its level (MOB_DY); several: the nearest in x.
Blind frames (no camera) change nothing.
"""
import argparse
import bisect
import json
import math
import pickle
import sys
import time
import zlib
from collections import Counter, deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
import dump  # noqa: E402
import load  # noqa: E402

PLAY_H, SW = dump.PLAY_H, dump.SW
PICK_KEY = "z"

# ---- the rules' constants
BAND_LO, BAND_HI = -5, 6        # resting feet y - foothold y (measured -4 .. +5, 1 px of slack each side)
NEW_LO = -4                     # a REST sighting above this is no birth (the hop's first frame reads dy -7 / -6)
Y_STEP, Y_RATE = 2.0, 8.0       # no bob fit yet: |y - last y| <= Y_STEP + Y_RATE * seconds since
BOB_T = 2.0                     # the bob's period, s
BOB_TAU = 8.0                   # the fit forgets with this time constant, s
BOB_MIN_N, BOB_MIN_S = 40, 1.5  # sightings / seconds before the fit is trusted (3/4 of a period)
BOB_TOL = 1.25                  # px a sighting may be off the fitted bob (830,167 sightings: p99 0.7, p99.99 1.0)
BOB_FAR = 1700                  # px: unsighted with us farther away than this, the drop's bob may have begun anew
                                # (650 gaps in its sightings: the phase held on 531 of 531 with us always nearer,
                                # restarted on 30 of 31 with us > 2400 px away, mixed between: the client drops
                                # far things and gets them again) -> any height of its band is taken, the fit redone
T_CONFIRM = 0.25                # s of sightings before a tentative drop is a drop
T_TENT = 0.10                   # a tentative drop unsighted this long is forgotten
HOP_GAP = 0.07                  # s between hop sightings (a game frame is ~33 ms)
HOP_DX, HOP_UP = 8, 24          # px a hop sighting may be from the last one (sideways / up)
HOP_GONE = 12                   # px risen = it left
LOOK_ABS = 0.50                 # the share of the WHOLE picture showing scenery above which the drop is not there.
                                # `calib`, 267,119 REST sightings of the 13 sound captures: a drop that IS there
                                # shows scenery on p50 0.7 % / p99 9.5 % of its picture (its own pixels that have
                                # the scenery's colour), at most 35.4 % (a Bubble on one light spot) and 43.1 % (a
                                # meso's 5 px edge-on frame on a dark map); every other picture <= 17.3 %
T_ABSENT = 0.15                 # s the look must say "not there" without a break (the edge-on frame shows ~0.08 s
                                # a turn: a wide frame follows it)
LIFE_MAX = 130.0                # s (the user's rule)
IN_VIEW_S = 1.5                 # gone this soon after its last sighting = "in view"
Z_FIT_S = 0.75                  # the pickup key went down at most this long before the drop's last resting frame
                                # (185 pickups whose hop was seen: p50 0.11, p99 0.54, max 0.62 s - the server's answer)
REACH_X = 32                    # px: our feet to the drop WHEN THE KEY WENT DOWN (the same 185, the nearest press of
REACH_UP, REACH_DOWN = 12, 36   # the window: |dx| p50 6, p99 21, max 25; our feet - its foothold -8 .. +33, 181 of
                                # them -1 .. +2). When the drop LEAVES we are up to 92 px away, 60 px up: we walk on
BORN_LO, BORN_HI = 0.6, 1.8     # s: die pose -> first resting sighting (277 drops with one death in a wide window:
BORN_MID = 1.39                 # p5 1.09, p50 1.39, p95 1.54; 268 inside 0.6-1.8, the other 9 over 2 s = not theirs)
MOB_DX = 110                    # px: landing x - death x (the same 277: p1 -85, p99 +96, |max| 107)
MOB_UP, MOB_DOWN = 100, 88      # px: the death above the drop's foothold (a mob killed in the air: p1 -69) / below
                                # it (the drop lands on the foothold under the point 85 px ABOVE the mob,
                                # docs/game_rules.md H2: 27 of the 277 lay 60-88 px above their mob)
FLY_S = 1.6                     # s of unclaimed sightings kept to follow a new drop's flight back


def out_root() -> Path:
    from maplebrain.config import CORPUS
    p = Path(CORPUS) / "work" / "track-plan" / "drops"
    p.mkdir(parents=True, exist_ok=True)
    return p


def res_path(cap) -> Path:
    return out_root() / f"lives_{str(cap).replace('#', '_')}.pkl"


# ------------------------------------------------------------------ what the look needs: pictures, front planes
class Pictures:
    """The item pictures on the CPU: per item its opaque masks (a meso: one per frame), name, class."""
    MESO = {9000000: "meso bronze", 9000001: "meso gold", 9000002: "meso bundle", 9000003: "meso sack"}
    KIND = {"Consume": "use", "Etc": "etc", "Install": "setup"}

    def __init__(self):
        from maplebrain import gamedata
        it = gamedata.load_items()
        self.meta, self.masks = it.meta, {}
        for g, pic in enumerate(it.pics):
            if it.weak[g] or it.cash[g]:
                continue
            mk = np.ascontiguousarray(pic[..., 3] == 255)
            self.masks.setdefault(int(it.item[g]), []).append((int(it.f[g]), mk, int(mk.sum())))

    def name(self, item) -> str:
        return (self.meta.get(str(int(item))) or {}).get("name") or str(int(item))

    def cls(self, item) -> str:
        if int(item) in self.MESO:
            return self.MESO[int(item)]
        return self.KIND.get((self.meta.get(str(int(item))) or {}).get("kind"), "equip")


class Fronts:
    """The map's front planes from assets/scene (the tiles / objects drawn OVER a foothold layer's things)."""

    def __init__(self, map_id):
        import cv2
        d = ROOT / "assets" / "scene" / str(map_id)
        sc = json.loads((d / "scene.json").read_text(encoding="utf-8"))
        self.x0, self.y0, self.planes = sc["x0"], sc["y0"], {}
        for L in sc.get("layers") or []:
            p = d / "layers" / f"front_{L}.png"
            if p.exists():
                self.planes[int(L)] = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)[..., 3] >= 128

    def crop(self, layer, mx, my, w, h):
        P = self.planes.get(layer)
        if P is None:
            return None
        ax, ay = mx - self.x0, my - self.y0
        if ax < 0 or ay < 0 or ay + h > P.shape[0] or ax + w > P.shape[1]:
            return None
        return P[ay:ay + h, ax:ax + w]


class Bits:
    """One frame's two bitmaps, unpacked on first use (most frames need no look)."""
    __slots__ = ("packed", "_s", "_w", "ms")

    def __init__(self, packed):
        self.packed, self._s, self._w, self.ms = packed, None, None, 0.0

    def get(self):
        if self._s is None:
            a = time.perf_counter()
            self._s, self._w = dump.bits(self.packed[1]), dump.bits(self.packed[2])
            self.ms = 1000 * (time.perf_counter() - a)
        return self._s, self._w


def counts(shows, world, fronts, C, mask, layer, mx, my):
    """The picture `mask` with its bottom-centre at map (mx, my): (px on screen, showing scenery, under front
    scenery, drawn over, not judgeable = UI / unknown scenery)."""
    h, w = mask.shape
    x, y = mx - C[0] - w // 2, my - C[1] - h
    x0, y0, x1, y1 = max(0, x), max(0, y), min(SW, x + w), min(PLAY_H, y + h)
    if x1 <= x0 or y1 <= y0:
        return 0, 0, 0, 0, 0
    mk = mask[y0 - y:y1 - y, x0 - x:x1 - x]
    sh, wo = shows[y0:y1, x0:x1], world[y0:y1, x0:x1]
    n_on = int(np.count_nonzero(mk))
    fr = fronts.crop(layer, x0 + C[0], y0 + C[1], x1 - x0, y1 - y0) if fronts is not None else None
    if fr is not None and fr.any():
        n_front = int(np.count_nonzero(mk & fr & sh))
        n_abs = int(np.count_nonzero(mk & sh & ~fr))
    else:
        n_front, n_abs = 0, int(np.count_nonzero(mk & sh))
    n_unk = int(np.count_nonzero(mk & ~wo))
    return n_on, n_abs, n_front, n_on - n_abs - n_front - n_unk, n_unk


# ------------------------------------------------------------------ the tracker
class Drop:
    __slots__ = ("id", "item", "x", "yf", "fh", "layer", "born_t", "born_n", "conf", "y", "y_t", "y_lo", "y_hi",
                 "last_t", "last_n", "last_rest_t", "n_rest", "n_weak", "seen", "cover", "unseen_s", "absent",
                 "hop", "hop_from", "sums", "sum_t", "fit", "fit_t0", "n_fit", "near", "fly", "from_mob", "end",
                 "cov_n", "twin", "first_f", "first", "seen_last", "lost", "born_view", "far")

    def __init__(self, i, item, x, yf, fh, layer, t, n, y):
        self.id, self.item, self.x, self.yf, self.fh, self.layer = i, item, x, yf, fh, layer
        self.born_t, self.born_n, self.conf = t, n, False
        self.y = self.y_lo = self.y_hi = y
        self.y_t = self.last_t = self.last_rest_t = t
        self.last_n = n
        self.n_rest = self.n_weak = 0
        self.seen, self.cover, self.unseen_s, self.absent = True, "none", 0.0, None
        self.hop, self.hop_from = None, None
        self.sums, self.sum_t, self.fit, self.fit_t0, self.n_fit = np.zeros(9), t, None, t, 0
        self.near, self.fly, self.from_mob, self.end = [], None, None, None
        self.cov_n, self.twin, self.first_f, self.first, self.seen_last = Counter(), False, None, [], None
        self.lost, self.born_view, self.far = None, False, 0.0

    # the bob: y(t) = c0 + c1 cos(wt) + c2 sin(wt), least squares over this drop's sightings, forgetting with BOB_TAU
    def learn(self, t, y):
        s = self.sums
        s *= math.exp(-(t - self.sum_t) / BOB_TAU)
        self.sum_t = t
        w = 2 * math.pi * t / BOB_T
        c, d = math.cos(w), math.sin(w)
        s += (1.0, c, d, c * c, c * d, d * d, y, y * c, y * d)
        self.n_fit += 1
        self.fit = None

    def expect(self, t):
        """Where the bob puts the feet at t (None: no trusted fit yet)."""
        if self.n_fit < BOB_MIN_N or self.sum_t - self.fit_t0 < BOB_MIN_S:
            return None
        if self.fit is None:
            s = self.sums
            A = np.array([[s[0], s[1], s[2]], [s[1], s[3], s[4]], [s[2], s[4], s[5]]])
            try:
                self.fit = np.linalg.solve(A, s[6:9])
            except np.linalg.LinAlgError:
                return None
            if not 1.2 <= math.hypot(self.fit[1], self.fit[2]) <= 4.5:      # not a bob (yet): don't trust it
                self.fit = False
        if self.fit is False:
            return None
        w = 2 * math.pi * t / BOB_T
        return float(self.fit[0] + self.fit[1] * math.cos(w) + self.fit[2] * math.sin(w))


class DropTracker:
    """step(n, t, C, sightings, me, bits) once a frame -> the events of that frame. `deaths`: [(t, x, y, key)] of
    the mobs' deaths known so far (here: the truth chains' first die poses, sorted by t); `z_down`: the times our
    pickup key went down (sorted)."""

    def __init__(self, pics: Pictures, fronts: Fronts | None, deaths=(), z_down=(), look_abs=LOOK_ABS, use_bob=True,
                 use_hop=True, t_absent=T_ABSENT):
        self.pics, self.fronts = pics, fronts
        self.deaths, self.death_t = list(deaths), [d[0] for d in deaths]
        self.z, self.z_me = list(z_down), []
        self.look_abs, self.use_bob, self.use_hop, self.t_absent = look_abs, use_bob, use_hop, t_absent
        self.live = {}                              # (item, x) -> [Drop] (tentative and confirmed)
        self.done, self.events, self.next_id = [], [], 1
        self.recent = deque()                       # unclaimed sightings of the last FLY_S s: (t, n, item, mx, my)
        self.t_prev, self.me_last = None, None
        self.cams = deque()                         # the cameras of the last 0.7 s: (t, C)
        self.stats = Counter()
        self.look_ms = 0.0
        self.n_looks = 0
        self.eps = []                               # calib: (item, n_on, n_abs) at REST-sighted places
        self.bob_err = Counter()                    # |sighting y - fitted bob| in 0.1 px, every matched sighting

    # ---- helpers
    def drops(self, conf=True):
        return [d for lst in self.live.values() for d in lst if d.conf or not conf]

    def _band(self, d):
        lo, hi = d.yf + BAND_LO, d.yf + BAND_HI
        return lo, hi

    def _fits(self, d, t, my):
        """The cost of sighting y `my` for drop d at t (None: not this drop)."""
        lo, hi = self._band(d)
        if not lo <= my <= hi:
            return None
        if d.far > BOB_FAR:                                 # its bob may have begun anew: any height of the band
            return 0.5 + 0.01 * abs(my - d.y)
        e = d.expect(t) if self.use_bob else None
        if e is not None:
            c = abs(my - e)
            return c if c <= BOB_TOL else None
        c = abs(my - d.y)
        return c if c <= Y_STEP + Y_RATE * (t - d.y_t) else None

    def _look(self, d, C, bits, t):
        """Is the drop's place seen without it? -> 'out' (off screen), 'edge' (too little of it on screen),
        'ui' (under the UI / unknown scenery), 'scenery' (behind front scenery), 'covered' (something is drawn
        there), 'absent' (the scenery shows where it would be, at every resting height and frame)."""
        lo, hi = self._band(d)
        sx, sy = d.x - C[0], d.yf - C[1]
        if sx < -20 or sx > SW + 20 or sy < -8 or sy > PLAY_H + 40:
            return "out"
        shows, world = bits.get()                           # (the unpacking is the replay's, not the look's)
        a = time.perf_counter()
        self.n_looks_frame += 1
        e = d.expect(t) if self.use_bob else None
        y0 = int(round(e)) if e is not None else d.y
        ys = sorted(range(max(lo + 1, d.y_hi - 7), min(hi - 1, d.y_lo + 7) + 1), key=lambda y: abs(y - y0))
        best, any_on = None, False
        for f, mask, n_op in self.pics.masks[d.item]:
            for y in ys:
                n_on, n_abs, n_front, n_cov, n_unk = counts(shows, world, self.fronts, C, mask, d.layer, d.x, y)
                any_on = any_on or n_on > 0
                # it may be there unless more than LOOK_ABS of the WHOLE picture shows scenery: a drop that is
                # there shows scenery on at most its own scenery-coloured pixels (calib), however little of it is
                # on screen / not under the UI. (Against the on-screen part, a meso's 5 px edge-on frame and a
                # Bubble half past the screen's side were 4 false "gone" in 4 minutes.)
                if n_abs <= self.look_abs * n_op:
                    best = (n_op, n_on, n_abs, n_front, n_cov, n_unk)
                    break
            if best is not None:
                break
        self.look_ms += 1000 * (time.perf_counter() - a)
        self.n_looks += 1
        if not any_on:
            return "out"
        if best is None:
            return "absent"
        n_op, n_on, n_abs, n_front, n_cov, n_unk = best
        if n_on < 0.7 * n_op:
            return "edge"
        if n_unk >= 0.3 * n_op:
            return "ui"
        if n_front >= 0.3 * n_op:
            return "scenery"
        return "covered"

    def _mobs_near(self, d):
        """The deaths in a generous window before the drop's first sighting (the numbers pick the window)."""
        i0 = bisect.bisect_left(self.death_t, d.born_t - 5.0)
        i1 = bisect.bisect_right(self.death_t, d.born_t + 0.5)
        out = []
        for dt, x, y, key in self.deaths[i0:i1]:
            if abs(x - d.x) <= 300 and abs(y - d.yf) <= 200:
                out.append((round(d.born_t - dt, 4), x - d.x, y - d.yf, key))
        return out

    @staticmethod
    def pick_mob(near, fly=None):
        """from_mob by the rule: (key or None, how many deaths fit). Several: the one whose delay is the usual."""
        c = [m for m in near if BORN_LO <= m[0] <= BORN_HI and abs(m[1]) <= MOB_DX and -MOB_UP <= m[2] <= MOB_DOWN]
        if not c:
            return None, 0
        return min(c, key=lambda m: (round(abs(m[0] - BORN_MID), 1), abs(m[1])))[3], len(c)

    def _fly_back(self, d):
        """Follow the unclaimed sightings of the item back from the drop's first resting sighting: its flight in.
        -> (t of the first one, its x, its y, how many) or None."""
        ct, cx, cy, k, first = d.born_t, d.x, d.y, 0, None
        gap = 0.20 if d.item >= 9000000 else 0.40           # items spin in flight: exact only when upright
        for t, n, item, mx, my in reversed(self.recent):
            if item != d.item or t >= ct:
                continue
            dt = ct - t
            if dt > gap:
                break
            if abs(mx - cx) <= 4 + 220 * dt and abs(my - cy) <= 8 + 750 * dt:
                ct, cx, cy, k, first = t, mx, my, k + 1, (t, mx, my)
        return None if first is None else (first[0], first[1], first[2], k)

    def _presses(self, d, back):
        """Our pickup key's presses from `back` s before the drop's last resting frame to it: [(s before, our feet
        then - the drop: dx, dy (None: our place was not known))]."""
        lo = bisect.bisect_left(self.z, d.last_t - back)
        hi = min(bisect.bisect_right(self.z, d.last_t + 0.02), len(self.z_me))
        out = []
        for i in range(lo, hi):
            m = self.z_me[i]
            out.append((round(d.last_t - self.z[i], 4), None if m is None else m[0] - d.x,
                        None if m is None else m[1] - d.yf))
        return out

    def _gone(self, d, n, t, how, me):
        i = bisect.bisect_right(self.z, d.last_t + 0.02) - 1
        d.end = {"n": n, "t": t, "how": how, "last_n": d.last_n, "last_t": d.last_t, "unseen_s": round(t - d.last_t, 4),
                 "hop": 0 if d.hop is None else len(d.hop), "age": round(t - d.born_t, 3), "me": d.seen_last,
                 "absent_t": None if d.absent is None else d.absent[0],
                 "absent_n": None if d.absent is None else d.absent[1],
                 "lost_t": None if d.lost is None else d.lost[0], "lost_n": None if d.lost is None else d.lost[1],
                 "hop_dx": None if not d.hop else d.hop[-1][1] - d.x,
                 "z_before": None if i < 0 else round(d.last_t - self.z[i], 4),
                 "z_after": None if i + 1 >= len(self.z) else round(self.z[i + 1] - d.last_t, 4),
                 "z": self._presses(d, 1.5)}
        self.live[(d.item, d.x)].remove(d)
        if not self.live[(d.item, d.x)]:
            del self.live[(d.item, d.x)]
        self.done.append(d)
        self.events.append({"n": n, "t": t, "ev": "drop_gone", "id": d.id, "item": d.item, "how": how})

    def _cause(self, d, t):
        """How a drop seen leaving / whose place shows without it went."""
        if t - d.last_t > IN_VIEW_S:
            return "found gone"
        for dz, dx, dy in self._presses(d, Z_FIT_S):        # a press of our pickup key with the drop in reach THEN
            if dx is not None and abs(dx) <= REACH_X and -REACH_UP <= dy <= REACH_DOWN:
                return "we took it"
        return "gone in view"

    # ---- one frame
    def step(self, n, t, C, sightings, me, bits):
        ev0 = len(self.events)
        self.n_looks_frame = 0
        if C is None or sightings is None:                  # blind: nothing changes
            self.stats["blind"] += 1
            return []
        self.t_prev = t
        if me is not None:
            self.me_last = (me, t)
        elif self.me_last is not None and t - self.me_last[1] <= 2.0:
            me = self.me_last[0]                            # our tag is missed on some frames: where we just were
        while len(self.z_me) < len(self.z) and self.z[len(self.z_me)] <= t:
            self.z_me.append(me)                            # where we stood when the pickup key went down
        # 1. sightings -> drops: the cheapest pairs first, one each
        S = []
        for s in sightings:
            mx, my = s["feet"][0] + C[0], s["feet"][1] + C[1]
            S.append((s["item"], mx, my, s["kind"] == "rest", s))
        pairs = []
        for j, (item, mx, my, rest, s) in enumerate(S):
            for d in self.live.get((item, mx), ()):
                c = self._fits(d, t, my)
                if c is not None:
                    pairs.append((c, not rest, j, d))
        pairs.sort(key=lambda p: (p[0], p[1], p[2]))
        got, used = {}, set()
        for c, _, j, d in pairs:
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
                if d.far > BOB_FAR:                             # back from far away: its bob is learnt again
                    d.sums[:], d.n_fit, d.fit, d.fit_t0, d.sum_t = 0.0, 0, None, t, t
                    self.stats["bob redone"] += 1
                elif d.conf:
                    e = d.expect(t)
                    if e is not None:
                        self.bob_err[min(40, int(round(10 * abs(my - e))))] += 1
                d.far = 0.0
                d.seen, d.y, d.y_t, d.last_t, d.last_n, d.unseen_s, d.absent = True, my, t, t, n, 0.0, None
                d.y_lo, d.y_hi = min(d.y_lo, my), max(d.y_hi, my)
                d.hop, d.seen_last = None, me
                d.learn(t, my)
                if t - d.born_t <= 2.0:
                    d.first.append((t, my))
                if rest:
                    d.n_rest, d.last_rest_t = d.n_rest + 1, t
                    d.cover = "none" if s["seen"] >= 0.95 * s["n_op"] else "drop" if s["under"] else \
                        "scenery" if s["front"] else "other"
                else:
                    d.n_weak += 1
                    d.cover = "other"
            if len(lst) > 1:
                both = [x for x in lst if x.conf and x.seen]
                if len(both) > 1:                           # two of one item at one x, both sighted this frame
                    for x in both:
                        x.twin = True
        # 2. the sightings no drop took: a hop of a drop that just lost its sighting, else (REST) a tentative drop
        lost = [d for lst in self.live.values() for d in lst if d.conf and not d.seen
                and (d.hop is not None or t - d.last_t <= HOP_GAP)] if self.use_hop else []
        for j, (item, mx, my, rest, s) in enumerate(S):
            if j in used:
                continue
            hopped = False
            for d in lost:
                if d.item != item:
                    continue
                if d.hop is None:
                    if abs(mx - d.x) <= HOP_DX and 4 <= d.y - my <= HOP_UP:
                        d.hop, d.hop_from, hopped = [(t, mx, my)], d.y, True
                else:
                    ht, hx, hy = d.hop[-1]
                    if 0 < t - ht <= HOP_GAP and abs(mx - hx) <= HOP_DX and -2 <= hy - my <= HOP_UP:
                        d.hop.append((t, mx, my))
                        hopped = True
                if hopped:
                    break
            if hopped:
                continue
            self.recent.append((t, n, item, mx, my))
            if rest and s["dy"] is not None and s["dy"] >= NEW_LO and s["fh"] is not None:
                d = Drop(self.next_id, item, mx, my - s["dy"], s["fh"], s["layer"], t, n, my)
                self.next_id += 1
                d.n_rest, d.seen_last, d.first_f = 1, me, s["f"]
                d.learn(t, my)
                d.first.append((t, my))
                # was its place on screen before it lay there (it landed in view), or did it come into view lying?
                d.born_view = all(any(a <= t - tc <= b and 30 <= mx - cc[0] <= SW - 30 and 60 <= d.yf - cc[1] <=
                                      PLAY_H - 10 for tc, cc in self.cams) for a, b in ((0.1, 0.25), (0.4, 0.6)))
                self.live.setdefault((item, mx), []).append(d)
        self.cams.append((t, C))
        while self.cams and t - self.cams[0][0] > 0.7:
            self.cams.popleft()
        while self.recent and t - self.recent[0][0] > FLY_S:
            self.recent.popleft()
        # 3. every drop: confirm, forget, gone
        for d in [x for lst in self.live.values() for x in lst]:
            if not d.conf:
                if d.seen and t - d.born_t >= T_CONFIRM:
                    d.conf = True
                    d.near, d.fly = self._mobs_near(d), self._fly_back(d)
                    d.from_mob = self.pick_mob(d.near, d.fly)[0]
                    self.events.append({"n": n, "t": t, "ev": "drop_new", "id": d.id, "item": d.item,
                                        "from_mob": d.from_mob, "born_t": d.born_t})
                elif not d.seen and t - d.last_t > T_TENT:
                    self.live[(d.item, d.x)].remove(d)
                    if not self.live[(d.item, d.x)]:
                        del self.live[(d.item, d.x)]
                    self.stats["tentative dropped"] += 1
                continue
            if t - d.born_t >= LIFE_MAX:
                self._gone(d, n, t, "130 s old" if not d.seen else "130 s old (still seen)", me)
                continue
            if d.seen:
                d.lost = None
                continue
            d.unseen_s = t - d.last_t
            if d.lost is None:
                d.lost = (t, n)                                 # the first frame without it
            if me is not None:
                d.far = max(d.far, math.hypot(me[0] - d.x, me[1] - d.yf))
            if d.hop is not None:
                if d.hop_from - d.hop[-1][2] >= HOP_GONE:
                    self._gone(d, n, t, self._cause(d, t), me)
                    continue
                if t - d.hop[-1][0] > HOP_GAP:
                    d.hop = None                                # it did not go on: no hop
            v = self._look(d, C, bits, t)
            d.cover = v
            d.cov_n[v] += 1
            if v == "absent":
                if d.absent is None:
                    d.absent = (t, n)                           # the first frame its place showed without it
                if t - d.absent[0] >= self.t_absent:
                    self._gone(d, n, t, self._cause(d, t), me)
            else:
                d.absent = None
        return self.events[ev0:]

    def finish(self, n, t):
        for d in self.drops():
            self._gone(d, n, t, "capture ended", None)


# ------------------------------------------------------------------ running it over a capture
def frames_of(cap, need_bits=True):
    """(row, packed bits) per frame of the kept replay, a chunk in memory at a time."""
    d, m = dump.out_dir(cap), dump.meta(cap)
    for k in range(m["chunks"]):
        rws = pickle.loads((d / f"rows_{k:03d}.pkl").read_bytes())
        bts = pickle.loads((d / f"bits_{k:03d}.pkl").read_bytes()) if need_bits else None
        for i, r in enumerate(rws):
            yield r, (bts[i] if bts is not None else None)
        del rws, bts


def deaths_of(cap) -> list:
    """[(t of the first die pose, x, y, chain index)] of the capture's truth chains, by t."""
    import cache
    import oracle
    out = []
    for k, ch in enumerate(cache.chains(cap)):
        for p in ch["parts"]:
            q = next((q for q in p["pts"] if load.anim_of(q[oracle.POSE]).startswith("die")), None)
            if q is not None:
                out.append((q[oracle.T], q[oracle.X], q[oracle.Y], k))
                break
    out.sort()
    return out


def again_of(d: Drop, done: list) -> list:
    """The self-check behind "declared gone, then seen again": the drops of the same item that ended at d's place
    before d was born, each with how well ITS bob predicts d's first 2 s of sightings (mean |px|; a drop's own bob
    fits itself to ~0.3 px, another drop's only by chance). -> [(id, s from its end to d's birth, its age then,
    mean px, sightings, how it ended)]."""
    out = []
    for o in done:
        if o is d or o.item != d.item or o.x != d.x or abs(o.yf - d.yf) > 2 or o.end["t"] > d.born_t + 0.3 \
                or d.born_t - o.born_t > LIFE_MAX + 5:
            continue
        e = [abs(y - o.expect(t)) for t, y in d.first if o.expect(t) is not None]
        out.append((o.id, round(d.born_t - o.end["t"], 3), round(d.born_t - o.born_t, 2),
                    round(float(np.mean(e)), 2) if e else None, len(e), o.end["how"]))
    return out


def life_of(d: Drop, pics: Pictures, done: list) -> dict:
    return {"id": d.id, "item": d.item, "name": pics.name(d.item), "class": pics.cls(d.item), "x": d.x, "yf": d.yf,
            "fh": d.fh, "layer": d.layer, "born_t": d.born_t, "born_n": d.born_n, "n_rest": d.n_rest,
            "n_weak": d.n_weak, "y_lo": d.y_lo, "y_hi": d.y_hi, "from_mob": d.from_mob, "near": d.near,
            "fly": d.fly, "end": d.end, "cover": dict(d.cov_n), "twin": d.twin, "again": again_of(d, done),
            "born_view": d.born_view,
            "first_span": round(d.first[-1][0] - d.first[0][0], 3) if d.first else 0.0}


def run(cap, verbose=True, calib_every=0, **kw) -> dict:
    """Track the drops of one capture from its kept replay -> the result (also what `numbers` reads)."""
    m = dump.meta(cap)
    pics, fronts = Pictures(), Fronts(m["map"])
    keys = load.keys(cap)
    z = sorted(k["t"] for k in keys if k["key"] == PICK_KEY and k["down"])
    deaths = deaths_of(cap)
    tr = DropTracker(pics, fronts, deaths, z, **kw)
    ms, alive, looks, T, N, me_at, cams = [], [], [], [], [], [], []
    t0 = time.perf_counter()
    n = t = None
    for r, packed in frames_of(cap):
        n, t = r["n"], r["t"]
        bits = Bits(packed)
        a = time.perf_counter()
        tr.step(n, t, r["C"], r["facts"].get("drops"), r["me_map"], bits)
        ms.append(1000 * (time.perf_counter() - a) - bits.ms)
        alive.append(sum(1 for lst in tr.live.values() for d in lst if d.conf))
        looks.append(tr.n_looks_frame)
        T.append(t)
        N.append(n)
        me_at.append(r["me_map"])
        cams.append(r["C"])
        if calib_every and r["C"] is not None and n % calib_every == 0:
            shows, world = bits.get()
            for s in r["facts"].get("drops") or []:
                if s["kind"] == "rest":
                    f = next(((mk, n_op) for ff, mk, n_op in pics.masks[s["item"]] if ff == s["f"]), None)
                    if f is not None:
                        c = counts(shows, world, fronts, r["C"], f[0], s["layer"], s["feet"][0] + r["C"][0],
                                   s["feet"][1] + r["C"][1])
                        tr.eps.append((s["item"], f[1], c[0], c[1], c[2], s["seen"], s["absent"], s["front"]))
    tr.finish(n, t)
    res = {"cap": str(cap), "map": m["map"], "frames": len(T), "t": [T[0], T[-1]],
           "lives": [life_of(d, pics, tr.done) for d in sorted(tr.done, key=lambda d: d.id)], "events": tr.events,
           "ms": np.array(ms, np.float32), "alive": np.array(alive, np.int16), "looks": np.array(looks, np.int16),
           "T": np.array(T), "N": np.array(N), "me": me_at, "z": z, "deaths": deaths, "stats": dict(tr.stats),
           "eps": tr.eps, "look_ms": tr.look_ms, "n_looks": tr.n_looks, "wall_s": time.perf_counter() - t0,
           "keys": {k: sorted(x["t"] for x in keys if x["key"] == k and x["down"]) for k in ("q", "w", "e", "z")},
           "blind": tr.stats["blind"], "bob_err": dict(tr.bob_err), "C": cams}
    if verbose:
        print(f"{cap}: {len(T)} frames in {res['wall_s']:.0f} s; {len(res['lives'])} drops; tentative dropped "
              f"{tr.stats['tentative dropped']}; looks {tr.n_looks} ({tr.look_ms / max(1, tr.n_looks):.3f} ms each)",
              flush=True)
    return res


def keep(res):
    res_path(res["cap"]).write_bytes(pickle.dumps(res, protocol=pickle.HIGHEST_PROTOCOL))


def kept(cap) -> dict:
    return pickle.loads(res_path(cap).read_bytes())


def pct(v, ps=(50, 90, 99, 100)):
    v = np.asarray(list(v), float)
    return [round(float(np.percentile(v, p)), 3) for p in ps] if len(v) else None


# ------------------------------------------------------------------ the numbers (1-6)
def hist(v, edges):
    h = np.histogram(np.asarray(list(v), float), edges)[0]
    return ", ".join(f"{edges[i]:g}-{edges[i + 1]:g}: {int(h[i])}" for i in range(len(h)) if h[i])


def mob_fit(l):
    """from_mob by the rule on a kept life: (chain or None, how many deaths fit)."""
    return DropTracker.pick_mob(l["near"], l["fly"])


def numbers(results, title):
    lives = [dict(l, cap=r["cap"]) for r in results for l in r["lives"]]
    ended = [l for l in lives if l["end"]["how"] != "capture ended"]
    print(f"\n================ {title}: {len(results)} capture(s), {sum(r['frames'] for r in results)} frames, "
          f"{sum(r['t'][1] - r['t'][0] for r in results) / 60:.1f} min, blind frames {sum(r['blind'] for r in results)}")
    # ---- 1
    alive = np.concatenate([r["alive"] for r in results])
    how = Counter(l["end"]["how"] for l in lives)
    print(f"\n1. DROPS: {len(lives)} lives; by class {dict(Counter(l['class'] for l in lives).most_common())}")
    print(f"   alive at once p50 / p99 / max: {pct(alive, (50, 99, 100))}")
    print(f"   how they ended: {dict(how.most_common())}")
    age = [l["end"]["age"] for l in ended]
    print(f"   lifetime (birth -> declared gone; {len(ended)} that ended in the capture): p10 / p50 / p90 / p99 / max "
          f"{pct(age, (10, 50, 90, 99, 100))} s")
    print(f"      by 10 s: {hist(age, [0, 1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 118, 120, 125, 130.5, 999])}")
    for h in how:
        a = [l["end"]["age"] for l in lives if l["end"]["how"] == h]
        print(f"      {h:24s} n {len(a):4d}  age p10 / p50 / p90 / max {pct(a, (10, 50, 90, 100))}")
    seenlast = [l["end"]["age"] - l["end"]["unseen_s"] for l in ended]
    print(f"   age at the LAST sighting: max {max(seenlast):.1f} s; over 118 s: {sum(a > 118 for a in seenlast)}, over "
          f"129 s: {sum(a > 129 for a in seenlast)}")
    fr = Counter()
    for l in lives:
        fr["sighted REST"] += l["n_rest"]
        fr["sighted weak"] += l["n_weak"]
        for k, v in l["cover"].items():
            fr[k] += v
    tot = sum(fr.values())
    print(f"   a live drop's frames ({tot}): " + ", ".join(f"{k} {v / tot:.1%}" for k, v in fr.most_common()))
    onscr = tot - fr["out"]
    print(f"      of its frames on screen ({onscr}): sighted {(fr['sighted REST'] + fr['sighted weak']) / onscr:.1%}, "
          f"covered {fr['covered'] / onscr:.1%}, at the edge {fr['edge'] / onscr:.1%}, under the UI {fr['ui'] / onscr:.1%}, "
          f"behind front scenery {fr['scenery'] / onscr:.2%}, place empty (the frames before 'gone') {fr['absent'] / onscr:.2%}")
    be = Counter()
    for r in results:
        be.update(r["bob_err"])
    nb = sum(be.values())
    if nb:
        cum, q = 0, {}
        for k in sorted(be):
            cum += be[k]
            for p in (0.5, 0.99, 0.999, 0.9999):
                if p not in q and cum >= p * nb:
                    q[p] = k / 10
        print(f"   |sighting y - the drop's fitted bob| over {nb} sightings: p50 {q[0.5]} px, p99 {q[0.99]}, p99.9 "
              f"{q[0.999]}, p99.99 {q[0.9999]} (allowed {BOB_TOL}); bob fits redone after we were > {BOB_FAR} px away: "
              f"{sum(r['stats'].get('bob redone', 0) for r in results)}")
    # ---- 2
    inview = [l for l in ended if l["end"]["how"] in ("we took it", "gone in view")]
    took = [l for l in inview if l["end"]["how"] == "we took it"]
    print(f"\n2. WENT IN VIEW (last sighting <= {IN_VIEW_S} s before 'gone'): {len(inview)}; 'we took it' {len(took)}")

    def zlag(l):                    # our pickup key going down -> the first frame without the drop
        e = l["end"]
        return None if e["z_before"] is None or e["lost_t"] is None else e["z_before"] + e["lost_t"] - e["last_t"]

    def medist(l):
        me = l["end"]["me"]
        return None if me is None else (me[0] - l["x"], me[1] - l["yf"])

    def press(l):                   # the press that fits best: in the window, the nearest to the drop
        c = [z for z in l["end"]["z"] if z[0] <= Z_FIT_S and z[1] is not None]
        return min(c, key=lambda z: (abs(z[2]) > 30, abs(z[1]))) if c else None
    if took:
        lag = [zlag(l) for l in took]
        pr = [p for p in (press(l) for l in took) if p]      # (track/drops.py: the key held through it has none)
        print(f"   'we took it': the LAST key down before it -> the first frame without the drop: p50 / p90 / max "
              f"{pct(lag, (50, 90, 100))} s; at the fitting press our feet to the drop |dx| p50 / p90 / p99 / max "
              f"{pct([abs(p[1]) for p in pr])} px, dy (our feet - its foothold) min / p5 / p50 / p95 / max "
              f"{pct([p[2] for p in pr], (0, 5, 50, 95, 100))}; the hop seen on {sum(l['end']['hop'] > 0 for l in took)}")
    hop = [l for l in inview if l["end"]["hop"] >= 2]
    hz = [l["end"]["z_before"] for l in hop if l["end"]["z_before"] is not None]
    hp = [press(l) for l in hop]
    print(f"   the hop seen (>= 2 hop sightings) on {len(hop)} of the {len(inview)} = pickups for sure. Their last key "
          f"down -> last resting frame p1 / p50 / p90 / p99 / max {pct(hz, (1, 50, 90, 99, 100))} s; none within 1 s: "
          f"{sum(l['end']['z_before'] is None or l['end']['z_before'] > 1.0 for l in hop)}")
    print(f"      by 0.05 s: {hist(hz, [-1, 0, .05, .1, .15, .2, .25, .3, .35, .4, .5, .75, 1, 2, 1e9])}")
    print(f"      our feet at the nearest press of the last {Z_FIT_S} s: |dx| p50 / p90 / p99 / max "
          f"{pct([abs(p[1]) for p in hp if p])}, by 10 px: {hist([abs(p[1]) for p in hp if p], list(range(0, 130, 10)) + [1e9])}")
    print(f"      ... dy (our feet - its foothold) min / p1 / p50 / p99 / max {pct([p[2] for p in hp if p], (0, 1, 50, 99, 100))}"
          f", by 10 px: {hist([p[2] for p in hp if p], [-200, -100, -70, -50, -30, -10, -1, 2, 10, 30, 50, 100, 200])}; "
          f"at their LAST sighting instead: |dx| max {max([abs(medist(l)[0]) for l in hop if medist(l)], default=None)}, dy min / max "
          f"{pct([medist(l)[1] for l in hop if medist(l)], (0, 100))}")
    print(f"      the hop seen but no press fits (key {Z_FIT_S} s, reach {REACH_X} px, {REACH_UP} up / {REACH_DOWN} down): "
          f"{sum(l['end']['how'] != 'we took it' for l in hop)}; 'we took it' without a hop seen: "
          f"{sum(l['end']['hop'] < 2 for l in took)} (aged 118-130.5 s: {sum(l['end']['hop'] < 2 and 118 <= l['end']['age'] <= 130.5 for l in took)})")
    noz = [l for l in inview if l["end"]["how"] == "gone in view"]
    exp_ = [l for l in noz if 118 <= l["end"]["age"] <= 130.5]
    lying = [l for l in noz if not 118 <= l["end"]["age"] <= 130.5 and not l["born_view"] and l["end"]["hop"] == 0]
    print(f"   in view with NO fitting key press: {len(noz)}: aged 118-130.5 s = expired {len(exp_)}; no hop, and it came "
          f"into view lying (its real age is not known: expired) {len(lying)}; the others:")
    for l in sorted(noz, key=lambda l: l["end"]["age"]):
        e = l["end"]
        if l not in exp_ and l not in lying:
            print(f"      {l['cap']} id {l['id']:4d} {l['name'][:22]:22s} x {l['x']:5d} yf {l['yf']:5d} age {e['age']:7.2f} last frame "
                  f"{e['last_n']} hop {e['hop']} key {e['z_before']} presses {e['z']} unseen {e['unseen_s']}")
    # ---- 3
    print("\n3. LINKING, by self-consistency")
    two = over = long_ = switch = 0
    ov_rows, sw_rows = [], []
    for r in results:
        L = r["lives"]
        byitem = {}
        for l in L:
            byitem.setdefault(l["item"], []).append(l)
        for it, ls in byitem.items():
            for i, a in enumerate(ls):
                for b in ls[i + 1:]:
                    if abs(a["x"] - b["x"]) <= 3 and abs(a["yf"] - b["yf"]) <= 12:
                        lo, hi = max(a["born_t"], b["born_t"]), min(a["end"]["t"], b["end"]["t"])
                        if hi - lo > 0.05:
                            over += 1
                            ov_rows.append((r["cap"], a, b, hi - lo))
                        first, second = (a, b) if a["end"]["t"] <= b["end"]["t"] else (b, a)
                        if 0 <= second["born_t"] - first["end"]["t"] < 1.0 or -0.3 <= second["born_t"] - first["end"]["t"] < 0:
                            switch += 1
                            sw_rows.append((r["cap"], first, second))
        long_ += sum(l["end"]["age"] > 131 for l in L)
    print(f"   a life with two items: 0 (the item is part of the link's key); a life over 131 s: {long_}")
    print(f"   two lives of one item overlapping in time within 3 px: {over}"
          f" (both sighted in ONE frame = two real drops: {sum(a['twin'] and b['twin'] for _, a, b, _ in ov_rows)})")
    for cap, a, b, s in ov_rows:
        print(f"      {cap} {a['name'][:20]:20s} x {a['x']} / {b['x']} yf {a['yf']}: id {a['id']} {a['born_t']:.2f}-{a['end']['t']:.2f} "
              f"({a['end']['how']}), id {b['id']} {b['born_t']:.2f}-{b['end']['t']:.2f} ({b['end']['how']}); together {s:.1f} s; "
              f"twins seen {a['twin'] and b['twin']}")
    print(f"   a life born where another of the item ended < 1 s earlier: {switch}")
    for cap, a, b in sw_rows:
        ag = next((x for x in b["again"] if x[0] == a["id"]), None)
        print(f"      {cap} {a['name'][:20]:20s} x {a['x']} -> {b['x']}: id {a['id']} ended {a['end']['t']:.2f} ({a['end']['how']}, "
              f"age {a['end']['age']:.1f}), id {b['id']} born {b['born_t']:.2f}; the old bob fits the new one to "
              f"{ag[3] if ag else None} px over {ag[4] if ag else 0} sightings; flight seen {b['fly'] is not None}")
    # ---- 4
    born = [l for l in lives if l["born_view"]]
    print(f"\n4. FROM_MOB: {len(lives)} drops, {len(born)} landed in view (their place was on screen before they lay there)")
    one = [l for l in born if len([m for m in l["near"] if 0 <= m[0] <= 4 and abs(m[1]) <= 250 and abs(m[2]) <= 150]) == 1]
    m1 = [next(m for m in l["near"] if 0 <= m[0] <= 4 and abs(m[1]) <= 250 and abs(m[2]) <= 150) for l in one]
    print(f"   measured on the {len(one)} with exactly ONE death in a wide window (4 s before, 250 px, 150 px):")
    print(f"      die pose -> first RESTING sighting: p1 / p5 / p50 / p95 / p99 / max {pct([m[0] for m in m1], (1, 5, 50, 95, 99, 100))} s"
          f"; by 0.2 s: {hist([m[0] for m in m1], [0, .2, .4, .6, .8, 1, 1.2, 1.4, 1.6, 1.8, 2, 2.5, 3, 4.01])}")
    print(f"      landing x - death x: p1 / p5 / p50 / p95 / p99 {pct([-m[1] for m in m1], (1, 5, 50, 95, 99))}, |dx| p50 / "
          f"p90 / p99 / max {pct([abs(m[1]) for m in m1])}; by 25 px: {hist([abs(m[1]) for m in m1], [0, 5, 15, 35, 60, 85, 110, 135, 160, 200, 251])}")
    print(f"      death y - the drop's foothold y: p1 / p5 / p50 / p95 / p99 {pct([m[2] for m in m1], (1, 5, 50, 95, 99))}; "
          f"by 10 px: {hist([m[2] for m in m1], [-151, -100, -80, -60, -40, -20, -10, -2, 3, 10, 20, 40, 60, 80, 100, 151])}")
    fl = [(l, m) for l, m in zip(one, m1) if l["fly"] is not None and l["fly"][3] >= 5]
    if fl:
        print(f"      with the flight followed back ({len(fl)}, mesos): die pose -> the flight's first sighting p5 / p50 / p95 / max "
              f"{pct([m[0] - (l['born_t'] - l['fly'][0]) for l, m in fl], (5, 50, 95, 100))} s; flight seen for p5 / p50 / p95 "
              f"{pct([l['born_t'] - l['fly'][0] for l, m in fl], (5, 50, 95))} s; its first x - death x |px| p50 / p90 / max "
              f"{pct([abs(l['fly'][1] - (l['x'] + m[1])) for l, m in fl], (50, 90, 100))}")
    fits = [mob_fit(l) for l in born]
    c = Counter("none" if k == 0 else "one" if k == 1 else "several" for _, k in fits)
    print(f"   by the rule ({BORN_LO}-{BORN_HI} s before, <= {MOB_DX} px, the death {MOB_UP} px above .. {MOB_DOWN} px "
          f"below the drop's foothold): exactly one "
          f"{c['one']} ({c['one'] / max(1, len(born)):.1%}), none {c['none']} ({c['none'] / max(1, len(born)):.1%}), several "
          f"{c['several']} ({c['several'] / max(1, len(born)):.1%})")
    nob = [mob_fit(l) for l in lives if not l["born_view"]]
    print(f"   the {len(nob)} that came into view lying: a death fits {sum(k > 0 for _, k in nob)} of them (not counted)")
    tot = near_us = with_drop = ours = ours_drop = 0
    for r in results:
        linked = {mob_fit(l)[0] for l in r["lives"] if l["born_view"]}
        T, me = r["T"], r["me"]
        atk = sorted(r["keys"]["q"] + r["keys"]["w"])
        for t, x, y, key in r["deaths"]:
            tot += 1
            i = min(len(T) - 1, int(np.searchsorted(T, t)))
            m = next((me[j] for j in range(i, max(-1, i - 30), -1) if me[j] is not None), None)
            if m is None or abs(x - m[0]) > 350 or abs(y - m[1]) > 200:
                continue
            near_us += 1
            with_drop += key in linked
            k = bisect.bisect_right(atk, t)
            if k and t - atk[k - 1] <= 1.0 and abs(x - m[0]) <= 200 and abs(y - m[1]) <= 60:
                ours += 1
                ours_drop += key in linked
    print(f"   the other way: {tot} deaths; {near_us} within 350 x 200 px of us, a drop follows {with_drop} "
          f"({with_drop / max(1, near_us):.1%}); with our attack key <= 1 s before and within 200 x 60 px: {ours}, a drop "
          f"follows {ours_drop} ({ours_drop / max(1, ours):.1%})")
    # ---- 5
    print("\n5. HOW QUICKLY 'GONE' IS NOTICED")
    look = [l for l in ended if l["end"]["absent_t"] is not None and l["end"]["how"] in ("we took it", "gone in view", "found gone")]
    byhop = [l for l in ended if l["end"]["absent_t"] is None and l["end"]["how"] in ("we took it", "gone in view", "found gone")]
    print(f"   by the look (its place shows without it): {len(look)}; 'gone' - the first frame the place showed empty: "
          f"p50 / p90 / max {pct([l['end']['t'] - l['end']['absent_t'] for l in look], (50, 90, 100))} s")
    print(f"   by the hop seen: {len(byhop)}; 'gone' - the first frame without it: p50 / p90 / max "
          f"{pct([l['end']['t'] - l['end']['lost_t'] for l in byhop], (50, 90, 100))} s")
    print(f"   in view, 'gone' - the first frame without it: p50 / p90 / p99 / max "
          f"{pct([l['end']['t'] - l['end']['lost_t'] for l in inview])} s; over 0.5 s: "
          f"{sum(l['end']['t'] - l['end']['lost_t'] > 0.5 for l in inview)} (of them aged 118-130.5 s = the fade: "
          f"{sum(l['end']['t'] - l['end']['lost_t'] > 0.5 and 118 <= l['end']['age'] <= 130.5 for l in inview)})")
    fg = [l for l in ended if l["end"]["how"] == "found gone"]
    cov = Counter()
    for l in fg:
        cov[max(l["cover"], key=lambda k: l["cover"][k] if k != "absent" else -1) if l["cover"] else "?"] += 1
    print(f"   'found gone': {len(fg)}; unseen for p50 / p90 / max {pct([l['end']['unseen_s'] for l in fg], (50, 90, 100))} s; "
          f"mostly: {dict(cov.most_common())}")
    again = [(l, x) for l in lives for x in l["again"] if x[1] <= 3.0]
    same = [(l, x) for l, x in again if x[3] is not None and x[3] <= 0.8 and x[4] >= 20 and l["fly"] is None]
    print(f"   declared gone, then one of the item born at the same place within 3 s: {len(again)}; of them the OLD drop's "
          f"bob fits the new one (<= 0.8 px, no flight seen) = the same drop seen again, a false 'gone': {len(same)}")
    for l, x in again:
        print(f"      {l['cap']} id {x[0]} ({x[5]}, age {x[2]}) -> id {l['id']} {l['name'][:20]} x {l['x']} born {l['born_t']:.2f}, "
              f"{x[1]} s later; old bob fits {x[3]} px over {x[4]}; flight seen {l['fly'] is not None}")
    # ---- 6
    ms = np.concatenate([r["ms"] for r in results])
    looks = np.concatenate([r["looks"] for r in results])
    n_looks, look_ms = sum(r["n_looks"] for r in results), sum(r["look_ms"] for r in results)
    print(f"\n6. COST: the tracker's step (Python, with its looks, without unpacking the bitmaps) p50 / p90 / p99 / max "
          f"{pct(ms)} ms a frame; of it the looks: {n_looks} in all, {look_ms / max(1, n_looks):.3f} ms each, "
          f"{look_ms / len(ms):.3f} ms a frame on average")
    print(f"   looks a frame (= the known drops the finder did not report, on screen): p50 / p90 / p99 / max "
          f"{pct(looks)}; frames with at least one: {np.mean(looks > 0):.1%}")
    return lives


# ------------------------------------------------------------------ by eye: sheets of random births and ends
TILE_W, TILE_H, TILE_S = 260, 200, 1.5          # px of the frame around the drop's place, the zoom


def _tile(rec, clip, res, pics, l, n, death=None):
    """Frame n around drop l's place (its foothold 70 % down), zoomed: a green frame where the drop lies, a red
    cross at the linked mob's place of death. -> (picture, the frame's number really used)."""
    import cv2
    i = min(max(int(np.searchsorted(res["N"], n)), 0), len(res["N"]) - 1)
    n, C = int(res["N"][i]), res["C"][i]
    out = np.full((int(TILE_H * TILE_S), int(TILE_W * TILE_S), 3), 40, np.uint8)
    img = rec.read(clip.run, rec.name_of(n)) if C is not None else None
    if img is None:
        cv2.putText(out, "no camera / no frame", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return out, n
    x0, y0 = l["x"] - C[0] - TILE_W // 2, l["yf"] - C[1] - int(0.7 * TILE_H)
    pad = cv2.copyMakeBorder(img, TILE_H, TILE_H, TILE_W, TILE_W, cv2.BORDER_CONSTANT, value=(90, 0, 90))
    out = cv2.resize(pad[y0 + TILE_H:y0 + 2 * TILE_H, x0 + TILE_W:x0 + 2 * TILE_W], None, fx=TILE_S, fy=TILE_S,
                     interpolation=cv2.INTER_NEAREST) if -TILE_W <= x0 <= img.shape[1] and -TILE_H <= y0 <= \
        img.shape[0] else out
    if out.shape[:2] != (int(TILE_H * TILE_S), int(TILE_W * TILE_S)):
        out = np.full((int(TILE_H * TILE_S), int(TILE_W * TILE_S), 3), 40, np.uint8)
        cv2.putText(out, "off screen", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        return out, n
    f, mask, _ = pics.masks[l["item"]][0]
    hh, ww = mask.shape

    def at(mx, my):
        return int(round((mx - C[0] - x0) * TILE_S)), int(round((my - C[1] - y0) * TILE_S))
    a, b = at(l["x"] - ww // 2 - 4, l["yf"] - 5 - hh - 4), at(l["x"] - ww // 2 + ww + 4, l["yf"] + 6 + 3)
    cv2.rectangle(out, a, b, (0, 255, 0), 1)
    if death is not None:
        px, py = at(*death)
        cv2.line(out, (px - 7, py - 7), (px + 7, py + 7), (0, 0, 255), 1)
        cv2.line(out, (px - 7, py + 7), (px + 7, py - 7), (0, 0, 255), 1)
    return out, n


def _sheet(rows, path):
    """rows: [(header lines, [(tile, caption)])] -> one PNG."""
    import cv2
    tw, th = int(TILE_W * TILE_S), int(TILE_H * TILE_S)
    W = 4 * tw + 5 * 6
    parts = []
    for head, tiles in rows:
        bar = np.zeros((18 * len(head) + 6, W, 3), np.uint8)
        for k, s in enumerate(head):
            cv2.putText(bar, s, (6, 16 + 18 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        row = np.zeros((th + 20, W, 3), np.uint8)
        for k, (tile, cap_) in enumerate(tiles):
            x = 6 + k * (tw + 6)
            row[:th, x:x + tw] = tile
            cv2.putText(row, cap_, (x, th + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 255, 255), 1, cv2.LINE_AA)
        parts += [bar, row]
    cv2.imwrite(str(path), np.vstack(parts))


def sheets(cap, n=20, seed=1, per=3):
    """20 random births and 20 random ends of the kept result, as sheets of frame crops + an index (json)."""
    import random
    import frames as rec
    res, pics = kept(cap), Pictures()
    clip = rec.clip(cap, False, "drops")
    out = out_root() / "sheets" / str(cap).replace("#", "_")
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    lives = res["lives"]
    deaths = {k: (t, x, y) for t, x, y, k in res["deaths"]}
    T, N = res["T"], res["N"]

    def n_at(t):
        return int(N[min(len(N) - 1, int(np.searchsorted(T, t)))])

    def t_of(nn):
        return float(T[min(len(N) - 1, int(np.searchsorted(N, nn)))])
    index = {"births": [], "ends": []}
    births = rng.sample(lives, min(n, len(lives)))
    rows = []
    for k, l in enumerate(births):
        key, fit = mob_fit(l)
        dth = deaths.get(key)
        m = next((m for m in l["near"] if m[3] == key), None)
        head = [f"B{k + 1:02d}  id {l['id']}  {l['name']} ({l['class']})  x {l['x']} foothold y {l['yf']}  born frame "
                f"{l['born_n']} t {l['born_t']:.2f}  landed in view: {l['born_view']}  flight followed back: "
                f"{'no' if l['fly'] is None else f'{l['born_t'] - l['fly'][0]:.2f} s, {l['fly'][3]} sightings'}",
                f"     from_mob: " + ("none fits" if dth is None else f"chain {key} ({fit} fit): die pose {m[0]:.2f} s "
                                      f"before, at dx {m[1]:+d} dy {m[2]:+d} of the drop (red cross)") +
                "   tiles: the mob's die pose (else 1.4 s before) / 0.5 s before / the first resting sighting / 1 s after"]
        frames_ = [n_at(dth[0]) if dth else n_at(l["born_t"] - 1.4), n_at(l["born_t"] - 0.5), l["born_n"],
                   n_at(l["born_t"] + 1.0)]
        tiles = []
        for nn in frames_:
            tile, used = _tile(rec, clip, res, pics, l, nn, None if dth is None else (dth[1], dth[2]))
            tiles.append((tile, f"frame {used} ({t_of(used) - l['born_t']:+.2f} s)"))
        rows.append((head, tiles))
        index["births"].append({"case": f"B{k + 1:02d}", "id": l["id"], "item": l["name"], "x": l["x"], "yf": l["yf"],
                                "born_n": l["born_n"], "frames": frames_, "from_mob": key, "fit": fit})
        if len(rows) == per or k == len(births) - 1:
            _sheet(rows, out / f"births_{(k // per) + 1:02d}.png")
            rows = []
    ends = rng.sample([l for l in lives if l["end"]["how"] != "capture ended"], min(n, len(lives)))
    rows = []
    for k, l in enumerate(ends):
        e = l["end"]
        me = e["me"]
        head = [f"E{k + 1:02d}  id {l['id']}  {l['name']}  x {l['x']} foothold y {l['yf']}  born t {l['born_t']:.2f}  -> "
                f"{e['how'].upper()}  at frame {e['n']} t {e['t']:.2f}, age {e['age']:.1f} s; last sighted frame "
                f"{e['last_n']} ({e['unseen_s']:.2f} s before)",
                f"     hop sightings {e['hop']}; pickup key down {e['z_before']} s before the last sighting; our feet "
                f"then: {'?' if me is None else f'dx {me[0] - l['x']:+.0f} dy {me[1] - l['yf']:+.0f}'}"
                f"   tiles: last sighting - 0.1 s / first frames without it / declared gone / 0.5 s after"]
        if e["how"].startswith("130 s"):
            frames_ = [e["last_n"], e["n"] - 60, e["n"], e["n"] + 60]
        elif e["how"] == "found gone":
            frames_ = [e["last_n"], (e["absent_n"] or e["n"]) - 2, e["n"], e["n"] + 30]
        else:
            frames_ = [e["last_n"] - 6, (e["lost_n"] or e["last_n"] + 1) + 3, e["n"], e["n"] + 30]
        tiles = []
        for nn in frames_:
            tile, used = _tile(rec, clip, res, pics, l, nn)
            tiles.append((tile, f"frame {used} ({t_of(used) - e['t']:+.2f} s)"))
        rows.append((head, tiles))
        index["ends"].append({"case": f"E{k + 1:02d}", "id": l["id"], "item": l["name"], "x": l["x"], "yf": l["yf"],
                              "how": e["how"], "frames": frames_, "end_n": e["n"], "last_n": e["last_n"]})
        if len(rows) == per or k == len(ends) - 1:
            _sheet(rows, out / f"ends_{(k // per) + 1:02d}.png")
            rows = []
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"{cap}: {len(births)} births, {len(ends)} ends -> {out}")


def main():
    import cache
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "numbers", "sheets", "calib"])
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    caps = list(cache.SOUND) if a.sound else a.caps
    if a.cmd == "run":
        for cap in caps:
            keep(run(cap))
    elif a.cmd == "numbers":
        res = [kept(cap) for cap in caps]
        numbers(res[:1], caps[0])
        if len(res) > 1:
            numbers(res, f"pooled over {len(res)} captures")
    elif a.cmd == "sheets":
        for cap in caps:
            sheets(cap, a.n, a.seed)
    elif a.cmd == "calib":
        pics = Pictures()
        for cap in caps:
            res = run(cap, calib_every=a.every)
            e = np.array([x[1:] for x in res["eps"]], float)        # n_op, on screen, shows scenery, front, seen, ..
            if len(e):
                sh = e[:, 2] / e[:, 0]
                worst = Counter()
                for x in res["eps"]:
                    worst[x[0]] = max(worst[x[0]], round(x[3] / x[1], 3))
                print(f"  {cap}: {len(e)} REST sightings looked at: the share of the WHOLE picture showing scenery "
                      f"p50 / p90 / p99 / max {pct(sh)}; > 0.2: {int((sh > 0.2).sum())}, > {LOOK_ABS}: "
                      f"{int((sh > LOOK_ABS).sum())}; the worst per item: "
                      f"{ {pics.name(k): v for k, v in worst.most_common(6)} }")
            keep_calib = out_root() / f"calib_{str(cap).replace('#', '_')}.npy"
            np.save(keep_calib, np.array(res["eps"], float))


if __name__ == "__main__":
    main()
