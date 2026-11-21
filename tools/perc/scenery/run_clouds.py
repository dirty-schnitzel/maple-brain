"""Prototype run: movers + weather clouds over a capture.
    python run_clouds.py CAP [--every K] [--show I,I] [--tag NAME] [--max N]
Per frame: the clouds found (picture, map place of its top-left), the share of the play area the frame equals the
expected picture before / after the clouds are drawn in. -> out/clouds_<tag>.json"""
import argparse
import json
import time

import numpy as np
import torch

import cam as camlib
import clouds as cl
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
cf = cl.CloudFinder(ms.dev)
from maplebrain.perception import hud
show = {int(x) for x in a.show.split(",") if x}
tag = a.tag or a.cap.replace("#", "_")
rows, ui = [], None
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
    valid = known & ui
    ta = time.perf_counter()
    found, E2, cov = cf.find(f.float(), exp.clone(), valid)
    torch.cuda.synchronize()
    tb = time.perf_counter()
    d1 = (f.float() - exp).abs().amax(dim=2)
    d2 = (f.float() - E2).abs().amax(dim=2)
    world = int(valid.sum())
    row = {"i": i, "t": t, "C": C, "shows1": float(((d1 <= 4) & valid).sum()) / world,
           "shows2": float(((d2 <= 4) & valid).sum()) / world, "cloud_px": float((cov > 0.02).sum()) / (msl.SW * msl.PLAY_H),
           "thick_px": float((cov > 0.8).sum()) / (msl.SW * msl.PLAY_H),
           "clouds": [[k, x + C[0], y + C[1], sh, nn, o, vis] for k, x, y, sh, nn, o, vis in found], "ms": 1000 * (tb - ta)}
    rows.append(row)
    if i in show:
        vis = img[:msl.PLAY_H].copy()
        b = ((d2 > 4) & valid).cpu().numpy()
        kn = valid.cpu().numpy()
        cv_ = cov.cpu().numpy()
        dm = np.zeros_like(vis)
        dm[b] = (0, 0, 255)
        dm[~kn] = (255, 128, 0)
        over = (0.45 * vis + 0.55 * dm).astype(np.uint8)
        over[~b & kn] = (vis[~b & kn] * 0.35).astype(np.uint8)
        g = (cv_ > 0.02) & ~b & kn                                    # explained through a cloud: green tint
        over[g] = (0.6 * over[g] + 0.4 * np.array([0, 160, 0]) * cv_[g][:, None]).astype(np.uint8)
        e8 = E2.clamp(0, 255).round().byte().cpu().numpy()
        import cv2
        for k, x, y, sh, nn, o, vv in found:
            cv2.putText(over, f"c{k} {sh:.2f} o{o:.2f}", (max(0, x) + 4, max(12, y + 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        msl.save(f"{tag}_c{i}_sheet.png", msl.tile([img[:msl.PLAY_H], e8, over], cols=1, scale=0.6,
                                                    labels=["frame", "expected with movers + clouds", "red = off, green = explained through a cloud, blue = unknown"]))
        msl.save(f"{tag}_c{i}_over.png", over)
    if len(rows) % 50 == 0:
        print(" ", len(rows), "frames; last:", found, flush=True)
g = lambda k: np.array([r[k] for r in rows])
print(f"{a.cap}: {len(rows)} frames in {time.perf_counter() - t0:.0f} s")
print(f"  frame = expected on {100 * g('shows1').mean():.1f} % of the known play area with the movers, {100 * g('shows2').mean():.1f} % with the clouds too (p10 {100 * np.percentile(g('shows2'), 10):.1f})")
print(f"  clouds per frame p50 {np.median([len(r['clouds']) for r in rows]):.0f} max {max(len(r['clouds']) for r in rows)}; under a cloud {100 * g('cloud_px').mean():.1f} % of the play area (p90 {100 * np.percentile(g('cloud_px'), 90):.1f}), thicker than 0.8: {100 * g('thick_px').mean():.2f} %; find ms p50 {np.median(g('ms')):.0f}")
(msl.OUT / f"clouds_{tag}.json").write_text(json.dumps(rows))
