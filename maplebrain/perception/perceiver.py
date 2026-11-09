"""Frame(s) -> Observation. Stateful only where perception needs memory (tracker, mob library, HUD smoothing);
it never presses keys and never decides anything."""
from collections import deque
from dataclasses import dataclass, field

import time

import cv2
import numpy as np

from ..config import Config
from ..geometry import bottom, cx, overlaps
from . import hud
from .mobs import MobLibrary, Tracker
from .motion import moving_blobs
from .selfpos import find_self
from .tags import find_tags, tag_body


@dataclass
class Observation:
    t: float
    me: tuple | None = None                 # (px, feet): our centre x and the top of our name tag
    hp: float = 1.0                         # HP share from the HUD's exact "HP [cur/max]" numbers (session 16:
    hp_raw: float = 1.0                     # the numbers, not the bar; same value, kept for the brain's damage check)
    mp: float = 1.0                         # MP share from "MP [cur/max]"
    hp_now: int | None = None               # the exact numbers (None until first read; a covered HUD keeps the
    hp_max: int | None = None               # last good reading)
    mp_now: int | None = None
    mp_max: int | None = None
    hp_potions: bool | None = None          # an item sits in the HP potion key's quickslot (None: can't tell)
    mp_potions: bool | None = None
    exp_points: int | None = None           # HUD "EXP. 885" points (median of the last 3 readable ones), exact
    dot: tuple | None = None                # our minimap position
    bar_mobs: list = field(default_factory=list)      # mobs under an HP bar, on our level
    known_mobs: list = field(default_factory=list)    # bar_mobs + sprite + remembered-appearance matches on our level
    sprite_mobs: list = field(default_factory=list)   # [(box, mob_id, score)] found by their game sprites
    target: tuple | None = None             # current target's box, if seen this frame
    target_src: str = "none"                # bar / track / wide / none
    target_has_bar: bool = False            # an HP bar is on the target right now
    target_dying: bool = False              # its death animation plays where the target was (sprite mode)
    moving: list | None = None              # motion-look candidates (only when a look was taken)
    look_align: float | None = None
    n_tags: int = 0
    scene_dx: float | None = None           # how far the scenery shifted on screen since the last frame (camera)
    scene_dy: float | None = None           # the same, vertically
    lie_detector: bool = False              # the game's Lie Detector (anti-bot test) is on screen
    drops: list = field(default_factory=list)          # [box] loot seen on the ground (loot by sight)
    map_pos: tuple | None = None            # our feet in map coordinates (nav.localize; needs --map)
    platform: int | None = None             # the platform we stand on (nav.navmap id); None: air / rope / unknown
    rope: float | None = None               # x of the rope we're on
    mobs: list = field(default_factory=list)          # the tracker's tracks (world.Track.as_dict; --gpu, passive)
    cam: tuple | None = None                # the tracker's camera: map = screen + cam
    cam_src: str | None = None              # what moved the camera this frame: platforms / scene (fallback)
    me_map: tuple | None = None             # our feet on the map from our tag + cam: exact px (minimap: 16 px steps)


def reachable_level(box, feet, tol, step_down, dx=None, climb_slope=0.0, climb_max=0.0) -> bool:
    """A mob standing on our ground line (within `tol`), or on lower ground up to `step_down` px below us (walk off
    the step), or - given its distance `dx` - higher up a gentle slope (rise <= climb_slope * |dx|, <= climb_max).
    Steeper/higher needs a jump (not built) and is where floating things (ghosts) are."""
    d = bottom(box) - feet                     # > 0: lower on screen than our feet
    if -tol <= d <= max(tol, step_down):
        return True
    return dx is not None and -climb_max <= d < -tol and -d <= climb_slope * abs(dx)


