"""Tracker plan, Part 2: THE MOB TRACKER PROTOTYPE - memory by evidence instead of timers. Runs from the kept
replay (dump.py: the fit's sightings + the two bitmaps of every frame; no GPU), graded by score.py against the
hindsight truth (cache.chains).

    python tools/perc/track/proto_mobs.py CAP [CAP ...] | --sound  [--set key=value ...] [--today] [--why N] [--quiet]

What it does differently from maplebrain/perception/world.py (PLAN-tracker.md, "The design"):
  * a track the fit does not see keeps a POSSIBLE SET: the places on its platform it can have reached (its kind's
    top speed from the client files), minus every place where the frame shows the scenery its body would cover
    (the `shows` bitmap). Seen again next to it: the same id. The set empty: the mob is gone, at once. Nothing to
    check (drawn over, behind the UI, out of view): kept `drawn_s` / `offscreen_s` at most. No lose_s / fight_s /
    covered_s / hidden_s.
  * a new track is TENTATIVE (not a mob yet, no memory) until one sighting shows it clearly (`solid_seen` of its
    full size, `solid_on` of its body on screen) or it was sighted for `confirm_s`; no "60 % of the body on
    screen" rule.
  * the feet of a look-alike pose (one picture, two feet points) are settled by where a surface is (`feet_fix`).
  * association: one cost over seen and remembered tracks, with the mob's facing in it (`facing_cost`).
`--set` changes a Cfg field (ablations); `--today` adds world.py's numbers on the same captures; `--why N` lists
why ids switched and which remembered tracks the truth does not have.
Output per capture: score.py's report, the fair switch / held counts (`sticky`), this prototype's own counts and
the ms a frame it took in Python.
"""
import argparse
import pickle
import sys
import time
from collections import Counter
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache  # noqa: E402
import dump  # noqa: E402
import score as S  # noqa: E402
from load import ASSETS, Map, map_of, name_of, ticks  # noqa: E402

SW, PLAY_H = 1366, 700
LIVE_ANIMS = ("stand", "move", "fly", "jump", "hit1")


@dataclass
class Cfg:
    evidence: bool = True        # False: world.py's timers instead of the possible set (the tracks otherwise alike)
    feet_fix: bool = True        # look-alike poses settled by the surface
    solid_seen: float = 0.25     # a sighting with this share of the kind's full size seen ...
    solid_on: float = 0.3        # ... and this share of its body box on screen confirms a track
    confirm_s: float = 0.5       # ... or sightings over this long (>= 80 % of its frames)
    tentative_s: float = 0.3     # a tentative track unseen this long is dropped (no event)
    edge_new: float = 0.0        # a new track needs this share of its body box on screen (world.py: 0.6)
    facing_cost: float = 8.0     # px added to a pairing that flips the mob's facing
    other_type: float = 12.0     # px added to a pairing with a sighting of another kind
    remembered_cost: float = 3.0   # px added to a pairing with a track not seen on the last frame
    abs_share: float = 0.4       # this share of the body's core showing the scene: the mob is not there
    step: int = 4                # px between the places of a possible set
    knock: float = 35.0          # px: one knockback's travel (game_rules D1: ~27 + ~4), the set's first half width
    margin: float = 6.0          # px beyond the set + half a body a sighting may be
    drawn_s: float = 4.0         # unseen with something drawn over its places: kept this long at most
    offscreen_s: float = 4.0     # unseen with nothing to check (out of view, behind the UI): kept this long
    stand_tol: float = 3.0       # feet this close to a surface: standing
    die_revert_s: float = 0.2    # a live pose on a "dying" track this soon after its first die pose: it lives
    fly_r: float = 160.0         # a flyer's set is kept within this of its last place; past it: lost
    gate: float = 6.0            # px a mob seen on the last frame may be off its place, + its bound x the time
    jump_h: int = 96             # a jumper is looked for up to this far over its platform (game_rules C4: 89-98)
    fade_s: float = 0.4         # a mob last seen fading in is not checked for this long (the fade-in lasts 0.32 s)
    speed_x: float = 2.0        # Classic World's mobs move at this many times the v83 rule's top speed (measured on
                                 # 8 kinds, proto_feet.py: 1.97-1.99 x at the median)


# ---------------------------------------------------------------------------------------------------- the kinds
class Kind:
    """One mob kind's facts from the client files: top speed, can it jump / fly, the die animation's length, its
    body's core (the pixels every live pose covers, feet at 0, 0), its full size, its look-alike poses."""

    def __init__(self, mob_id: int, info: dict, poses: list, speed_x: float = 1.0):
        fr, inf = info.get("frames") or {}, info.get("info") or {}
        self.id = mob_id
        self.fly, self.jump = bool(fr.get("fly")), bool(fr.get("jump"))
        self.v_file = ((inf.get("flySpeed") or 0) + 100) * 1.25 if self.fly else ((inf.get("speed") or 0) + 100) * 0.625
        self.v = self.v_file * speed_x                     # px/s: the top speed it is seen to move at
        self.vb = max(self.v, 125.0 * speed_x)             # px/s bound from one frame to the next (a knockback)
        self.die_s = sum((f.get("delay") or 100) for f in fr.get("die1") or []) / 1000 or 0.6
        f0 = (fr.get("stand") or fr.get("move") or fr.get("fly") or [{}])[0]
        self.lt, self.rb = f0.get("lt") or [-30, -50], f0.get("rb") or [30, 0]
        self.half_w = (self.rb[0] - self.lt[0]) / 2
        mine = [p for p in poses if p.type == mob_id]
        live = [p for p in mine if p.pose.rsplit("_", 1)[0] in LIVE_ANIMS]
        self.full = float(np.median([(p.pic[..., 3] > 128).sum() for p in live])) if live else 1000.0
        cv = np.zeros((len(live), 400, 400), bool)         # feet at (300, 200)
        for k, p in enumerate(live):
            h, w = p.pic.shape[:2]
            y0, x0 = 300 - p.oy, 200 - p.ox
            cv[k, max(0, y0):y0 + h, max(0, x0):x0 + w] = (p.pic[..., 3] > 128)[max(0, -y0):, max(0, -x0):][:400 - max(0, y0), :400 - max(0, x0)]
        core = cv.all(axis=0)
        if core.sum() < 200:
            core = cv.mean(axis=0) >= 0.8
        ys, xs = np.nonzero(core)
        self.core_n = len(ys)
        sel = ((ys + xs) % 3 == 0) if len(ys) > 300 else np.ones(len(ys), bool)
        self.cdy, self.cdx = (ys[sel] - 300).astype(np.int64), (xs[sel] - 200).astype(np.int64)
        # look-alike poses: one picture (same facing), another feet point -> {(pose, facing): [(pose2, dx, dy)]}
        self.alike = {}
        by_pic = {}
        for p in mine:
            by_pic.setdefault((p.facing, p.pic.shape, p.pic.tobytes()), []).append(p)
        for (facing, _, _), ps in by_pic.items():
            for a in ps:
                for b in ps:
                    if a is not b and (a.ox, a.oy) != (b.ox, b.oy):
                        self.alike.setdefault((a.pose, facing), []).append((b.pose, b.ox - a.ox, b.oy - a.oy))


