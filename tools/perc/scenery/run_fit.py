"""Prototype: the mob fit (maplebrain.perception.fit.Fitter, unchanged) on a map with moving scenery, three ways:
  A  today's expected picture (movers unknown, the export's sky colour)
  B  the prototype's (movers drawn at their places, colours fixed)
  C  B + the weather clouds undone: frame' = (frame - cloud colour x alpha) / (1 - alpha) where alpha <= AMAX, the
     thicker pixels not valid ("covered by cloud")
    python run_fit.py CAP --clouds out/clouds_<tag>.json [--every K] [--sheets N]
-> counts, per-frame rows (out/fit_<tag>.json), sheets of the mobs only C finds / only B finds."""
import argparse
import json

import cv2
import numpy as np
import torch

import cam as camlib
import clouds as cl
import msl
import proto
from maplebrain.perception import hud
from maplebrain.perception.fit import Fitter

AMAX = 0.85
ASSETS = msl.ROOT / "assets" / "mcw"
ap = argparse.ArgumentParser()
ap.add_argument("cap")
ap.add_argument("--clouds", default=None)
ap.add_argument("--every", type=int, default=1)
ap.add_argument("--sheets", type=int, default=24)
ap.add_argument("--tag", default=None)
a = ap.parse_args()
msl.guard()
c = msl.clip(a.cap)
fr = c.frames()
cams = {r[0]: r for r in camlib.cams(a.cap)["rows"]}
ms = proto.MScene(c.map_id)
old = msl.scene_of(c.map_id)
fz = Fitter(ms.scene, c.map_id, ASSETS)
cf = cl.CloudFinder(ms.dev)
cloud_rows = {r["i"]: r for r in json.loads((msl.OUT / a.clouds).read_text())} if a.clouds else {}
tag = a.tag or a.cap.replace("#", "_")
names = {p.type: json.loads((ASSETS / "mobs" / str(p.type) / "mob.json").read_text(encoding="utf-8")).get("name") for p in fz.poses}
ui = None
rows = []
msA, msB = [], []


def boxes(mobs):
    out = []
    for m in mobs:
        p = fz.poses[fz.pose_ix[(m.type, m.pose, m.facing)]]
        h, w = p.pic.shape[:2]
        out.append((m.feet[0] - p.ox, m.feet[1] - p.oy, w, h))
    return out


def match(A, B, r=12):
    """Mobs of A with no mob of the same type within r px in B."""
    return [m for m in A if not any(n.type == m.type and abs(n.feet[0] - m.feet[0]) <= r and abs(n.feet[1] - m.feet[1]) <= r for n in B)]


