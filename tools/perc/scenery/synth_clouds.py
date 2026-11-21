"""Prototype: how thick may a cloud be before the fit stops finding the mob under it? Truth by construction.

Real frames of a capture; where the frame shows only the scene (explained, valid) a mob sprite of the map is pasted
standing on a foothold, then ONE cloud picture (random picture, opacity, place) is blended over it the way the
client does (frame = under + o a (s - under), rounded). Then, per placement:
  none    the mob, no cloud                                   (the fit's own recall here)
  raw     the cloud left in the frame                         (what happens with no cloud handling)
  undone  the cloud undone: frame' = (frame - P) / (1 - A)    (the plan's)
-> found share per mean cloud alpha over the mob's pixels.     python synth_clouds.py CAP [--n 600]"""
import argparse
import json
import random

import numpy as np
import torch

import cam as camlib
import clouds as cl
import fastpipe
import msl
import proto
from maplebrain.perception import hud
from maplebrain.perception.fit import Fitter

SW, PLAY_H = 1366, 700
ap = argparse.ArgumentParser()
ap.add_argument("cap")
ap.add_argument("--n", type=int, default=600)
ap.add_argument("--amax", type=float, default=0.9)
a = ap.parse_args()
msl.guard()
rnd = random.Random(7)
c = msl.clip(a.cap)
fr = c.frames()
cams = [r for r in camlib.cams(a.cap)["rows"] if r[3] is not None]
ms = proto.MScene(c.map_id)
cf = cl.CloudFinder(ms.dev)
fc = fastpipe.FastClouds(cf)
ASSETS = msl.ROOT / "assets" / "mcw"
fz = Fitter(ms.scene, c.map_id, ASSETS)
m = json.loads((ASSETS / "maps" / str(c.map_id) / "map.json").read_text(encoding="utf-8"))
fhs = [f for f in (m.get("footholds") or {}).values() if f["x1"] != f["x2"]]
poses = [(g, p) for g, p in enumerate(fz.poses) if p.pose.split("_")[0] in ("stand", "move")]
ui = None
res = []
tries = 0
order = list(range(0, len(cams)))
rnd.shuffle(order)


class CloudVote:
    """The vote's palette ids under a cloud: an undone pixel is off its sprite colour by up to ~0.5 / (1 - A)
    levels (the frame's rounding, amplified), so there the id comes from the Voter's TOLERANT tables (the fade
    search's, FADE_TOLS = +-2 / 3 / 4 / 6 levels) at the level the pixel's cloud alpha asks for - exact elsewhere."""

    def __init__(self, voter):
        self.v, self.orig = voter, voter.ids
        self.A = None

    def ids(self, frame, exp=None, known=None, tol=4.0, resid=False):
        out = self.orig(frame, exp, known, tol, resid)
        if self.A is None or exp is None:
            return out
        ids = out[0] if resid else out
        v = self.v
        A = self.A
        need = 1.0 + 0.5 / (1 - A).clamp(min=0.05)
        tols = torch.tensor(v.FADE_TOLS, dtype=need.dtype, device=need.device)
        li = (need[..., None] > tols).sum(dim=-1).clamp_(max=len(v.FADE_TOLS) - 1)
        key = v._key(frame[:700].float()) + li * 258 ** 3 + (1 + 258 + 258 * 258)
        unexpl = (frame[:700].float() - exp).abs().amax(dim=2) > tol
        if known is not None:
            unexpl |= ~known
        m = (A > 0.004) & (ids == 0) & unexpl
        ids = torch.where(m, v.lut_tol[key], ids)
        return (ids, out[1], out[2]) if resid else ids


cv = CloudVote(fz.voter)
fz.voter.ids = cv.ids


def found(mobs, typ, fx, fy):
    return any(mb.type == typ and abs(mb.feet[0] - fx) <= 3 and abs(mb.feet[1] - fy) <= 3 for mb in mobs)


