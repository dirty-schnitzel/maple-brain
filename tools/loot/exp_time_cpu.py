"""E-L7b (PLAN-loot.md): the drop finder on a CPU reader thread BESIDE the mob fit - what does it cost the tick?

    python tools/loot/exp_time_cpu.py RUN [--t0 S] [--t1 S] [--n 150] [--rounds 3] [--check] [--busy N]

Frames of RUN are read and uploaded first; per frame the expected scene and D's packed mask (bit 0 may vote, 1 the
scene explains it, 2 known) are made once (D's work: one more byte-plane in its download, not counted).
The loop per frame, as the Perceiver would run it:
    A  the mob fit alone                                   (today)
    B  submit the CPU drop finder to a thread -> the mob fit -> join the thread     (the proposal)
    C  the mob fit, then the CPU drop finder on the main thread                      (no thread: its plain cost)
--busy N: N more threads doing numpy work the whole time (the tag / HUD / players' tags readers of the real tick).
Prints the loop's ms per frame p50 / p90 for A, B, C, the finder's own ms inside the thread, and how late the thread
was at the join (ms the main thread waited). --check: CPU finder = the GPU prototype (dropvote) on every frame.
"""
import argparse
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lootlib import frame, map_of, run_ticks, world_mask, PLAY_H, ROOT  # noqa: E402
from dropcpu import CpuFinder  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--t1", type=float, default=1e9)
ap.add_argument("--n", type=int, default=150)
ap.add_argument("--rounds", type=int, default=3)
ap.add_argument("--check", action="store_true")
ap.add_argument("--busy", type=int, default=0)
ap.add_argument("--votes", type=int, default=16)
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
fz = CpuFinder(cand_votes=a.votes)
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
    expl = known & ((ft.float() - exp).abs().amax(dim=2) <= 4)
    dm = (((~expl) & ui).to(torch.uint8) | (expl.to(torch.uint8) << 1) | (known.to(torch.uint8) << 2)).cpu().numpy()
    me = None if not k["me"] else (k["me"][0] - 40, k["me"][1] - 85, k["me"][0] + 40, k["me"][1] + 30)
    data.append((ft, reg[0], exp, known, me, np.ascontiguousarray(f[:PLAY_H]), dm))
print(f"{run.name}: {len(data)} frames")
sync = torch.cuda.synchronize
if a.check:
    bad = 0
    for ft, C, exp, known, me, fn, dm in data:
        A = sorted((d.item, d.frame, tuple(d.box), d.n_seen, d.n_abs, d.n_fseen, d.extra["n_cd"], d.extra["ring_e"])
                   for d in fz.find(ft, exp, known, ui))
        B = sorted((d.item, d.frame, tuple(d.box), d.n_seen, d.n_abs, d.n_fseen, d.extra["n_cd"], d.extra["ring_e"])
                   for d in fz.find_cpu(fn, dm))
        bad += A != B
        if A != B and bad <= 3:
            print("  differs:", [x for x in A if x not in B][:2], "|", [x for x in B if x not in A][:2])
    print(f"CPU finder vs the GPU prototype: {len(data) - bad} / {len(data)} frames identical")
pool = ThreadPoolExecutor(1, thread_name_prefix="drops")
stop = threading.Event()


def busy():
    x = np.random.default_rng(0).integers(0, 255, (768, 1366, 3), dtype=np.uint8)
    while not stop.is_set():
        g = x.astype(np.float32).sum(axis=2)
        (g[1:] - g[:-1]).max()
        time.sleep(0.004)


for _ in range(a.busy):
    threading.Thread(target=busy, daemon=True).start()
for ft, C, exp, known, me, fn, dm in data[:20]:
    fitter.fit(ft, C, exp, known, ui, me)
    fz.find_cpu(fn, dm)
sync()
res = {"A": [], "B": [], "C": [], "thread": [], "wait": [], "vote": [], "check": [], "px": [], "feat": [], "cands": []}
for rd in range(a.rounds):
    for mode in "ABC":
        for ft, C, exp, known, me, fn, dm in data:
            sync()
            t = time.perf_counter()
            if mode == "B":
                fut = pool.submit(fz.find_cpu, fn, dm)
            fitter.fit(ft, C, exp, known, ui, me)
            sync()
            if mode == "B":
                tw = time.perf_counter()
                fut.result()
                res["wait"].append((time.perf_counter() - tw) * 1000)
                res["thread"].append(fz.ms_cpu["all"])
            elif mode == "C":
                fz.find_cpu(fn, dm)
                for kk in ("vote", "check", "px", "feat", "cands"):
                    res[kk].append(fz.ms_cpu[kk])
            res[mode].append((time.perf_counter() - t) * 1000)
stop.set()
P = lambda v, q: float(np.percentile(v, q))  # noqa: E731
for kk, name in (("A", "fit alone"), ("B", "fit + drops on a thread"), ("C", "fit, then drops on this thread")):
    print(f"   {name:32s} ms p50 {P(res[kk], 50):.2f} p90 {P(res[kk], 90):.2f} p99 {P(res[kk], 99):.2f}")
print(f"   B - A: p50 {P(res['B'], 50) - P(res['A'], 50):+.2f} p90 {P(res['B'], 90) - P(res['A'], 90):+.2f} ms | "
      f"C - A: p50 {P(res['C'], 50) - P(res['A'], 50):+.2f} p90 {P(res['C'], 90) - P(res['A'], 90):+.2f} ms")
print(f"   the finder inside its thread: p50 {P(res['thread'], 50):.2f} p90 {P(res['thread'], 90):.2f} ms; main thread waited "
      f"at the join p50 {P(res['wait'], 50):.2f} p90 {P(res['wait'], 90):.2f} ms")
print(f"   alone (C): vote p50 {P(res['vote'], 50):.2f} p90 {P(res['vote'], 90):.2f}, check + pick p50 {P(res['check'], 50):.2f} p90 "
      f"{P(res['check'], 90):.2f} ms | pixels that may vote p50 {P(res['px'], 50):.0f} p90 {P(res['px'], 90):.0f}, features p50 "
      f"{P(res['feat'], 50):.0f}, candidates p50 {P(res['cands'], 50):.0f} p90 {P(res['cands'], 90):.0f}")
