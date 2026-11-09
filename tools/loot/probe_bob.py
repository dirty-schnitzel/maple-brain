"""Feasibility v3: items bob in place. Pairs of frames ~0.4 s apart (camera aligned): small changed blobs in the
ground band whose old crop re-appears at the same x, shifted only vertically. usage: probe_bob.py RUN OUT T0 T1"""
import json, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from maplebrain.perception.tags import find_tags, tag_body

run, out = Path(sys.argv[1]), Path(sys.argv[2]); t0, t1 = float(sys.argv[3]), float(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
F = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
F = [k for k in F if k["frame"] and k["obs"]["me"] and t0 <= k["obs"]["t"] <= t1]
img = lambda k: cv2.imread(str(run / "frames" / k["frame"]))

def detect(fa, fb, feet, mex):
    y0, y1 = feet - 60, feet + 6
    ga, gb = [cv2.cvtColor(x[y0 - 150:y1], cv2.COLOR_BGR2GRAY).astype(np.float32) for x in (fa, fb)]
    (sx, sy), resp = cv2.phaseCorrelate(ga, gb)
    if resp < 0.3: return []
    A = cv2.warpAffine(fa, np.float32([[1, 0, round(sx)], [0, 1, 0]]), (fa.shape[1], fa.shape[0]))
    d = cv2.absdiff(A[y0:y1], fb[y0:y1]).max(axis=2)
    m = (d > 28).astype(np.uint8)
    m[:, :max(0, int(round(sx))) + 1] = 0; m[:, 1366 + min(0, int(round(sx))) - 1:] = 0
    for tg in find_tags(fb):
        b = tag_body(tg, above=130, pad=4)
        m[max(0, b[1] - y0):max(0, b[1] + b[3] - y0), max(0, b[0]):b[0] + b[2]] = 0   # characters (incl. us)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    hits = []
    for i in range(1, n):
        x, y, w, h, _ = (int(v) for v in st[i]); y += y0
        if not (10 <= w <= 44 and 8 <= h <= 46): continue
        tpl = A[y:y + h, x:x + w]
        if tpl.std() < 18: continue
        win = fb[y - 8:y + h + 8, max(0, x - 3):x + w + 3]
        r = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
        _, s, _, l = cv2.minMaxLoc(r)
        dx, dy = l[0] - (x - max(0, x - 3)), l[1] - 8
        s0 = float(r[8, x - max(0, x - 3)]) if r.shape[0] > 8 else -1
        if s >= 0.8 and abs(dx) <= 1 and 1 <= abs(dy) <= 7 and s - s0 > 0.05:
            hits.append((x, y, w, h, round(s, 2), dy))
    return hits

rows = []
for i in range(3, len(F)):
    a, b = F[i - 3], F[i]                      # ~0.4 s apart (frames are every 3rd tick)
    if not 0.25 <= b["obs"]["t"] - a["obs"]["t"] <= 0.7: continue
    fb = img(b); hits = detect(img(a), fb, int(b["obs"]["me"][1]), b["obs"]["me"][0])
    if hits:
        print(f"{b['obs']['t']:7.2f} {b['frame']} {hits}")
        feet = int(b["obs"]["me"][1]); v = fb[feet - 90:feet + 20].copy()
        for x, y, w, h, s, dy in hits:
            cv2.rectangle(v, (x, y - feet + 90), (x + w, y + h - feet + 90), (0, 0, 255), 1)
        cv2.putText(v, f"{b['obs']['t']:.1f}", (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        rows.append(v)
print("frames", len(F), "with hits", len(rows))
for j in range(0, min(len(rows), 40), 10):
    cv2.imwrite(str(out / f"bob_{run.name}_{j:03d}.png"), np.vstack(rows[j:j + 10]))