class Perceiver:
    def __init__(self, cfg: Config, self_template: np.ndarray, sprites=None, lie_detector=None, drops=None,
                 locator=None):
        self.cfg, self.tpl, self.sprites = cfg, self_template, sprites
        self.locator = locator                          # nav.localize.MinimapLocator, or None (no map position)
        self.canvas_try = -1.0
        self.drops = drops                              # DropSpotter, or None (no loot by sight)
        self.lie_detector = lie_detector                # LieDetector, or None (not checked)
        self.me_near = None
        self.wide_next_t = -1e9                         # tag lost: next whole-screen look
        self.hp_pair = None                             # last accepted (cur, max) from the HUD text
        self.mp_pair = None
        self.new_max = {}                               # "hp"/"mp" -> a max seen once (a level-up / gear changes
                                                        # it; one misread must not)
        self.slot_hist = {}                             # key -> recent slot readings (majority vote)
        self.points_hist = deque(maxlen=3)
        self.library = MobLibrary(cfg.perception.library_size, cfg.perception.library_score)
        self.tracker: Tracker | None = None
        self.last_frame = None
        self.target_proven = False
        self.prev_small = None
        self.last_t = 0.0
        self.confirmed_at = 0.0                         # target last seen by its HP bar or its sprite
        self.target_mob = None                          # the target's mob id (from its sprite), for its death frames
        self.last_sprites = []                          # the last frame's sprite hits (to know a new target's id)
        self.world = None                               # the mob tracker (--gpu): logs obs.mobs, the brain doesn't
        ctx = getattr(sprites, "track_ctx", None)       # use it yet
        if ctx is not None:
            from concurrent.futures import ThreadPoolExecutor
            from .world import World
            self.world = World(*ctx)
            self.tag_pool = ThreadPoolExecutor(1)       # name tags (CPU) while the GPU finds mobs
            self.plat_shift = None                      # the camera's shift measured on the platforms (camshift.py)
            if self.world.nav is not None and cfg.perception.platform_shift:
                from .camshift import PlatformShift
                self.plat_shift = PlatformShift(self.world.nav)
        self.use_tracks = bool(cfg.perception.tracker and self.world is not None)
        self.target_id = None                           # --tracker: the target is this track

    def _locate(self, frame, obs):
        """Minimap dot -> obs.dot; with a locator also our map position, platform and rope. The minimap canvas is
        searched (3.6 ms) until found, at most about once a second (window closed / covered). A window showing only
        part of the canvas scrolls with us: followed every tick, before the dot is read against it."""
        loc = self.locator
        if loc is not None and (loc.origin is None or loc.lost) and obs.t - self.canvas_try >= 1.0:
            self.canvas_try = obs.t
            loc.calibrate(frame)
        if loc is not None:
            loc.follow(frame)
        obs.dot = hud.minimap_dot(frame, loc.dot_box() if loc is not None else hud.MINIMAP_BOX)
        w = loc.where(obs.dot) if loc is not None else None
        if w is not None:
            obs.map_pos, obs.platform, obs.rope = (round(w.x, 1), round(w.y, 1)), w.platform, w.rope

    # ---- commands from the brain (via the runner)
    def track(self, frame, box):
        if self.use_tracks:                             # the target = the track whose box this is (by id from now on)
            trs = [tr for tr in self._brain_tracks(self.last_t) if abs(cx(self._box(tr)) - cx(box)) < 30]
            best = min(trs, key=lambda tr: abs(cx(self._box(tr)) - cx(box)), default=None)
            self.target_id = best.id if best is not None else None
            self.target_mob = best.mob_id if best is not None else None
            self.confirmed_at = self.last_t
            return
        self.tracker = Tracker(frame, box)
        self.confirmed_at = self.last_t                 # it was just seen (that's why it's the target)
        hit = [s for s in self.last_sprites if abs(cx(s[0]) - cx(box)) < 15]
        self.target_mob = hit[0][1] if hit else None

    def untrack(self):
        self.target_id = None
        self.tracker = None
        self.target_mob = None

    def learn_target(self):
        if self.tracker is not None:
            self.library.add(self.tracker.tpl)

    def forget_target(self, frame=None):
        if self.tracker is not None:
            self.library.forget_like(self.tracker.tpl)
            frame = frame if frame is not None else self.last_frame
            if frame is not None:
                self.library.forget_at(frame, self.tracker.box)

    # ---- observing
    def _pair(self, frame, name, span, last):
        """The HUD's [cur/max] for HP or MP. Unreadable (covered) -> the last good reading. A different max is
        taken only when read twice in a row (level-up / gear), so a single misread can't change it."""
        r = hud.read_pair(frame, span)
        if r is None:
            return last
        if last is not None and r[1] != last[1]:
            if self.new_max.get(name) != r[1]:
                self.new_max[name] = r[1]
                return last
        self.new_max.pop(name, None)
        return r

    def _slot(self, frame, key, cursor):
        """Majority of the last 5 readings of `key`'s quickslot; a frame with the cursor over the key layout is
        skipped (its tooltip covers the slots next to it: pkg_sprites7b frame 300)."""
        h = self.slot_hist.setdefault(key, deque(maxlen=5))
        if not hud.in_quickslots(cursor):
            v = hud.slot_filled(frame, key)
            if v is None:
                return None
            h.append(v)
        return (sum(h) * 2 > len(h)) if h else None

    def observe(self, frame, t: float, cursor=None) -> Observation:
        p, z = self.cfg.perception, self.cfg.zones
        obs = Observation(t=t)
        self.last_frame, self.last_t = frame, t
        self.parts, self._t0 = {}, time.perf_counter()      # ms per part of this frame (ticks timings.parts)
        if self.lie_detector is not None:
            obs.lie_detector = self.lie_detector.check(frame, t)[0]
        self._mark("lie")
        small = cv2.resize(cv2.cvtColor(frame[:620], cv2.COLOR_BGR2GRAY), (341, 155),
                           interpolation=cv2.INTER_AREA).astype(np.float32)
        if self.prev_small is not None:
            (dx, dy), resp = cv2.phaseCorrelate(self.prev_small, small)
            obs.scene_dx = float(dx * 4) if resp > 0.2 else None
            obs.scene_dy = float(dy * 4) if resp > 0.2 else None
        self.prev_small = small
        self._mark("scene")
        me = None
        if self.me_near is not None:
            me = find_self(frame, self.tpl, near=self.me_near, min_score=p.self_near_score)
        if me is None and not 0 < self.wide_next_t - t <= 1.0:   # lost: the whole screen ~4x a second (25-150 ms;
            near_edge = self.me_near is None or not 150 < self.me_near[0] < frame.shape[1] - 150   # the minimap
            me = find_self(frame, self.tpl, min_score=p.self_min_score, edges=near_edge)          # meanwhile)
            self.wide_next_t = t + (0 if me is not None else p.self_wide_every_s)
            self._mark("self_wide")
        self._mark("self")
        self.hp_pair = self._pair(frame, "hp", hud.HP_TEXT, self.hp_pair)
        self.mp_pair = self._pair(frame, "mp", hud.MP_TEXT, self.mp_pair)
        if self.hp_pair:
            obs.hp_now, obs.hp_max = self.hp_pair
            obs.hp = obs.hp_raw = self.hp_pair[0] / self.hp_pair[1]
        if self.mp_pair:
            obs.mp_now, obs.mp_max = self.mp_pair
            obs.mp = self.mp_pair[0] / self.mp_pair[1]
        obs.hp_potions = self._slot(frame, self.cfg.keys.hp_potion, cursor)
        obs.mp_potions = self._slot(frame, self.cfg.keys.mp_potion, cursor)
        pts = hud.exp_points(frame)
        if pts is not None:
            self.points_hist.append(pts)
        if len(self.points_hist) == 3:                  # 2 of 3 agree: one misread never makes a kill
            obs.exp_points = int(np.median(self.points_hist))
        self._mark("hud")
        self._locate(frame, obs)
        self._mark("locate")
        if self.world is not None:
            self._track(frame, obs, me)
        if me is None:
            return obs
        self.me_near = (me[0] + me[2] / 2, me[1])
        px, feet = self.me_near
        obs.me = (px, feet)
        my_body = (int(px - 30), int(feet - 75), 60, 92)

        if self.sprites is None:            # sprite mode (--map) doesn't use mob HP bars at all: Perion's fog washes
            bars = [hud.bar_mob_box(b) for b in hud.find_mob_bars(frame)]       # them out (perion2/3)
            obs.bar_mobs = [b for b in bars if reachable_level(b, feet, z.same_level + 15, z.step_down)]
        if self.sprites is not None:          # no body exclusion: a snail at our feet is still a snail
            above = int(z.climb_max + getattr(self.sprites, "max_h", 60) + 5)   # up a slope: the whole sprite
            obs.sprite_mobs = [s for s in self.sprites.find(frame, feet, below=z.step_down, above=above,
                                                            exclude=obs.bar_mobs)
                               if reachable_level(s[0], feet, z.same_level, z.step_down, cx(s[0]) - px,
                                                  z.climb_slope, z.climb_max)]
        if self.use_tracks:                   # --tracker: the brain's mobs are the tracks on our level
            obs.sprite_mobs = [(self._box(tr), tr.mob_id, tr.score) for tr in self._brain_tracks(t)]
            obs.sprite_mobs = [s for s in obs.sprite_mobs
                               if reachable_level(s[0], feet, z.same_level, z.step_down, cx(s[0]) - px,
                                                  z.climb_slope, z.climb_max)]
        self.last_sprites = obs.sprite_mobs
        spr = [s[0] for s in obs.sprite_mobs]
        lib = [] if self.sprites is not None else [     # sprites cover this map's mobs (and cost less)
            b for b in self.library.find(frame, feet, [my_body] + obs.bar_mobs + spr, below=z.step_down)
            if reachable_level(b, feet, z.same_level, z.step_down)]
        obs.known_mobs = obs.bar_mobs + spr + lib
        if self.drops is not None:
            obs.drops = [b for b, _ in self.drops.update(frame, t, feet, px)]

        if self.use_tracks and self.target_id is not None:
            tr = next((x for x in self.world.tracks if x.id == self.target_id), None)
            if tr is not None and tr.state not in ("offscreen",):
                obs.target = self._box(tr)
                obs.target_dying = tr.state == "dying"
                alive_now = tr.src != "none" and tr.state != "dying"
                obs.target_src = "sprite" if alive_now else "track"        # "sprite": seen alive this frame
                if alive_now:
                    self.confirmed_at = t
        if self.tracker is not None:
            exp_x = self.tracker.centre_x()
            near = [b for b in obs.bar_mobs if abs(cx(b) - exp_x) < 70]
            if near:
                b = min(near, key=lambda b: abs(cx(b) - exp_x))
                self.tracker.box, self.confirmed_at = b, t
                obs.target, obs.target_src, obs.target_has_bar = b, "bar", True
            else:
                shift = obs.scene_dx or 0.0                 # the camera moved: so did it, on screen
                spr = [s[0] for s in obs.sprite_mobs if abs(cx(s[0]) - (exp_x + shift)) < 70]
                if spr:                                     # re-found by its sprite: the surest sighting there is
                    b = min(spr, key=lambda b: abs(cx(b) - (exp_x + shift)))
                    self.tracker = Tracker(frame, b)
                    self.confirmed_at = t
                    obs.target, obs.target_src = self.tracker.box, "sprite"
                    self.target_mob = next((s[1] for s in obs.sprite_mobs if s[0] == b), self.target_mob)
                else:
                    if self.sprites is not None and self.target_mob is not None:     # gone: dying right there?
                        obs.target_dying = self.sprites.dying(frame, exp_x + shift, feet,
                                                              mob_id=self.target_mob) >= p.die_score
                    src = self.tracker.update(frame, refresh=not self.target_proven)
                    on_me = self.sprites is not None and abs(self.tracker.centre_x() - px) < 20
                    # with sprites, the template tracker only bridges short gaps: unconfirmed it drifts onto
                    # scenery (pkg_sprites7b 7-20 s: onto flowers after the snail was gone; 14 s of swinging)
                    stale = self.sprites is not None and t - self.confirmed_at > p.unconfirmed_s
                    if src and not on_me and not stale:                   # (pkg_sprites4 44.9 s: the template slid onto our own
                        obs.target, obs.target_src = self.tracker.box, src   # body; swung at air for 7.5 s)
        return obs

    def _box(self, tr):
        """A track's body box on screen (the client's lt/rb of its stand frame, at its feet)."""
        lt, rb = self.world.body.get(tr.mob_id, ([-30, -50], [30, 0]))
        return (int(tr.sx + lt[0]), int(tr.sy + lt[1]), int(rb[0] - lt[0]), int(rb[1] - lt[1]))

    def _brain_tracks(self, t):
        """The tracks the brain gets: confirmed, alive, seen now / hidden / unseen <= track_coast_s."""
        cs = self.cfg.perception.track_coast_s
        return [tr for tr in self.world.tracks if tr.state not in ("tentative", "dying", "offscreen")
                and (tr.src != "none" or tr.state == "hidden" or t - tr.seen <= cs)]

    def _mark(self, name):
        now = time.perf_counter()
        self.parts[name] = round(self.parts.get(name, 0) + 1000 * (now - self._t0), 1)
        self._t0 = now

    def _track(self, frame, obs, me):
        band = self.sprites
        tags = self.tag_pool.submit(find_tags, frame)  # players' bodies hide mobs (they're drawn over them)
        hits = band._all(frame)
        self._mark("gpu")
        me_s = (me[0] + me[2] / 2, me[1]) if me is not None else None
        shift = None
        if self.plat_shift is not None:                 # platforms move 1:1 with the camera; the whole frame doesn't
            shift = self.plat_shift.update(frame, self.world.cam.C, me_s, obs.t)
            obs.cam_src = "platforms" if shift is not None else "scene"
            self._mark("camshift")
        if shift is None and obs.scene_dx is not None:
            shift = (obs.scene_dx, obs.scene_dy)
        trs = self.world.update(obs.t, hits, me_s, obs.map_pos, shift,
                                near=lambda spots, pad=24, vis=None: band.gpu.find_near(frame, spots, pad=pad, vis=vis),
                                tags=tags.result())
        self._mark("world")
        obs.mobs = [tr.as_dict(obs.t) for tr in trs]
        obs.cam = tuple(round(v, 1) for v in self.world.cam.C) if self.world.cam.C else None
        if me_s is not None and obs.cam is not None:   # our feet on the map, exact px (the tag's screen x + camera)
            obs.me_map = (round(me_s[0] + obs.cam[0], 1), round(me_s[1] + obs.cam[1], 1))

    def look(self, frames, obs: Observation, cursor=None) -> Observation:
        """Motion look: moving things on our ground line that aren't characters, drops, ghosts or the cursor."""
        p, z = self.cfg.perception, self.cfg.zones
        blobs, align = moving_blobs(frames)
        obs.look_align = align
        if obs.me is None:
            obs.moving = []
            return obs
        px, feet = obs.me
        tags = find_tags(frames[-1])
        obs.n_tags = len(tags)
        bodies = [(int(px - 30), int(feet - 130), 60, 147)]
        for tg in tags:
            body = tag_body(tg)
            if not any(overlaps(body, m, pad=0) for m in obs.bar_mobs):     # a tag under a mob HP bar is a mob's
                bodies.append(body)
        out = []
        for b in blobs:
            if b[2] < p.mob_min_w or b[2] * b[3] < p.mob_min_area:           # drops, butterflies, foliage
                continue
            if not reachable_level(b, feet, 18, z.step_down):               # floating (ghosts) / up on a ledge
                continue
            if any(overlaps(b, body, pad=0) for body in bodies) or any(overlaps(b, m) for m in obs.bar_mobs):
                continue
            if cursor and abs(cx(b) - cursor[0]) < 40 and abs(b[1] + b[3] / 2 - cursor[1]) < 40:
                continue
            out.append(b)
        if self.sprites is not None:
            # every mob type on this map has a sprite: motion that no sprite explains is grass in the wind, a coin,
            # a player (pkg_sprites1: 3 of 3 motion targets were flowers or a coin, ~6 s lost each)
            seen = [s[0] for s in self.sprites.find(frames[-1], feet, below=z.step_down)]
            out = [b for b in out if any(overlaps(b, s, pad=4) for s in seen)]
        obs.moving = out
        return obs
