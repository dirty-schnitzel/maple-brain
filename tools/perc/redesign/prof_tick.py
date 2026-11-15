"""Profile the live v2 tick (bench.py's loop) per part and per hot function; CPU vs GPU.
    python prof_tick.py [--frames DIR] [--map ID] [--n N] [--mode parts|cprofile|cuda] [--dt 0.06]
"""
import argparse
import cProfile
import functools
import io
import pstats
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(r"C:\Users\Yoav\dev\maple-work")
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "tools" / "perf"))
import bench  # noqa: E402

ACC = defaultdict(float)     # label -> ms this tick
CNT = defaultdict(int)


def wrap(owner, name, label, sync=False):
    f = getattr(owner, name)
    torch = None
    if sync:
        import torch

    @functools.wraps(f)
    def g(*a, **kw):
        if sync:
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        try:
            return f(*a, **kw)
        finally:
            if sync:
                torch.cuda.synchronize()
            ACC[label] += 1000 * (time.perf_counter() - t0)
            CNT[label] += 1
    setattr(owner, name, g)


def instrument(per, rig, sync):
    from maplebrain import capture
    from maplebrain.perception import hud, perceiver, gpu_sprites, world, camshift, selfpos, tags
    from maplebrain import cover
    from maplebrain.nav import localize
    gpu = rig.sprites.gpu
    wrap(gpu, "find", "gpu.find", sync)
    wrap(gpu, "_dev_frame", "gpu._dev_frame(upload)", sync)
    wrap(gpu, "scores", "gpu.scores(coarse conv)", sync)
    wrap(gpu, "_refine", "gpu._refine", sync)
    wrap(gpu, "find_near", "world>find_near(GPU)", sync)
    wrap(gpu, "_occluded", "world>find_near>_occluded", sync)
    wrap(cv2, "resize", "cv2.resize(any)")
    wrap(cv2, "cvtColor", "cv2.cvtColor(any)")
    wrap(cv2, "matchTemplate", "cv2.matchTemplate(any)")
    wrap(cv2, "phaseCorrelate", "scene>phaseCorrelate")
    wrap(perceiver, "find_self", "self>find_self")
    wrap(selfpos, "ui_mask", "ui_mask")
    wrap(perceiver, "find_tags", "tags(thread)>find_tags")
    wrap(hud, "read_pair", "hud>read_pair")
    wrap(hud, "slot_filled", "hud>slot_filled")
    wrap(hud, "exp_points", "hud>exp_points")
    wrap(hud, "minimap_dot", "locate>minimap_dot")
    loc = rig.locator
    wrap(loc, "follow", "locate>follow")
    wrap(loc, "calibrate", "locate>calibrate")
    wrap(loc, "where", "locate>where")
    W = per.world
    wrap(W, "_occlusion", "world>_occlusion")
    wrap(W, "_vis_map", "world>_vis_map")
    wrap(W, "_probes", "world>_probes")
    wrap(W, "_share", "world>_share")
    if per.plat_shift is not None:
        wrap(per.plat_shift, "update", "camshift>update")
    wrap(per, "_track", "_track(gpu+camshift+world)")
    wrap(per.lie_detector, "check", "lie>check")


def run(frames, map_id, mode, dt, sync):
    from maplebrain.capture import normalize
    from maplebrain.nav.sim import SimDriver
    per, me, brain, rig = bench.build(map_id)
    drv = SimDriver()
    imgs = [cv2.imread(str(p)) for p in frames]
    big = cv2.resize(imgs[0], bench.SCREEN)
    if mode == "parts":
        instrument(per, rig, sync)
    prof = cProfile.Profile() if mode == "cprofile" else None
    tprof = None
    rows = []
    t = 0.0
    for i, img in enumerate(imgs):
        t += dt
        if i == bench.WARMUP:
            if prof:
                prof.enable()
            if mode == "cuda":
                import torch
                tprof = torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,
                                                           torch.profiler.ProfilerActivity.CUDA])
                tprof.__enter__()
        ACC.clear()
        t0 = time.perf_counter()
        normalize(big)
        t1 = time.perf_counter()
        obs = per.observe(img, t)
        t2 = time.perf_counter()
        drv.keys(t)
        s = me.update(t, obs.me_map, obs.map_pos, drv.want)
        brain.step(t, obs, s, drv)
        t3 = time.perf_counter()
        if i >= bench.WARMUP:
            rows.append({"tick": 1000 * (t3 - t0), "resize": 1000 * (t1 - t0), "perceive": 1000 * (t2 - t1),
                         "brain": 1000 * (t3 - t2), **{f"p.{k}": v for k, v in per.parts.items()},
                         **{f"f.{k}": v for k, v in ACC.items()},
                         "n_tracks": len(per.world.tracks), "n_hits": len(rig.sprites.all_hits)})
    if prof:
        prof.disable()
        s = io.StringIO()
        st = pstats.Stats(prof, stream=s)
        st.sort_stats("tottime").print_stats(45)
        print(s.getvalue())
        s = io.StringIO()
        pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(60)
        print(s.getvalue())
    if tprof:
        tprof.__exit__(None, None, None)
        ka = tprof.key_averages()
        n = len(rows)
        print(f"--- torch profiler over {n} ticks (per tick)")
        print(ka.table(sort_by="cuda_time_total", row_limit=25))
        print(ka.table(sort_by="cpu_time_total", row_limit=25))
    keys = sorted({k for r in rows for k in r})
    print(f"frames {len(rows)} (dt {dt}, sync {sync})")
    for k in keys:
        v = sorted(r.get(k, 0.0) for r in rows)
        mean = sum(v) / len(v)
        print(f"{k:42s} p50 {statistics.median(v):7.2f}  mean {mean:7.2f}  p90 {v[int(0.9 * (len(v) - 1))]:7.2f}  max {v[-1]:7.2f}")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, default=None)
    ap.add_argument("--map", type=int, default=bench.ANT4)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--mode", default="parts")
    ap.add_argument("--dt", type=float, default=0.06)
    ap.add_argument("--sync", action="store_true")
    a = ap.parse_args()
    fr = sorted(a.frames.glob("*.jpg"))[a.start:a.start + a.n] if a.frames else bench.fixture_frames()
    run(fr, a.map, a.mode, a.dt, a.sync)