def kinds_of(mp: Map, speed_x: float = 1.0) -> dict:
    from maplebrain.perception.vote import load_poses
    poses = load_poses(mp.id, ASSETS)
    return {i: Kind(i, m, poses, speed_x) for i, m in mp.mobs.items()}


# ---------------------------------------------------------------------------------------------------- one track
class Tr:
    __slots__ = ("id", "votes", "mob", "x", "y", "t_seen", "born", "vx", "facing", "pose", "node", "air", "life",
                 "seen", "poss", "gx", "gy", "carry", "out_since", "die_t", "x_seen", "y_seen", "sx", "sy",
                 "born_how", "n_seen", "cover", "hist", "conf", "vis", "vy", "rin", "rout", "n_seen_at", "o")

    def __init__(self, tid, s, t, how):
        self.id, self.votes, self.mob = tid, {s.kind: 1.0}, s.kind
        self.x = self.x_seen = s.x
        self.y = self.y_seen = s.y
        self.t_seen = self.born = t
        self.vx, self.facing, self.pose = 0.0, s.facing, s.pose
        self.node, self.air = s.node, s.air
        self.life = "dying" if s.die else "alive"
        self.die_t = t if s.die else None
        self.seen, self.poss, self.gx, self.gy, self.carry = True, None, None, None, 0.0
        self.out_since = None
        self.sx, self.sy = s.sx, s.sy
        self.born_how, self.n_seen, self.cover = how, 1, "none"
        self.hist = [(t, s.x)]
        self.conf = "solid" if s.solid else None
        self.vis, self.o = s.vis, s.o
        self.vy = 0.0
        self.rin = self.rout = 0                           # frames remembered in view / with nothing to check
        self.n_seen_at = None                              # the frame number it was last seen on


class Sight:
    __slots__ = ("kind", "pose", "facing", "x", "y", "sx", "sy", "o", "node", "air", "die", "hit", "solid", "vis", "on",
                 "cands", "raw", "C")


