"""The mob tracker (PLAN-tracker.md design 4; docs/state_model.md sections 2-3). Memory by evidence instead of
timers. The reference is the prototype tools/perc/track/proto_mobs.py (version 5, measurement 1): its rules and
constants (config.Track) are ported, not redesigned; the placement is the graph's one rule (track/graph.py, design 3)
and the evidence one interface with two sources (track/evidence.py, design 2). Nothing here knows the brain.

Per frame, `update(facts, evidence)`: perception's facts of the frame (perception/facts.FrameFacts: the fit's mobs,
the camera, the players' tags, the drops, our tag) -> the mob records (track/state.Mob) and this frame's events.

1. SIGHTINGS: each fit mob of a known kind, its feet on the map (screen feet + the camera). A look-alike pose (one
   picture under two feet points, track/kinds.py) gives every reading; the first choice is the reading that stands
   on a surface (within settle_tol), none does: the jump / fly pose's. A sighting is CLEAR when it shows solid_seen
   of its kind's full size with solid_on of its body box on screen.
2. PAIRING, one cost over every track x every reading (arrays): the distance to where the track's motion puts it
   (a track seen on the last frame: within gate + gate_v x its bound x the time; in y a walker 10 + 200 t, a jumper
   14 + 700 t, a flyer like x), half the vertical distance (at most dy_cap; a hop: from its own vertical motion),
   other_type for another kind, facing_cost for a turned facing; a remembered track: a sighting within half a body
   + margin of its possible set (a jumper also on another node, within 110 px up or down and 40 px more sideways),
   + remembered_cost. A reading under the floor the track stands on / jumped from is not taken (unless all are);
   another reading of a look-alike pose costs alt_cost more. Then nearest first, each track and sighting once.
3. A PAIRED track: placed by the graph's rule with its step since the last frame (stand: within 3 px of a surface
   and not moving up or down; its node changes only on stand), its speed over its last 0.25 s, its kind voted (a
   clear sighting counts for more), confirmed by a clear sighting or after confirm_s of sightings, its life from
   the pose and the fade's direction (the user, 2026-11-25: "dying needs falling opacity, a spawn needs rising"): a die
   pose at full opacity (die_full_o 0.99, checked first: a death starts there) = dying; under it the direction from
   two NEIGHBOURING sightings - fallen = dying, rising or flat = the live mob (a spawn's landing squash read as
   die1_2: PLAN-tracker "Step 3b, try 3"); on a track not seen on the frame before, the die pose is HELD and judged on
   its next sighting (fallen: dying from the held frame). A live-mob or held die pose keeps the track's last feet
   and place (its reading's are 18 px off). A live pose within die_revert_s of the first die pose takes a death back.
4. A track NOT SEEN: dying -> gone when its die1 animation is over (+ die_extra_s); tentative -> dropped after
   tentative_s; last seen fading in -> not checked for fade_s; else its POSSIBLE SET - the places of its node every
   set_step px, starting knock + set_step either side of where it was last seen, widening at its kind's speed (a
   flyer: a square grid every fly_step px, within fly_r) - is tested on this frame: a place is EMPTY when abs_share
   of the body's core shows the scene (a jumper: at every height of a hop, every jump_dh up to jump_h). Empty set:
   gone at once. Nothing to check (out of view, behind the UI or animated scenery): kept offscreen_s; something
   drawn over it: kept drawn_s since it was last seen; `cover` = "edge" when its body box at x, y crosses the
   screen's left or right side or the window's bottom (the edge wins over what covers its in-view part: the user,
   2026-11-24; the top is not an edge: step 3's carry-over 2, L2 case 30), else what is over the nearest place left
   (us, a player, a seen mob, a drop by their boxes; else an effect). Us and the players come from the SORTED tag
   list when the caller gives it (track/players.py + track/us.py, step 4b: our tag, other characters and their pets
   at their own widths - not mobs' own name tags, log lines or text); without it every tag is a player's box (step
   3). x, y = the middle of the places left.
5. NEW TRACKS from the sightings left over (not over a platform and not a flyer: none), with two fields (the user,
   2026-11-24): how it came into sight - "there at entry" (within entry_s of the first frame with a camera),
   "faded in" (opacity under fade_o in a live pose AND rising by more than fade_rise within its first fade_k
   sightings: a spawn fades in; flat or falling - seen through an effect - it is "came into view" / "uncovered" as
   below; until settled the record says "faded in" and its mob_new event waits), "came into view" (at the screen's
   edge) or "uncovered" - and its first pose (`first_pose`: a die pose = first seen dying; a die pose is faint
   because the death fades it out); tentative until confirmed (then a `mob_new` event).
6. THE HP METERS (PLAN-tracker step 5a; perception/meters.py finds them and reads each one's green share): a meter
   names the fit's sightings whose expected meter box it is at; it teaches `hp` (0..1) and `hp_t` to the one track
   whose sighting it names alone, when its fill was read and no other track overlaps that mob (`_overlapped`; design 1:
   a meter over two overlapping mobs teaches nothing). `hp` is kept while the track lives; None = never read.
A frame without a camera (blind) changes nothing: the records keep their values with cover "blind" and `seen` False
(nothing is found on it; the prototype kept a track seen on the frame before "seen" through the blind frames).
Events: mob_new (confirmed; how born), mob_died (a die pose seen, its animation over), mob_gone (its places show the
scene / drawn over for drawn_s / a flyer's set outgrew fly_r), mob_left (nothing to check for offscreen_s).
"""
import time
from collections import Counter

import numpy as np

from ..config import Track
from .graph import FLY, NONE, PLACES, STAND
from .state import Mob

