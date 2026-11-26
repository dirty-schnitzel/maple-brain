"""FrameFacts: what ONE frame shows, nothing remembered (PLAN-perception.md step 2; ROADMAP phase 2's perception
record).

The Perceiver reads the frame once into these facts, then its memory parts (HUD smoothing, the tracker, the camera)
turn facts into the `Observation` the brain gets. Facts are pure data: no state of earlier frames inside, except
where a reading was made on an earlier frame by a thread (`lie`: the newest finished Lie Detector look) or depends on
the tracker's predictions (`fit_hints`).
Versioned (`v`) and recordable: `as_dict` -> JSON (ticks.jsonl "facts") -> `from_dict` gives the same facts back.

v1 (2026-11-16): own tag, HUD numbers, quickslots, minimap dot / position, the two camera shifts, the whole-screen
detector's hits, players' name tags, the Lie Detector look.
v2 (2026-11-16, step 3.1): + `patches` = D's blobs (scene.Scene.diff / patches).
v3 (2026-11-17, step 3.3): + `fit` (fit.FitMob dicts), `fit_ms`, `fit_hints` (one stage-2 look per track the fit
did not find).
v4 (2026-11-17, the old perception deleted): - `scene_shift`, `plat_shift` (phase correlation / camshift.py) and
`hits` (the old whole-screen detector): the camera is the scene camera's, the mobs are `fit`. Older records read
(those keys ignored; missing new ones None).
v5 (2026-11-17, PLAN-loot.md S8, in shadow: nothing reads them): + `drops` (perception/drops.py: one dict a sighting -
item class, meso frame, box, feet, kind rest / weak, the pixel counts, ring, foothold) and `drops_ms`.
v6 (2026-11-23, PLAN-moving-scenery.md step 3): + `movers` (scene.MoverFollow: per moving background, its place on
the map, found on this frame or coasting on its law, the share of its samples matching) and `movers_ms`; step 4:
+ `clouds` (perception/clouds.py: the weather clouds followed on a cloud map) and `clouds_ms`; step 5 (the clouds
undone): a `fit` dict carries `cloud` (mean cloud alpha over its SEEN pixels) and `n_cloud` (informative pixels
under a cloud too thick to undo), a `fit_hints` row the same two on a cloud map (older records: absent = 0).
v7 (2026-11-24, PLAN-tracker step 7): `slots` = the hotkey reader (perception/slots.py), every key of the bar:
{key: [kind, id, amount] or None}. Before v7 it held "an item is in it" (True / False / None) for the two potion keys
only: an older record's `slots` is read as {} (that reading is not this one).
v8 (2026-11-26, PLAN-tracker step 5a): + `meters` = the HP meters over the mobs we hit (perception/meters.py: per meter
its box's top-left, the green share or None, the frame columns seen, the `fit` mobs it may belong to) and `meters_ms`.
Older records: None (not read).
"""
from dataclasses import asdict, dataclass, field, fields

VERSION = 8


@dataclass
class FrameFacts:
    t: float
    v: int = VERSION
    tag: tuple | None = None              # own name tag (x, y, w, h, score): selfpos.find_self
    tag_look: str | None = None           # where it was looked for: "near" (the last place) / "wide" (whole screen)
    hp: tuple | None = None               # HUD "HP [cur/max]" as read on this frame (None: unreadable / covered)
    mp: tuple | None = None
    exp_points: int | None = None         # HUD "EXP. n" as read on this frame
    slots: dict = field(default_factory=dict)      # hotkey -> [kind, id, amount] read exactly on this frame (kind
                                          # item / skill / skill_disabled / skill_mouseover / action / empty; amount
                                          # None: none drawn), None: not readable (a tooltip, the cursor, a fade);
                                          # {}: not read (no pack). perception/slots.py
    dot: tuple | None = None              # minimap dot, relative to hud.MINIMAP_BOX's corner
    map_pos: tuple | None = None          # our feet on the map from the dot (nav.localize), with its platform / rope
    platform: int | None = None
    rope: float | None = None
    scene_cam: tuple | None = None        # the camera registered on the scene model (scene.SceneCamera), exact px;
                                          # None: not found this frame (the hunt pauses) / no clean scene
    scene_share: float | None = None      # ... the share of its landmarks that matched (a wrong camera: ~2 %)
    tags: list = field(default_factory=list)       # [(x, y, w, h)] other characters' name tags (tags.find_tags)
    lie: tuple | None = None              # (on screen, score, top-left) of the newest finished Lie Detector look
    patches: list | None = None           # [(x, y, w, h, area)] what the scene doesn't explain (D, scene.patches);
                                          # None: no D on this frame (no clean scene / camera not found)
    fit: list | None = None               # [FitMob.to_dict()] the fit's mobs (perception/fit.py); None: not run
    fit_ms: float | None = None           # ... its ms (Fitter.ms["fit"]; the looks not counted)
    fit_hints: list | None = None         # [Fitter.look rows] tracks the fit did not find, looked at once each
    drops: list | None = None             # [drops.DropFinder.fetch dicts] item pictures on screen; None: not run
                                          # (no scene camera / perception.drops off)
    drops_ms: dict | None = None          # ... the main thread's ms (launch / fetch / pick) + feature counts
    movers: list | None = None            # [(back index, place X on the map or None = never found, found on this
                                          # frame, share)] the moving backgrounds (scene.MoverFollow); None: the map
                                          # has none / no camera. Not found = coasting on its law; X None = its rows
                                          # are unknown to the scene model now
    movers_ms: float | None = None        # ... MoverFollow.update's ms
    clouds: list | None = None            # [(id, picture, map x, map y of its top-left, vx, vy, opacity, seen on this
                                          # frame, share, informative px)] the weather clouds on screen (perception/
                                          # clouds.py); None: not a cloud map / no camera. On screen = undone
                                          # before D, the fit and the drops (step 5)
    clouds_ms: dict | None = None         # ... its parts' ms (follow, layer, whitened, find) + residue_px
    meters: list | None = None            # [(x0, y0, fill, cols, cand)] the HP meters over mobs we hit (perception/
                                          # meters.py): the box's top-left (screen px), the green share 0..1 (None: not
                                          # known - its end or the green's end not seen), the frame columns seen (48 =
                                          # all), the indexes into `fit` of the mobs whose expected box it is at; None:
                                          # not read (no camera / no fit / perception.meters off)
    meters_ms: float | None = None        # ... MeterReader.read's ms

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FrameFacts":
        if d.get("v") not in (1, 2, 3, 4, 5, 6, 7, VERSION):
            raise ValueError(f"FrameFacts v{d.get('v')} (this code reads v1-v{VERSION})")

        def tup(v):
            return None if v is None else tuple(tup(x) if isinstance(x, list) else x for x in v)

        kw = {f.name: d[f.name] for f in fields(cls) if f.name in d}
        if d.get("v") not in (7, VERSION):
            kw.pop("slots", None)                       # v1-v6: the two potion keys' "holds something", not this
        for k in ("tag", "hp", "mp", "dot", "map_pos", "scene_cam", "lie"):
            kw[k] = tup(kw.get(k))
        kw["tags"] = [tuple(x) for x in kw.get("tags") or []]
        if kw.get("patches") is not None:
            kw["patches"] = [tuple(x) for x in kw["patches"]]
        for k in ("movers", "clouds"):
            if kw.get(k) is not None:
                kw[k] = [tuple(x) for x in kw[k]]
        if kw.get("meters") is not None:
            kw["meters"] = [tuple(x[:4]) + (tuple(x[4]),) for x in kw["meters"]]
        return cls(**kw)
