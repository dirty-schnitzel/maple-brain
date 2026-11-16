"""FrameFacts: what ONE frame shows, nothing remembered (PLAN-perception.md step 2; ROADMAP phase 2's perception
record).

The Perceiver reads the frame once into these facts, then its memory parts (HUD smoothing, the tracker, the camera)
turn facts into the `Observation` the brain gets. Facts are pure data: no state of earlier frames inside, except
where a reading compares two frames by its nature (`scene_shift`, `plat_shift`: the scenery's motion since the frame
before) or was made on an earlier frame by a thread (`lie`: the newest finished Lie Detector look).
Versioned (`v`) and recordable: `as_dict` -> JSON (ticks.jsonl "facts") -> `from_dict` gives the same facts back.

v1 (2026-11-16): today's readings, unchanged - own tag, HUD numbers, quickslots, minimap dot / position, the two
camera shifts, the whole-screen detector's hits, players' name tags, the Lie Detector look.
"""
from dataclasses import asdict, dataclass, field, fields

from .gpu_sprites import Hit
from .sprites import Pose

VERSION = 1


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
    scene_shift: tuple | None = None      # (dx, dy) the whole frame moved since the frame before (phase correlation)
    plat_shift: tuple | None = None       # (dx, dy) the platforms moved since the frame before (camshift.py)
    scene_cam: tuple | None = None        # the camera registered on the scene model (scene.SceneCamera), exact px
    scene_share: float | None = None      # ... the share of its landmarks that matched (a wrong camera: ~2 %)
    hits: list = field(default_factory=list)       # [Hit] the whole-screen mob detector (gpu_sprites)
    tags: list = field(default_factory=list)       # [(x, y, w, h)] other characters' name tags (tags.find_tags)
    lie: tuple | None = None              # (on screen, score, top-left) of the newest finished Lie Detector look

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FrameFacts":
        if d.get("v") != VERSION:
            raise ValueError(f"FrameFacts v{d.get('v')} (this code reads v{VERSION})")

        def tup(v):
            return None if v is None else tuple(tup(x) if isinstance(x, list) else x for x in v)

        kw = {f.name: d[f.name] for f in fields(cls) if f.name in d}
        for k in ("tag", "hp", "mp", "dot", "map_pos", "scene_shift", "plat_shift", "scene_cam", "lie"):
            kw[k] = tup(kw.get(k))
        kw["tags"] = [tuple(x) for x in kw.get("tags") or []]
        kw["hits"] = [Hit(h["mob_id"], tuple(h["box"]), tuple(h["feet"]), Pose(**h["pose"]), h["score"])
                      for h in kw.get("hits") or []]
        return cls(**kw)