for j in order:
    if len(res) >= a.n:
        break
    r = cams[j]
    i = r[0]
    img = c.read(fr[i][1])
    if ui is None:
        mk = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
        mk = mk.copy()
        x0, y0, x1, y1 = hud.CHAT_WORLD
        mk[y0:y1, x0:x1] = True
        ui = torch.from_numpy(np.ascontiguousarray(mk[:700])).to(ms.dev)
    f = proto.frame_tensor(img, ms.dev)
    C = (r[3], r[4])
    for k_, mv in ms.movers.items():                      # every frame alone: the movers looked for anew
        mv.X, mv.lost_n = None, 0
    ms.locate(f, C, fr[i][2])
    E1, known = ms.expected(C)
    valid = known & ui
    expl = ((f.float() - E1).abs().amax(dim=2) <= 4) & valid
    base = fz.fit(f, C, E1, known, ui)
    for _ in range(6):
        tries += 1
        fh = rnd.choice(fhs)
        tt = rnd.random()
        mx = fh["x1"] + tt * (fh["x2"] - fh["x1"])
        my = fh["y1"] + tt * (fh["y2"] - fh["y1"])
        fx, fy = int(round(mx - C[0])), int(round(my - C[1]))
        g, p = rnd.choice(poses)
        h, w = p.pic.shape[:2]
        bx, by = fx - p.ox, fy - p.oy
        if bx < 10 or by < 10 or bx + w > SW - 10 or by + h > PLAY_H - 10:
            continue
        if float(expl[by:by + h, bx:bx + w].float().mean()) < 0.97:
            continue
        if any(abs(mb.feet[0] - fx) < 80 and abs(mb.feet[1] - fy) < 60 for mb in base):
            continue
        pic = torch.from_numpy(np.ascontiguousarray(p.pic)).to(ms.dev).float()
        pa = pic[..., 3:4] / 255.0
        fm = f.clone()
        fm[by:by + h, bx:bx + w] = (fm[by:by + h, bx:bx + w].float() * (1 - pa) + pic[..., :3] * pa).round().byte()
        # a cloud over it
        k = rnd.randrange(7)
        o = rnd.uniform(0.45, 0.88)
        s, al = cf.sprites[k]
        ch, cw = al.shape
        ys, xs = (al >= rnd.choice([0.2, 0.5, 0.8, 0.95]) * float(al.max())).nonzero(as_tuple=True)
        q = rnd.randrange(len(ys))
        cx0, cy0 = fx - int(xs[q]), by + h // 2 - int(ys[q])
        P, A = fc.layer([(k, cx0, cy0, o)])
        fcl = (fm.half() * (1 - A) + P).float().round().clamp(0, 255).byte()
        op = (pic[..., 3] == 255)
        am = float(A[by:by + h, bx:bx + w, 0].float()[op].mean())
        amx = float(A[by:by + h, bx:bx + w, 0].float()[op].max())
        m_none = fz.fit(fm, C, E1, known, ui)
        m_raw = fz.fit(fcl, C, E1, known, ui)
        f2, thick = fc.undo(fcl, P, A, a.amax)
        m_und = fz.fit(f2, C, E1, known & ~thick, ui)
        cv.A = A[..., 0].float()
        m_tol = fz.fit(f2, C, E1, known & ~thick, ui)
        cv.A = None
        extra = sum(1 for mb in m_und if not found([type("M", (), {"type": mb.type, "feet": mb.feet})()], p.type, fx, fy)
                    and not any(b.type == mb.type and abs(b.feet[0] - mb.feet[0]) <= 6 and abs(b.feet[1] - mb.feet[1]) <= 6 for b in base))
        res.append({"i": i, "type": p.type, "pose": p.pose, "feet": [fx, fy], "k": k, "o": o, "am": am, "amx": amx,
                    "none": found(m_none, p.type, fx, fy), "raw": found(m_raw, p.type, fx, fy),
                    "undone": found(m_und, p.type, fx, fy), "tolvote": found(m_tol, p.type, fx, fy), "extra": extra,
                    "extra_tol": sum(1 for mb in m_tol if not (mb.type == p.type and abs(mb.feet[0] - fx) <= 3 and abs(mb.feet[1] - fy) <= 3)
                                     and not any(b.type == mb.type and abs(b.feet[0] - mb.feet[0]) <= 6 and abs(b.feet[1] - mb.feet[1]) <= 6 for b in base)), "thick": float(thick[by:by + h, bx:bx + w][op].float().mean())})
        break
print(f"{a.cap}: {len(res)} placements ({tries} tries)")
bins = [(0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9)]
print("  mean cloud alpha over the mob | placements | found: no cloud | cloud left in | cloud undone | undone + tolerant vote | false mobs made (undone / tolerant)")
for lo, hi in bins:
    sel = [x for x in res if lo <= x["am"] < hi]
    if sel:
        n = len(sel)
        print(f"   {lo:.1f}-{hi:.1f}   {n:4d}    {100 * sum(x['none'] for x in sel) / n:5.1f} %   {100 * sum(x['raw'] for x in sel) / n:5.1f} %   "
              f"{100 * sum(x['undone'] for x in sel) / n:5.1f} %   {100 * sum(x['tolvote'] for x in sel) / n:5.1f} %   {sum(x['extra'] for x in sel)} / {sum(x['extra_tol'] for x in sel)}")
n = len(res)
print(f"   all       {n:4d}    {100 * sum(x['none'] for x in res) / n:5.1f} %   {100 * sum(x['raw'] for x in res) / n:5.1f} %   {100 * sum(x['undone'] for x in res) / n:5.1f} %   {100 * sum(x['tolvote'] for x in res) / n:5.1f} %   {sum(x['extra'] for x in res)} / {sum(x['extra_tol'] for x in res)}")
(msl.OUT / "synth_clouds.json").write_text(json.dumps(res))
