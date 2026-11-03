"""Feasibility v2: new near our kill + keeps its x (bobbing allowed) + coins by sprite.
usage: probe_persist.py RUN OUT_DIR MESO_DIR"""
import glob, json, re, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from maplebot.perception.tags import find_tags, tag_body

run, out, meso_dir = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]; out.mkdir(parents=True, exist_ok=True)
T = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
F = [k for k in T if k["frame"] and k["obs"]["me"]]
img = lambda k: cv2.imread(str(run / "frames" / k["frame"]))
at = lambda t: min(F, key=lambda k: abs(k["obs"]["t"] - t))
COINS = []
for p in sorted(glob.glob(meso_dir + "/0900000[0-3]_*.png")):
    im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if im.shape[1] >= 12:
        COINS.append((np.ascontiguousarray(im[..., :3]), (im[..., 3] > 200).astype(np.uint8)))

def shift(a, b, feet):
    y0, y1 = max(0, feet - 200), min(620, feet + 40)
    ga, gb = [cv2.cvtColor(x[y0:y1], cv2.COLOR_BGR2GRAY).astype(np.float32) for x in (a, b)]
    (sx, sy), _ = cv2.phaseCorrelate(ga, gb)
    return sx, sy

def warp(a, sx, sy):
    return cv2.warpAffine(a, np.float32([[1, 0, sx], [0, 1, sy]]), (a.shape[1], a.shape[0]))

def best(win, t, m=None):
    if win.shape[0] < t.shape[0] or win.shape[1] < t.shape[1]:
        return -1, (0, 0)
    r = cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED, mask=m); r[~np.isfinite(r)] = -1
    _, s, _, l = cv2.minMaxLoc(r); return s, l

kills = [(float(m.group(1)), int(m.group(2))) for l in open(run / "log.txt", encoding="utf-8")
         if (m := re.match(r"\s*([\d.]+)s loot at dx ([+-]\d+) -> waiting", l))]
for kt, dx in kills:
    k0 = at(kt); px, feet = k0["obs"]["me"]; feet = int(feet)
    a = at(kt + 1.1); fa = img(a)
    later = [at(kt + 1.45), at(kt + 1.8)]
    new = np.full(fa.shape[:2], 255, np.uint8)
    for r in [at(kt - s) for s in (0.0, 0.7, 1.4)]:
        fr = img(r); sx, sy = shift(fr, fa, feet)
        new = np.minimum(new, cv2.absdiff(warp(fr, sx, sy), fa).max(axis=2))
    sxk, _ = shift(img(k0), fa, feet); kx = int(px + dx + sxk)
    zy0, zy1, zx0, zx1 = feet - 45, feet + 4, max(0, kx - 90), min(1366, kx + 90)
    m = np.zeros(fa.shape[:2], np.uint8); m[zy0:zy1, zx0:zx1] = (new[zy0:zy1, zx0:zx1] > 40)
    for tg in find_tags(fa):
        b = tag_body(tg, above=130, pad=0)
        if abs((b[0] + b[2] / 2) - a["obs"]["me"][0]) > 20:          # other players (not us)
            m[max(0, b[1]):b[1] + b[3], max(0, b[0]):b[0] + b[2]] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    items = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in st[i])
        if area < 50 or not (8 <= w <= 40 and 8 <= h <= 40):
            continue
        tpl = fa[y - 2:y + h + 2, x - 2:x + w + 2]
        ok = []
        for L in later:
            fl = img(L); sx, sy = shift(fa, fl, feet)
            X, Y = int(x - 2 + sx), int(y - 2 + sy)
            win = fl[Y - 7:Y + h + 4 + 7, X - 4:X + w + 4 + 4]
            s, l = best(win, tpl); ok.append(round(s, 2))
        if min(ok) >= 0.7:
            items.append((x, y, w, h, ok))
    coins = []
    for L in [a] + later:
        fl = img(L); sx, _ = shift(fa, fl, feet)
        win = fl[zy0 - 5:zy1 + 5, int(zx0 + sx):int(zx1 + sx)]
        for t, mk in COINS:
            r = cv2.matchTemplate(win, t, cv2.TM_CCOEFF_NORMED, mask=mk); r[~np.isfinite(r)] = -1
            for yy, xx in zip(*np.where(r >= 0.8)):
                X = int(zx0 + xx)                                     # in fa coordinates
                if not any(abs(X - c) < 15 for c in coins):
                    coins.append(X)
    print(f"{kt:6.1f}s dx {dx:+4d} items {[(i[0], i[1], i[2], i[3], i[4]) for i in items]} coins {coins}")
    x0 = max(0, min(1366 - 300, kx - 150)); vis = fa[feet - 80:feet + 20, x0:x0 + 300].copy()
    for i in items:
        cv2.rectangle(vis, (i[0] - x0, i[1] - feet + 80), (i[0] + i[2] - x0, i[1] + i[3] - feet + 80), (0, 0, 255), 1)
    for c in coins:
        cv2.rectangle(vis, (c - x0, 70), (c - x0 + 23, 96), (0, 255, 255), 1)
    cv2.line(vis, (kx - x0, 0), (kx - x0, 6), (0, 255, 255), 2)
    cv2.putText(vis, f"{run.name} {kt:.1f}", (2, 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    cv2.imwrite(str(out / f"{run.name}_{kt:05.1f}.png"), vis)