# ---------------------------------------------------------------------------------------------------- the tracker
class Tracker:
    def __init__(self, mp: Map, cfg: Cfg):
        self.mp, self.nav, self.cfg = mp, mp.nav, cfg
        self.kinds = kinds_of(mp, cfg.speed_x)
        self.tracks, self.next_id, self.t = [], 1, None
        self.ev = Counter()                    # how tracks were born / ended, what the memory did
        self.rem = []                          # remembered episodes: (seconds, how it ended, next to its set?, cover)
        self.grids = {}                        # node id -> (xs, ys) of its places
        self.t0 = None
        self.ended = {}                        # track id -> (t, how, unseen s, last pose, in the air, cover)
        self.ms = {"sight + pair": [], "unseen (test)": [], "replay decode": []}
        self.trace = set()                     # track ids to print frame by frame (debugging)
        self.n = None                          # this frame's number in the session
        self.episodes = []                     # every time a track was remembered: (id, frame last seen, frame it
                                               # ended, x, y last seen, how it ended, cover, seconds, x, y seen again)
        self.boxes = {}                        # this frame's known things on screen, by kind: [(x0, y0, x1, y1)]

    # ---- placement
    def _place(self, x, y):
        p = self.nav.platform_at(x, y, tol=self.cfg.stand_tol)
        if p is not None:
            return p.id, False
        b = self.nav.below(x, y)
        return (b.id if b is not None else None), True

    def _settle(self, k: Kind, pose, facing, x, y):
        """A look-alike pose (one picture, two feet points) -> every reading [(pose, x, y)], the one to use without a
        track first: the reading that stands on a surface; none does: the air pose's. With a track, the reading
        that continues its motion wins (`_cost`): a jump passing a platform's level is not standing on it."""
        alts = k.alike.get((pose, facing)) if self.cfg.feet_fix else None
        if not alts:
            return [(pose, x, y)]
        cands = [(pose, x, y)] + [(p2, x + dx, y + dy) for p2, dx, dy in alts]
        on = [c for c in cands if self.nav.platform_at(c[1], c[2], tol=1.5) is not None]
        if len(on) == 1:
            first = on[0]
        elif not on:
            air = [c for c in cands if c[0].startswith(("jump", "fly"))]
            first = air[0] if air else cands[0]
        else:
            first = cands[0]
        return [first] + [c for c in cands if c is not first]

    def _onscreen(self, k: Kind, sx, sy) -> float:
        w, h = max(1, k.rb[0] - k.lt[0]), max(1, k.rb[1] - k.lt[1])
        x0, y0 = sx + k.lt[0], sy + k.lt[1]
        return max(0.0, min(x0 + w, SW) - max(x0, 0)) * max(0.0, min(y0 + h, PLAY_H) - max(y0, 0)) / (w * h)

    def _sights(self, r) -> list:
        C, out, c = r["C"], [], self.cfg
        for m in r["facts"].get("fit") or []:
            k = self.kinds.get(m["type"])
            if k is None:
                continue
            s = Sight()
            x, y = m["feet"][0] + C[0], m["feet"][1] + C[1]
            s.cands = self._settle(k, m["pose"], m["facing"], x, y)
            s.raw, s.C = (x, y), C
            s.kind, s.facing, s.o = m["type"], m["facing"], m["opacity"]
            self._read(s, 0)
            s.on = self._onscreen(k, s.sx, s.sy)
            s.vis = min(1.0, m["n_seen"] / k.full)
            s.solid = s.vis >= c.solid_seen and s.on >= c.solid_on
            out.append(s)
        return out

    def _read(self, s, ci: int):
        """Take reading `ci` of a sighting's look-alike readings: its pose, feet and placement."""
        s.pose, s.x, s.y = s.cands[ci]
        s.sx, s.sy = s.x - s.C[0], s.y - s.C[1]
        s.node, s.air = self._place(s.x, s.y)
        s.die, s.hit = s.pose.startswith("die"), s.pose.startswith("hit")

    # ---- the possible set
    def _grid(self, node):
        if node not in self.grids:
            p = self.nav.platforms[node]
            xs = np.arange(int(p.left), int(p.right) + 1, self.cfg.step, dtype=np.int64)
            ys = np.array([p.y_at(float(x)) if p.y_at(float(x)) is not None else np.nan for x in xs])
            ok = ~np.isnan(ys)
            self.grids[node] = (xs[ok], np.round(ys[ok]).astype(np.int64))
        return self.grids[node]

    def _start_set(self, tr: Tr, k: Kind):
        c = self.cfg
        if k.fly or tr.node is None or tr.node not in self.nav.platforms:
            n = int(c.fly_r // 8)
            g = np.arange(-n, n + 1) * 8
            tr.gx, tr.gy = np.meshgrid(tr.x_seen + g, tr.y_seen + g)
            tr.gx, tr.gy = tr.gx.astype(np.int64), tr.gy.astype(np.int64)
            tr.poss = (np.abs(tr.gx - tr.x_seen) <= 12) & (np.abs(tr.gy - tr.y_seen) <= 12)
        else:
            tr.gx, tr.gy = self._grid(tr.node)
            tr.poss = np.abs(tr.gx - tr.x_seen) <= c.knock + c.step
            if not tr.poss.any() and len(tr.gx):
                tr.poss[np.argmin(np.abs(tr.gx - tr.x_seen))] = True
        tr.carry = 0.0

    def _widen(self, tr: Tr, k: Kind, dt: float):
        step = 8 if tr.poss.ndim == 2 else self.cfg.step
        tr.carry += k.v * dt
        n = int(tr.carry // step)
        if n <= 0:
            return
        tr.carry -= n * step
        p = tr.poss
        for _ in range(min(n, 64)):
            q = p.copy()
            if p.ndim == 1:
                q[1:] |= p[:-1]
                q[:-1] |= p[1:]
            else:
                q[1:, :] |= p[:-1, :]
                q[:-1, :] |= p[1:, :]
                q[:, 1:] |= p[:, :-1]
                q[:, :-1] |= p[:, 1:]
            p = q
        tr.poss = p

    def _test(self, tr: Tr, k: Kind, C, shows, world):
        """Drop every place of the set where the frame shows the scene instead of the body (a jumper: at every
        height of a hop). Sets tr.cover from what is over the places left. -> places left."""
        ii = np.nonzero(tr.poss.ravel())[0]
        if not len(ii):
            return 0
        fx = tr.gx.ravel()[ii] - int(C[0])
        fy = tr.gy.ravel()[ii] - int(C[1])
        n = len(k.cdx)
        heights = range(0, self.cfg.jump_h + 1, 16) if (k.jump and tr.poss.ndim == 1) else (0,)
        absent = np.ones(len(ii), bool)
        n_in = np.zeros(len(ii), np.int64)
        n_world = np.zeros(len(ii), np.int64)
        for hgt in heights:
            xs = fx[:, None] + k.cdx[None, :]
            ys = fy[:, None] + k.cdy[None, :] - hgt
            inside = (xs >= 0) & (xs < SW) & (ys >= 0) & (ys < PLAY_H)
            xc, yc = np.clip(xs, 0, SW - 1), np.clip(ys, 0, PLAY_H - 1)
            absent &= (shows[yc, xc] & inside).sum(axis=1) >= self.cfg.abs_share * n
            if hgt == 0:
                n_in = inside.sum(axis=1)
                n_world = (world[yc, xc] & inside).sum(axis=1)
                xs0, ys0 = xs, ys
        flat = tr.poss.ravel().copy()
        flat[ii[absent]] = False
        tr.poss = flat.reshape(tr.poss.shape)
        left = ~absent
        if not left.any():
            return 0
        # what is over the places left: nothing to check there (off the screen / not judgeable) or something drawn
        checkable = (n_world >= 0.5 * n) & left
        if not checkable.any():
            tr.cover = "out of view" if (n_in[left] < 0.5 * n).all() else "ui / scenery"
        else:
            j = int(np.nonzero(checkable)[0][np.argmin(np.abs(fx[checkable] - (tr.x_seen - C[0])))])
            px, py = xs0[j], ys0[j]
            best, share = "effect", 0.3
            for name, bx in self.boxes.items():
                inb = np.zeros(n, bool)
                for x0, y0, x1, y1 in bx:
                    inb |= (px >= x0) & (px < x1) & (py >= y0) & (py < y1)
                if inb.mean() > share:
                    best, share = name, float(inb.mean())
            tr.cover = best
        return int(left.sum())

    def _boxes(self, r):
        """This frame's known things on screen (boxes): us, other players (their tags), the mobs seen, the drops."""
        f, me = r["facts"], r["me"]
        b = {"us": [], "player": [], "mob": [], "drop": []}
        if me is not None:
            b["us"].append((me[0] - 34, me[1] - 80, me[0] + 34, me[1] + 12))
        for x, y, w, h in f.get("tags") or []:
            cx = x + w / 2
            b["player"].append((cx - 24, y - 70, cx + 24, y))
        for tr in self.tracks:
            if tr.seen:
                k = self.kinds[tr.mob]
                b["mob"].append((tr.sx + k.lt[0], tr.sy + k.lt[1], tr.sx + k.rb[0], tr.sy + k.rb[1]))
        for d in f.get("drops") or []:
            x, y, w, h = d["box"]
            b["drop"].append((x, y, x + w, y + h))
        self.boxes = b

    # ---- association
    def _cost(self, tr: Tr, s: Sight, t: float):
        """The cheapest reading of the sighting for this track -> (cost, reading index) or None."""
        best = None
        floor = self.nav.platforms.get(tr.node) if (len(s.cands) > 1 and tr.node is not None) else None
        ok = list(range(len(s.cands)))
        if floor is not None:                                  # never a reading under the floor it stands on /
            under = [ci for ci in ok if floor.left <= s.cands[ci][1] <= floor.right     # jumped from - unless all are
                     and (floor.y_at(s.cands[ci][1]) or 1e9) + 3 < s.cands[ci][2]]
            if len(under) < len(ok):
                ok = [ci for ci in ok if ci not in under]
        for ci in ok:
            self._read(s, ci)
            v = self._cost1(tr, s, t)
            if v is not None and (best is None or v + (2 if ci else 0) < best[0]):
                best = (v + (2 if ci else 0), ci)
        if len(s.cands) > 1:
            self._read(s, 0)
        return best

    def _cost1(self, tr: Tr, s: Sight, t: float):
        c, k = self.cfg, self.kinds[tr.mob]
        if tr.life == "dying" and not s.die:
            if not (tr.die_t is not None and t - tr.die_t <= c.die_revert_s and abs(s.x - tr.x) <= 8 and abs(s.y - tr.y) <= 8):
                return None
        g = max(0.0, t - tr.t_seen)
        dy = abs(s.y - tr.y_seen)
        if tr.poss is None:                                    # seen on the last frame, or tentative
            gx = c.gate + k.vb * g * 1.5
            gy = (c.gate + k.v * g * 1.5) if k.fly else (14 + 700 * g) if k.jump else 10 + 200 * g
            if abs(s.x - tr.x_seen) > gx or dy > gy:
                return None
            d = abs(s.x - (tr.x_seen + tr.vx * g))
        else:
            if not tr.poss.any():
                return None
            if tr.poss.ndim == 2:
                dd = np.abs(tr.gx[tr.poss] - s.x) + np.abs(tr.gy[tr.poss] - s.y)
                if dd.min() > k.half_w + c.margin + 16:
                    return None
            else:
                dd = np.abs(tr.gx[tr.poss] - s.x)
                lim = k.half_w + c.margin
                if s.node != tr.node:
                    if not k.jump or dy > 110:
                        if dy > 12:
                            return None
                    else:
                        lim += 40
                elif dy > (110 if k.jump else 12):
                    return None
                if dd.min() > lim:
                    return None
            d = abs(s.x - (tr.x_seen + tr.vx * min(g, 0.4))) + c.remembered_cost
        dyp = abs(s.y - (tr.y_seen + tr.vy * g)) if g < 0.1 else dy     # a hop is ballistic: where its motion takes it
        return d + 0.5 * min(dyp, 40) + (0 if s.kind == tr.mob else c.other_type) + (0 if s.facing == tr.facing else c.facing_cost)

    def _apply(self, tr: Tr, s: Sight, t: float):
        if tr.poss is not None:                                # it was remembered: how did that go
            near = True
            if tr.poss.ndim == 1 and tr.poss.any():
                near = bool(np.abs(tr.gx[tr.poss] - s.x).min() <= self.kinds[tr.mob].half_w)
            self.rem.append((t - tr.t_seen, "seen again", near, tr.cover, tr.rin, tr.rout))
            self.episodes.append((tr.id, tr.n_seen_at, self.n, round(tr.x_seen), round(tr.y_seen), "seen again", tr.cover,
                                  round(t - tr.t_seen, 2), round(s.x), round(s.y)))
            tr.rin = tr.rout = 0
        tr.n_seen_at = self.n
        tr.hist.append((t, s.x))
        while len(tr.hist) > 2 and t - tr.hist[0][0] > 0.25:
            tr.hist.pop(0)
        t0, x0 = tr.hist[0]
        tr.vx = (s.x - x0) / (t - t0) if t - t0 >= 0.05 else tr.vx
        # standing = on a surface AND not moving up or down (a jump passing a platform's level is in the air)
        dyf, dxf = abs(s.y - tr.y_seen), abs(s.x - tr.x_seen)
        recent = 0 < t - tr.t_seen < 0.1
        tr.vy = (s.y - tr.y_seen) / (t - tr.t_seen) if 0 < t - tr.t_seen < 0.05 else 0.0
        stand = (not s.air) and (dyf <= 1 + 0.9 * dxf or not recent)   # 0.9 = the steepest slope a mob walks
        tr.x = tr.x_seen = s.x
        tr.y = tr.y_seen = s.y
        tr.sx, tr.sy = s.sx, s.sy
        tr.t_seen, tr.seen, tr.poss, tr.out_since = t, True, None, None
        tr.facing, tr.pose, tr.node, tr.air, tr.cover = s.facing, s.pose, (s.node if stand else tr.node), not stand, "none"
        tr.vis, tr.o = s.vis, s.o
        tr.n_seen += 1
        tr.votes[s.kind] = tr.votes.get(s.kind, 0.0) + max(0.05, s.vis)     # a clear sighting counts for more
        tr.mob = max(tr.votes, key=tr.votes.get)
        if tr.conf is None:
            if s.solid:
                tr.conf = "solid"
            elif t - tr.born >= self.cfg.confirm_s:
                tr.conf = "sighted long"
            if tr.conf:
                self.ev["confirmed: " + tr.conf] += 1
        if s.die:
            if tr.life != "dying":
                tr.life, tr.die_t = "dying", t
        elif tr.life == "dying":
            tr.life, tr.die_t = "alive", None                 # a live pose right after one die sighting: it lives
            self.ev["death taken back"] += 1
        else:
            tr.life = "hit" if s.hit else "alive"

    def _end(self, tr: Tr, how: str, t: float):
        self.ev["end: " + how] += 1
        self.ended[tr.id] = (round(t, 2), how, round(t - tr.t_seen, 2), tr.pose, tr.air, tr.cover)
        if tr.poss is not None:
            self.rem.append((t - tr.t_seen, how, None, tr.cover, tr.rin, tr.rout))
            self.episodes.append((tr.id, tr.n_seen_at, self.n, round(tr.x_seen), round(tr.y_seen), how, tr.cover,
                                  round(t - tr.t_seen, 2), None, None))

    # ---- one frame
    def step(self, r, bits_of) -> list:
        c = self.cfg
        t, C = r["t"], r["C"]
        self.n = r["n"]
        if C is None:                                          # blind: nothing begins, nothing ends
            self.ev["blind frames"] += 1
            return self._rows(t)
        dt = 0.0 if self.t is None else min(1.0, max(0.0, t - self.t))
        if self.t0 is None:
            self.t0 = t
        self.t = t
        ta = time.perf_counter()
        sights = self._sights(r)
        for tr in self.tracks:
            tr.seen = False
        pairs = []
        for j, tr in enumerate(self.tracks):
            for i, s in enumerate(sights):
                v = self._cost(tr, s, t)
                if v is not None:
                    pairs.append((v[0], i, j, v[1]))
        used_s, used_t = set(), set()
        pairs.sort(key=lambda p: p[0])                         # nearest first (a best-total pairing was not tried:
        for _, i, j, ci in pairs:                              # scipy is not in the venv)
            if i in used_s or j in used_t:
                continue
            used_s.add(i)
            used_t.add(j)
            if ci:
                self._read(sights[i], ci)
            if sights[i].cands[ci][1:] != sights[i].raw:
                self.ev["feet settled"] += 1
            self._apply(self.tracks[j], sights[i], t)
        self._boxes(r)
        if self.trace:
            for tr in self.tracks:
                if tr.id in self.trace:
                    k = self.kinds[tr.mob]
                    near = [(round(s.x), round(s.y), s.pose, len(s.cands), None if (v := self._cost(tr, s, t)) is None else round(v[0], 1))
                            for s in sights if abs(s.x - tr.x_seen) < 150 and abs(s.y - tr.y_seen) < 150]
                    ps = tr.gx[tr.poss] if tr.poss is not None and tr.poss.any() else None
                    print(f"   trace {tr.id} n {self.n} t {t:.3f} seen {tr.seen} at ({tr.x_seen:.0f}, {tr.y_seen:.0f}) vy {tr.vy:.0f} node {tr.node} "
                          f"air {tr.air} pose {tr.pose} life {tr.life} conf {tr.conf} set {None if ps is None else (int(ps.min()), int(ps.max()), len(ps))} "
                          f"node y {None if tr.node not in self.nav.platforms else self.nav.platforms[tr.node].y_at(tr.x_seen)} sightings {near}")
        tb = time.perf_counter()
        self.ms["sight + pair"].append(1000 * (tb - ta))
        dec = 0.0
        # ---- the tracks nobody saw
        shows = world = None
        keep = []
        for tr in self.tracks:
            k = self.kinds[tr.mob]
            if tr.seen:
                keep.append(tr)
                continue
            gone = t - tr.t_seen
            if tr.life == "dying":                             # the body is gone when die1 ends (game_rules D4)
                if t - tr.die_t > k.die_s + 0.1:
                    self._end(tr, "died (seen)", t)
                    continue
                keep.append(tr)
                continue
            if tr.conf is None:                                # never seen clearly: no memory
                if gone > c.tentative_s:
                    self.ev["tentative dropped"] += 1
                    continue
                keep.append(tr)
                continue
            if not c.evidence:
                if self._timers(tr, k, t, r):
                    keep.append(tr)
                continue
            if tr.o < 0.9 and gone <= c.fade_s:                # fading in (a spawn): too faint to check yet
                tr.cover = "fading in"
                keep.append(tr)
                continue
            if tr.poss is None:
                self._start_set(tr, k)
            else:
                self._widen(tr, k, dt)
            if shows is None:
                td = time.perf_counter()
                shows, world = bits_of()
                dec = 1000 * (time.perf_counter() - td)
            if shows is None:
                keep.append(tr)
                continue
            left = self._test(tr, k, C, shows, world)
            if left == 0:
                self._end(tr, "gone: its places show the scene", t)
                continue
            if tr.poss.ndim == 2 and (np.abs(tr.gx[tr.poss] - tr.x_seen).max() >= c.fly_r - 8):
                self._end(tr, "lost: a flyer's set outgrew its reach", t)
                continue
            if tr.cover in ("out of view", "ui / scenery"):
                tr.rout += 1
            else:
                tr.rin += 1
            if tr.cover in ("out of view", "ui / scenery"):
                tr.out_since = tr.out_since if tr.out_since is not None else t
                if t - tr.out_since > c.offscreen_s:
                    self._end(tr, "left: nothing to check for 4 s (" + tr.cover + ")", t)
                    continue
            else:
                tr.out_since = None
                if gone > c.drawn_s:
                    self._end(tr, "gone: drawn over for 4 s (" + tr.cover + ")", t)
                    continue
            px = tr.gx[tr.poss]
            tr.x = float(px.mean())
            if tr.poss.ndim == 2:
                tr.y = float(tr.gy[tr.poss].mean())
            else:
                tr.y = float(tr.gy[tr.poss][np.argmin(np.abs(px - tr.x))])
            tr.sx, tr.sy = tr.x - C[0], tr.y - C[1]
            keep.append(tr)
        self.ms["unseen (test)"].append(1000 * (time.perf_counter() - tb) - dec)
        self.ms["replay decode"].append(dec)
        # ---- new tracks
        for i, s in enumerate(sights):
            if i in used_s:
                continue
            k = self.kinds[s.kind]
            if s.on < c.edge_new:
                self.ev["no track: body past the edge"] += 1
                continue
            if s.node is None and not k.fly:
                self.ev["no track: over no platform"] += 1
                continue
            how = ("there at entry" if t - self.t0 < 0.5 else "dying" if s.die else "faded in" if s.o < 0.9
                   else "came into view" if S.edge(s.sx, s.sy) else "uncovered")
            tr = Tr(self.next_id, s, t, how)
            tr.n_seen_at = self.n
            keep.append(tr)
            self.next_id += 1
            self.ev["new: " + how] += 1
            if tr.conf:
                self.ev["confirmed: at once"] += 1
        self.tracks = keep
        return self._rows(t)

    def _timers(self, tr: Tr, k: Kind, t: float, r) -> bool:
        """world.py's ends (lose_s 0.5, fight_s 1.2 near us, offscreen_s 4) on this prototype's tracks: the A/B of
        the memory alone."""
        C, me = r["C"], r["me"]
        tr.sx, tr.sy = tr.x - C[0], tr.y - C[1]
        gone = t - tr.t_seen
        if not (-40 <= tr.sx < SW + 40 and 0 <= tr.sy < PLAY_H + 40):
            tr.cover = "out of view"
            if gone > 4.0:
                self._end(tr, "left: out of view 4 s", t)
                return False
            return True
        tr.cover = "timer"
        near = me is not None and abs(tr.sx - me[0]) <= 140 and -90 <= tr.sy - me[1] <= 20
        if gone > (1.2 if near else 0.5):
            self._end(tr, "timer", t)
            return False
        return True

    def _rows(self, t) -> list:
        out = []
        for tr in self.tracks:
            st = ("tentative" if tr.conf is None else "dying" if tr.life == "dying" else "live" if tr.seen and tr.life == "alive"
                  else "hit" if tr.seen else "offscreen" if tr.cover in ("out of view", "ui / scenery") else "hidden")
            out.append({"id": tr.id, "mob": tr.mob, "state": st, "x": round(tr.x, 1), "y": round(tr.y, 1),
                        "sx": round(tr.sx), "sy": round(tr.sy), "src": "acq" if tr.seen else "none",
                        "unseen": round(t - tr.t_seen, 2), "cover": tr.cover, "node": tr.node, "air": tr.air,
                        "vis": round(tr.vis, 2), "facing": tr.facing})
        return out


# ---------------------------------------------------------------------------------------------------- running it
def run(cap, cfg: Cfg):
    """-> (rows [{"n", "t", "mobs"}], the tracker, ms a frame)."""
    mp = Map(map_of(cap))
    trk = Tracker(mp, cfg)
    d = dump.out_dir(cap)
    rows, ms = [], []
    for kch in range(dump.meta(cap)["chunks"]):
        rs = pickle.loads((d / f"rows_{kch:03d}.pkl").read_bytes())
        bs = pickle.loads((d / f"bits_{kch:03d}.pkl").read_bytes())
        for r, (n, sh, wo) in zip(rs, bs):
            assert n == r["n"]

            def bits_of(sh=sh, wo=wo):
                return (dump.bits(sh), dump.bits(wo)) if sh is not None else (None, None)
            a = time.perf_counter()
            mobs = trk.step(r, bits_of)
            ms.append(1000 * (time.perf_counter() - a))
            rows.append({"n": r["n"], "t": r["t"], "mobs": mobs})
    return rows, trk, np.array(ms)


def cands(mobs, typ, x, y, r=24.0) -> dict:
    """Every confirmed track of this type within r of (x, y): id -> distance."""
    out = {}
    for m in mobs:
        if m["state"] == "tentative" or m["mob"] != typ:
            continue
        dx, dy = abs(m["x"] - x), abs(m["y"] - y)
        if dx <= r and dy <= r:
            out[m["id"]] = dx + dy + (1000 if m.get("src", "none") == "none" else 0)
    return out


def sticky(tk, ch, rows) -> dict:
    """The fair identity count. score.py takes the NEAREST track at every tick, so two mobs standing within 24 px
    make "switches" on tracks that never changed. Here the chain keeps its track for as long as that track is
    still within 24 px of it; a switch is counted only when it is not. -> extra ids per chain, and per gap
    (alive, unseen, by length) whether the track before it is still on the mob after it."""
    n2i = {k["n"]: i for i, k in enumerate(tk)}
    row_at = {n2i[r["n"]]: r for r in rows if r["n"] in n2i}
    cis = S.index(tk, ch)
    near = {}                                              # tick -> [(x, y, chain, type)]: who else is there
    for kc, ci in enumerate(cis):
        for i, q in ci["pts"].items():
            near.setdefault(i, []).append((q[S.X], q[S.Y], kc, ci["c"]["type"]))
    sw, sw_clear, gaps = [], [], []
    for kc, ci in enumerate(cis):
        typ, cur, n_sw, n_clear, last_i = ci["c"]["type"], None, 0, 0, None
        gap_of = {b: a for a, b in ci["gaps"]}
        for i in sorted(ci["pts"]):
            q = ci["pts"][i]
            if S.anim_of(q[S.POSE]).startswith("die") or i not in row_at:
                continue
            cs = cands(row_at[i]["mobs"], typ, q[S.X], q[S.Y])
            if i in gap_of and last_i is not None and cur is not None:
                gaps.append((tk[i]["t"] - tk[gap_of[i]]["t"], cur in cs))
            if cs:
                if cur is None:
                    cur = min(cs, key=cs.get)
                elif cur not in cs:
                    cur = min(cs, key=cs.get)
                    n_sw += 1
                    crowd = any(k2 != kc and ty == typ and abs(x - q[S.X]) <= 60 and abs(y - q[S.Y]) <= 45
                                for x, y, k2, ty in near.get(i, []) + near.get(last_i, []))
                    n_clear += not crowd
                last_i = i
        sw.append(n_sw)
        sw_clear.append(n_clear)
    return {"sw": sw, "sw_clear": sw_clear, "gaps": gaps}


def sticky_report(st, name="") -> str:
    sw, sc = np.array(st["sw"]), np.array(st["sw_clear"])
    L = [f"  FAIR IDS {name}: {int(sw.sum())} extra ids over {len(sw)} chains; one id for life on {100 * np.mean(sw == 0):.1f} %; "
         f"not counting a change beside another mob of its kind (within 60 px): {int(sc.sum())} extra ids, one id on {100 * np.mean(sc == 0):.1f} %"]
    g = st["gaps"]
    parts = []
    for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.5), (1.5, 99)):
        b = [h for d, h in g if lo < d <= hi]
        if b:
            parts.append(f"{lo}-{hi if hi < 99 else '4'} s {100 * np.mean(b):.1f} % ({len(b)})")
    L.append(f"  FAIR HELD: {100 * np.mean([h for _, h in g]) if g else 0:.1f} % of {len(g)} gaps; " + ", ".join(parts))
    return "\n".join(L)


