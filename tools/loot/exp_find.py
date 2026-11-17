"""E-L2 (PLAN-loot.md): run the prototype drop finder (dropvote.py) over a recording's saved frames.

    python tools/loot/exp_find.py RUN [--every N] [--t0 S] [--t1 S] [--out NAME] [--kinds Etc,Consume] [--no-scene]
                                      [--cands] [--votes 12]

Per saved frame with a scene camera: the expected scene (Scene.expected at the recording's camera, re-registered
within 12 px), the UI mask (hud.ui_mask + the chat rect as world), the finder -> RUN/loot/find_<NAME>.jsonl, one row a
frame: {n, t, frame, cam, drops: [...], ms}. Prints the items seen and the ms (NOT a timing gate: unpinned, shared GPU).
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, map_of, run_ticks, world_mask, PLAY_H, ROOT  # noqa: E402
from dropvote import DropFinder  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--every", type=int, default=1)
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--t1", type=float, default=1e9)
ap.add_argument("--out", default="all")
ap.add_argument("--kinds", default="")
ap.add_argument("--no-scene", action="store_true")
ap.add_argument("--cands", action="store_true")
ap.add_argument("--votes", type=int, default=12)
ap.add_argument("--fit", action="store_true", help="run the mob fit first: its mobs' SEEN pixels -> n_mob per drop")
ap.add_argument("--old-mask", action="store_true", help="the default minimap rectangle (find_all / find_v2 used it)")
a = ap.parse_args()

import torch  # noqa: E402
from maplebrain.perception import hud  # noqa: E402
from maplebrain.scene import Scene  # noqa: E402

run = Path(a.run)
ticks = [k for k in run_ticks(run) if a.t0 <= (k["t"] or 0) <= a.t1][::a.every]
mid = map_of(run)
scene = Scene.load(mid)
fitter = None
if a.fit:
    from maplebrain.perception.fit import Fitter
    fitter = Fitter(scene, mid, ROOT / "assets" / "mcw")
fz = DropFinder(kinds=tuple(a.kinds.split(",")) if a.kinds else None, cand_votes=a.votes)
v = fz.voter
print(f"finder: {len(fz.poses)} pictures, built in {fz.build_s:.1f} s; {v.stats()}")
ui = None
out = run / "loot"
out.mkdir(exist_ok=True)
seen, ms_v, ms_c, n_fr, n_cam = Counter(), [], [], 0, 0
last = share = None
with open(out / f"find_{a.out}.jsonl", "w", encoding="utf-8") as fo:
    for k in ticks:
        f = frame(run, k["frame"])
        if f is None:
            continue
        n_fr += 1
        ft = torch.from_numpy(np.ascontiguousarray(f)).to(scene.dev)
        if ui is None:
            if a.old_mask:
                m = hud.ui_mask(f.shape, None)[:PLAY_H] > 0
                x0, y0, x1, y1 = hud.CHAT_WORLD
                m[y0:min(y1, PLAY_H), x0:x1] = True
            else:
                m = world_mask(mid, f.shape)
            ui = torch.from_numpy(np.ascontiguousarray(m)).to(scene.dev)
        C, exp, known = None, None, None
        guess, seed = k["cam"] or last, k["cam"] or k.get("seed")
        if guess is not None or seed is not None:
            reg = scene.locate(ft, C_guess=guess, seed=seed, mask=ui, last_share=share)
            if reg is not None:
                C, share = reg[0], reg[1]
                last = C
        if C is None:
            fo.write(json.dumps({"n": k["n"], "t": k["t"], "frame": k["frame"], "cam": None, "drops": None}) + "\n")
            continue
        n_cam += 1
        if not a.no_scene:
            exp, known = scene.expected(C)
        taken = None
        if fitter is not None:
            me = None if not k["me"] else (k["me"][0] - 40, k["me"][1] - 85, k["me"][0] + 40, k["me"][1] + 30)
            mobs = fitter.fit(ft[:PLAY_H], C, exp, known, ui, me)
            Pd = max(fitter.KH, fitter.KW)
            taken = fitter.taken[Pd:Pd + PLAY_H, Pd:Pd + ft.shape[1]] if fitter.taken is not None else \
                np.zeros((PLAY_H, ft.shape[1]), bool)
        # characters' body boxes: ours (the tag's top = our feet) + the other players' (their name tags, FrameFacts)
        chars = np.zeros((PLAY_H, ft.shape[1]), bool)
        boxes = [(k["me"][0], k["me"][1])] if k["me"] else []
        boxes += [(tg[0] + tg[2] / 2, tg[1]) for tg in (k.get("facts") or {}).get("tags") or []]
        for cx, fy_ in boxes:
            chars[max(0, int(fy_) - 90):max(0, int(fy_) + 22), max(0, int(cx) - 42):max(0, int(cx) + 42)] = True
        r = fz.find(ft, exp, known, ui, keep_cands=a.cands, mob_taken=taken, chars=chars)
        drops, cands = r if a.cands else (r, None)
        ms_v.append(fz.ms["vote"])
        ms_c.append(fz.ms["check"])
        for d in drops:
            seen[d.item] += 1
        row = {"n": k["n"], "t": k["t"], "frame": k["frame"], "cam": list(C), "drops": [d.to_dict() for d in drops],
               "ms": {x: round(y, 2) if isinstance(y, float) else y for x, y in fz.ms.items()}}
        if cands is not None:
            row["cands"] = cands
        fo.write(json.dumps(row) + "\n")
print(f"{run.name}: {n_fr} frames, camera on {n_cam}; frames with a drop: "
      f"{sum(1 for _ in open(out / f'find_{a.out}.jsonl') if '\"item\"' in _)}")
if ms_v:
    print(f"vote ms p50 {np.median(ms_v):.2f} p90 {np.percentile(ms_v, 90):.2f} | check ms p50 {np.median(ms_c):.2f} "
          f"p90 {np.percentile(ms_c, 90):.2f} (unpinned: not a timing gate)")
for it, n in seen.most_common(40):
    print(f"  {it:8d} {fz.items.name(it)[:40]:40s} {fz.items.kind(it):8s} {n} frame-sightings")
