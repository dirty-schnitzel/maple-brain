"""E-L4 (PLAN-loot.md): identity + recall with EVERY item picture, on real frames (exact truth by construction).

    python tools/loot/exp_synth.py RUN [--frames 24] [--seed 1] [--mode alone|pile|cover] [--out NAME]

Base = saved frames of RUN at their registered camera. The client's pictures are pasted as the client draws a resting
drop (straight alpha over whatever is there, integer position) on a grid of free cells (no UI, no finder drop of the
unpasted frame within 40 px):
  alone   one picture per cell, every picture of the catalogue once (identity over all 4.6 k pictures)
  pile    3 pictures per cell, 14-22 px apart in x, +-3 px in y, pasted left to right (the last is in front): what a
          kill's drops look like; the first two are partly covered
  cover   one picture per cell with a band of it (a random side, 20-80 % of the opaque pixels) painted over with
          colours that are no palette colour (an effect / damage digits in front)
The finder (dropvote.py, all pictures) runs on the pasted frame. Scored per pasted picture: found = a drop of ITS
picture (or one that looks the same there: the visible part identical) with its box exactly at the pasted box.
Prints recall by kind and by visible share, wrong identities, extra drops (not pasted, not in the unpasted frame).
Writes RUN/loot/synth_<NAME>.json (every pasted picture: item, box, visible share, found, n_seen, n_fseen).
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, map_of, run_ticks, PLAY_H, SW  # noqa: E402
from dropvote import DropFinder  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--frames", type=int, default=24)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--mode", default="alone")
ap.add_argument("--out", default="")
ap.add_argument("--cell", type=int, default=64)
ap.add_argument("--min-seen", type=int, default=40)
ap.add_argument("--seen-min", type=float, default=0.25)
a = ap.parse_args()

import torch  # noqa: E402
from maplebrain.perception import hud  # noqa: E402
from maplebrain.scene import Scene  # noqa: E402

rng = np.random.default_rng(a.seed)
run = Path(a.run)
scene = Scene.load(map_of(run))
fz = DropFinder(min_seen=a.min_seen, seen_min=a.seen_min)
fz.voter.max_cells = 1024
P = len(fz.poses)
ticks = run_ticks(run)
ticks = [ticks[int(i)] for i in np.linspace(0, len(ticks) - 1, a.frames)]
order = rng.permutation(P)
nxt = 0
res, extra, n_frames = [], 0, 0
ui = None
for k in ticks:
    f = frame(run, k["frame"])
    ft = torch.from_numpy(np.ascontiguousarray(f)).to(scene.dev)
    if ui is None:
        m = hud.ui_mask(f.shape, None)[:PLAY_H] > 0
        x0, y0, x1, y1 = hud.CHAT_WORLD
        m[y0:min(y1, PLAY_H), x0:x1] = True
        ui_np, ui = m, torch.from_numpy(np.ascontiguousarray(m)).to(scene.dev)
    reg = scene.locate(ft, C_guess=k["cam"], seed=k["cam"] or k.get("seed"), mask=ui)
    if reg is None:
        continue
    exp, known = scene.expected(reg[0])
    base = fz.find(ft, exp, known, ui)
    base_boxes = [d.box for d in base]
    g = f.copy()
    pasted = []
    for cy in range(8, PLAY_H - a.cell, a.cell):
        for cx in range(8, SW - a.cell, a.cell):
            if not ui_np[cy:cy + a.cell, cx:cx + a.cell].all():
                continue
            if any(abs(b[0] - cx) < a.cell + 40 and abs(b[1] - cy) < a.cell + 40 for b in base_boxes):
                continue
            n = 3 if a.mode == "pile" else 1
            x = cx + 2
            for j in range(n):
                gi = int(order[nxt % P])
                nxt += 1
                p = fz.poses[gi]
                h, w = p.pic.shape[:2]
                y = cy + a.cell - 4 - h + (int(rng.integers(-3, 4)) if a.mode == "pile" else 0)
                if x + w > min(SW, cx + a.cell + (40 if a.mode == "pile" else 0)):
                    nxt -= 1
                    break
                al = p.pic[..., 3:4].astype(np.float32) / 255
                g[y:y + h, x:x + w] = (p.pic[..., :3] * al + g[y:y + h, x:x + w] * (1 - al) + 0.5).astype(np.uint8)
                vis = np.ones((h, w), bool)
                if a.mode == "cover":
                    op = p.pic[..., 3] == 255
                    share = rng.uniform(0.2, 0.8)
                    side = int(rng.integers(0, 4))
                    cum = np.cumsum(op.sum(axis=0 if side < 2 else 1)) / max(1, op.sum())
                    cut = int(np.searchsorted(cum, share if side % 2 == 0 else 1 - share))
                    band = np.zeros((h, w), bool)
                    if side == 0:
                        band[:, :cut + 1] = True
                    elif side == 1:
                        band[:, cut:] = True
                    elif side == 2:
                        band[:cut + 1] = True
                    else:
                        band[cut:] = True
                    noise = rng.integers(0, 256, (h, w, 3)).astype(np.uint8)
                    noise[..., 1] = 255 - noise[..., 0]          # garish: no palette colour by chance (checked below)
                    g[y:y + h, x:x + w][band] = noise[band]
                    vis &= ~band
                pasted.append({"g": gi, "item": p.type, "box": (x, y, w, h), "vis_mask": vis})
                # a later picture of the pile covers the earlier ones
                for q in pasted[:-1]:
                    qx, qy, qw, qh = q["box"]
                    ox0, oy0, ox1, oy1 = max(x, qx), max(y, qy), min(x + w, qx + qw), min(y + h, qy + qh)
                    if ox1 > ox0 and oy1 > oy0:
                        cov = p.pic[oy0 - y:oy1 - y, ox0 - x:ox1 - x, 3] > 0
                        q["vis_mask"][oy0 - qy:oy1 - qy, ox0 - qx:ox1 - qx] &= ~cov
                x += int(rng.integers(14, 23))
    gt = torch.from_numpy(np.ascontiguousarray(g)).to(scene.dev)
    drops = fz.find(gt, exp, known, ui)
    n_frames += 1
    used = set()
    for q in pasted:
        p = fz.poses[q["g"]]
        op = p.pic[..., 3] == 255
        q["vis"] = float((op & q["vis_mask"]).sum() / max(1, op.sum()))
        hit = None
        for di, d in enumerate(drops):
            if tuple(d.box) == q["box"]:
                same = d.item == q["item"]
                if not same:        # another picture, the same where visible?
                    o = next(pp for pp, mm in zip(fz.poses, fz.meta) if mm[0] == d.item and mm[1] == d.frame)
                    same = o.pic.shape == p.pic.shape and np.array_equal(o.pic[q["vis_mask"]], p.pic[q["vis_mask"]])
                    q["twin"] = d.item
                hit = (di, d, same)
                break
        q["found"] = bool(hit and hit[2])
        q["wrong"] = bool(hit and not hit[2])
        if hit:
            used.add(hit[0])
            q["n_seen"], q["n_fseen"], q["n_feat"] = hit[1].n_seen, hit[1].n_fseen, hit[1].n_feat
        res.append({kk: vv for kk, vv in q.items() if kk != "vis_mask"})
    for di, d in enumerate(drops):
        if di in used:
            continue
        if any(abs(d.box[0] - b[0]) <= 2 and abs(d.box[1] - b[1]) <= 8 for b in base_boxes):
            continue
        near = [q for q in pasted if abs(d.box[0] - q["box"][0]) < 44 and abs(d.box[1] - q["box"][1]) < 44]
        extra += 1
        if extra <= 12:
            print(f"   extra: {d.item} {fz.items.name(d.item)[:24]} box {d.box} seen {d.n_seen}/{d.n_op} "
                  f"near pasted {[(q['item'], q['box']) for q in near][:2]}")

kind = lambda i: "meso" if i >= 9000000 else fz.items.kind(i)  # noqa: E731
print(f"{run.name} mode {a.mode}: {n_frames} frames, {len(res)} pasted pictures ({len({r['g'] for r in res})} distinct of {P})")
tot = defaultdict(lambda: [0, 0, 0])
for r in res:
    t = tot[kind(r["item"]) if kind(r["item"]) in ("meso", "Etc", "Consume", "Install") else "equip"]
    t[0] += 1
    t[1] += r["found"]
    t[2] += r["wrong"]
for kd, (n, fnd, wr) in sorted(tot.items()):
    print(f"   {kd:8s} found {fnd} / {n} = {100 * fnd / n:.2f} %, wrong identity {wr}")
n, fnd, wr = len(res), sum(r["found"] for r in res), sum(r["wrong"] for r in res)
print(f"   ALL      found {fnd} / {n} = {100 * fnd / n:.2f} %, wrong identity {wr}, extra drops {extra}")
if a.mode != "alone":
    bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = [r for r in res if lo <= r["vis"] < hi]
        if sel:
            print(f"   visible {lo:.1f}-{min(hi, 1.0):.1f}: found {sum(r['found'] for r in sel)} / {len(sel)} = "
                  f"{100 * sum(r['found'] for r in sel) / len(sel):.1f} %, wrong {sum(r['wrong'] for r in sel)}")
miss = [r for r in res if not r["found"] and r["vis"] >= 0.9]
if miss:
    c = Counter(r["item"] for r in miss)
    print(f"   missed at >= 90 % visible: {len(miss)}: " + ", ".join(f"{i} {fz.items.name(i)[:18]}" for i, _ in c.most_common(15)))
tw = Counter((r["item"], r.get("twin")) for r in res if r.get("twin") and r["found"])
if tw:
    print(f"   found as a look-alike (same pixels where visible): {sum(tw.values())}, e.g. {tw.most_common(5)}")
out = run / "loot"
out.mkdir(exist_ok=True)
(out / f"synth_{a.out or a.mode}.json").write_text(json.dumps([{k: (list(v) if isinstance(v, tuple) else v)
                                                                 for k, v in r.items()} for r in res]), encoding="utf-8")
