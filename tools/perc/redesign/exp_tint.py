"""E9c (2026-11-17): the blue mobs. python tools/perc/redesign/exp_tint.py N,TYPE,FEETX,FEETY ...
   e.g. 6636,21,1003,576 6780,21,1191,687 4116,19,1101,564   (012059_1, labelled "h")

A frozen mob (the user's ice hits) is drawn in its pose with every colour MULTIPLIED per channel:
frame = sprite * (B 255, G 168, R 10) / 255, rounded - 100 % of the opaque pixels follow one colour -> colour map
(3161 of 3161, 1977 of 1977), per-channel fit error <= 0.5. So a tint = more palette colours, exactly computable.
The tool aligns the type's poses near the given feet by how functional the map sprite colour -> frame colour is,
then fits frame = a * sprite + b per channel: use it on any mob-shaped thing the vote does not find."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, 'tools/perc')
import frames as rec  # noqa

run = Path('runs/play/20261116_012059_1')
MOBS = Path('assets/mcw/mobs')


def poses(t):
    info = json.loads((MOBS / str(t) / 'mob.json').read_text(encoding='utf-8'))
    out = []
    for anim, fs in info['frames'].items():
        for i, f in enumerate(fs):
            im = cv2.imread(str(MOBS / str(t) / f['file']), cv2.IMREAD_UNCHANGED)
            if im is None or im.ndim != 3 or im.shape[2] != 4 or (im[..., 3] > 0).sum() < 60:
                continue
            ox, oy = f['origin']
            out.append((f'{anim}_{i}', 'left', im, ox, oy))
            out.append((f'{anim}_{i}', 'right', np.ascontiguousarray(im[:, ::-1]), im.shape[1] - ox, oy))
    return out


def key(a):
    return a[..., 0].astype(np.int64) | (a[..., 1].astype(np.int64) << 8) | (a[..., 2].astype(np.int64) << 16)


for arg in sys.argv[1:]:
    n, t, fx, fy = map(int, arg.split(','))
    frame = rec.read(run, f'{n:06d}.png')
    best = None
    for name, facing, im, ox, oy in poses(t):
        h, w = im.shape[:2]
        op = im[..., 3] == 255
        sk = key(im[..., :3])[op]
        for dx in range(-8, 9):
            for dy in range(-6, 7):
                x0, y0 = fx + dx - ox, fy + dy - oy
                if x0 < 0 or y0 < 0 or x0 + w > 1366 or y0 + h > 700:
                    continue
                fk = key(frame[y0:y0 + h, x0:x0 + w])[op]
                # functional consistency: per sprite colour, the count of its most common frame colour
                order = np.lexsort((fk, sk))
                s2, f2 = sk[order], fk[order]
                pair = s2 * (1 << 24) + f2
                u, c = np.unique(pair, return_counts=True)
                us = u >> 24
                # max count per sprite colour
                score = 0
                last = -1
                m = 0
                for a, b in zip(us, c):
                    if a != last:
                        score += m
                        m = 0
                        last = a
                    m = max(m, b)
                score += m
                if best is None or score > best[0]:
                    best = (score, name, facing, dx, dy, int(op.sum()), x0, y0, im)
    score, name, facing, dx, dy, nop, x0, y0, im = best
    h, w = im.shape[:2]
    op = im[..., 3] == 255
    s = im[..., :3][op].astype(float)
    f = frame[y0:y0 + h, x0:x0 + w][op].astype(float)
    sk, fk = key(im[..., :3])[op], key(frame[y0:y0 + h, x0:x0 + w])[op]
    maps = defaultdict(Counter)
    for a, b in zip(sk, fk):
        maps[int(a)][int(b)] += 1
    print(f'n{n} type {t}: best {name} {facing} at offset ({dx}, {dy}): {score} of {nop} opaque pixels follow one colour -> colour map '
          f'({100 * score / nop:.1f} %); exact equal {100 * (sk == fk).mean():.1f} %')
    # the consistent pixels: fit per channel f = a * s + b
    cons = np.array([maps[int(a)].most_common(1)[0][0] == int(b) for a, b in zip(sk, fk)])
    for ch, nm in enumerate('bgr'):
        A = np.stack([s[cons, ch], np.ones(cons.sum())], 1)
        coef, res, *_ = np.linalg.lstsq(A, f[cons, ch], rcond=None)
        err = np.abs(A @ coef - f[cons, ch])
        print(f'    {nm}: frame = {coef[0]:.4f} * sprite + {coef[1]:.2f}   |err| mean {err.mean():.2f} max {err.max():.1f}')
    # cross-channel? print a few colour pairs
    top = sorted(maps.items(), key=lambda kv: -sum(kv[1].values()))[:8]
    for a, cnt in top:
        b, c = cnt.most_common(1)[0]
        print(f'    sprite (b,g,r) {(a & 255, (a >> 8) & 255, a >> 16)} -> frame {(b & 255, (b >> 8) & 255, b >> 16)}  x{c} of {sum(cnt.values())}')
