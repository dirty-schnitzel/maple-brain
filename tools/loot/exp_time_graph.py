"""E-L7c (PLAN-loot.md): the drop pass as ONE fixed-size GPU graph - same drops? what does it cost beside the fit?

    python tools/loot/exp_time_graph.py RUN [--t0 S] [--t1 S] [--n 150] [--rounds 3] [--check] [--no-graph]
                                            [--nf 32768] [--maxp 4] [--nc 64]

Frames of RUN are read and uploaded first; expected() once per frame, not counted (D's).
--check: the graph's drops = the eager prototype's (dropfast.find_fast) per frame (item, box, counts).
Timing loop per frame (pinned, synced where said):
    A  the mob fit alone, synced                                                  (today)
    B  the mob fit, then launch the drop graph and WAIT for it, then pick         (its whole cost in line)
    C  launch the drop graph (no wait) -> the mob fit, synced -> fetch + pick     (the proposal: launched first, read
       after the fit; `launch` / `fetch` / `pick` are the main thread's own ms)
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, map_of, run_ticks, world_mask, PLAY_H, ROOT  # noqa: E402
from dropgraph import GraphFinder  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--t1", type=float, default=1e9)
ap.add_argument("--n", type=int, default=150)
ap.add_argument("--rounds", type=int, default=3)
ap.add_argument("--check", action="store_true")
ap.add_argument("--no-graph", action="store_true")
ap.add_argument("--nf", type=int, default=32768)
ap.add_argument("--maxp", type=int, default=4)
ap.add_argument("--nc", type=int, default=64)
ap.add_argument("--votes", type=int, default=16)
ap.add_argument("--side", action="store_true", help="the graph on its own CUDA stream")
ap.add_argument("--ids", default="", help="only these item ids (+ the mesos): a short list instead of every picture")
a = ap.parse_args()

import torch  # noqa: E402
from maplebrain import procperf  # noqa: E402
from maplebrain.perception.fit import Fitter  # noqa: E402
from maplebrain.scene import Scene  # noqa: E402

print(procperf.prefer_performance())
run = Path(a.run)
mid = map_of(run)
scene = Scene.load(mid)
fitter = Fitter(scene, mid, ROOT / "assets" / "mcw")
fitter.warm()
fz = GraphFinder(cand_votes=a.votes, NF=a.nf, MAXP=a.maxp, NC=a.nc,
                 ids=[int(x) for x in a.ids.split(",")] if a.ids else None)
print(f"graph finder: {len(fz.poses)} pictures; table entries kept at <= {a.maxp} places per key: {fz.kept_entries} of "
      f"{fz.all_entries} ({100 * fz.kept_entries / fz.all_entries:.1f} %); NF {a.nf}, NC {a.nc}")
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
if not a.no_graph:
    t = time.perf_counter()
    fz.prepare(side_stream=a.side)
    print(f"graph captured in {time.perf_counter() - t:.2f} s{' (its own CUDA stream)' if a.side else ''}")
else:
    fz.g_oxy = torch.from_numpy(fz.oxy.astype(np.int64)).to(fz.dev)
sig = lambda ds: sorted((d.item, d.frame, tuple(int(v) for v in d.box), d.n_seen, d.n_abs, d.n_fseen,  # noqa: E731
                         d.extra["n_cd"], d.extra["ring_e"]) for d in ds)
if a.check:
    bad = lost = extra = 0
    nfm = 0
    for ft, C, exp, known, me in data:
        A = sig(fz.find_fast(ft, exp, known, ui))
        B = sig(fz.fetch(fz.launch(ft, exp, known, ui)))
        nfm = max(nfm, fz.ms_g["feat"])
        if A != B:
            bad += 1
            lost += len([x for x in A if x not in B])
            extra += len([x for x in B if x not in A])
            if bad <= 3:
                print("  differs: only eager", [x for x in A if x not in B][:2], "| only graph", [x for x in B if x not in A][:2])
    print(f"graph vs the eager prototype: {len(data) - bad} / {len(data)} frames identical (drops only eager {lost}, only graph "
          f"{extra}); most features on a frame {nfm} (NF {a.nf})")
for ft, C, exp, known, me in data[:20]:
    fitter.fit(ft, C, exp, known, ui, me)
    fz.fetch(fz.launch(ft, exp, known, ui))
sync()
res = {k: [] for k in ("A", "B", "C", "launch", "wait", "fetch", "pick", "gpu")}
for rd in range(a.rounds):
    for mode in "ABC":
        for ft, C, exp, known, me in data:
            sync()
            t = time.perf_counter()
            if mode == "C":
                out = fz.launch(ft, exp, known, ui)
                res["launch"].append((time.perf_counter() - t) * 1000)
            fitter.fit(ft, C, exp, known, ui, me)
            sync()
            if mode == "B":
                t1 = time.perf_counter()
                out = fz.launch(ft, exp, known, ui)
                sync()
                res["gpu"].append((time.perf_counter() - t1) * 1000)
                fz.fetch(out)
            elif mode == "C":
                fz.fetch(out)
                res["fetch"].append(fz.ms_g["fetch"])
                res["pick"].append(fz.ms_g["pick"])
            res[mode].append((time.perf_counter() - t) * 1000)
P = lambda v, q: float(np.percentile(v, q))  # noqa: E731
for kk, name in (("A", "fit alone"), ("B", "fit, then the drop pass in line"), ("C", "drop pass launched first, read after the fit")):
    print(f"   {name:46s} ms p50 {P(res[kk], 50):.2f} p90 {P(res[kk], 90):.2f} p99 {P(res[kk], 99):.2f}")
print(f"   B - A: p50 {P(res['B'], 50) - P(res['A'], 50):+.2f} p90 {P(res['B'], 90) - P(res['A'], 90):+.2f} ms | C - A: p50 "
      f"{P(res['C'], 50) - P(res['A'], 50):+.2f} p90 {P(res['C'], 90) - P(res['A'], 90):+.2f} ms")
print(f"   the pass alone, launched + waited for: p50 {P(res['gpu'], 50):.2f} p90 {P(res['gpu'], 90):.2f} ms | in C: launch p50 "
      f"{P(res['launch'], 50):.2f} p90 {P(res['launch'], 90):.2f}, fetch p50 {P(res['fetch'], 50):.2f} p90 {P(res['fetch'], 90):.2f}, "
      f"pick p50 {P(res['pick'], 50):.2f} p90 {P(res['pick'], 90):.2f} ms")