SW, PLAY_H, SH = 1366, 700, 768
OUT = ("out of view", "ui / scenery")               # covers with nothing to check
FACING = {"left": -1, "right": 1}


class _Tr:
    """One track (the prototype's Tr)."""
    __slots__ = ("id", "votes", "mob", "x", "y", "t_seen", "born", "vx", "vy", "facing", "pose", "node", "air",
                 "life", "die_t", "seen", "poss", "gx", "gy", "carry", "out_since", "x_seen", "y_seen", "sx", "sy",
                 "born_how", "n_seen", "cover", "hist", "conf", "vis", "o", "rin", "rout", "n_seen_at", "place",
                 "cur_node", "off", "n_frames", "first_pose", "how_alt", "o0", "new_held", "seen_prev",
                 "hold_o", "hold_t", "hp", "hp_t", "fi")

    def __init__(self, tid, kind, pose, facing, x, y, sx, sy, node, air, place, off, o, vis, solid, die, t, how):
        self.id, self.votes, self.mob = tid, {kind: 1.0}, kind
        self.x = self.x_seen = x
        self.y = self.y_seen = y
        self.t_seen = self.born = t
        self.vx, self.vy, self.facing, self.pose, self.first_pose = 0.0, 0.0, facing, pose, pose
        self.node, self.air, self.place, self.cur_node, self.off = node, air, place, node, off
        self.life = "dying" if die else "alive"
        self.die_t = t if die else None
        self.seen, self.poss, self.gx, self.gy, self.carry = True, None, None, None, 0.0
        self.out_since = None
        self.sx, self.sy = sx, sy
        self.born_how, self.n_seen, self.cover = how, 1, "none"
        self.hist = [(t, x)]
        self.conf = "solid" if solid else None
        self.vis, self.o = vis, o
        self.rin = self.rout = 0                        # frames remembered in view / with nothing to check
        self.n_seen_at = None
        self.n_frames = 1                               # frames with a camera since birth
        self.how_alt = None                             # a faint birth not settled yet: how it came into sight if its
        self.o0 = o                                     # opacity does not rise from o0 (else "faded in")
        self.new_held = False                           # its mob_new event waits for that
        self.seen_prev = False                          # seen on the frame before this one (blind frames skipped)
        self.hold_o = self.hold_t = None                # a die pose under die_full_o on a remembered track: held,
                                                        # judged on its next sighting (its opacity and time)
        self.hp = self.hp_t = None                      # its HP meter's last reading taught (0..1) and when (step 5a)
        self.fi = None                                  # this frame: the index into facts.fit of its sighting


class _Readings:
    """This frame's sightings and their readings, padded to (S, M): M = the most readings of one sighting."""
    __slots__ = ("S", "M", "n", "ok", "x", "y", "pose", "node", "air", "place", "off", "die", "hit", "kind",
                 "facing", "o", "vis", "on", "solid", "raw_x", "raw_y", "C", "src")


