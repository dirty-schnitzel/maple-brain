"""A frame, the expected scene and where they differ.  python look.py CAP IDX [IDX ...] [--tag NAME]
IDX = index into the capture's frames (0 = first). Writes out/<tag>_<idx>_{frame,exp,diff}.png + a half-size sheet."""
import argparse

import numpy as np
import torch

import msl

ap = argparse.ArgumentParser()
ap.add_argument("cap")
ap.add_argument("idx", nargs="+", type=int)
ap.add_argument("--tag", default=None)
ap.add_argument("--tol", type=int, default=4)
a = ap.parse_args()
msl.guard()
c = msl.clip(a.cap)
fr = c.frames()
rows = msl.kept(a.cap)
scene = msl.scene_of(c.map_id)
tag = a.tag or a.cap.replace("#", "_")
print(c.map_id, len(fr), "frames; kept replay:", None if rows is None else len(rows))
for i in a.idx:
    n, name, t = fr[i]
    img = c.read(name)
    if rows is not None:
        C = rows[i]["C"]
    else:
        import cam as _cam
        cc = {r[0]: r for r in _cam.cams(a.cap)["rows"]}
        C = (cc[i][3], cc[i][4]) if i in cc and cc[i][3] is not None else None
    if C is None:
        print(i, "no camera in the kept replay")
        continue
    f = torch.from_numpy(np.ascontiguousarray(img[:msl.PLAY_H])).to(scene.dev)
    exp, known = scene.expected(C)
    d = (f.float() - exp).abs().amax(dim=2)
    bad = (d > a.tol) & known
    e8 = exp.clamp(0, 255).round().byte().cpu().numpy()
    vis = img[:msl.PLAY_H].copy()
    b = bad.cpu().numpy()
    k = known.cpu().numpy()
    dm = np.zeros_like(vis)
    dm[b] = (0, 0, 255)            # red: known but off
    dm[~k] = (255, 128, 0)         # blue: unknown
    over = (0.45 * vis + 0.55 * dm).astype(np.uint8)
    over[~b & k] = (vis[~b & k] * 0.35).astype(np.uint8)
    msl.save(f"{tag}_{i}_frame.png", img[:msl.PLAY_H])
    msl.save(f"{tag}_{i}_exp.png", e8)
    msl.save(f"{tag}_{i}_diff.png", over)
    msl.save(f"{tag}_{i}_sheet.png", msl.tile([img[:msl.PLAY_H], e8, over], cols=1, scale=0.6,
                                               labels=["frame", "expected", "red = known but off, blue = unknown"]))
    print(i, name, "t", round(t, 2), "C", C, f"off {100 * b.sum() / max(1, k.sum()):.1f} % of known; unknown "
          f"{100 * (~k).mean():.1f} %")
