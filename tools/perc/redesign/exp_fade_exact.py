"""E9b (2026-11-17): fading mobs. python tools/perc/redesign/exp_fade_exact.py real | synth [tol]

(A) real: how exactly does a fading mob's pixel equal B + o (s - B)? 161 real fading mobs (the fit's, o 0.2-0.95):
    residual 0 on 90.1 % of the pixels, <= 1 on 95.7 % (the rest covered) - one o per mob, exact blending.
(B) a DEAD END kept for the record: "this residue pixel is SOME palette colour at SOME opacity" (per pixel, free o)
    holds for 35-43 % of non-mob residue pixels (players, effects, UI) - not selective, and 6.5 ms. What is
    selective: one alpha for a whole screen cell + sprite colour PAIRS (exp_vote.py fade_alphas).
Needs RUN/fit/labels_loose.jsonl (tools/perc/fit/run.py labels RUN --loose) for (A)."""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, 'tools/perc/redesign')
sys.path.insert(0, '.')
sys.path.insert(0, 'tools/perc')
import exp_vote as E  # noqa
import frames as rec  # noqa
from maplebrain.scene import Scene  # noqa

PH, SW = 700, 1366
MOBS = Path('assets/mcw/mobs')
TOL = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0


def palette(v):
    lut = v.lut.cpu().numpy()
    keys = np.nonzero(lut)[0]
    keys = keys[np.argsort(lut[keys])]
    return torch.tensor(np.stack([keys & 255, (keys >> 8) & 255, (keys >> 16) & 255], 1), dtype=torch.float32, device='cuda')


def feasible(f, exp, known, ids, pal, tol=TOL, omin=0.12, omax=0.97, cmin=24):
    """-> (yx of residue pixels, feas (R,) bool, o (R,) of the best pair, n residue)"""
    r = f.float() - exp
    res = ((r.abs().amax(2) > 4) & known & (ids == 0)).nonzero()
    out_f, out_o = [], []
    for i in range(0, len(res), 20000):
        yx = res[i:i + 20000]
        rI, Bp = r[yx[:, 0], yx[:, 1]], exp[yx[:, 0], yx[:, 1]]
        q = pal[None] - Bp[:, None]
        qq = (q * q).sum(-1).clamp(min=1.0)
        o = (rI[:, None] * q).sum(-1) / qq
        resid = (rI[:, None] - o[..., None] * q).abs().amax(-1)
        ok = (o >= omin) & (o <= omax) & (resid <= tol) & (q.abs().amax(-1) >= cmin)
        resid = torch.where(ok, resid, torch.full_like(resid, 1e9))
        k = resid.argmin(1)
        out_f.append(ok.any(1))
        out_o.append(o.gather(1, k[:, None])[:, 0])
    if not out_f:
        z = torch.zeros(0, device='cuda')
        return res, z.bool(), z, 0
    return res, torch.cat(out_f), torch.cat(out_o), len(res)


def masks(res, feas):
    fm = torch.zeros((PH, SW), dtype=torch.bool, device='cuda')
    fm[res[:, 0], res[:, 1]] = feas
    rm = np.zeros((PH, SW), bool)
    rr = res.cpu().numpy()
    rm[rr[:, 0], rr[:, 1]] = True
    return fm.cpu().numpy(), rm


