"""E-L1 (PLAN-loot.md): the item pictures as vote material - sizes, alpha, palette, 2x2 features, how unique they are.

    python tools/loot/exp_palette.py

Per kind (Etc, Consume, Install, equips, mesos) and for all together: pictures, size p50 / max, opaque / soft-alpha
pixels, colours, features (2x2 blocks of opaque pixels, not one flat colour), distinct keys, places per key, and how
many pictures have < 24 / < 60 features (the mob fit's candidate bar is 16 exclusive votes). Also: icon vs iconRaw.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import Items  # noqa: E402

it = Items()
EQUIP = ("Accessory", "Cap", "Cape", "Coat", "Glove", "Longcoat", "Pants", "Ring", "Shield", "Shoes", "Weapon")


def key24(p):
    return p[..., 0].astype(np.int64) | (p[..., 1].astype(np.int64) << 8) | (p[..., 2].astype(np.int64) << 16)


def feats(pic):
    op = pic[..., 3] == 255
    k = np.where(op, key24(pic), -1)
    a, b, c, d = k[:-1, :-1], k[:-1, 1:], k[1:, :-1], k[1:, 1:]
    ok = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0) & ~((a == b) & (a == c) & (a == d))
    return np.stack([a[ok], b[ok], c[ok], d[ok]], 1)


def report(name, pics):
    if not pics:
        return
    hs = np.array([p.shape[0] for p in pics])
    ws = np.array([p.shape[1] for p in pics])
    op = np.array([(p[..., 3] == 255).sum() for p in pics])
    soft = np.array([((p[..., 3] > 0) & (p[..., 3] < 255)).sum() for p in pics])
    cols = np.unique(np.concatenate([key24(p)[p[..., 3] == 255] for p in pics]))
    fs = [feats(p) for p in pics]
    nf = np.array([len(f) for f in fs])
    allf = np.concatenate(fs)
    _, inv, cnt = np.unique(allf, axis=0, return_inverse=True, return_counts=True)
    # per picture: features whose key occurs in <= 64 places (the vote table's max_entries) / only in this picture
    own = np.repeat(np.arange(len(pics)), nf)
    kept = np.bincount(own[cnt[inv] <= 64], minlength=len(pics))
    print(f"{name:10s} n {len(pics):5d} | size p50 {np.median(ws):.0f}x{np.median(hs):.0f} max {ws.max()}x{hs.max()} | "
          f"opaque px p50 {np.median(op):.0f} (p5 {np.percentile(op, 5):.0f}), soft px p50 {np.median(soft):.0f} "
          f"({100 * soft.sum() / max(1, op.sum() + soft.sum()):.1f} % of drawn) | colours {len(cols)} | features p50 "
          f"{np.median(nf):.0f} p5 {np.percentile(nf, 5):.0f} min {nf.min()}, keys {len(cnt)}, places per key p50 "
          f"{np.median(cnt):.0f} p99 {np.percentile(cnt, 99):.0f} max {cnt.max()} | kept (<= 64 places) p5 "
          f"{np.percentile(kept, 5):.0f}; pictures with < 16 kept {int((kept < 16).sum())}, < 60 {int((kept < 60).sum())}")
    return cols


groups = {"Etc": ("Etc",), "Consume": ("Consume",), "Install": ("Install",), "equips": EQUIP}
everything = []
for name, kinds in groups.items():
    pics = [it.raw(i)[0] for i in it.ids(kinds) if it.raw(i) is not None and it.raw(i)[0] is not None]
    report(name, pics)
    everything += pics
mesos = [p for n in range(4) for p, _, _ in it.meso(n)]
report("mesos", mesos)
report("ALL raw", everything + mesos)
# icon vs iconRaw
same = diff = 0
dsz = []
for i in it.ids(("Etc", "Consume")):
    r, c = it.raw(i), it.icon(i)
    if r is None or c is None or r[0] is None or c[0] is None:
        continue
    if r[0].shape == c[0].shape and np.array_equal(r[0], c[0]) and r[1] == c[1]:
        same += 1
    else:
        diff += 1
        dsz.append((r[0].shape[1] - c[0].shape[1], r[0].shape[0] - c[0].shape[0], r[1][0] - c[1][0], r[1][1] - c[1][1]))
print(f"Etc + Consume: icon == iconRaw (pixels + origin) {same}, differ {diff}")
if dsz:
    d = np.array(dsz)
    u, n = np.unique(d, axis=0, return_counts=True)
    for row, k in sorted(zip(u.tolist(), n.tolist()), key=lambda x: -x[1])[:8]:
        print(f"   raw - icon (w, h, ox, oy) {row}: {k}")
for n in range(4):
    print(f"meso {n}:", [(p.shape[1], p.shape[0], o, dl) for p, o, dl in it.meso(n)])
