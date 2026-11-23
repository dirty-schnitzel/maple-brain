"""Frame -> Observation. Stateful only where perception needs memory (the tracker, HUD smoothing); it never presses
keys and never decides anything.

The mob path (PLAN-perception.md; the old detectors deleted 2026-11-17): the frame goes to the GPU once; the scene
camera registers it on the map's scene model (scene.SceneCamera, clean maps only) -> the camera, exact; the fit
(perception/fit.py) explains the frame's mobs -> the tracker's sightings; the fit's look at every track it did not
find is the tracker's search around tracks (world.py). No scene camera on a tick (not found / no clean scene): no
camera, no mobs that tick (obs.scene_cam None) - the hunt pauses on it (runtime/hunt_v2.py).
Drops (PLAN-loot.md, in shadow - nothing reads them): with the camera found, the drop pass (perception/drops.py, ONE
DropFinder per process, MapKit.drops) is launched on its own CUDA stream right after the expected scene and read after
the fit and the tracker (it needs the fit's explained pixels and the characters' tags) -> FrameFacts.drops.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import time

import cv2
import numpy as np

from ..config import Config
from . import hud
from .facts import FrameFacts
from .selfpos import find_self
from .tags import find_tags
from .vote import PLAY_H, SW


@dataclass
class Observation:
    t: float
    me: tuple | None = None                 # (px, feet): our centre x and the top of our name tag
    hp: float = 1.0                         # HP share from the HUD's exact "HP [cur/max]" numbers
    mp: float = 1.0                         # MP share from "MP [cur/max]"
    hp_now: int | None = None               # the exact numbers (None until first read; a covered HUD keeps the
    hp_max: int | None = None               # last good reading)
    mp_now: int | None = None
    mp_max: int | None = None
    hp_potions: bool | None = None          # an item sits in the HP potion key's quickslot (None: can't tell)
    mp_potions: bool | None = None
    exp_points: int | None = None           # HUD "EXP. 885" points (median of the last 3 readable ones), exact
    dot: tuple | None = None                # our minimap position
    lie_detector: bool = False              # the game's Lie Detector (anti-bot test) is on screen
    map_pos: tuple | None = None            # our feet in map coordinates (nav.localize; needs the map)
    platform: int | None = None             # the platform we stand on (nav.navmap id); None: air / rope / unknown
    rope: float | None = None               # x of the rope we're on
    mobs: list = field(default_factory=list)          # the tracker's tracks (world.Track.as_dict)
    cam: tuple | None = None                # the camera: map = screen + cam (the scene camera's; None: not found)
    cam_src: str | None = None              # "exact" when the scene camera was found this tick, else None
    me_map: tuple | None = None             # our feet on the map from our tag + cam: exact px (minimap: 16 px steps)
    scene_cam: tuple | None = None          # the camera from the scene model (exact px; None: not found / no scene)


@dataclass
class MapKit:
    """What perception needs of the hunt's map (runtime.runner._load_map, loaded once per map)."""
    map_id: int
    nav: object                             # nav.navmap.NavMap
    mobs: dict                              # mob id -> mob.json dict (the map's mob types)
    dev: object = None                      # the torch device (the frame's one upload, the GPU looks)
    scene: object = None                    # scene.Scene (clean maps only; None: see `why`)
    fitter: object = None                   # fit.Fitter on that scene
    cover: object = None                    # cover.Cover (world.py's `hidden` state; until step 4)
    drops: object = None                    # drops.DropFinder: ONE per process, shared by every map's kit (None: off)
    why: str = ""                           # no scene camera on this map: why (the hunt refuses to start)

    @property
    def clean(self) -> bool:
        """The map has the scene camera + the fit: the only mob perception there is."""
        return self.scene is not None and self.fitter is not None

    @property
    def names(self) -> dict:
        return {i: m.get("name", str(i)) for i, m in self.mobs.items()}


def _patches(blob):
    """D's blob mask -> (its patches, ms) on a reader thread (cv2 releases the GIL)."""
    from ..scene import patches
    t0 = time.perf_counter()
    out = patches(blob)
    return out, round(1000 * (time.perf_counter() - t0), 1)