class MobTracker:
    """`graph`: the map's track/graph.Graph (nodes and placement; no edges needed); `kinds`: track/kinds.kinds();
    `cfg`: config.Track. `keep` True: the episodes of memory and the ends are kept for the tools (`episodes`,
    `ended`); `stats` counts how tracks were born / ended / what the memory did."""

    def __init__(self, graph, kinds: dict, cfg: Track | None = None, keep: bool = False):
        self.g, self.kinds, self.cfg = graph, kinds, cfg or Track()
        self.tracks: list = []
        self.next_id, self.t, self.t0, self.n = 1, None, None, None
        self.grids = {}                                 # node id -> (xs, ys) of its places
        self.stats = Counter()
        self.keep = keep
        self.rem = []                                   # keep: (unseen s, how it ended, next to its set?, cover, rin, rout)
        self.episodes = []                              # keep: (id, frame last seen, frame it ended, x, y, how, cover,
                                                        # seconds, x, y seen again)
        self.ended = {}                                 # keep: id -> (t, how, unseen s, pose, air, cover)
        self.ms = {}                                    # the last frame's parts
        self.asked = 0                                  # places tested on the last frame
        self.records: list = []
        self._ev = []

    # ------------------------------------------------------------------ one frame
    def update(self, facts, evidence, n=None, tags=None) -> list:
        """-> this frame's events; `records` = the mob records (track/state.Mob), tentative tracks included. `tags`:
        the sorted tags' boxes on the screen, {"us": [(x0, y0, x1, y1)], "player": [...]} (bodies, not the tags), or
        a callable that returns them - called only when a cover is named, after this frame's evidence transfer (the
        players' body question rides in it: step 4b try 2); None: our tag = facts.tag and every tag of facts.tags a
        player's."""
        c = self.cfg
        t, C = facts.t, facts.scene_cam
        self.n, self._ev = n, []
        if C is None:                                   # blind: nothing begins, nothing ends
            self.stats["blind frames"] += 1
            self.records = self._records(t, blind=True)
            return self._ev
        dt = 0.0 if self.t is None else min(1.0, max(0.0, t - self.t))
        if self.t0 is None:
            self.t0 = t
        self.t = t
        ta = time.perf_counter()
        R = self._sights(facts, C)
        for tr in self.tracks:
            tr.seen_prev, tr.seen = tr.seen, False
            tr.n_frames += 1
            tr.fi = None
        used_s = self._pair(R, t)
        tb = time.perf_counter()
        got = []

        def boxes():                                    # the known things' boxes, made on the first need
            if not got:
                got.append(self._boxes(facts, tags() if callable(tags) else tags))
            return got[0]
        keep = self._unseen(t, dt, C, evidence, boxes)
        tc = time.perf_counter()
        self._born(R, used_s, t, keep)
        self.tracks = keep
        self._meters(facts, t)
        self.records = self._records(t)
        self.ms = {"pair": 1000 * (tb - ta), "unseen": 1000 * (tc - tb), "new": 1000 * (time.perf_counter() - tc)}
        return self._ev

    # ------------------------------------------------------------------ sightings
    def _sights(self, facts, C) -> _Readings:
        c, g = self.cfg, self.g
        R = _Readings()
        R.C = C
        S, rows = 0, []
        for q, m in enumerate(facts.fit or []):
            k = self.kinds.get(m["type"])
            if k is None:
                continue
            x, y = m["feet"][0] + C[0], m["feet"][1] + C[1]
            alts = k.alike.get((m["pose"], m["facing"]))
            cands = [(m["pose"], x, y)] + ([(p2, x + dx, y + dy) for p2, dx, dy in alts] if alts else [])
            rows.append((k, m, x, y, cands, q))
            S += 1
        R.S = S
        if not S:
            R.M = 1
            return R
        R.src = [r[5] for r in rows]                    # the sighting's index into facts.fit (the meters name it)
        multi = [r for r in rows if len(r[4]) > 1]
        if multi:                                       # the first choice: the one reading that stands on a surface
            xs = np.array([cd[1] for r in multi for cd in r[4]], np.float64)
            ys = np.array([cd[2] for r in multi for cd in r[4]], np.float64)
            on = g.nearest(xs, ys, c.settle_tol)[0] != NONE
            a = 0
            for r in multi:
                cands, n = r[4], len(r[4])
                o = on[a:a + n]
                a += n
                if o.sum() == 1:
                    first = int(np.argmax(o))
                elif not o.any():
                    air = [i for i, cd in enumerate(cands) if cd[0].startswith(("jump", "fly"))]
                    first = air[0] if air else 0
                else:
                    first = 0
                if first:
                    cands[:] = [cands[first]] + [cd for i, cd in enumerate(cands) if i != first]
        M = max(len(r[4]) for r in rows)
        R.M = M
        R.n = np.array([len(r[4]) for r in rows], np.int64)
        R.ok = np.arange(M)[None, :] < R.n[:, None]
        R.x = np.zeros((S, M))
        R.y = np.zeros((S, M))
        R.pose = np.empty((S, M), object)
        for i, r in enumerate(rows):
            for j, (p, x, y) in enumerate(r[4]):
                R.x[i, j], R.y[i, j], R.pose[i, j] = x, y, p
        R.kind = np.array([r[0].id for r in rows], np.int64)
        R.facing = np.array([FACING.get(r[1]["facing"], 0) for r in rows], np.int64)
        R.o = np.array([r[1]["opacity"] for r in rows], np.float64)
        fly = np.repeat(np.array([r[0].fly for r in rows]), M)
        P = g.place(R.x.ravel(), R.y.ravel(), fly=fly)
        R.place = P.place.reshape(S, M)
        R.air = R.place != STAND
        R.node = P.node.reshape(S, M)
        R.off = P.off.reshape(S, M)
        pre = np.array([[str(p).startswith("die") if p is not None else False for p in row] for row in R.pose])
        R.die = pre.reshape(S, M)
        R.hit = np.array([[str(p).startswith("hit") if p is not None else False for p in row] for row in R.pose])
        R.raw_x = np.array([r[2] for r in rows])
        R.raw_y = np.array([r[3] for r in rows])
        # clear: from reading 0 (the screen feet, as the fit names them or settled)
        lt = np.array([r[0].lt for r in rows], np.float64)
        rb = np.array([r[0].rb for r in rows], np.float64)
        w, h = np.maximum(1, rb[:, 0] - lt[:, 0]), np.maximum(1, rb[:, 1] - lt[:, 1])
        x0, y0 = R.x[:, 0] - C[0] + lt[:, 0], R.y[:, 0] - C[1] + lt[:, 1]
        R.on = (np.maximum(0.0, np.minimum(x0 + w, SW) - np.maximum(x0, 0))
                * np.maximum(0.0, np.minimum(y0 + h, PLAY_H) - np.maximum(y0, 0)) / (w * h))
        full = np.array([r[0].full for r in rows])
        R.vis = np.minimum(1.0, np.array([r[1]["n_seen"] for r in rows], np.float64) / full)
        R.solid = (R.vis >= c.solid_seen) & (R.on >= c.solid_on)
        return R

    # ------------------------------------------------------------------ pairing
    def _costs(self, R: _Readings, t: float):
        """-> (cost (T, S): the cheapest reading of each sighting for each track, inf: not possible; its index)."""
        c, trs = self.cfg, self.tracks
        T, S, M = len(trs), R.S, R.M
        kd = [self.kinds[tr.mob] for tr in trs]

        def col(v):
            return np.asarray(v)[:, None, None]
        vb = np.array([k.vb for k in kd])
        v = np.array([k.v for k in kd])
        fly = np.array([k.fly for k in kd])
        jump = np.array([k.jump for k in kd])
        xs = np.array([tr.x_seen for tr in trs], np.float64)
        ys = np.array([tr.y_seen for tr in trs], np.float64)
        vx = np.array([tr.vx for tr in trs], np.float64)
        vy = np.array([tr.vy for tr in trs], np.float64)
        g = np.maximum(0.0, t - np.array([tr.t_seen for tr in trs], np.float64))
        rem = np.array([tr.poss is not None for tr in trs])
        rx, ry = R.x[None], R.y[None]
        dy = np.abs(ry - col(ys))
        bad = np.broadcast_to(~R.ok[None], (T, S, M)).copy()
        # a dying track takes a live pose only right after its first die pose, where it died
        dying = np.array([tr.life == "dying" for tr in trs])
        if dying.any():
            die_t = np.array([np.nan if tr.die_t is None else tr.die_t for tr in trs], np.float64)
            back = (col(t - die_t <= c.die_revert_s) & (np.abs(rx - col([tr.x for tr in trs])) <= c.die_revert_px)
                    & (np.abs(ry - col([tr.y for tr in trs])) <= c.die_revert_px))
            bad |= col(dying) & ~R.die[None] & ~back
        # seen on the last frame, or tentative: near where its motion puts it
        gxl = c.gate + vb * g * c.gate_v
        gyl = np.where(fly, c.gate + v * g * c.gate_v,
                       np.where(jump, c.gate_y_jump[0] + c.gate_y_jump[1] * g, c.gate_y[0] + c.gate_y[1] * g))
        d = np.abs(rx - col(xs + vx * g))
        bad_new = (np.abs(rx - col(xs)) > col(gxl)) | (dy > col(gyl))
        if rem.any():                                   # remembered: next to its possible set
            d = np.where(col(rem), np.abs(rx - col(xs + vx * np.minimum(g, c.mem_vx_s))) + c.remembered_cost, d)
            for j in np.flatnonzero(rem):
                tr, k = trs[j], kd[j]
                if not tr.poss.any():
                    bad_new[j] = True
                    continue
                if tr.poss.ndim == 2:
                    px, py = tr.gx[tr.poss], tr.gy[tr.poss]
                    dd = (np.abs(px[:, None, None] - R.x) + np.abs(py[:, None, None] - R.y)).min(0)
                    bad_new[j] = dd > k.half_w + c.margin + c.mem_fly_x
                    continue
                dd = np.abs(tr.gx[tr.poss][:, None, None] - R.x).min(0)
                if k.jump:
                    lim = k.half_w + c.margin + np.where(R.node != tr.node, c.mem_jump_x, 0.0)
                    bad_new[j] = (dy[j] > c.mem_dy_jump) | (dd > lim)
                else:
                    bad_new[j] = (dy[j] > c.mem_dy) | (dd > k.half_w + c.margin)
        bad |= bad_new
        dyp = np.where(col(g < c.ballistic_s), np.abs(ry - col(ys + vy * g)), dy)
        mob = np.array([tr.mob for tr in trs], np.int64)
        face = np.array([tr.facing for tr in trs], np.int64)
        cost = (d + 0.5 * np.minimum(dyp, c.dy_cap) + np.where(R.kind[None, :, None] == col(mob), 0.0, c.other_type)
                + np.where(R.facing[None, :, None] == col(face), 0.0, c.facing_cost))
        if M > 1:
            cost[:, :, 1:] += c.alt_cost
            # never a reading under the floor the track stands on / jumped from - unless all of them are
            node = np.array([tr.node for tr in trs], np.int64)
            multi = R.n > 1
            jj, ss = np.nonzero((node != NONE)[:, None] & multi[None, :])
            if len(jj):
                ids = np.repeat(node[jj], M)
                sy = self.g.surface_y(ids, R.x[ss].ravel()).reshape(len(jj), M)
                with np.errstate(invalid="ignore"):
                    under = (sy + c.under_tol < R.y[ss]) & R.ok[ss]
                drop = under & (under.sum(1) < R.n[ss])[:, None]
                bad[jj, ss] |= drop
        cost[bad] = np.inf
        return cost.min(2), cost.argmin(2)

    def _pair(self, R: _Readings, t: float) -> np.ndarray:
        """Nearest first -> the sightings used (bool (S,))."""
        used_s = np.zeros(R.S, bool)
        if not R.S or not self.tracks:
            return used_s
        cmin, ci = self._costs(R, t)
        T, S = cmin.shape
        flat = cmin.ravel()
        order = np.argsort(flat, kind="stable")
        order = order[flat[order] < np.inf]
        used_t = np.zeros(T, bool)
        mj, mi = [], []
        for f in order.tolist():
            j, i = divmod(f, S)
            if used_t[j] or used_s[i]:
                continue
            used_t[j] = used_s[i] = True
            mj.append(j)
            mi.append(i)
        if not mj:
            return used_s
        mj, mi = np.array(mj), np.array(mi)
        mm = ci[mj, mi]
        self._apply(R, mj, mi, mm, t)
        return used_s

    def _apply(self, R: _Readings, mj, mi, mm, t: float):
        c, trs = self.cfg, self.tracks
        rx, ry = R.x[mi, mm], R.y[mi, mm]
        tj = [trs[j] for j in mj]
        xs = np.array([tr.x_seen for tr in tj], np.float64)
        ys = np.array([tr.y_seen for tr in tj], np.float64)
        ago = t - np.array([tr.t_seen for tr in tj], np.float64)
        recent = (ago > 0) & (ago < c.ballistic_s)
        last = np.array([tr.node for tr in tj], np.int64)
        # the graph's rule with the step since the last frame (no step when not seen on it: stand = on a surface)
        P = self.g.place(rx, ry, np.where(recent, rx - xs, 0.0), np.where(recent, ry - ys, 0.0), last, last,
                         fly=np.array([self.kinds[int(k)].fly for k in R.kind[mi]]))
        for q, tr in enumerate(tj):
            i, m = int(mi[q]), int(mm[q])
            x, y = float(rx[q]), float(ry[q])
            o_last, o_new = tr.o, float(R.o[i])
            # the fade rule (the user, 2026-11-25): a die pose at full opacity (die_full_o) = a death; under it the
            # direction from two NEIGHBOURING sightings - fallen = a death, rising or flat = the live mob (the fit's
            # misreading: a spawn's landing squash read as die1_2, its feet 18 px off). On a track not seen on the
            # frame before it is HELD (judged on its next sighting). A live-mob or held die pose: seen, but its feet
            # and place stay the last ones (answer (a)).
            die_now = held = live_die = False
            die_t = t
            if R.die[i, m] and tr.life != "dying":
                if o_new >= c.die_full_o:
                    die_now = True
                    if tr.hold_o is not None:
                        die_t = tr.hold_t               # it began dying on the held frame
                elif tr.hold_o is not None:             # its held die pose's next sighting: judged now
                    if o_new < tr.hold_o - c.fade_eps:
                        die_now, die_t = True, tr.hold_t
                        self.stats["held die pose: fallen, dying"] += 1
                    else:
                        live_die = True
                        self.stats["held die pose: not fallen, alive"] += 1
                elif tr.seen_prev:
                    if o_new < o_last - c.fade_eps:
                        die_now = True
                    else:
                        live_die = True
                else:
                    held = True
                    self.stats["die pose on a remembered track: held"] += 1
            elif tr.hold_o is not None:
                self.stats["held die pose: a live pose next, alive"] += 1
            if not held:
                tr.hold_o = tr.hold_t = None
            if live_die or held:
                x, y = tr.x_seen, tr.y_seen
            if x != R.raw_x[i] or y != R.raw_y[i]:
                self.stats["feet settled"] += 1
            if tr.poss is not None:                     # it was remembered: how did that go
                near = True
                if tr.poss.ndim == 1 and tr.poss.any():
                    near = bool(np.abs(tr.gx[tr.poss] - x).min() <= self.kinds[tr.mob].half_w)
                if self.keep:
                    self.rem.append((t - tr.t_seen, "seen again", near, tr.cover, tr.rin, tr.rout))
                    self.episodes.append((tr.id, tr.n_seen_at, self.n, round(tr.x_seen), round(tr.y_seen), "seen again",
                                          tr.cover, round(t - tr.t_seen, 2), round(x), round(y)))
                tr.rin = tr.rout = 0
            tr.n_seen_at = self.n
            if not (live_die or held):
                tr.hist.append((t, x))
                while len(tr.hist) > 2 and t - tr.hist[0][0] > c.vx_s:
                    tr.hist.pop(0)
                t0, x0 = tr.hist[0]
                tr.vx = (x - x0) / (t - t0) if t - t0 >= c.vx_min_s else tr.vx
                tr.vy = (y - tr.y_seen) / (t - tr.t_seen) if 0 < t - tr.t_seen < c.vy_s else 0.0
                stand = bool(P.place[q] == STAND)
                tr.node, tr.air = int(P.from_node[q]), not stand
                tr.place, tr.cur_node, tr.off = int(P.place[q]), int(P.node[q]), float(P.off[q])
            tr.x = tr.x_seen = x
            tr.y = tr.y_seen = y
            tr.sx, tr.sy = x - R.C[0], y - R.C[1]
            tr.t_seen, tr.seen, tr.poss, tr.out_since = t, True, None, None
            tr.fi = R.src[i]
            tr.facing, tr.pose = int(R.facing[i]), R.pose[i, m]
            tr.cover = "none"
            tr.vis, tr.o = float(R.vis[i]), o_new
            tr.n_seen += 1
            if tr.how_alt is not None:                  # a faint birth: faded in only with its opacity rising
                if tr.o - tr.o0 > c.fade_rise:
                    self._settle(tr, "faded in", t)
                elif tr.o < tr.o0 - c.fade_rise or tr.n_seen >= c.fade_k:
                    self._settle(tr, tr.how_alt, t)
            kind = int(R.kind[i])
            tr.votes[kind] = tr.votes.get(kind, 0.0) + max(c.vote_min, tr.vis)     # a clear sighting counts more
            tr.mob = max(tr.votes, key=tr.votes.get)
            if tr.conf is None:
                if R.solid[i]:
                    tr.conf = "solid"
                elif t - tr.born >= c.confirm_s:
                    tr.conf = "sighted long"
                if tr.conf:
                    self.stats["confirmed: " + tr.conf] += 1
                    self._new_ev(tr, t)
            if held:
                tr.hold_o, tr.hold_t = tr.o, t          # its life as it was until the next sighting
            elif live_die:
                tr.life = "alive"                       # a die pose with the opacity rising (or flat, faint): the
                self.stats["die pose, opacity not falling: alive"] += 1     # live mob (a spawn's landing squash)
            elif die_now:
                tr.life, tr.die_t = "dying", die_t
            elif R.die[i, m]:
                pass                                    # dying already
            elif tr.life == "dying":
                tr.life, tr.die_t = "alive", None       # a live pose right after one die sighting: it lives
                self.stats["death taken back"] += 1
            else:
                tr.life = "hit" if R.hit[i, m] else "alive"

    # ------------------------------------------------------------------ the tracks nobody saw
    def _boxes(self, facts, tags=None) -> dict:
        """This frame's known things on screen (boxes, screen px): us, other players (the sorted tags', else every
        tag), the mobs seen, the drops."""
        c = self.cfg
        b = {"us": [], "player": [], "mob": [], "drop": []}
        if tags is not None:
            b["us"] += list(tags.get("us") or [])
            b["player"] += list(tags.get("player") or [])
        else:
            tag = facts.tag
            if tag is not None:
                mx, my = tag[0] + tag[2] / 2, tag[1]
                b["us"].append((mx + c.us_box[0], my + c.us_box[1], mx + c.us_box[2], my + c.us_box[3]))
            for x, y, w, h in facts.tags or []:
                cx = x + w / 2
                b["player"].append((cx + c.player_box[0], y + c.player_box[1], cx + c.player_box[2],
                                    y + c.player_box[3]))
        for tr in self.tracks:
            if tr.seen:
                k = self.kinds[tr.mob]
                b["mob"].append((tr.sx + k.lt[0], tr.sy + k.lt[1], tr.sx + k.rb[0], tr.sy + k.rb[1]))
        for d in facts.drops or []:
            x, y, w, h = d["box"]
            b["drop"].append((x, y, x + w, y + h))
        return {k: np.array(v, np.float64).reshape(-1, 4) for k, v in b.items()}

    def _grid(self, node):
        if node not in self.grids:
            g = self.g
            ix = g.index[node]
            xs = np.arange(int(g.left[ix]), int(g.right[ix]) + 1, self.cfg.set_step, dtype=np.int64)
            ys = g.surface_y(np.full(len(xs), node, np.int64), xs.astype(np.float64))
            ok = ~np.isnan(ys)
            self.grids[node] = (xs[ok], np.round(ys[ok]).astype(np.int64))
        return self.grids[node]

    def _start_set(self, tr: _Tr, k):
        c = self.cfg
        if k.fly or tr.node == NONE or tr.node not in self.g.index or tr.node < 0:
            n = int(c.fly_r // c.fly_step)
            gg = np.arange(-n, n + 1) * c.fly_step
            gx, gy = np.meshgrid(tr.x_seen + gg, tr.y_seen + gg)
            tr.gx, tr.gy = gx.astype(np.int64), gy.astype(np.int64)
            tr.poss = (np.abs(tr.gx - tr.x_seen) <= c.fly_start) & (np.abs(tr.gy - tr.y_seen) <= c.fly_start)
        else:
            tr.gx, tr.gy = self._grid(tr.node)
            tr.poss = np.abs(tr.gx - tr.x_seen) <= c.knock + c.set_step
            if not tr.poss.any() and len(tr.gx):
                tr.poss[np.argmin(np.abs(tr.gx - tr.x_seen))] = True
        tr.carry = 0.0

    def _widen(self, tr: _Tr, k, dt: float):
        step = self.cfg.fly_step if tr.poss.ndim == 2 else self.cfg.set_step
        tr.carry += k.v * dt
        n = int(tr.carry // step)
        if n <= 0:
            return
        tr.carry -= n * step
        n = min(n, 64)
        p = tr.poss
        if p.ndim == 1:                                 # n steps either way at once
            cs = np.concatenate([[0], np.cumsum(p)])
            i = np.arange(len(p))
            tr.poss = (cs[np.minimum(i + n + 1, len(p))] - cs[np.maximum(i - n, 0)]) > 0
            return
        for _ in range(n):
            q = p.copy()
            q[1:, :] |= p[:-1, :]
            q[:-1, :] |= p[1:, :]
            q[:, 1:] |= p[:, :-1]
            q[:, :-1] |= p[:, 1:]
            p = q
        tr.poss = p

    def _unseen(self, t, dt, C, evidence, boxes) -> list:
        """Every track not seen on this frame: kept or ended; the possible sets tested in one evidence call."""
        c = self.cfg
        keep, test = [], []
        for tr in self.tracks:
            k = self.kinds[tr.mob]
            if tr.seen:
                keep.append(tr)
                continue
            gone = t - tr.t_seen
            if tr.life == "dying":                      # the body is gone when die1 ends (game_rules D4)
                if t - tr.die_t > k.die_s + c.die_extra_s:
                    self._end(tr, "died (seen)", t, "mob_died")
                    continue
                keep.append(tr)
                continue
            if tr.conf is None:                         # never seen clearly: no memory
                if gone > c.tentative_s:
                    self.stats["tentative dropped"] += 1
                    continue
                keep.append(tr)
                continue
            if tr.o < c.fade_o and gone <= c.fade_s:    # fading in (a spawn): too faint to check yet
                tr.cover = "fading in"
                keep.append(tr)
                continue
            if tr.poss is None:
                self._start_set(tr, k)
            else:
                self._widen(tr, k, dt)
            if not evidence.ready:
                keep.append(tr)
                continue
            keep.append(tr)
            test.append(tr)
        self.asked = 0
        if test:
            gone_ids = self._test(test, C, evidence, boxes)
            tested = {tr.id for tr in test}
            out = []
            for tr in keep:
                if tr.id in gone_ids:
                    continue
                if tr.id in tested and not self._after_test(tr, t, C):
                    continue
                out.append(tr)
            keep = out
        return keep

    def _test(self, test: list, C, evidence, boxes) -> set:
        """Drop every place of each set where the frame shows the scene instead of the body (a jumper: at every
        height of a hop) - one evidence call for all; set each track's cover from what is over its places left.
        -> the ids whose set came up empty (ended here)."""
        c = self.cfg
        C0, C1 = int(C[0]), int(C[1])
        heights_j = np.arange(0, c.jump_h + 1, c.jump_dh)
        per_kind = {}                                   # kind -> [(track, ii, fx, fy, heights)]
        for tr in test:
            k = self.kinds[tr.mob]
            ii = np.flatnonzero(tr.poss.ravel())
            fx = tr.gx.ravel()[ii] - C0
            fy = tr.gy.ravel()[ii] - C1
            hs = heights_j if (k.jump and tr.poss.ndim == 1) else heights_j[:1]
            per_kind.setdefault(tr.mob, []).append((tr, ii, fx, fy, hs))
        groups, order = [], []
        for kid, items in per_kind.items():
            k = self.kinds[kid]
            gfx = np.concatenate([np.tile(fx, len(hs)) for _, _, fx, _, hs in items]) if items else np.zeros(0, np.int64)
            gfy = np.concatenate([(fy[None, :] - hs[:, None]).ravel() for _, _, _, fy, hs in items])
            groups.append((gfx.astype(np.int64), gfy.astype(np.int64), k.cdx, k.cdy))
            order.append((kid, items))
        res = evidence.count(groups)
        self.asked = sum(len(gr[0]) for gr in groups)
        gone = set()
        for (kid, items), (n_sh, n_in, n_wo) in zip(order, res):
            k = self.kinds[kid]
            n = len(k.cdx)
            a = 0
            for tr, ii, fx, fy, hs in items:
                P, H = len(ii), len(hs)
                sh = n_sh[a:a + P * H].reshape(H, P)
                n_in0, n_wo0 = n_in[a:a + P], n_wo[a:a + P]
                a += P * H
                absent = (sh >= c.abs_share * n).all(axis=0)
                flat = tr.poss.ravel().copy()
                flat[ii[absent]] = False
                tr.poss = flat.reshape(tr.poss.shape)
                left = ~absent
                if not left.any():
                    gone.add(tr.id)
                    self._end(tr, "gone: its places show the scene", self.t, "mob_gone")
                    continue
                checkable = (n_wo0 >= c.check_share * n) & left
                if not checkable.any():
                    tr.cover = "out of view" if (n_in0[left] < c.check_share * n).all() else "ui / scenery"
                    continue
                if self._crosses_edge(k, fx[left], fy[left], tr.poss.ndim == 2):
                    tr.cover = "edge"                   # the edge wins over what covers its in-view part
                    continue
                cj = np.flatnonzero(checkable)
                j = int(cj[np.argmin(np.abs(fx[checkable] - (tr.x_seen - C[0])))])
                px, py = fx[j] + k.cdx, fy[j] + k.cdy
                best, share = "effect", c.cover_share
                for name, bx in boxes().items():
                    if not len(bx):
                        continue
                    inb = ((px[None, :] >= bx[:, 0:1]) & (px[None, :] < bx[:, 2:3])
                           & (py[None, :] >= bx[:, 1:2]) & (py[None, :] < bx[:, 3:4])).any(0)
                    if inb.mean() > share:
                        best, share = name, float(inb.mean())
                tr.cover = best
        return gone

    @staticmethod
    def _crosses_edge(k, fx, fy, flyer: bool) -> bool:
        """Does the body box at the middle of the places left (screen px; where the record puts it: _after_test)
        cross the screen's left or right side or the window's bottom? (Not the top: step 4b.)"""
        mx = float(fx.mean())
        my = float(fy.mean()) if flyer else float(fy[np.argmin(np.abs(fx - mx))])
        return mx + k.lt[0] < 0 or mx + k.rb[0] > SW or my + k.rb[1] > SH

    def _after_test(self, tr: _Tr, t, C) -> bool:
        """A tested track with places left: the limits, then its place = the middle of the places left."""
        c = self.cfg
        if tr.poss.ndim == 2 and (np.abs(tr.gx[tr.poss] - tr.x_seen).max() >= c.fly_r - c.fly_step):
            self._end(tr, "lost: a flyer's set outgrew its reach", t, "mob_gone")
            return False
        if tr.cover in OUT:
            tr.rout += 1
            tr.out_since = tr.out_since if tr.out_since is not None else t
            if t - tr.out_since > c.offscreen_s:
                self._end(tr, "left: nothing to check for 4 s (" + tr.cover + ")", t, "mob_left")
                return False
        else:
            tr.rin += 1
            tr.out_since = None
            if t - tr.t_seen > c.drawn_s:
                self._end(tr, "gone: drawn over for 4 s (" + tr.cover + ")", t, "mob_gone")
                return False
        px = tr.gx[tr.poss]
        tr.x = float(px.mean())
        if tr.poss.ndim == 2:
            tr.y = float(tr.gy[tr.poss].mean())
        else:
            tr.y = float(tr.gy[tr.poss][np.argmin(np.abs(px - tr.x))])
        tr.sx, tr.sy = tr.x - C[0], tr.y - C[1]
        return True

    def _end(self, tr: _Tr, how: str, t: float, ev: str):
        self.stats["end: " + how] += 1
        if tr.conf is not None:
            self._ev.append({"ev": ev, "t": t, "id": tr.id, "kind": tr.mob, "how": how,
                             "unseen_s": round(t - tr.t_seen, 3), "cover": tr.cover})
        if self.keep:
            self.ended[tr.id] = (round(t, 2), how, round(t - tr.t_seen, 2), tr.pose, tr.air, tr.cover)
            if tr.poss is not None:
                self.rem.append((t - tr.t_seen, how, None, tr.cover, tr.rin, tr.rout))
                self.episodes.append((tr.id, tr.n_seen_at, self.n, round(tr.x_seen), round(tr.y_seen), how, tr.cover,
                                      round(t - tr.t_seen, 2), None, None))

    # ------------------------------------------------------------------ new tracks
    def _born(self, R: _Readings, used_s, t, keep: list):
        c = self.cfg
        for i in np.flatnonzero(~used_s) if R.S else []:
            k = self.kinds[int(R.kind[i])]
            node, air = int(R.node[i, 0]), bool(R.air[i, 0])
            if node == NONE and not k.fly:
                self.stats["no track: over no platform"] += 1
                continue
            x, y = float(R.x[i, 0]), float(R.y[i, 0])
            sx, sy = x - R.C[0], y - R.C[1]
            die, o = bool(R.die[i, 0]), float(R.o[i])
            how = ("there at entry" if t - self.t0 < c.entry_s else "faded in" if o < c.fade_o and not die
                   else "came into view" if self._edge(sx, sy) else "uncovered")     # the first pose apart; a die
            #                                                       pose is faint because the death fades it OUT
            tr = _Tr(self.next_id, k.id, R.pose[i, 0], int(R.facing[i]), x, y, sx, sy, node, air,
                     int(R.place[i, 0]), float(R.off[i, 0]), o, float(R.vis[i]), bool(R.solid[i]), die, t, how)
            tr.n_seen_at = self.n
            tr.fi = R.src[i]
            if how == "faded in":                       # settled by its next sightings (the opacity rising or not)
                tr.how_alt, tr.o0 = ("came into view" if self._edge(sx, sy) else "uncovered"), o
            keep.append(tr)
            self.next_id += 1
            self.stats["new: " + how] += 1
            if tr.conf:
                self.stats["confirmed: at once"] += 1
                self._new_ev(tr, t)

    def _new_ev(self, tr: _Tr, t: float):
        """The mob_new event of a confirmed track - held while how it came into sight is not settled yet."""
        if tr.how_alt is not None:
            tr.new_held = True
            return
        self._ev.append({"ev": "mob_new", "t": t, "id": tr.id, "kind": tr.mob, "how": tr.born_how})

    def _settle(self, tr: _Tr, how: str, t: float):
        """A faint birth settled: "faded in" (its opacity rose) or how it came into sight otherwise (flat / falling:
        seen through an effect or half under something, not a spawn)."""
        if how != tr.born_how:
            self.stats["new: " + tr.born_how] -= 1
            self.stats["new: " + how] += 1
            self.stats["faint birth, opacity not rising: " + how] += 1
        tr.born_how, tr.how_alt = how, None
        if tr.new_held:
            tr.new_held = False
            self._new_ev(tr, t)

    def _edge(self, sx, sy) -> bool:
        L, Rr, B, Tp = self.cfg.edge_px
        return sx < L or sx > SW - Rr or sy > PLAY_H - B or sy < Tp

    # ------------------------------------------------------------------ the HP meters (step 5a)
    def _meters(self, facts, t: float):
        """Perception's HP meters (facts.meters, perception/meters.py: each names the fit's sightings whose expected
        meter box it is at) -> the tracks' `hp`, `hp_t`. A meter teaches ONE track: it names one sighting, that
        sighting is this track's on this frame, its fill was read, and no other track stands over this mob (design
        1: a meter over two overlapping mobs teaches nothing). Nothing else changes `hp`: it is kept while the track
        lives (no HP guessed, no healing modelled)."""
        ms = getattr(facts, "meters", None)
        if not ms:
            return
        by_fi = {tr.fi: tr for tr in self.tracks if tr.fi is not None}
        for _, _, fill, _, cand in ms:
            tr = by_fi.get(cand[0]) if len(cand) == 1 else None
            if tr is None:
                self.stats["meter: " + ("over two sightings" if len(cand) > 1 else "no track")] += 1
            elif fill is None:
                self.stats["meter: fill not seen"] += 1
            elif self._overlapped(tr):
                self.stats["meter: over two mobs"] += 1
            else:
                tr.hp, tr.hp_t = float(fill), t
                self.stats["meter: taught"] += 1

    def _overlapped(self, tr: _Tr) -> bool:
        """Another track (seen, remembered or tentative; not dying: a dead mob's meter is gone) whose body's x range -
        a remembered one's anywhere it can be - meets this one's, its feet within meter_same_dy up or down."""
        k = self.kinds[tr.mob]
        lo, hi = tr.x - k.half_w, tr.x + k.half_w
        for u in self.tracks:
            if u is tr or u.life == "dying" or abs(u.y - tr.y) > self.cfg.meter_same_dy:
                continue
            hw = self.kinds[u.mob].half_w
            if not u.seen and u.poss is not None and u.poss.ndim == 1 and u.poss.any():
                px = u.gx[u.poss]
                ulo, uhi = float(px.min()) - hw, float(px.max()) + hw
            else:
                ulo, uhi = u.x - hw, u.x + hw
            if ulo <= hi and uhi >= lo:
                return True
        return False

    # ------------------------------------------------------------------ the records
    def _records(self, t: float, blind: bool = False) -> list:
        out = []
        for tr in self.tracks:
            st = ("tentative" if tr.conf is None else "dying" if tr.life == "dying" else "live" if tr.seen and
                  tr.life == "alive" else "hit" if tr.seen else "offscreen" if tr.cover in OUT else "hidden")
            life = tr.life if tr.life != "alive" or tr.o >= self.cfg.fade_o else "spawning"
            can = None
            if not tr.seen and tr.poss is not None and tr.poss.any():
                px = tr.gx[tr.poss]
                can = (float(px.min()), float(px.max()))
            out.append(Mob(tr.id, tr.mob, tr.conf is not None, st, tr.x, tr.y, tr.sx, tr.sy, tr.x_seen, tr.y_seen,
                           PLACES[tr.place], tr.cur_node, tr.node, tr.off, tr.vx, tr.vy, tr.facing, tr.pose, tr.o,
                           life, tr.seen and not blind, tr.vis, "blind" if blind else tr.cover, t - tr.t_seen,
                           None if can is None else can[0], None if can is None else can[1], tr.born, tr.born_how,
                           tr.first_pose, seen_share=tr.n_seen / max(1, tr.n_frames), hp=tr.hp, hp_t=tr.hp_t))
        return out

    def mobs(self) -> list:
        """The mobs of the state: the confirmed records."""
        return [m for m in self.records if m.confirmed]
