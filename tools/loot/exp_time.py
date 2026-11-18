"""E-L7 (PLAN-loot.md): what the drop finder costs a tick, BESIDE the mob fit - pinned, synced, game running.

    python tools/loot/exp_time.py RUN [--t0 S] [--t1 S] [--n 150] [--rounds 3] [--kinds Etc,Consume] [--check]

Frames of RUN (evenly from t0..t1) are read and uploaded first; expected() once per frame, not counted (D's, as in
the fit's numbers). Per round, per frame: the mob fit (Fitter.fit, as the Perceiver calls it) then the drop finder
(dropfast.FastFinder.find_fast: vote + GPU check + pick), each timed to its own sync. Prints p50 / p90 of the drop
finder's parts and of the fit with / without the finder after it. --check: the GPU check = dropvote's numpy check on
every frame (same drops, same counts).
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, map_of, run_ticks, world_mask, PLAY_H, ROOT  # noqa: E402
from dropfast import FastFinder  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--t1", type=float, default=1e9)
ap.add_argument("--n", type=int, default=150)
ap.add_argument("--rounds", type=int, default=3)
ap.add_argument("--kinds", default="")
ap.add_argument("--ids", default="")
ap.add_argument("--check", action="store_true")
ap.add_argument("--no-fit", action="store_true")
ap.add_argument("--votes", type=int, default=16)
a = ap.parse_args()

import torch  # noqa: E402
from maplebrain import procperf  # noqa: E402
from maplebrain.perception import hud  # noqa: E402
from maplebrain.perception.fit import Fitter  # noqa: E402
from maplebrain.scene import Scene  # noqa: E402

print(procperf.prefer_performance())
run = Path(a.run)
mid = map_of(run)
scene = Scene.load(mid)
fitter = None if a.no_fit else Fitter(scene, mid, ROOT / "assets" / "mcw")
if fitter is not None:
    fitter.warm()
fz = FastFinder(kinds=tuple(a.kinds.split(",")) if a.kinds else None,
                ids=[int(x) for x in a.ids.split(",")] if a.ids else None, cand_votes=a.votes)
print(f"finder: {len(fz.poses)} pictures; {fz.voter.stats()}")
ticks = [k for k in run_ticks(run) if a.t0 <= (k["t"] or 0) <= a.t1]
ticks = [ticks[int(i)] for i in np.linspace(0, len(ticks) - 1, min(a.n, len(ticks)))]
data, ui, last, share = [], None, None, None
for k in ticks:
    f = frame(run, k["frame"])
    ft = torch.from_numpy(np.ascontiguousarray(f[:PLAY_H])).to(scene.dev)
    if ui is None:
        ui = torch.from_numpy(world_mask(mid, f.shape)).to(scene.dev)
    reg = scene.locate(ft, C_guess=k["cam"] or last, seed=k["cam"] or k.get("seed"), mask=ui, last_share=share)
    if reg is None:
        continue
    last, share = reg[0], reg[1]
    exp, known = scene.expected(reg[0])
    me = None if not k["me"] else (k["me"][0] - 40, k["me"][1] - 85, k["me"][0] + 40, k["me"][1] + 30)
    data.append((ft, reg[0], exp, known, me))
print(f"{run.name}: {len(data)} frames on the GPU")
sync = torch.cuda.synchronize
if a.check:
    bad = 0
    for ft, C, exp, known, me in data:
        A = sorted((d.item, d.frame, tuple(d.box), d.n_seen, d.n_abs, d.n_fseen, tuple(sorted(d.extra.items())))
                   for d in fz.find(ft, exp, known, ui))
        B = sorted((d.item, d.frame, tuple(d.box), d.n_seen, d.n_abs, d.n_fseen, tuple(sorted(d.extra.items())))
                   for d in fz.find_fast(ft, exp, known, ui))
        bad += A != B
        if A != B and bad <= 3:
            print("  differs:", [x for x in A if x not in B][:2], "|", [x for x in B if x not in A][:2])
    print(f"GPU check vs numpy check: {len(data) - bad} / {len(data)} frames identical")
for ft, C, exp, known, me in data[:20]:                       # warm-up
    if fitter is not None:
        fitter.fit(ft, C, exp, known, ui, me)
    fz.find_fast(ft, exp, known, ui)
sync()
res = {"fit_alone": [], "fit_before": [], "vote": [], "check": [], "pick": [], "all": [], "cands": [], "feat": [],
       "drops": []}
for rd in range(a.rounds):
    for with_drops in (False, True):
        for ft, C, exp, known, me in data:
            sync()
            t = time.perf_counter()
            if fitter is not None:
                fitter.fit(ft, C, exp, known, ui, me)
                sync()
            t_fit = (time.perf_counter() - t) * 1000
            if not with_drops:
                res["fit_alone"].append(t_fit)
                continue
            res["fit_before"].append(t_fit)
            t = time.perf_counter()
            d = fz.find_fast(ft, exp, known, ui)
            sync()
            res["all"].append((time.perf_counter() - t) * 1000)
            for kk in ("vote", "check", "pick", "cands", "feat"):
                res[kk].append(fz.ms[kk])
            res["drops"].append(len(d))
P = lambda v, q: float(np.percentile(v, q))  # noqa: E731
for kk in ("fit_alone", "fit_before", "all", "vote", "check", "pick"):
    v = res[kk]
    print(f"   {kk:10s} ms p50 {P(v, 50):.2f} p90 {P(v, 90):.2f} p99 {P(v, 99):.2f}")
print(f"   candidates p50 {P(res['cands'], 50):.0f} p90 {P(res['cands'], 90):.0f} | features p50 {P(res['feat'], 50):.0f} p90 "
      f"{P(res['feat'], 90):.0f} | drops a frame p50 {P(res['drops'], 50):.0f} p90 {P(res['drops'], 90):.0f}")