class Perceiver:
    def __init__(self, cfg: Config, self_template: np.ndarray, kit: MapKit | None = None, lie_detector=None,
                 locator=None):
        """`kit` None: no map - our tag, HUD, Lie Detector and minimap only (on the CPU)."""
        self.cfg, self.tpl, self.kit = cfg, self_template, kit
        self.locator = locator                          # nav.localize.MinimapLocator, or None (no map position)
        self.canvas_try = -1.0
        self.lie_detector = lie_detector                # LieDetector, or None (not checked)
        self.me_near = None
        self.wide_next_t = -1e9                         # tag lost: next whole-screen look
        self.hp_pair = None                             # last accepted (cur, max) from the HUD text
        self.mp_pair = None
        self.new_max = {}                               # "hp"/"mp" -> a max seen once (a level-up / gear changes
                                                        # it; one misread must not)
        self.slot_hist = {}                             # key -> recent slot readings (majority vote)
        self.hud_text = hud.HudText()                   # HP / MP / EXP text, re-read only when it changed
        self.points_hist = deque(maxlen=3)
        self.last_t = 0.0
        # the CPU readers' threads (2.9b): our tag + grey, HUD, players' tags - one each, beside the GPU work
        self.readers = ThreadPoolExecutor(3, thread_name_prefix="read")
        self._pending = []                              # this tick's readers until it ends
        self.dev = kit.dev if kit is not None else None
        self.frame_u8 = None                            # this tick's frame on the GPU (uint8 h, w, 3)
        self.tag_gpu = None                             # our tag's whole-frame look on the GPU (step 2.7)
        if self.dev is not None:
            import torch
            self.torch = torch
            from .selfpos import GpuTagLook
            self.tag_gpu = GpuTagLook(self_template, self.dev)
            if lie_detector is not None and cfg.perception.lie_gpu:     # its look on the uploaded frame (step 2.8)
                lie_detector.use_gpu(self.dev)
        self.world = self.scene_cam = self.fitter = self.drops = self.movers = None
        if kit is not None and kit.clean and self.dev is not None:
            from ..scene import SceneCamera
            from .world import World
            self.world = World(kit.nav, kit.mobs, cover=kit.cover)
            self.scene_cam = SceneCamera(kit.scene, tol=cfg.perception.scene_tol)
            # the moving backgrounds' places (PLAN-moving-scenery.md step 3): None on a map without one
            if any(b.get("mover") is not None for b, _ in kit.scene.backs):
                from ..scene import MoverFollow
                self.movers = MoverFollow(kit.scene, cfg.perception)
            self.fitter = kit.fitter
            if kit.drops is not None:                   # drops (PLAN-loot.md, in shadow): this map's footholds and
                self.drops = kit.drops                  # front planes
                self.drops.set_map(kit.map_id, kit.scene)
        self._fit_ui = (None, None)                     # (hud.ui_mask array, the fit's GPU mask of it)
        self._look_ms = 0.0                             # this tick's looks (the search around tracks)
        self.minimap_t = -1e9                           # last minimap read (only ~1 / s while the scene camera holds)

    @property
    def minimap(self) -> tuple | None:
        """The minimap window's rectangle as the locator last measured it (it differs per map: Line 1 277 px wide),
        or None = hud.UI_RECTS' default: what the UI mask leaves out for our tag and players' tags."""
        w = getattr(getattr(self, "locator", None), "window", None)
        return hud.minimap_rect(w) if w is not None else None

    def _wide_tag(self, frame, gray, min_score, edges):
        """Our tag anywhere on the screen. With the GPU: its look finds the best place, the CPU's near search confirms
        it (the same place and score as the CPU's whole-frame look); nothing there and the tag was last near a
        screen side -> the CPU's look with its edge search (a tag cut by the screen's side), as before."""
        if self.tag_gpu is None:
            return find_self(frame, self.tpl, min_score=min_score, edges=edges, gray=gray, minimap=self.minimap)
        _, x, y = self.tag_gpu.look(self.frame_u8, hud.ui_mask(frame.shape, self.minimap))
        me = find_self(frame, self.tpl, near=(x + self.tpl.shape[1] / 2, y), radius=40, min_score=min_score,
                       edges=False, gray=gray, minimap=self.minimap)
        if me is None and edges:
            me = find_self(frame, self.tpl, min_score=min_score, edges=True, gray=gray, minimap=self.minimap)
        return me

    def _exact(self) -> bool:
        """The scene camera had the camera on the last tick: the minimap is then read only ~1 / s."""
        return self.scene_cam is not None and self.scene_cam.found

    def _locate(self, frame, obs, fresh: bool = False):
        """Minimap dot -> obs.dot; with a locator also our map position, platform and rope. The minimap canvas is
        searched (3.6 ms) until found, at most about once a second (window closed / covered). A window showing only
        part of the canvas scrolls with us: followed every tick, before the dot is read against it. `fresh`: not read
        for a while (the scene camera held): a scrolled window may have moved past `follow`'s reach - found anew."""
        loc = self.locator
        if fresh and loc is not None and loc.view is not None and loc.origin is not None:
            loc.lost, self.canvas_try = True, -1e9
        if loc is not None and (loc.origin is None or loc.lost) and obs.t - self.canvas_try >= 1.0:
            self.canvas_try = obs.t
            loc.calibrate(frame)
        if loc is not None:
            loc.follow(frame)
        f = self.facts
        obs.dot = f.dot = hud.minimap_dot(frame, loc.dot_box() if loc is not None else hud.MINIMAP_BOX)
        w = loc.where(obs.dot) if loc is not None else None
        if w is not None:
            f.map_pos, f.platform, f.rope = (round(w.x, 1), round(w.y, 1)), w.platform, w.rope
            obs.map_pos, obs.platform, obs.rope = f.map_pos, f.platform, f.rope

    def _pair(self, r, name, last):
        """The HUD's [cur/max] for HP or MP from this frame's reading `r` (FrameFacts hp / mp). Unreadable (covered)
        -> the last good reading. A different max is taken only when read twice in a row (level-up / gear), so a
        single misread can't change it."""
        if r is None:
            return last
        if last is not None and r[1] != last[1]:
            if self.new_max.get(name) != r[1]:
                self.new_max[name] = r[1]
                return last
        self.new_max.pop(name, None)
        return r

    def _slot(self, key, slots):
        """Majority of the last 5 readings of `key`'s quickslot; a frame with the cursor over the key layout is
        skipped (its tooltip covers the slots next to it: pkg_sprites7b frame 300). `slots`: this frame's readings
        (`_read_hud`), None when skipped."""
        h = self.slot_hist.setdefault(key, deque(maxlen=5))
        self.facts.slots[key] = None
        if slots is not None:
            v = self.facts.slots[key] = slots.get(key)
            if v is None:
                return None
            h.append(v)
        return (sum(h) * 2 > len(h)) if h else None

    # ---- the CPU readers (2.9b): pure, run on `self.readers` while the GPU works
    def _read_self(self, frame, near, minimap):
        """The frame's grey and our tag's near search around `near` (None: not searched) -> (gray, tag or None)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        me = None
        if near is not None:
            me = find_self(frame, self.tpl, near=near, min_score=self.cfg.perception.self_near_score, gray=gray,
                           minimap=minimap)
        return gray, me

    def _read_hud(self, frame, cursor):
        """HP / MP / EXP text (cached while unchanged) + the potion keys' quickslots (None: the cursor is over
        them) -> (hp, mp, exp points, {key: filled} or None). Only this reader touches `hud_text`."""
        hp, mp, pts = self.hud_text.read(frame)
        keys = (self.cfg.keys.hp_potion, self.cfg.keys.mp_potion)
        slots = None if hud.in_quickslots(cursor) else {k: hud.slot_filled(frame, k) for k in keys}
        return hp, mp, pts, slots

    def observe(self, frame, t: float, cursor=None) -> Observation:
        p = self.cfg.perception
        obs = Observation(t=t)
        f = self.facts = FrameFacts(t=t)                    # what this frame shows (facts.py); obs = facts + memory
        self.last_t = t
        self.parts, self._t0 = {}, time.perf_counter()      # ms per part of this frame (ticks timings.parts)
        # step 2.9b: the frame goes to the GPU first, then the CPU readers start on their threads (the frame's grey +
        # our tag's near search / the HUD text + quickslots / players' tags) while this thread runs the GPU work.
        # Readers are pure (frame + what they're handed now -> readings); everything with memory is applied below,
        # on this thread, after the join.
        for fut in self._pending:                       # a tick that raised: its readers end before new ones start
            fut.result()
        if self.dev is not None:
            self.frame_u8 = self.torch.from_numpy(np.ascontiguousarray(frame)).to(self.dev)
        mm = self.minimap
        rd_self = self.readers.submit(self._read_self, frame, self.me_near, mm)
        rd_hud = self.readers.submit(self._read_hud, frame, cursor)
        tags = self.readers.submit(find_tags, frame, None, mm) if self.world is not None else None
        self._pending = [x for x in (rd_self, rd_hud, tags) if x is not None]
        self._mark("upload")
        if self.lie_detector is not None:
            on_gpu = self.frame_u8 is not None and self.lie_detector.gpu is not None
            g = None if on_gpu else rd_self.result()[0]                           # the CPU look needs the grey
            f.lie = self.lie_detector.check(frame, t, gray=g, frame_u8=self.frame_u8 if on_gpu else None)
            obs.lie_detector = f.lie[0]
        self._mark("lie")
        gray, me = rd_self.result()
        self._mark("scene")
        if self.me_near is not None:
            f.tag_look = "near"
        if me is None and not 0 < self.wide_next_t - t <= 1.0:   # lost: the whole screen ~4x a second (25-150 ms;
            near_edge = self.me_near is None or not 150 < self.me_near[0] < frame.shape[1] - 150   # the minimap
            me = self._wide_tag(frame, gray, p.self_min_score, near_edge)                          # meanwhile)
            f.tag_look = "wide"
            self.wide_next_t = t + (0 if me is not None else p.self_wide_every_s)
            self._mark("self_wide")
        f.tag = me
        self._mark("self")
        f.hp, f.mp, pts, slots = rd_hud.result()
        self.hp_pair = self._pair(f.hp, "hp", self.hp_pair)
        self.mp_pair = self._pair(f.mp, "mp", self.mp_pair)
        if self.hp_pair:
            obs.hp_now, obs.hp_max = self.hp_pair
            obs.hp = self.hp_pair[0] / self.hp_pair[1]
        if self.mp_pair:
            obs.mp_now, obs.mp_max = self.mp_pair
            obs.mp = self.mp_pair[0] / self.mp_pair[1]
        obs.hp_potions = self._slot(self.cfg.keys.hp_potion, slots)
        obs.mp_potions = self._slot(self.cfg.keys.mp_potion, slots)
        f.exp_points = pts
        if pts is not None:
            self.points_hist.append(pts)
        if len(self.points_hist) == 3:                  # 2 of 3 agree: one misread never makes a kill
            obs.exp_points = int(np.median(self.points_hist))
        self._mark("hud")
        if not (self._exact() and me is not None and t - self.minimap_t < p.minimap_every_s):
            self._locate(frame, obs, fresh=t - self.minimap_t > 0.5)   # the minimap: the camera's seed, and our map
            self.minimap_t = t                                         # position without a tag (SelfTracker)
        self._mark("locate")
        if self.world is not None:
            self._track(frame, obs, me, tags)
        self._pending = []
        if me is not None:
            self.me_near = (me[0] + me[2] / 2, me[1])
            obs.me = self.me_near
        return obs

    def _mark(self, name):
        now = time.perf_counter()
        self.parts[name] = round(self.parts.get(name, 0) + 1000 * (now - self._t0), 1)
        self._t0 = now

    def _track(self, frame, obs, me, tags):
        """The scene camera, then (found) D, the fit and the tracker; `tags` = the players' tags reader (players'
        bodies hide mobs, drawn over them). Not found: no camera, no mobs this tick (the tracks wait as they are)."""
        f, sc = self.facts, self.scene_cam
        me_s = (me[0] + me[2] / 2, me[1]) if me is not None else None
        # the camera registered on the scene model (step 2.6), on the uploaded frame. Seed: the last camera; at the
        # start (or after a map change) the minimap's (our map position - our screen position)
        seed = self.world.cam.C
        if seed is None and obs.map_pos is not None and me_s is not None:
            seed = (obs.map_pos[0] - me_s[0], obs.map_pos[1] - me_s[1])
        ui = hud.ui_mask(frame.shape, self.minimap)
        exact = sc.update(self.frame_u8, seed=seed, mask=ui)
        self._mark("scenecam")
        if exact is None:
            f.tags = tags.result()
            return
        f.scene_cam, f.scene_share = exact, round(sc.share, 3)
        obs.scene_cam, obs.cam_src = exact, "exact"
        X = None
        if self.movers is not None:                     # the moving backgrounds' places, then drawn into the scene
            t = time.perf_counter()
            X = self.movers.update(self.frame_u8, exact, obs.t)
            mv = self.movers
            f.movers = [(i, None if X[i] is None else round(X[i], 2), bool(mv.found[j]), round(float(mv.share[j]), 3))
                        for j, i in enumerate(mv.idx)]
            f.movers_ms = round(1000 * (time.perf_counter() - t), 2)
            self._mark("movers")
        ek = sc.scene.expected(exact, X=X)              # ONE expected scene a tick: D, the fit and the drops (3.3)
        drops = self.drops is not None and self.cfg.perception.drops
        if drops:                                       # the drop pass starts on its own CUDA stream; read after the
            t = time.perf_counter()                     # fit and the tracker (part `drops` = its main-thread ms)
            self.drops.launch(self.frame_u8, exact, ek[0], ek[1], self._world_ui(frame.shape))
            self._aside("drops", t)
        d_list = None
        if self.cfg.perception.scene_diff:
            # D (step 3.1): the unexplained pixels' blobs on the GPU, their list from a reader thread while the
            # tracker runs -> FrameFacts.patches
            blob = sc.scene.diff(self.frame_u8, exact, tol=sc.tol, mask=sc._mask_t(ui), ek=ek)
            d_list = self.readers.submit(_patches, blob)
            self._mark("diff")
        # step 3.4: the fit's mobs are the sightings; its look at each unseen track's predicted feet is the search
        # around tracks
        mobs = self._fit_mobs(self.frame_u8, exact, ek, me_s, frame.shape)
        hits, f.fit_hints = [self.fitter.hit(m.type, m.pose, m.facing, m.feet) for m in mobs], []
        self._look_ms = 0.0
        f.tags = tags.result()
        trs = self.world.update(obs.t, hits, exact, me_s, tags=f.tags, look=self._look)
        self._mark("world")
        self.parts["world"] = round(self.parts["world"] - self._look_ms, 1)     # the looks: their own part
        self.parts["hints"] = round(self._look_ms, 1)
        if drops:
            f.drops = self._fetch_drops(me_s, f.tags, [h.box for h in hits])
            f.drops_ms = self.drops.ms
            self._mark("drops")
        if d_list is not None:
            f.patches, self.parts["patches"] = d_list.result()
        obs.mobs = [tr.as_dict(obs.t) for tr in trs]
        obs.cam = tuple(round(v, 1) for v in self.world.cam.C)
        if me_s is not None:                           # our feet on the map, exact px (the tag's screen x + camera)
            obs.me_map = (round(me_s[0] + obs.cam[0], 1), round(me_s[1] + obs.cam[1], 1))

    def _look(self, trs) -> list:
        """The search around tracks (step 3.4; world.update's `look`): the fit's look at each track's predicted
        feet; SEEN by the fit's own rule -> a Hit there (score 1.0), ABSENT / COVERED -> None (the tracker's
        timeouts stay until step 4). The rows -> facts.fit_hints."""
        t0, fz = time.perf_counter(), self.fitter
        rows = fz.look(trs)
        self.facts.fit_hints += [r for r in rows if r is not None]
        out = [fz.hit(r["mob"], r["pose"], r["facing"], (r["sx"], r["sy"])) if r is not None and fz.seen(r) else None
               for r in rows]
        self._look_ms += 1000 * (time.perf_counter() - t0)
        return out

    def _aside(self, name, t):
        """The time since `t` -> part `name`, left out of the next `_mark`'s part."""
        dt = time.perf_counter() - t
        self.parts[name] = round(self.parts.get(name, 0) + 1000 * dt, 1)
        self._t0 += dt

    def _world_ui(self, shape):
        """The world mask on the GPU (bool (PLAY_H, SW), True = may show a mob / drop): D's UI mask (the measured
        minimap) with the chat rect as world (the user keeps the chat minimized); remade when the UI mask changes."""
        ui = hud.ui_mask(shape, self.minimap)
        if self._fit_ui[0] is not ui:
            m = ui[:hud.CHAT_WORLD[3]] > 0
            x0, y0, x1, y1 = hud.CHAT_WORLD
            m[y0:y1, x0:x1] = True
            self._fit_ui = (ui, self.torch.from_numpy(np.ascontiguousarray(m)).to(self.dev))
        return self._fit_ui[1]

    def _fetch_drops(self, me_s, tags, mob_boxes) -> list:
        """The drop pass' sightings (drops.DropFinder.fetch) with what the tick knows by now: the pixels the fit's
        accepted mobs explained (+ their boxes), the characters' body boxes (our tag's, the players' tags')."""
        fz = self.fitter
        mob = None
        if fz.taken is not None:
            P = max(fz.KH, fz.KW)
            mob = fz.taken[P:P + PLAY_H, P:P + SW]
        feet = ([me_s] if me_s is not None else []) + [(x + w / 2, y) for x, y, w, h in tags or []]
        return self.drops.fetch(mob, [(cx - 42, fy - 90, cx + 42, fy + 22) for cx, fy in feet], mob_boxes)

    def _fit_mobs(self, frame_u8, C, ek, me_s, shape) -> list:
        """The fit (perception/fit.py) on the uploaded frame with this tick's expected scene `ek` (D's), ui =
        `_world_ui`, our body box kept out of the fade search -> [FitMob], facts.fit / fit_ms. Part `fit`."""
        f, fz = self.facts, self.fitter
        me = None if me_s is None else (me_s[0] - 40, me_s[1] - 85, me_s[0] + 40, me_s[1] + 30)
        mobs = fz.fit(frame_u8, C, ek[0], ek[1], self._world_ui(shape), me)
        f.fit, f.fit_ms = [m.to_dict() for m in mobs], round(fz.ms["fit"], 2)
        self._mark("fit")
        return mobs
