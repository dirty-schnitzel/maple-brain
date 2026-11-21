"""Prototype run: the expected picture with the moving layers over a capture.
    python run_proto.py CAP [--every K] [--show I,I,...] [--tag NAME] [--nofix]
Per frame: locate the movers, expected -> known share of the play area, the share of known pixels the frame equals
(within tol), each mover found / share. Before = Scene.expected as it is today (the export's colours)."""
import argparse
import json
import time

import numpy as np
import torch

import cam as camlib
import msl
import proto

ap = argparse.ArgumentParser()
ap.add_argument("cap")
ap.add_argument("--every", type=int, default=1)
ap.add_argument("--show", default="")
ap.add_argument("--tag", default=None)
ap.add_argument("--max", type=int, default=10 ** 9)
a = ap.parse_args()
msl.guard()
c = msl.clip(a.cap)
fr = c.frames()
cams = {r[0]: r for r in camlib.cams(a.cap)["rows"]}
ms = proto.MScene(c.map_id)
old = msl.scene_of(c.map_id)
from maplebrain.perception import hud
show = {int(x) for x in a.show.split(",") if x}
tag = a.tag or a.cap.replace("#", "_")
rows = []
ui = None
t0 = time.perf_counter()
for i in range(0, len(fr), a.every):
    if len(rows) >= a.max:
        break
    r = cams.get(i)
    if r is None or r[3] is None:
        continue
    n, name, t = fr[i]
    img = c.read(name)
    if ui is None:
        ui = torch.from_numpy(np.ascontiguousarray(hud.ui_mask(img.shape, None)[:msl.PLAY_H] > 0)).to(ms.dev)
    f = proto.frame_tensor(img, ms.dev)
    C = (r[3], r[4])
    ms.locate(f, C, t)
    exp, known = ms.expected(C)
    d = (f.float() - exp).abs().amax(dim=2)
    ok = (d <= ms.tol) & known & ui
    e0, k0 = old.expected(C)
    ok0 = ((f.float() - e0).abs().amax(dim=2) <= 4) & k0 & ui
    world = int(ui.sum())
    row = {"i": i, "t": t, "C": C, "known": float((known & ui).sum()) / world, "expl": float(ok.sum()) / max(1, int((known & ui).sum())),
           "shows": float(ok.sum()) / world, "known0": float((k0 & ui).sum()) / world,
           "expl0": float(ok0.sum()) / max(1, int((k0 & ui).sum())), "shows0": float(ok0.sum()) / world,
           "movers": {k: [m.found, round(m.share, 3), m.X] for k, m in ms.movers.items()}}
    rows.append(row)
    if i in show:
        e8 = exp.clamp(0, 255).round().byte().cpu().numpy()
        vis = img[:msl.PLAY_H].copy()
        b = ((d > ms.tol) & known).cpu().numpy()
        k = known.cpu().numpy()
        dm = np.zeros_like(vis)
        dm[b] = (0, 0, 255)
        dm[~k] = (255, 128, 0)
        over = (0.45 * vis + 0.55 * dm).astype(np.uint8)
        over[~b & k] = (vis[~b & k] * 0.35).astype(np.uint8)
        msl.save(f"{tag}_p{i}_sheet.png", msl.tile([img[:msl.PLAY_H], e8, over], cols=1, scale=0.6,
                                                    labels=["frame", "expected with the moving layers", "red = known but off, blue = unknown"]))
        msl.save(f"{tag}_p{i}_frame.png", img[:msl.PLAY_H])
        msl.save(f"{tag}_p{i}_exp.png", e8)
        np.save(str(msl.OUT / f"{tag}_p{i}_known.npy"), k)
    if len(rows) % 100 == 0:
        print(" ", len(rows), "frames", {k: (m.found, round(m.share, 2)) for k, m in ms.movers.items()}, flush=True)
dt = time.perf_counter() - t0
g = lambda k: np.array([r[k] for r in rows])
print(f"{a.cap}: map {c.map_id}, {len(rows)} frames in {dt:.0f} s")
print(f"  today:      known {100 * g('known0').mean():5.1f} % of the play area, of which the frame equals the scene {100 * g('expl0').mean():5.1f} %  -> shows {100 * g('shows0').mean():5.1f} %")
print(f"  prototype:  known {100 * g('known').mean():5.1f} %,                    of which {100 * g('expl').mean():5.1f} % (p10 {100 * np.percentile(g('expl'), 10):.1f})  -> shows {100 * g('shows').mean():5.1f} %")
for k, m in ms.movers.items():
    f_ = np.array([r["movers"][k][0] for r in rows])
    s_ = np.array([r["movers"][k][1] for r in rows])
    print(f"  mover {k} {m.b['file']} rx {m.b['rx']}: found on {100 * f_.mean():.1f} % of frames, share when found p50 {np.median(s_[f_]) if f_.any() else 0:.2f}")
print("  looks:", ms.stats)
(msl.OUT / f"proto_{tag}.json").write_text(json.dumps(rows))
