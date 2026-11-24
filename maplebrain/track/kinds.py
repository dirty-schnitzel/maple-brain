"""The mob kinds' facts for the tracker (PLAN-tracker.md design 4; the reference: tools/perc/track/proto_mobs.py
`Kind`). Per kind, from the client files (assets/mcw mobs/<id>/mob.json and its pictures): its top speed, whether
it jumps / flies, how long its die animation runs, its body box, its full size, its body's CORE and its look-alike
poses. Fixed per map; step 6 moves the numbers into the facts registry (state_model.md section 5).

  speed     the files' rule ((speed + 100) x 0.625 px/s; a flyer (flySpeed + 100) x 1.25) x Track.mob_speed_x (2.0:
            measured, PLAN-tracker measurement 4) = `v`, the speed a possible set widens at; `vb` = the frame-to-frame
            bound (at least a knockback's Track.knock_v x mob_speed_x).
  die_s     the die1 frames' delays summed (0.6 s when there are none).
  lt, rb    the body box of the first stand (else move, fly) frame around the feet; half_w its half width.
  full      the median drawn size (alpha > 128 pixels) of its live poses (stand, move, fly, jump, hit1).
  core      the pixels EVERY live pose covers (feet at 0, 0; under 200 of them: those 80 % of the poses cover),
            every third one kept when there are more than 300 -> (cdx, cdy): where a possible set's place is tested.
  alike     one picture (same facing) under two feet points (a Bubbling's jump = its walking picture drawn 17 px
            higher): {(pose, facing): [(other pose, dx, dy)]} - the fit names either, the tracker keeps both.
"""
from dataclasses import dataclass

import numpy as np

LIVE_ANIMS = ("stand", "move", "fly", "jump", "hit1")
CANVAS = (400, 400)                     # the core's canvas: feet at row 300, column 200
FEET = (300, 200)


@dataclass
class Kind:
    id: int
    fly: bool
    jump: bool
    v_file: float                       # px/s: the files' top speed (the v83 rule)
    v: float                            # px/s: the top speed it is seen to move at (v_file x mob_speed_x)
    vb: float                           # px/s: the bound from one frame to the next
    die_s: float
    lt: tuple
    rb: tuple
    half_w: float
    full: float
    core_n: int                         # pixels in the core (before thinning)
    cdx: np.ndarray                     # int64 offsets from the feet of the core's kept pixels
    cdy: np.ndarray
    alike: dict
    name: str = ""

    @property
    def box_w(self) -> float:
        return max(1, self.rb[0] - self.lt[0])

    @property
    def box_h(self) -> float:
        return max(1, self.rb[1] - self.lt[1])


def kind(mob_id: int, info: dict, poses: list, speed_x: float, knock_v: float) -> Kind:
    """One kind from its mob.json dict and the map's poses (perception/vote.load_poses: every pose, both facings)."""
    fr, inf = info.get("frames") or {}, info.get("info") or {}
    fly, jump = bool(fr.get("fly")), bool(fr.get("jump"))
    v_file = ((inf.get("flySpeed") or 0) + 100) * 1.25 if fly else ((inf.get("speed") or 0) + 100) * 0.625
    v = v_file * speed_x
    vb = max(v, knock_v * speed_x)
    die_s = sum((f.get("delay") or 100) for f in fr.get("die1") or []) / 1000 or 0.6
    f0 = (fr.get("stand") or fr.get("move") or fr.get("fly") or [{}])[0]
    lt, rb = tuple(f0.get("lt") or [-30, -50]), tuple(f0.get("rb") or [30, 0])
    mine = [p for p in poses if p.type == mob_id]
    live = [p for p in mine if p.pose.rsplit("_", 1)[0] in LIVE_ANIMS]
    full = float(np.median([(p.pic[..., 3] > 128).sum() for p in live])) if live else 1000.0
    H, W = CANVAS
    fy0, fx0 = FEET
    cv = np.zeros((len(live), H, W), bool)
    for k, p in enumerate(live):
        h, w = p.pic.shape[:2]
        y0, x0 = fy0 - p.oy, fx0 - p.ox
        cv[k, max(0, y0):y0 + h, max(0, x0):x0 + w] = \
            (p.pic[..., 3] > 128)[max(0, -y0):, max(0, -x0):][:H - max(0, y0), :W - max(0, x0)]
    core = cv.all(axis=0)
    if core.sum() < 200:
        core = cv.mean(axis=0) >= 0.8
    ys, xs = np.nonzero(core)
    sel = ((ys + xs) % 3 == 0) if len(ys) > 300 else np.ones(len(ys), bool)
    alike, by_pic = {}, {}
    for p in mine:
        by_pic.setdefault((p.facing, p.pic.shape, p.pic.tobytes()), []).append(p)
    for (facing, _, _), ps in by_pic.items():
        for a in ps:
            for b in ps:
                if a is not b and (a.ox, a.oy) != (b.ox, b.oy):
                    alike.setdefault((a.pose, facing), []).append((b.pose, b.ox - a.ox, b.oy - a.oy))
    return Kind(mob_id, fly, jump, v_file, v, vb, die_s, lt, rb, (rb[0] - lt[0]) / 2, full, len(ys),
                (xs[sel] - fx0).astype(np.int64), (ys[sel] - fy0).astype(np.int64), alike, info.get("name", ""))


def kinds(mobs: dict, poses: list, speed_x: float, knock_v: float) -> dict:
    """{mob id: Kind} for the map's kinds (`mobs` = {id: mob.json dict}, as MapKit.mobs)."""
    return {int(i): kind(int(i), m, poses, speed_x, knock_v) for i, m in mobs.items()}