def own_report(trk: Tracker, ms, rows) -> str:
    L = []
    ev = trk.ev
    L.append("  born: " + ", ".join(f"{k[5:]} {v}" for k, v in sorted(ev.items()) if k.startswith("new: ")))
    L.append("  ended: " + ", ".join(f"{k[5:]} {v}" for k, v in sorted(ev.items()) if k.startswith("end: ")))
    L.append("  other: " + ", ".join(f"{k} {v}" for k, v in sorted(ev.items()) if not k.startswith(("new: ", "end: "))))
    rem = trk.rem
    if rem:
        again = [x for x in rem if x[1] == "seen again"]
        dur = np.array([x[0] for x in again]) if again else np.array([0.0])
        ins = [x[2] for x in again if x[2] is not None]
        L.append(f"  remembered {len(rem)} times; seen again {len(again)} (s p50/p90/p99/max {S.pct(dur, (50, 90, 99, 100))}); "
                 f"next to its set {100 * np.mean(ins) if ins else 0:.2f} % of {len(ins)}")
        for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.5), (1.5, 4), (4, 1e9)):
            b = [x for x in rem if lo < x[0] <= hi]
            if b:
                L.append(f"     unseen {lo}-{hi if hi < 1e9 else 'more'} s: {len(b):5d} -> " + ", ".join(f"{k} {v}" for k, v in Counter(x[1] for x in b).most_common()))
    hid = Counter()
    for r in rows:
        for m in r["mobs"]:
            if m["state"] in ("hidden", "offscreen"):
                hid[m["cover"]] += 1
    L.append("  remembered track-frames by cover: " + ", ".join(f"{k} {v}" for k, v in hid.most_common()))
    L.append(f"  cost in Python: ms a frame p50 / p90 / p99 / max {S.pct(ms, (50, 90, 99, 100))}; parts p50 / p90 / p99: "
             + ", ".join(f"{k} {S.pct(v, (50, 90, 99))}" for k, v in trk.ms.items()))
    return "\n".join(L)