mode = sys.argv[1]
if mode == 'real':
    run = Path('runs/play/20261116_012059_1')
    v = E.Voter(rec.map_of(run))
    scene = Scene.load(rec.map_of(run))
    pal = palette(v)
    cams = json.load(open(run / 'labels/cams.json'))
    rows = [json.loads(line) for line in open(run / 'fit/labels_loose.jsonl')]
    hist = Counter()
    n_f = 0
    shares, res_n, feas_other, ms = [], [], [], []
    cache = {}

    def sprite(t, pose, facing):
        key = (t, pose, facing)
        if key not in cache:
            info = json.loads((MOBS / str(t) / 'mob.json').read_text(encoding='utf-8'))
            anim, i = pose.rsplit('_', 1)
            fr = info['frames'][anim][int(i)]
            im = cv2.imread(str(MOBS / str(t) / fr['file']), cv2.IMREAD_UNCHANGED)
            ox, oy = fr['origin']
            if facing == 'right':
                im = np.ascontiguousarray(im[:, ::-1])
                ox = im.shape[1] - ox
            cache[key] = (im, ox, oy)
        return cache[key]

    for r in rows:
        name = f"{r['n']:06d}.png"
        C = cams.get(name)
        if C is None:
            continue
        frame = rec.read(run, name)
        f = torch.from_numpy(frame[:PH].copy()).cuda()
        exp, known = scene.expected(tuple(C))
        ids = v.ids(f)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        res, feas, o, R = feasible(f, exp, known, ids, pal)
        torch.cuda.synchronize()
        ms.append((time.perf_counter() - t0) * 1000)
        fm, rm = masks(res, feas)
        expn = exp.cpu().numpy()
        mobmask = np.zeros((PH, SW), bool)
        for m in r['mobs']:
            im, ox, oy = sprite(m['mob'], m['fit']['pose'], m['fit']['facing'])
            x0, y0 = m['sx'] - ox, m['sy'] - oy
            h, w = im.shape[:2]
            if x0 < 0 or y0 < 0 or x0 + w > SW or y0 + h > PH:
                continue
            mobmask[max(0, y0 - 4):y0 + h + 4, max(0, x0 - 4):x0 + w + 4] = True
            oo = m['fit']['opacity']
            if not (0.2 <= oo <= 0.95 and m['fit']['seen'] >= 0.7):
                continue
            op = im[..., 3] == 255
            s = im[..., :3].astype(np.float32)
            B = expn[y0:y0 + h, x0:x0 + w]
            I = frame[y0:y0 + h, x0:x0 + w].astype(np.float32)
            d = np.abs(I - B - oo * (s - B)).max(2)[op]
            inf = (np.abs(oo * (s - B)).max(2) > 8)[op]
            for val, c in zip(*np.unique(np.minimum(np.round(d[inf]), 9), return_counts=True)):
                hist[int(val)] += int(c)
            shares.append((fm[y0:y0 + h, x0:x0 + w][op][inf].mean(), oo))
            n_f += 1
        res_n.append(R)
        feas_other.append((int((fm & ~mobmask).sum()), int((rm & ~mobmask).sum())))
    tot = sum(hist.values())
    cum = 0
    print(f'{n_f} real fading mobs (fit o 0.2-0.95, seen >= 0.7): residual |I - (B + o (s - B))| at informative opaque pixels')
    for k in sorted(hist):
        cum += hist[k]
        label = '>=9' if k >= 9 else str(k)
        print(f'   {label:>4}: {100 * hist[k] / tot:5.1f} %  cum {100 * cum / tot:5.1f} %')
    sh = np.array(shares)
    by = {}
    for a, b in ((0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 0.96)):
        sel = (sh[:, 1] >= a) & (sh[:, 1] < b)
        if sel.any():
            by[f'{a:.1f}-{b:.1f}'] = (round(float(sh[sel, 0].mean()), 2), int(sel.sum()))
    print(f"fade-feasible (tol {TOL}) share of those mobs' informative pixels: p10 {np.percentile(sh[:, 0], 10):.2f} "
          f"p50 {np.median(sh[:, 0]):.2f} mean {sh[:, 0].mean():.2f}; by o (share, mobs): {by}")
    fo = np.array(feas_other)
    print(f'residue (D-bad, no palette colour) px / frame p50 {np.median(res_n):.0f} p90 {np.percentile(res_n, 90):.0f}; '
          f'away from fit mobs: feasible {fo[:, 0].sum()} of {fo[:, 1].sum()} = {100 * fo[:, 0].sum() / fo[:, 1].sum():.1f} %; '
          f'feasibility ms p50 {np.median(ms[3:]):.2f} p90 {np.percentile(ms[3:], 90):.2f}')
else:
    out = Path('runs/synth/ant4_500')
    meta = json.load(open(out / 'synth.json'))
    v = E.Voter(meta['map'])
    scene = Scene.load(meta['map'])
    pal = palette(v)
    sh, other = [], []
    for n, fr in meta['frames'].items():
        if fr['case'] not in ('fade', 'free', 'player', 'effect'):
            continue
        img = cv2.imread(str(out / 'frames' / fr['frame']))
        f = torch.from_numpy(img[:PH].copy()).cuda()
        exp, known = scene.expected(tuple(fr['C']))
        ids = v.ids(f)
        res, feas, o, R = feasible(f, exp, known, ids, pal)
        fm, rm = masks(res, feas)
        mm = np.zeros((PH, SW), bool)
        for m in fr['mobs']:
            x, y, w, h = m['box']
            mm[max(0, y - 4):y + h + 4, max(0, x - 4):x + w + 4] = True
            if m['opacity'] < 0.999 and fr['case'] == 'fade':
                box = fm[max(0, y):y + h, max(0, x):x + w]
                rb = rm[max(0, y):y + h, max(0, x):x + w]
                sh.append((box.sum() / max(rb.sum(), 1), m['opacity'], int(box.sum())))
        other.append((fr['case'], int((fm & ~mm).sum()), int((rm & ~mm).sum())))
    sh = np.array(sh)
    by = {}
    for a, b in ((0.2, 0.35), (0.35, 0.5), (0.5, 0.7), (0.7, 0.91)):
        sel = (sh[:, 1] >= a) & (sh[:, 1] < b)
        by[f'{a:.2f}-{b:.2f}'] = (round(float(sh[sel, 0].mean()), 2), int(sh[sel, 2].mean()), int(sel.sum()))
    print(f'synth fade mobs {len(sh)}: feasible (tol {TOL}) share of their residue pixels by opacity (share, px, mobs): {by}')
    for c in ('free', 'player', 'effect', 'fade'):
        a = np.array([(x, y) for cc, x, y in other if cc == c])
        print(f'  {c}: residue away from mobs: feasible {a[:, 0].sum()} of {a[:, 1].sum()} = {100 * a[:, 0].sum() / max(a[:, 1].sum(), 1):.1f} %')
