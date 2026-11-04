"""Mob tracker in map coordinates (perception rework, stage 3, 2026-11-04).

Per frame: the whole-screen detector's hits (acquire) + a search around every track it didn't see (track, all
poses, lower threshold) -> `Track`s with an id, map feet x/y, velocity, facing, pose and state. Backend-agnostic:
`update` takes the frame's hits and a `near(spots)` callable (GPU: `GpuSpriteDetector.find_near`).

Screen -> map: map = screen + C. `Camera` keeps C: moved every frame by the scenery's shift (exact, drifts ~20 px
in 3 min), pulled slowly to (our minimap map pos - our screen pos) (no drift, +-10 px noise), and clamped to the
map's vrBounds (the game's camera never shows past them: on the Rain-Forest C sits at the clamp most of the time).
Relative geometry (a mob vs us) stays exact in screen px; map x/y are for platforms and memory.
"""
from dataclasses import dataclass, field
import math

import numpy as np

SCREEN_W, SCREEN_H, PLAY_H = 1366, 768, 700


@dataclass
class TrackCfg:
    pull: float = 0.05            # camera: share of the minimap anchor taken per frame
    leash: float | None = 24.0    # camera: our feet (tag + C) at most this far from the minimap's (16 px steps + lag)
    gate_x: float = 30.0          # association: px allowed off the prediction, + vmax * time unseen
    gate_y: float = 24.0
    gate_y_air: float = 90.0
    vmax: float = 160.0           # px/s, generous: the fastest mob step seen (measured per track, not hardcoded)
    v_gain: float = 0.5           # velocity: share of a new measurement
    v_half_s: float = 0.6         # unseen: velocity halves every this many s (mobs stop / turn ~every 1.6 s)
    confirm_score: float = 0.75   # one sighting this good confirms a new track (else: two within confirm_s)
    new_score: float = 0.55       # a new track needs this (the detector reports down to ~0.5: grass over a Pig's
                                  # feet gives 0.53-0.55, scenery next to it 0.40-0.42); known tracks take any hit
    jump_h: float = 140.0         # feet up to this far over a platform: a mob mid-jump (Pigs jump ~45-100 px)
    confirm_s: float = 0.5
    tentative_s: float = 0.3      # unconfirmed and unseen this long -> dropped
    lose_s: float = 0.5           # confirmed, in view, not covered, unseen this long -> gone
    lose_frames: int = 4          # ... and in this many frames (the bot's loop stalls up to ~0.5 s during taps)
    covered_s: float = 2.0        # ... covered by our body
    fight_s: float = 1.2          # ... next to us (our attack effects cover mobs we hit: 4 frames at 0.34-0.44)
    fight_dx: float = 140.0
    offscreen_s: float = 4.0      # off screen: kept (coasting) this long
    hit_s: float = 0.6            # hit1 pose: 600 ms in the client data
    die_sure: float = 0.75        # a death counts on one die sighting this good, or on two (l1a1_rec: one 0.59
                                  # die match flagged a live Bubbling; a dead one's spot was taken by a new one)
    near_pad: int = 24            # search window around a track, +- px (+ vmax * time unseen, up to near_pad_max)
    near_pad_max: int = 32
    other_type: float = 12.0      # association: cost of a hit of another mob type (look-alikes: the type is voted)
    near_score: float = 0.55
    surface_tol: float = 16.0     # feet this close to a platform surface: on it
    dup_px: float = 14.0          # two tracks of one mob type this close: one mob
    hidden_vis: float = 0.35      # cover (map objects drawn in front): less of the body visible -> hidden, not missed
    hidden_s: float = 2.0         # hidden this long at most (longer: ghosts in the grass, labels track1b)
    new_vis: float = 0.25         # a new track needs this much of its body visible
    player_half_w: int = 24       # a player's body over its name tag (players are drawn over mobs): +-px, height
    player_h: int = 70
    probe_score: float = 0.65     # a new track from a probe (visible-only search beside players / in cover)
    probe_step: int = 40          # px between cover probes along a platform
    probe_max: int = 4            # cover probes per frame, taken in turns (a new mob is found within a few frames)
    edge_px: int = 6              # edge probes: this far inside the left / right screen edge, on every platform
    edge_max: int = 2             # ... per frame, in turns of their own
    probe_players: bool = False   # also beside every character (track1b: +2 of 82 mobs, +4 false, +10 ms: off)


