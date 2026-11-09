"""Feasibility: drops = appeared near our kill (differs from every earlier frame) and still (same in two frames
~0.3 s apart). usage: probe_new_still.py RUN OUT_DIR"""
import json, re, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from maplebrain.perception.tags import find_tags, tag_body

run, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
T = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
F = [k for k in T if k["frame"] and k["obs"]["me"]]
img = lambda k: cv2.imread(str(run / "frames" / k["frame"]))
at = lambda t: min(F, key=lambda k: abs(k["obs"]["t"] - t))

def shift(a, b, feet):          # camera shift a -> b, measured on the ground band
    y0, y1 = max(0, feet - 200), min(620, feet + 40)
    ga, gb = [cv2.cvtColor(x[y0:y1], cv2.COLOR_BGR2GRAY).astype(np.float32) for x in (a, b)]
    (sx, sy), r = cv2.phaseCorrelate(ga, gb)
    return sx, sy, r

def warp(a, sx, sy):
    return cv2.warpAffine(a, np.float32([[1, 0, sx], [0, 1, sy]]), (a.shape[1], a.shape[0]), borderValue=(0, 0, 0))

kills = [(float(m.group(1)), int(m.group(2))) for l in open(run / "log.txt", encoding="utf-8")
         if (m := re.match(r"\s*([\d.]+)s loot at dx ([+-]\d+) -> waiting", l))]
for kt, dx in kills:
    k0 = at(kt); px, feet = k0["obs"]["me"]; feet = int(feet)
    refs = [at(kt - s) for s in (0.0, 0.7, 1.4)]
    a1, a2 = at(kt + 1.05), at(kt + 1.4)
    f2 = img(a2); f1 = img(a1)
    pxa, _ = a2["obs"]["me"]
    sx1, sy1, _ = shift(f1, f2, feet); f1w = warp(f1, sx1, sy1)
    new = np.full(f2.shape[:2], 255, np.uint8)
    for r in refs:
        fr = img(r); sx, sy, resp = shift(fr, f2, feet)
        new = np.minimum(new, cv2.absdiff(warp(fr, sx, sy), f2).max(axis=2))
    still = cv2.absdiff(f1w, f2).max(axis=2)
    cand = ((new > 40) & (still < 25)).astype(np.uint8)
    # where the kill was, in a2's screen: kill spot moved with the camera
    sxk, syk, _ = shift(img(k0), f2, feet)
    kx = int(px + dx + sxk)
    zone = np.zeros_like(cand); zone[feet - 45:feet + 6, max(0, kx - 90):kx + 90] = 1
    zone[:, int(pxa) - 28:int(pxa) + 28] = 0                       # our own body
    for tg in find_tags(f2):
        b = tag_body(tg); zone[max(0, b[1]):b[1] + b[3], max(0, b[0]):b[0] + b[2]] = 0
    cand &= zone
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(cand)
    blobs = [tuple(int(v) for v in st[i]) for i in range(1, n) if st[i, 4] >= 40 and 6 <= st[i, 2] <= 45 and 6 <= st[i, 3] <= 45]
    print(f"{kt:6.1f}s dx {dx:+d} frames {a1['frame']},{a2['frame']} blobs {blobs}")
    x0 = max(0, kx - 140); vis = f2[feet - 80:feet + 20, x0:x0 + 280].copy()
    for b in blobs:
        cv2.rectangle(vis, (b[0] - x0, b[1] - feet + 80), (b[0] + b[2] - x0, b[1] + b[3] - feet + 80), (0, 0, 255), 1)
    cv2.line(vis, (kx - x0, 0), (kx - x0, 6), (0, 255, 255), 2)
    m = cv2.cvtColor((cand * 255)[feet - 80:feet + 20, x0:x0 + 280], cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(out / f"{run.name}_{kt:05.1f}.png"), cv2.resize(np.vstack([vis, m]), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
