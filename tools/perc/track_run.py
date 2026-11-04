"""Run the tracker over a recorded run (perception rework, stage 3).

  python tools/perc/track_run.py RUN MAP [--t0 S --t1 S] [--every K] [--no-near] [--out tracks.jsonl]
  python tools/perc/track_run.py RUN MAP --show 40 45 [--step 0.25] [--width 160]    (console map per tick)

Detector (GPU whole screen) + `World` on every saved frame -> RUN/tracks.jsonl, one line per frame:
  {"n", "frame", "t", "C": [cx, cy], "me": [x, feet], "tracks": [Track.as_dict], "ms": {"find", "near", "world"}}
The camera shift is recomputed from the frames the way the Perceiver does (old ticks have no scene_dy).
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from maplebot.nav.navmap import NavMap  # noqa: E402
from maplebot.perception.gpu_sprites import GpuSpriteDetector  # noqa: E402
from maplebot.perception.mapascii import header, render  # noqa: E402
from maplebot.perception.world import World, letters, marks  # noqa: E402
from maplebot.cover import Cover  # noqa: E402
from maplebot.perception.tags import find_tags  # noqa: E402


class Shift:
    def __init__(self):
        self.prev = None

    def __call__(self, frame):
        small = cv2.resize(cv2.cvtColor(frame[:620], cv2.COLOR_BGR2GRAY), (341, 155),
                           interpolation=cv2.INTER_AREA).astype(np.float32)
        out = None
        if self.prev is not None:
            (dx, dy), resp = cv2.phaseCorrelate(self.prev, small)
            out = (float(dx * 4), float(dy * 4)) if resp > 0.2 else None
        self.prev = small
        return out


def load(map_id):
    root = ROOT / "assets" / "mcw"
    mj = json.loads((root / "maps" / str(map_id) / "map.json").read_text(encoding="utf-8"))
    ids = sorted({int(x["id"]) for x in mj.get("mobs") or []})
    mobs = {i: json.loads((root / "mobs" / str(i) / "mob.json").read_text(encoding="utf-8")) for i in ids}
    return mj, mobs, NavMap.from_json(mj)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("map", type=int)
    ap.add_argument("--t0", type=float, default=0)
    ap.add_argument("--t1", type=float, default=1e9)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--no-near", action="store_true")
    ap.add_argument("--no-cover", action="store_true", help="ignore the cover masks (what is drawn over mobs)")
    ap.add_argument("--no-players", action="store_true", help="don't mask other players' bodies")
    ap.add_argument("--min", type=float, default=0.5, help="the whole-screen pass's threshold")
    ap.add_argument("--out", default="tracks.jsonl")
    ap.add_argument("--show", nargs=2, type=float, default=None, help="print the console map from T0 to T1")
    ap.add_argument("--step", type=float, default=0.25, help="--show: seconds between printed frames")
    ap.add_argument("--width", type=int, default=160)
    a = ap.parse_args()
    run = Path(a.run)
    mj, mobs, nav = load(a.map)
    det = GpuSpriteDetector.for_map(a.map, ROOT / "assets" / "mcw", min_score=a.min)
    cover = None if a.no_cover else Cover.for_map(a.map, ROOT / "assets" / "mcw")
    world = World(nav, mj, mobs, cover=cover)
    let = letters({i: m.get("name", str(i)) for i, m in mobs.items()})
    ticks = [json.loads(l) for l in open(run / "ticks.jsonl", encoding="utf-8")]
    ticks = [k for k in ticks if k.get("frame")][::a.every]
    if a.show:
        a.t0, a.t1 = min(a.t0, a.show[0] - 3), a.show[1]              # 3 s warm-up before the shown span
        print(header(mj))
        print("letters:", {mobs[i]["name"]: c for i, c in let.items()})
    shift = Shift()
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(1)
    near_fn = None
    ms_near = [0.0]
    if not a.no_near:
        def near_fn(spots, pad=24, vis=None):
            t0 = time.perf_counter()
            r = det.find_near(frame, spots, pad=pad, vis=vis)
            ms_near[0] += (time.perf_counter() - t0) * 1000
            return r
    det.find(np.zeros((768, 1366, 3), np.uint8))                     # warm-up (cudnn picks its kernels)
    if not a.no_near:
        print(f"near warm-up {det.warm_near(occluded=True):.1f}s")
    out = open(run / a.out, "w", encoding="utf-8") if not a.show else None
    times, last_show = [], -1e9
    for k in ticks:
        t = k["obs"]["t"]
        if not a.t0 <= t <= a.t1:
            continue
        frame = cv2.imread(str(run / "frames" / k["frame"]))
        if frame is None:
            continue
        o = k["obs"]
        sh = shift(frame)
        t0 = time.perf_counter()
        tags_job = None if a.no_players else pool.submit(find_tags, frame)   # CPU, while the GPU finds mobs
        hits = det.find(frame)
        t1 = time.perf_counter()
        ms_near[0] = 0.0
        me = tuple(o["me"]) if o.get("me") else None
        tags = None if tags_job is None else tags_job.result()
        trs = world.update(t, hits, me, tuple(o["map_pos"]) if o.get("map_pos") else None, sh, near_fn, tags=tags)
        t2 = time.perf_counter()
        ms = {"find": round((t1 - t0) * 1000, 1), "near": round(ms_near[0], 1),
              "world": round((t2 - t1) * 1000 - ms_near[0], 2)}
        times.append(ms)
        if out:
            out.write(json.dumps({"n": k["n"], "frame": k["frame"], "t": round(t, 3),
                                  "C": [round(v, 1) for v in world.cam.C] if world.cam.C else None,
                                  "me": o.get("me"), "tracks": [tr.as_dict(t) for tr in trs], "ms": ms}) + "\n")
        if a.show and a.show[0] <= t and t - last_show >= a.step - 1e-6:
            last_show = t
            C = world.cam.C
            mk = marks(trs, t, let)
            if me and C:
                mk.append(("@", me[0] + C[0], me[1] + C[1]))
            scr = (C[0], C[0] + 1366) if C else None
            desc = " ".join(f"{let.get(tr.mob_id, 'M')}{tr.id}:{tr.state[:4]}/{tr.anim}/{tr.src}"
                            f"{'' if tr.src != 'none' else f'({t - tr.seen:.1f}s)'}" for tr in trs)
            print(f"\n--- tick {k['n']}  t={t:.2f}s  C={tuple(round(v) for v in C) if C else None}  "
                  f"hits={len(hits)}  tracks={len(trs)}  {desc}")
            print(render(mj, marks=mk, screen=scr, width=a.width, spawns=False))
    if out:
        out.close()
    if times:
        for key in ("find", "near", "world"):
            v = sorted(x[key] for x in times)
            print(f"{key:5s} ms: median {statistics.median(v):.2f}  p90 {v[int(len(v) * 0.9)]:.2f}  max {v[-1]:.2f}")
        print("frames", len(times), "stats", world.stats)


if __name__ == "__main__":
    main()