@dataclass
class Track:
    id: int
    mob_id: int
    x: float                      # map feet
    y: float
    born: float
    seen: float                   # last sighting (s)
    sx: float = 0.0               # screen feet (last sighting, or the prediction while unseen)
    sy: float = 0.0
    vx: float = 0.0
    facing: str = "left"
    anim: str = "stand"
    score: float = 0.0
    platform: int | None = None
    air: bool = False
    kind: str = "mob"             # mob / pet
    state: str = "tentative"      # tentative / live / hit / dying / offscreen
    sightings: int = 1
    until: float = 0.0            # end of the hit / die animation
    last_x: float = 0.0           # map x at the last sighting (velocity)
    src: str = "acq"              # how it was seen this frame: acq / near / none
    votes: dict = field(default_factory=dict)      # mob id -> summed sighting scores (mob_id = the top one)
    misses: int = 0               # frames in a row it wasn't seen
    die_hits: int = 0             # die-pose sightings so far (see die_sure)
    vis: float = 1.0              # share of its body nothing is drawn over (cover masks), at the prediction

    def as_dict(self, t: float) -> dict:
        return {"id": self.id, "mob": self.mob_id, "kind": self.kind, "state": self.state,
                "x": round(self.x, 1), "y": round(self.y, 1), "sx": round(self.sx), "sy": round(self.sy),
                "vx": round(self.vx, 1), "facing": self.facing, "anim": self.anim, "score": self.score,
                "platform": self.platform, "air": self.air, "unseen": round(t - self.seen, 2), "src": self.src,
                "vis": round(self.vis, 2)}


class Camera:
    def __init__(self, vr: dict | None, pull: float = 0.05, w: int = SCREEN_W, h: int = SCREEN_H,
                 leash: float | None = None):
        """`leash`: if set, our feet (screen + C) never sit farther than this from the minimap's position on either
        axis - the minimap is coarse (16 px steps, a little late) but never drifts; a missed camera shift (a loop
        stall past the search range) is then bounded instead of paid back slowly by the pull."""
        self.vr, self.pull, self.w, self.h, self.leash = vr or None, pull, w, h, leash
        self.C = None             # (cx, cy): map = screen + C

    def update(self, shift, me_screen, me_map):
        """`shift`: (dx, dy) the scenery moved on screen since the last frame, or None. `me_screen`: our feet on
        screen (x, y) or None; `me_map`: our feet on the map (the minimap) or None."""
        C = self.C
        if C is not None and shift is not None:
            C = (C[0] - shift[0], C[1] - shift[1])
        if me_screen is not None and me_map is not None:
            a = (me_map[0] - me_screen[0], me_map[1] - me_screen[1])
            C = a if C is None else (C[0] + self.pull * (a[0] - C[0]), C[1] + self.pull * (a[1] - C[1]))
            if self.leash is not None:
                L = self.leash
                C = (min(max(C[0], a[0] - L), a[0] + L), min(max(C[1], a[1] - L), a[1] + L))
        if C is not None and self.vr:
            C = (min(max(C[0], self.vr["left"]), self.vr["right"] - self.w),
                 min(max(C[1], self.vr["top"]), self.vr["bottom"] - self.h))
        self.C = C
        return C


def _die_s(info: dict) -> float:
    fr = (info.get("frames") or {}).get("die1") or []
    return sum((f.get("delay") or 100) for f in fr) / 1000 or 0.6


