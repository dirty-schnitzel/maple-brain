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
"""
from dataclasses import asdict, dataclass, field, fields

VERSION = 5


@dataclass
class FrameFacts:
    t: float
    v: int = VERSION
    tag: tuple | None = None              # own name tag (x, y, w, h, score): selfpos.find_self
    tag_look: str | None = None           # where it was looked for: "near" (the last place) / "wide" (whole screen)
    hp: tuple | None = None               # HUD "HP [cur/max]" as read on this frame (None: unreadable / covered)
    mp: tuple | None = None
    exp_points: int | None = None         # HUD "EXP. n" as read on this frame
    slots: dict = field(default_factory=dict)      # quickslot key -> an item in it (None: can't tell / not read)
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

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FrameFacts":
        if d.get("v") not in (1, 2, 3, 4, VERSION):
            raise ValueError(f"FrameFacts v{d.get('v')} (this code reads v1-v{VERSION})")

        def tup(v):
            return None if v is None else tuple(tup(x) if isinstance(x, list) else x for x in v)

        kw = {f.name: d[f.name] for f in fields(cls) if f.name in d}
        for k in ("tag", "hp", "mp", "dot", "map_pos", "scene_cam", "lie"):
            kw[k] = tup(kw.get(k))
        kw["tags"] = [tuple(x) for x in kw.get("tags") or []]
        if kw.get("patches") is not None:
            kw["patches"] = [tuple(x) for x in kw["patches"]]
        return cls(**kw)