def mem_report(rems) -> str:
    """What the memory was worth: the frames a track was remembered IN VIEW (something drawn over its places), by
    how that ended - seen again (it was there), its places showed the scene (it had gone), the 4 s limit."""
    by = Counter()
    for x in rems:
        how = "seen again" if x[1] == "seen again" else "found gone" if x[1].startswith("gone: its places") else \
            "limit: drawn over 4 s" if x[1].startswith("gone: drawn") else "limit: nothing to check 4 s" if x[1].startswith("left") else x[1]
        by[how] += x[4]
    tot = max(1, sum(by.values()))
    L = [f"  frames remembered in view: {sum(by.values())}; by how it ended: " + ", ".join(f"{k} {v} ({100 * v / tot:.1f} %)" for k, v in by.most_common())]
    for lo, hi in ((0, 0.1), (0.1, 0.3), (0.3, 0.6), (0.6, 1.5), (1.5, 4), (4, 1e9)):
        b = [x for x in rems if lo < x[0] <= hi]
        if b:
            c = Counter("seen again" if x[1] == "seen again" else "found gone" if x[1].startswith("gone: its") else "limit / left" for x in b)
            L.append(f"     unseen {lo}-{hi if hi < 1e9 else 'more'} s: {len(b):5d} -> " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    L.append("  by what was over it when it ended (times seen again by seconds unseen: <= 0.3 / 0.3-1 / 1-2 / 2-4 / more | found gone | limit):")
    for cov in sorted({x[3] for x in rems}):
        b = [x for x in rems if x[3] == cov]
        ag = [x[0] for x in b if x[1] == "seen again"]
        L.append(f"     {cov:14s} {sum(1 for d in ag if d <= 0.3):5d} / {sum(1 for d in ag if 0.3 < d <= 1):4d} / {sum(1 for d in ag if 1 < d <= 2):4d} / "
                 f"{sum(1 for d in ag if 2 < d <= 4):4d} / {sum(1 for d in ag if d > 4):3d} | {sum(1 for x in b if x[1].startswith('gone: its')):4d} | "
                 f"{sum(1 for x in b if x[1].startswith(('gone: drawn', 'left', 'lost'))):4d}")
    return "\n".join(L)


def truth_places(tk, ch) -> dict:
    out = {}
    for ci in S.index(tk, ch):
        for i in range(ci["i0"], ci["i1"] + 1):
            p = S.pos_at(ci, i)
            if p is not None:
                out.setdefault(i, []).append(p)
    return out


def ghosts_by_state(tk, ch, rows) -> str:
    """score.py's GHOST split by what the track says: seen now (live / hit) or remembered (hidden)."""
    n2i = {k["n"]: i for i, k in enumerate(tk)}
    alive = truth_places(tk, ch)
    g = {"seen": [0, 0], "remembered": [0, 0]}
    for r in rows:
        ps = alive.get(n2i.get(r["n"]), [])
        for m in r["mobs"]:
            if m["state"] not in S.LIVE or not (0 <= m["sx"] < SW and 0 <= m["sy"] < PLAY_H):
                continue
            key = "seen" if m["src"] != "none" else "remembered"
            g[key][0] += 1
            g[key][1] += not any(abs(m["x"] - x) <= 40 and abs(m["y"] - y) <= 40 for x, y in ps)
    return (f"  GHOST by state: seen {g['seen'][1]} of {g['seen'][0]} ({100 * g['seen'][1] / max(1, g['seen'][0]):.2f} %), "
            f"remembered {g['remembered'][1]} of {g['remembered'][0]} ({100 * g['remembered'][1] / max(1, g['remembered'][0]):.1f} %)")


def why_switch(tk, ch, rows, trk, n_ex: int = 0) -> str:
    """Each fair id switch along a truth chain, by what became of the old track."""
    n2i = {k["n"]: i for i, k in enumerate(tk)}
    row_at = {n2i[r["n"]]: r for r in rows if r["n"] in n2i}
    why, ex = Counter(), []
    for ci in S.index(tk, ch):
        typ, cur, last_i = ci["c"]["type"], None, None
        for i in sorted(ci["pts"]):
            q = ci["pts"][i]
            if S.anim_of(q[S.POSE]).startswith("die") or i not in row_at:
                continue
            cs = cands(row_at[i]["mobs"], typ, q[S.X], q[S.Y])
            if not cs:
                continue
            if cur is not None and cur not in cs:
                old = next((x for x in row_at[i]["mobs"] if x["id"] == cur), None)
                if old is None:
                    e = trk.ended.get(cur)
                    w = "old track ended: " + (e[1] if e else "tentative / ?") + (" (in the air)" if e and e[4] else "")
                else:
                    d = abs(old["x"] - q[S.X]) + abs(old["y"] - q[S.Y])
                    w = (f"old track still there, {'near' if d <= 60 else 'far'}, "
                         f"{'seen' if old['src'] != 'none' else 'remembered'}{', other kind' if old['mob'] != typ else ''}")
                    if d <= 60 and old["src"] != "none" and "facing" in old:
                        # who changed mob - the track or the truth? Over the last 40 frames (the two were within
                        # 24 px of each other for a while before the change shows): the one that turned round
                        # while the other kept its facing took the other mob (mobs walk through each other).
                        win = [j for j in range(i - 40, i + 1) if j in ci["pts"] and j in row_at]
                        cf = [ci["pts"][j][5] for j in win]
                        tf = [m["facing"] for j in win for m in row_at[j]["mobs"] if m["id"] == cur and m["src"] != "none"]
                        c_fl = sum(1 for a, b in zip(cf, cf[1:]) if a != b)
                        t_fl = sum(1 for a, b in zip(tf, tf[1:]) if a != b)
                        w += (": the truth's mob turned round, the track did not (the truth changed mob)" if c_fl and not t_fl else
                              ": the track turned round, the truth's mob did not (the track changed mob)" if t_fl and not c_fl else
                              ": both or neither turned round (cannot say)")
                why[w] += 1
                if len(ex) < n_ex:
                    ex.append((round(q[S.T], 2), w, int(q[S.SX]), int(q[S.SY]), cur, min(cs, key=cs.get), i - last_i, trk.ended.get(cur)))
                cur = min(cs, key=cs.get)
            elif cur is None:
                cur = min(cs, key=cs.get)
            last_i = i
    why_switch.last = why
    L = [f"  FAIR SWITCHES by why ({sum(why.values())}):"] + [f"    {n:4d}  {w}" for w, n in why.most_common()]
    return "\n".join(L + [f"      {e}" for e in ex])


def ghost_tracks(tk, ch, rows, top: int = 10) -> str:
    """The remembered tracks with the most frames the truth has no mob for: id, frames, when, where, covers."""
    n2i = {k["n"]: i for i, k in enumerate(tk)}
    alive = truth_places(tk, ch)
    g = {}
    for r in rows:
        ps = alive.get(n2i.get(r["n"]), [])
        for m in r["mobs"]:
            if m["state"] not in S.LIVE or m["src"] != "none" or not (0 <= m["sx"] < SW and 0 <= m["sy"] < PLAY_H):
                continue
            if not any(abs(m["x"] - x) <= 40 and abs(m["y"] - y) <= 40 for x, y in ps):
                e = g.setdefault(m["id"], {"n": 0, "t0": r["t"], "t1": r["t"], "n0": r["n"], "sx": m["sx"], "sy": m["sy"], "cov": Counter()})
                e["n"] += 1
                e["t1"], e["n1"] = r["t"], r["n"]
                e["cov"][m["cover"]] += 1
    L = [f"  remembered tracks the truth has no mob for (within 40 px): {len(g)}"]
    for i, e in sorted(g.items(), key=lambda kv: -kv[1]["n"])[:top]:
        L.append(f"    id {i}: {e['n']} frames, t {e['t0']:.2f}-{e['t1']:.2f} (frames {e['n0']}-{e.get('n1')}), first at screen "
                 f"({e['sx']}, {e['sy']}), cover {dict(e['cov'])}")
    return "\n".join(L)


def merge_sticky(sts: list) -> dict:
    return {k: [x for s in sts for x in s[k]] for k in ("sw", "sw_clear", "gaps")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("caps", nargs="*")
    ap.add_argument("--why", type=int, default=-1, help="classify the id switches and list the ghost tracks (+ N examples)")
    ap.add_argument("--sound", action="store_true")
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="only the pooled report")
    a = ap.parse_args()
    cfg = Cfg()
    types = {f.name: f.type for f in fields(Cfg)}
    for kv in a.set:
        k, v = kv.split("=")
        setattr(cfg, k, (v == "True") if types[k] is bool else types[k](v))
    caps = cache.SOUND if a.sound else a.caps
    ss, st, fs, ft, all_ms, evs, rems, whys = [], [], [], [], [], Counter(), [], Counter()
    for cap in caps:
        tk = ticks(cap)
        ch = cache.chains(cap, tk)
        rows, trk, ms = run(cap, cfg)
        s = S.score(tk, ch, rows, S.me_fn(tk))
        f = sticky(tk, ch, rows)
        ss.append(s)
        fs.append(f)
        all_ms.append(ms)
        evs.update(trk.ev)
        rems += trk.rem
        if not a.quiet:
            print(S.report(s, f"{name_of(cap)} [prototype]"))
            print(sticky_report(f))
            print(ghosts_by_state(tk, ch, rows))
            print(own_report(trk, ms, rows), flush=True)
            if a.why >= 0:
                print(why_switch(tk, ch, rows, trk, a.why))
                print(ghost_tracks(tk, ch, rows), flush=True)
        elif a.why >= 0:
            why_switch(tk, ch, rows, trk, 0)
        if a.why >= 0:
            whys.update(why_switch.last)
        if a.today:
            s0 = S.score(tk, ch, tk, S.me_fn(tk))
            f0 = sticky(tk, ch, tk)
            st.append(s0)
            ft.append(f0)
            if not a.quiet:
                print(S.report(s0, f"{name_of(cap)} [today]"))
                print(sticky_report(f0), flush=True)
    if len(ss) > 1 or a.quiet:
        print(S.report(S.merge(ss), f"POOLED prototype ({len(ss)} captures) {' '.join(a.set)}"))
        print(sticky_report(merge_sticky(fs)))
        print("  ended: " + ", ".join(f"{k[5:]} {v}" for k, v in sorted(evs.items()) if k.startswith("end: ")))
        print("  other: " + ", ".join(f"{k} {v}" for k, v in sorted(evs.items()) if not k.startswith("end: ")))
        again = [x for x in rems if x[1] == "seen again" and x[2] is not None]
        print(f"  remembered {len(rems)} times; seen again {len(again)}, next to its set {100 * np.mean([x[2] for x in again]) if again else 0:.2f} %")
        print(mem_report(rems))
        if whys:
            print(f"  FAIR SWITCHES by why, all captures ({sum(whys.values())}):")
            for w, n in whys.most_common():
                print(f"    {n:4d}  {w}")
        print(f"  cost in Python, all frames: ms p50 / p90 / p99 {S.pct(np.concatenate(all_ms), (50, 90, 99))}")
        if st:
            print(S.report(S.merge(st), f"POOLED today ({len(st)} captures)"))
            print(sticky_report(merge_sticky(ft)))


if __name__ == "__main__":
    main()