sheets = []
for i in range(0, len(fr), a.every):
    r = cams.get(i)
    if r is None or r[3] is None:
        continue
    n, name, t = fr[i]
    img = c.read(name)
    if ui is None:
        m = hud.ui_mask(img.shape, None)[:hud.CHAT_WORLD[3]] > 0
        x0, y0, x1, y1 = hud.CHAT_WORLD
        m = m.copy()
        m[y0:y1, x0:x1] = True
        ui = torch.from_numpy(np.ascontiguousarray(m[:700])).to(ms.dev)
    f = proto.frame_tensor(img, ms.dev)
    C = (r[3], r[4])
    ms.locate(f, C, t)
    E0, k0 = old.expected(C)
    E1, k1 = ms.expected(C)
    torch.cuda.synchronize()
    A = fz.fit(f, C, E0, k0, ui)
    msA.append(dict(fz.ms))
    B = fz.fit(f, C, E1, k1, ui)
    msB.append(dict(fz.ms))
    P = torch.zeros((700, 1366, 3), device=ms.dev)
    cov = torch.zeros((700, 1366), device=ms.dev)
    for k, mx, my, sh, nn, o, vis in (cloud_rows.get(i) or {}).get("clouds", []):
        cf.draw(P, cov, k, mx - C[0], my - C[1], o)
    und = ((f.float() - P) / (1 - cov).clamp(min=0.05)[..., None]).round().clamp(0, 255).byte()
    f2 = torch.where((cov > 0.004)[..., None], und, f)
    Cm = fz.fit(f2, C, E1, k1 & (cov <= AMAX), ui)
    covn = cov.cpu().numpy()

    def under(mobs):
        out = []
        for (x, y, w, h) in boxes(mobs):
            sub = covn[max(0, y):max(0, y + h), max(0, x):max(0, x + w)]
            out.append(float(sub.mean()) if sub.size else 0.0)
        return out
    row = {"i": i, "t": t, "A": [m.to_dict() for m in A], "B": [m.to_dict() for m in B], "C": [m.to_dict() for m in Cm],
           "uA": under(A), "uB": under(B), "uC": under(Cm), "cloud_px": float((cov > 0.02).float().mean()),
           "onlyC": [m.to_dict() for m in match(Cm, B)], "onlyB": [m.to_dict() for m in match(B, Cm)],
           "onlyB_vsA": [m.to_dict() for m in match(B, A)], "onlyA": [m.to_dict() for m in match(A, B)]}
    rows.append(row)
    for kind, lst, src in (("only with the clouds undone", match(Cm, B), f2), ("lost when the clouds are undone", match(B, Cm), f2),
                           ("only today's picture", match(A, B), f)):
        for m in lst:
            if len(sheets) >= a.sheets * 3:
                break
            x, y = m.feet
            x0, y0 = max(0, min(1366 - 240, x - 120)), max(0, min(700 - 180, y - 130))
            raw = img[y0:y0 + 180, x0:x0 + 240].copy()
            un = f2.cpu().numpy()[y0:y0 + 180, x0:x0 + 240].copy()
            ex = E1.clamp(0, 255).byte().cpu().numpy()[y0:y0 + 180, x0:x0 + 240].copy()
            bx = boxes([m])[0]
            for im_ in (raw, un):
                cv2.rectangle(im_, (bx[0] - x0, bx[1] - y0), (bx[0] - x0 + bx[2], bx[1] - y0 + bx[3]), (0, 255, 0), 1)
            lab = f"{kind}: {names.get(m.type)} {m.pose} o{m.opacity} seen {m.n_seen} fr {i}"
            sheets.append((kind, np.hstack([raw, un, ex]), lab))
    if len(rows) % 50 == 0:
        print(" ", len(rows), "frames", flush=True)

nA, nB, nC = (sum(len(r[k]) for r in rows) for k in "ABC")
print(f"{a.cap}: {len(rows)} frames. Mobs the fit finds: A today's picture {nA}, B movers explained {nB}, C + clouds undone {nC}")
for nm, lst in (("A", msA), ("B", msB)):
    print(f"  fit ms {nm}: p50 {np.median([x['fit'] for x in lst[5:]]):.2f} p90 {np.percentile([x['fit'] for x in lst[5:]], 90):.2f}  (vote {np.median([x['vote'] for x in lst[5:]]):.2f}, fade {np.median([x['fade'] for x in lst[5:]]):.2f}, stage 2 {np.median([x['s2'] for x in lst[5:]]):.2f}; candidates p50 {np.median([x['cands'] for x in lst[5:]]):.0f}, features p50 {np.median([x['feat'] for x in lst[5:]]):.0f})")
print(f"  B finds, A does not: {sum(len(r['onlyB_vsA']) for r in rows)};  A finds, B does not: {sum(len(r['onlyA']) for r in rows)}")
print(f"  C finds, B does not: {sum(len(r['onlyC']) for r in rows)};  B finds, C does not: {sum(len(r['onlyB']) for r in rows)}")
uB = [u for r in rows for u in r["uB"]]
uC = [u for r in rows for u in r["uC"]]
for lo, hi in ((0.02, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 1.01)):
    print(f"  mobs whose box is under a cloud of mean alpha {lo}-{hi}: B {sum(lo <= u < hi for u in uB)}, C {sum(lo <= u < hi for u in uC)}")
print(f"  mobs under no cloud (< 0.02): B {sum(u < 0.02 for u in uB)}, C {sum(u < 0.02 for u in uC)}")
(msl.OUT / f"fit_{tag}.json").write_text(json.dumps(rows))
for kind in sorted({s[0] for s in sheets}):
    pics = [s for s in sheets if s[0] == kind][:a.sheets]
    tiles = []
    for _, im_, lab in pics:
        im_ = cv2.resize(im_, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_NEAREST)
        cv2.putText(im_, lab[len(kind) + 2:], (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3)
        cv2.putText(im_, lab[len(kind) + 2:], (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        tiles.append(im_)
    for s0 in range(0, len(tiles), 8):
        p = msl.save(f"fit_{tag}_{kind.split()[0]}_{kind.split()[1]}_{s0 // 8}.png", np.vstack(tiles[s0:s0 + 8]))
        print("  sheet (frame | clouds undone | expected):", kind, "->", p.name)
