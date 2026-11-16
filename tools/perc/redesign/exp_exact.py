"""E9a (2026-11-17): how exactly do frame pixels equal the client sprite's colours (opaque pixels) on real native
frames, and how small are the sprites' palettes? Uses the fit's accepted mobs on the labelled frames of 012059_1
(RUN/fit/labels_loose.jsonl: tools/perc/fit/run.py labels RUN --loose; pose, facing, feet known to the pixel).

    python tools/perc/redesign/exp_exact.py        (from the repo root)

Result: difference 0 on 98.57 % of 827 k opaque pixels of 369 clear mobs (the rest covered); Horny Mushroom 77
colours over all poses, Zombie Mushroom 134, Stirge 14, Bubbling 60 opaque (+ alpha classes 187 / 204 / 221 / 238)."""
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path('.').resolve()
sys.path.insert(0, 'tools/perc')
import frames as rec  # noqa

run = Path('runs/play/20261116_012059_1')
rows = [json.loads(l) for l in open(run / 'fit' / 'labels_loose.jsonl')]
MOBS = ROOT / 'assets' / 'mcw' / 'mobs'
cache = {}


def sprite(t, pose, facing):
    key = (t, pose, facing)
    if key not in cache:
        info = json.loads((MOBS / str(t) / 'mob.json').read_text(encoding='utf-8'))
        anim, i = pose.rsplit('_', 1)
        f = info['frames'][anim][int(i)]
        im = cv2.imread(str(MOBS / str(t) / f['file']), cv2.IMREAD_UNCHANGED)
        ox, oy = f['origin']
        if facing == 'right':
            im = np.ascontiguousarray(im[:, ::-1])
            ox = im.shape[1] - ox
        cache[key] = (im, ox, oy)
    return cache[key]


hist = Counter()          # max abs diff over channels at opaque pixels (all, incl. covered)
sign = Counter()          # signed per-channel diffs where max abs diff <= 8
n_mobs = 0
per_mob_exact = []
alpha_hist = Counter()
for r in rows[:150]:
    ms = [m for m in r['mobs'] if m['fit']['seen'] >= 0.9 and m['fit']['opacity'] >= 0.999]
    if not ms:
        continue
    frame = rec.read(run, f"{r['n']:06d}.png")
    for m in ms:
        im, ox, oy = sprite(m['mob'], m['fit']['pose'], m['fit']['facing'])
        x0, y0 = m['sx'] - ox, m['sy'] - oy
        h, w = im.shape[:2]
        if x0 < 0 or y0 < 0 or x0 + w > 1366 or y0 + h > 700:
            continue
        crop = frame[y0:y0 + h, x0:x0 + w].astype(np.int16)
        op = im[..., 3] == 255
        d = crop[op] - im[..., :3][op].astype(np.int16)
        mx = np.abs(d).max(axis=1)
        for v, c in zip(*np.unique(np.minimum(mx, 20), return_counts=True)):
            hist[int(v)] += int(c)
        near = mx <= 8
        for v, c in zip(*np.unique(d[near].ravel(), return_counts=True)):
            sign[int(v)] += int(c)
        per_mob_exact.append(float((mx == 0).mean()))
        n_mobs += 1
tot = sum(hist.values())
print(f"{n_mobs} opaque clear mobs, {tot} opaque sprite pixels")
cum = 0
for v in sorted(hist):
    cum += hist[v]
    print(f"  max|diff| {'>=20' if v == 20 else v:>4}: {100 * hist[v] / tot:6.2f} %   cum {100 * cum / tot:6.2f} %")
print("signed per-channel diffs (pixels within 8):", {k: sign[k] for k in sorted(sign)})
pm = np.array(per_mob_exact)
print(f"per mob share of opaque pixels EXACTLY equal: p5 {np.percentile(pm, 5):.3f} p50 {np.median(pm):.3f} p95 {np.percentile(pm, 95):.3f}")

# sprite alpha values + palettes, for the clean maps' types
for t in (19, 21, 17, 14):
    info = json.loads((MOBS / str(t) / 'mob.json').read_text(encoding='utf-8'))
    al, cols_all, per_pose = Counter(), Counter(), []
    for anim, fs in info['frames'].items():
        for f in fs:
            im = cv2.imread(str(MOBS / str(t) / f['file']), cv2.IMREAD_UNCHANGED)
            if im is None or im.ndim != 3 or im.shape[2] != 4 or (im[..., 3] > 0).sum() < 60:
                continue
            a = im[..., 3]
            for v, c in zip(*np.unique(a[a > 0], return_counts=True)):
                al[int(v)] += int(c)
            op = a == 255
            col = im[..., :3][op].astype(np.int64)
            keys = col[:, 0] | (col[:, 1] << 8) | (col[:, 2] << 16)
            u, c = np.unique(keys, return_counts=True)
            per_pose.append((f"{anim}_{f.get('n', '?')}", int(op.sum()), len(u), int((c <= 3).sum()), int(c[c <= 3].sum())))
            for k, n in zip(u, c):
                cols_all[int(k)] += int(n)
    tot_a = sum(al.values())
    print(f"type {t} {info.get('name')}: alpha values {dict(sorted(al.items(), key=lambda kv: -kv[1])[:8])} (opaque share {100 * al.get(255, 0) / tot_a:.1f} %)")
    print(f"   distinct opaque colours over all poses {len(cols_all)}; per pose (name, opaque px, distinct colours, colours used <=3 times, px of those):")
    for p in per_pose[:6]:
        print("    ", p)
    low_bits = Counter()
    for k in cols_all:
        low_bits[(k & 7, (k >> 8) & 7, (k >> 16) & 7)] += 1
    print(f"   low 3 bits (b,g,r) of the colours: {low_bits.most_common(6)}")