class World:
    def __init__(self, navmap, map_json: dict, mobs: dict, cfg: TrackCfg | None = None, cover=None):
        """`mobs`: mob id -> mob.json dict (the map's mobs). `cover`: cover.Cover (what is drawn in front of mobs)
        or None."""
        self.nav, self.cfg, self.cover = navmap, cfg or TrackCfg(), cover
        self.body = {}                                         # mob id -> (lt, rb) of its stand frame (feet = 0, 0)
        for i, m in mobs.items():
            fr = (m.get("frames") or {})
            f0 = (fr.get("stand") or fr.get("move") or fr.get("fly") or [{}])[0]
            self.body[i] = (f0.get("lt") or [-30, -50], f0.get("rb") or [30, 0])
        self.cam = Camera(map_json.get("vrBounds"), self.cfg.pull, leash=self.cfg.leash)
        self.flyers = {i for i, m in mobs.items() if (m.get("frames") or {}).get("fly")}
        self.die_s = {i: _die_s(m) for i, m in mobs.items()}
        self.tracks: list[Track] = []
        self._cover_pts = None
        self.next_id = 1
        self.t = None
        self.stats = {"new": 0, "rejected_off_platform": 0, "rejected_covered": 0, "near_found": 0,
                      "dup_merged": 0, "ended": 0}

    # ------------------------------------------------------------------ helpers
    def _on(self, x, y):
        p = self.nav.platform_at(x, y, tol=self.cfg.surface_tol) if self.nav is not None else None
        return p

    def _over_platform(self, x, y) -> bool:
        """A platform surface 0..jump_h px under (x, y): a mob there may be mid-jump."""
        return self.nav is not None and any(0 < yp - y <= self.cfg.jump_h for _, yp in self.nav.surfaces(x))

    def _layer(self, platform_id, x, y):
        if self.cover is None:
            return None
        if platform_id is None and self.nav is not None:      # mid-jump: the platform under it
            p = self.nav.below(x, y)
            platform_id = p.id if p is not None else None
        return self.cover.layer(platform_id)

    def _vis(self, mob_id, layer, sx, sy, C) -> float:
        if self.cover is None or layer is None:
            return 1.0
        lt, rb = self.body.get(mob_id, ([-30, -50], [30, 0]))
        return self.cover.visible_share(layer, C, (sx + lt[0], sy + lt[1], rb[0] - lt[0], rb[1] - lt[1]))

    def _predict(self, tr: Track, dt: float, t: float):
        c = self.cfg
        if tr.seen < t - dt and tr.state != "hidden":          # unseen last frame too: the mob may stop / turn
            tr.vx *= 0.5 ** (dt / c.v_half_s)
        x = tr.x + tr.vx * dt
        if tr.platform is not None and not tr.air:
            p = self.nav.platforms.get(tr.platform)
            if p is not None:
                if not p.left <= x <= p.right:
                    x, tr.vx = p.clamp(x), 0.0                 # mobs turn at the edge
                y = p.y_at(x)
                tr.y = tr.y if y is None else y
        tr.x = x

    def _gate(self, tr: Track, t: float):
        c = self.cfg
        gone = max(0.0, t - tr.seen)
        return c.gate_x + c.vmax * gone, (c.gate_y_air if tr.air else c.gate_y) + 200 * gone

    def _apply(self, tr: Track, h, mx, my, t: float, src: str):
        c = self.cfg
        dt = t - tr.seen
        if dt > 0.02:
            v = (mx - tr.last_x) / dt
            v = max(-c.vmax, min(c.vmax, v))
            tr.vx += c.v_gain * (v - tr.vx)
        tr.x, tr.y, tr.last_x = mx, my, mx
        tr.sx, tr.sy = h.feet
        tr.seen, tr.score, tr.src, tr.misses = t, h.score, src, 0
        tr.facing, tr.anim = h.pose.facing, h.pose.anim
        tr.sightings += 1
        tr.votes[h.mob_id] = tr.votes.get(h.mob_id, 0.0) + h.score
        tr.mob_id = max(tr.votes, key=tr.votes.get)
        p = self._on(mx, my)
        tr.platform, tr.air = (p.id, False) if p is not None else (tr.platform, True)
        if h.pose.anim.startswith("die"):
            tr.die_hits += 1
            if tr.state != "dying" and (h.score >= c.die_sure or tr.die_hits >= 2):
                tr.state, tr.until = "dying", t + self.die_s.get(tr.mob_id, 0.6)
        elif h.pose.anim.startswith("hit"):
            tr.state, tr.until = "hit", t + c.hit_s
        elif tr.state == "tentative":
            tr.die_hits = 0
            if tr.sightings >= 2 or h.score >= c.confirm_score:
                tr.state = "live"
        else:
            tr.die_hits = 0                                   # a clear live pose: a lone weak die match was wrong
            if tr.state in ("hit", "offscreen", "hidden"):
                tr.state = "live"

    @staticmethod
    def _in_view(sx, sy):
        """On screen, or with its feet just past a side edge (a mob half off screen is still visible)."""
        return -40 <= sx < SCREEN_W + 40 and 0 <= sy < PLAY_H + 40

    # ------------------------------------------------------------------ the frame
    def _occlusion(self, tags, me_screen, shape=(PLAY_H, SCREEN_W)):
        """(h, w) bool, False where a player's body is (they're drawn over mobs): from their name tags, + ours. A
        tag just under a tracked mob's feet is that mob's own ("Lv.7 Pig"): skipped. None: nothing."""
        c = self.cfg
        bodies = []
        for x, y, w, h in tags or ():
            cx = x + w / 2
            if any(abs(cx - tr.sx) < 30 and -6 <= y - tr.sy <= 30 for tr in self.tracks):
                continue
            bodies.append((cx, y))
        if me_screen is not None:
            bodies.append((me_screen[0], me_screen[1]))
        self._bodies = bodies
        if not bodies:
            return None
        m = np.ones(shape, bool)
        for cx, top in bodies:
            x0, x1 = max(0, int(cx - c.player_half_w)), min(shape[1], int(cx + c.player_half_w))
            y0, y1 = max(0, int(top - c.player_h)), min(shape[0], int(top))
            m[y0:y1, x0:x1] = False
        return m

    def _cover_probes(self):
        """Map points (x, feet y, platform) along platforms, every probe_step px, where map objects cover part of a
        mob standing there (cover > 15 % of a 60 x 45 body): where a plain search loses mobs."""
        out = []
        if self.cover is None or self.nav is None:
            return out
        for p in self.nav.platforms.values():
            L = self.cover.layer(p.id)
            m = self.cover.masks.get(L)
            if m is None:
                continue
            x = p.left + self.cfg.probe_step / 2
            while x < p.right:
                y = p.y_at(x)
                if y is not None:
                    bx, by = int(x - 30 - self.cover.x0), int(y - 45 - self.cover.y0)
                    sub = m[max(0, by):max(0, by + 45), max(0, bx):max(0, bx + 60)]
                    if sub.size and 1 - sub.mean() > 0.15:
                        out.append((x, y, p.id))
                x += self.cfg.probe_step
        return out

    def _probes(self, C, occ, me_screen):
        """Screen spots for the visible-only search that no track covers: both sides of every character's body (we
        and other players are drawn over mobs) and the cover probes in view. Nearest us first, <= probe_max."""
        c = self.cfg
        if self._cover_pts is None:
            self._cover_pts = self._cover_probes()
        spots = []
        for cx, top in getattr(self, "_bodies", []) if occ is not None and c.probe_players else []:
            for dx in (-c.player_half_w, c.player_half_w):
                spots.append((cx + dx, top, None))
        for x, y, pid in self._cover_pts:
            spots.append((x - C[0], y - C[1], pid))
        out = []
        for sx, sy, pid in spots:
            if not (0 <= sx < SCREEN_W and 0 <= sy < PLAY_H + 40):
                continue
            if any(abs(tr.sx - sx) < 30 and abs(tr.sy - sy) < 30 for tr in self.tracks):
                continue                                       # a track's own search covers it
            if any(abs(o[0] - sx) < 20 and abs(o[1] - sy) < 20 for o in out):
                continue
            out.append((sx, sy, pid))
        edges = []
        if self.nav is not None:                               # screen edges: a mob half off screen (whole-screen
            for sx in (c.edge_px, SCREEN_W - c.edge_px):       # search can't place a cut sprite; visible-only can)
                for p, y in self.nav.surfaces(sx + C[0]):
                    if 0 <= y - C[1] < PLAY_H + 40 and not any(abs(tr.sx - sx) < 40 and abs(tr.sy - (y - C[1])) < 30
                                                               for tr in self.tracks):
                        edges.append((sx, y - C[1], p.id))
        return self._turns(out, c.probe_max, "_probe_turn") + self._turns(edges, c.edge_max, "_edge_turn")

    def _turns(self, spots, k, name):
        """k of the spots, a window that moves on each frame (a stable order first)."""
        if len(spots) <= k:
            return spots
        spots.sort(key=lambda s: (s[0], s[1]))
        turn = (getattr(self, name, 0) + k) % len(spots)
        setattr(self, name, turn)
        return [spots[(turn + i) % len(spots)] for i in range(k)]

    def _vis_map(self, layer, C, occ):
        base = self.cover.visible(layer, C) if self.cover is not None and layer is not None else None
        if occ is None:
            return base
        if base is None:
            return occ
        key = (layer, id(occ))
        if key not in self._vis_cache:
            self._vis_cache[key] = base & occ
        return self._vis_cache[key]

    def _share(self, mob_id, vmap, sx, sy) -> float:
        if vmap is None:
            return 1.0
        lt, rb = self.body.get(mob_id, ([-30, -50], [30, 0]))
        x0, y0 = max(0, int(sx + lt[0])), max(0, int(sy + lt[1]))
        x1, y1 = min(vmap.shape[1], int(sx + rb[0])), min(vmap.shape[0], int(sy + rb[1]))
        return float(vmap[y0:y1, x0:x1].mean()) if x1 > x0 and y1 > y0 else 1.0

    def update(self, t: float, hits: list, me_screen=None, me_map=None, shift=None, near=None,  # noqa: C901
               tags=None) -> list:
        """One frame. `hits`: [Hit] from the whole-screen pass (screen px). `me_screen`: our feet on screen;
        `me_map`: our feet from the minimap; `shift`: the scenery's (dx, dy) since the last frame; `near(spots, pad, vis)`:
        [(mob ids, sx, sy)], +-pad px each, per spot the screen visibility of its layer (cover) -> [Hit | None]
        (search around tracks; None = no search). `tags`: other characters' name tags (screen boxes) -> their
        bodies don't count against a mob behind them. -> the tracks."""
        c = self.cfg
        dt = 0.0 if self.t is None else max(0.0, t - self.t)
        self.t = t
        C = self.cam.update(shift, me_screen, me_map)
        if C is None:
            return self.tracks                                 # no map position yet: nothing to place
        for tr in self.tracks:
            self._predict(tr, dt, t)
            tr.sx, tr.sy = tr.x - C[0], tr.y - C[1]
            tr.src = "none"
        self._vis_cache = {}
        occ = self._occlusion(tags, me_screen)
        for tr in self.tracks:
            tr.vis = self._share(tr.mob_id, self._vis_map(self._layer(tr.platform if not tr.air else None, tr.x,
                                                                       tr.y), C, occ), tr.sx, tr.sy)
        # --- associate the whole-screen hits: same mob type, nearest prediction first
        hm = [(h, h.feet[0] + C[0], h.feet[1] + C[1]) for h in hits]
        pairs = []
        for i, (h, mx, my) in enumerate(hm):
            for j, tr in enumerate(self.tracks):
                if tr.state == "dying" and not h.pose.anim.startswith("die"):
                    continue                                   # dead is final: a live mob there is another one
                gx, gy = self._gate(tr, t)
                dx, dy = abs(mx - tr.x), abs(my - tr.y)
                if dx <= gx and dy <= gy:
                    pairs.append((dx + 0.5 * dy + (0 if tr.state != "tentative" else 5)
                                  + (0 if tr.mob_id == h.mob_id else c.other_type), i, j))
        pairs.sort()
        used_h, used_t = set(), set()
        for _, i, j in pairs:
            if i in used_h or j in used_t:
                continue
            used_h.add(i)
            used_t.add(j)
            h, mx, my = hm[i]
            self._apply(self.tracks[j], h, mx, my, t, "acq")
        # --- search around the tracks nobody saw, + probes (beside characters / in cover: new mobs a plain search
        # can't see) - one batched call
        probe_found = []
        if near is not None:
            todo = [tr for j, tr in enumerate(self.tracks) if j not in used_t and self._in_view(tr.sx, tr.sy)]
            probes = self._probes(C, occ, me_screen)
            if todo or probes:
                pads = [c.near_pad if t - tr.seen <= 0.12 else c.near_pad_max for tr in todo]   # 2 sizes (warm_near)
                vis = [self._vis_map(self._layer(tr.platform if not tr.air else None, tr.x, tr.y), C, occ)
                       for tr in todo]                         # (given: visible-only NCC, past the edges too)
                for sx, sy, pid in probes:
                    vis.append(self._vis_map(self._layer(pid, sx + C[0], sy + C[1] - 1), C, occ))
                spots = [(tuple(tr.votes) or (tr.mob_id,), tr.sx, tr.sy) for tr in todo]
                spots += [(None, sx, sy) for sx, sy, _ in probes]
                res = near(spots, pads + [c.near_pad] * len(probes), vis) or []
                found, probe_found = res[:len(todo)], res[len(todo):]
                taken = [h.feet for i, (h, _, _) in enumerate(hm) if i in used_h]
                for tr, h in zip(todo, found):
                    if h is None:
                        continue
                    if tr.state == "dying" and not h.pose.anim.startswith("die"):
                        hm.append((h, h.feet[0] + C[0], h.feet[1] + C[1]))     # a live mob where one died: new
                        continue
                    if any(abs(f[0] - h.feet[0]) < c.dup_px and abs(f[1] - h.feet[1]) < 20 for f in taken):
                        continue                               # that's another track's mob
                    taken.append(h.feet)
                    self._apply(tr, h, h.feet[0] + C[0], h.feet[1] + C[1], t, "near")
                    self.stats["near_found"] += 1
        for h in probe_found:
            if h is not None and h.score >= c.probe_score and not h.pose.anim.startswith("die"):
                hm.append((h, h.feet[0] + C[0], h.feet[1] + C[1]))
                self.stats["probe_hits"] = self.stats.get("probe_hits", 0) + 1
        # --- new tracks from the hits nobody claimed (on a platform, or a flyer)
        for i, (h, mx, my) in enumerate(hm):
            if i in used_h:
                continue
            live_pose = not h.pose.anim.startswith("die")
            if any(tr.src != "none" and abs(tr.x - mx) < c.dup_px and abs(tr.y - my) < 20
                   and not (live_pose and tr.state == "dying") for tr in self.tracks):
                continue                                       # a near search already took it
            if h.score < c.new_score:
                continue
            p = self._on(mx, my)
            if p is None and h.mob_id not in self.flyers and not self._over_platform(mx, my):
                self.stats["rejected_off_platform"] += 1
                continue
            if self._share(h.mob_id, self._vis_map(self._layer(p.id if p else None, mx, my), C, None),
                           h.feet[0], h.feet[1]) < c.new_vis:
                self.stats["rejected_covered"] += 1             # nothing of it can be seen there: not a sighting
                continue
            tr = Track(self.next_id, h.mob_id, mx, my, born=t, seen=t, sx=h.feet[0], sy=h.feet[1],
                       facing=h.pose.facing, anim=h.pose.anim, score=h.score, platform=p.id if p else None,
                       air=p is None, last_x=mx, src="acq", votes={h.mob_id: h.score})
            if h.score >= c.confirm_score:
                tr.state = "live"
            self.next_id += 1
            self.stats["new"] += 1
            self.tracks.append(tr)
        # --- states, ends
        body = fight = None
        if me_screen is not None:
            body = (me_screen[0] - 34, me_screen[1] - 80, me_screen[0] + 34, me_screen[1] + 12)
            fight = (me_screen[0] - c.fight_dx, me_screen[1] - 90, me_screen[0] + c.fight_dx, me_screen[1] + 20)
        keep = []
        for tr in self.tracks:
            gone = t - tr.seen
            hidden = tr.src == "none" and tr.vis < c.hidden_vis and tr.state in ("live", "hidden", "hit")
            if hidden:
                tr.state = "hidden"                            # behind map objects: unseen is expected there
            elif tr.src == "none":
                tr.misses += 1
                if tr.state == "hidden":                       # out in the open again and still not seen
                    tr.state = "live"
            if tr.state == "hit" and t > tr.until:
                tr.state = "live"
            if tr.src == "none" and tr.die_hits and tr.state not in ("dying", "tentative"):
                tr.state, tr.until = "dying", tr.seen + self.die_s.get(tr.mob_id, 0.6)   # last seen dying: dead
            if tr.state == "dying":
                if t > tr.until + 0.2:
                    self.stats["ended"] += 1
                    continue
            elif tr.state == "tentative":
                if gone > c.tentative_s and tr.misses >= 2:
                    continue
            elif tr.state == "hidden":
                if gone > c.hidden_s:
                    self.stats["ended"] += 1
                    continue
            elif not self._in_view(tr.sx, tr.sy):
                tr.state = "offscreen"
                if gone > c.offscreen_s:
                    self.stats["ended"] += 1
                    continue
            else:
                inside = lambda b: b is not None and b[0] <= tr.sx <= b[2] and b[1] <= tr.sy <= b[3]  # noqa: E731
                limit = c.covered_s if inside(body) else c.fight_s if inside(fight) else c.lose_s
                if tr.state == "offscreen":
                    tr.state = "live"
                if gone > limit and tr.misses >= c.lose_frames:
                    self.stats["ended"] += 1
                    continue
            keep.append(tr)
        # --- one mob, two tracks: keep the older one
        keep.sort(key=lambda tr: tr.born)
        out = []
        for tr in keep:
            if any(abs(o.x - tr.x) < c.dup_px and abs(o.y - tr.y) < 20 and (o.state == "dying") == (tr.state == "dying")
                   for o in out):
                self.stats["dup_merged"] += 1
                continue
            out.append(tr)
        self.tracks = out
        return out

    def confirmed(self) -> list:
        return [tr for tr in self.tracks if tr.state != "tentative"]


def letters(names: dict) -> dict:
    """mob id -> one letter for the console map (first free letter of its name's words)."""
    out, used = {}, set("@pO.H#=")
    for mid in sorted(names):
        for ch in "".join(w[0] for w in names[mid].split()[::-1]) + names[mid].replace(" ", "") + "MNXYZ":
            ch = ch.upper()
            if ch.isalpha() and ch not in used:
                out[mid] = ch
                used.add(ch)
                break
    return out


def marks(tracks, t: float, letter: dict) -> list:
    """Tracks -> console map marks: letter + id + facing (< >), ? unseen, x dying, ^ in the air, p pet."""
    out = []
    for tr in tracks:
        if tr.kind == "pet":
            out.append(("p", tr.x, tr.y))
            continue
        s = f"{letter.get(tr.mob_id, 'M')}{tr.id}{'<' if tr.facing == 'left' else '>'}"
        if tr.state == "dying":
            s += "x"
        elif tr.air:
            s += "^"
        elif t - tr.seen > 0.05:
            s += "?"
        out.append((s, tr.x, tr.y))
    return out
