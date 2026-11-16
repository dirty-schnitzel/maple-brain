"""The hunt's tick with the Lie Detector looked at in different ways (PLAN-perception.md step 2.8, part 3).

Each setting = the hunt's own look (CPU thread / GPU on the uploaded frame) x a `maplebrain watch` process beside
it (off / every 0.3 s / every 1 s, CPU or GPU). The tick is bench.py's (the live Perceiver + brain v2 on the perf
fixture), played forth and back `--reps` times in one build, so a run has ~45 x 2 x reps ticks. The watch processes
end by themselves (--seconds): nothing is killed. The game must be running (the GPU idles slow without it) and
visible (watch grabs the screen). Settings run in turn, the whole cycle `--cycles` times (drift shows).

    python tools/perc/ld/ld_speed.py [--reps 3] [--cycles 2]
"""
import argparse
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perf"))
SETTINGS = [("hunt cpu-thread, watch off", False, None),           # before 2.8 without watch
            ("hunt cpu-thread, watch 0.3 s cpu", False, (0.3, False)),   # before 2.8, the live setup
            ("hunt gpu, watch off", True, None),
            ("hunt gpu, watch 0.3 s cpu", True, (0.3, False)),
            ("hunt gpu, watch 1 s cpu", True, (1.0, False)),
            ("hunt gpu, watch 1 s gpu", True, (1.0, True))]


def run_ticks(lie_gpu: bool, frames, reps: int) -> list:
    import cv2
    import bench
    import maplebrain.config as C
    sys.path.insert(0, str(ROOT / "tools" / "perc"))
    import frames as rec
    orig = C.Config

    class Cfg(orig):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.perception.lie_gpu = lie_gpu
    C.Config = Cfg
    try:
        per, me, brain, rig = bench.build(bench.ANT4, scene_tol=30)
    finally:
        C.Config = orig
    from maplebrain.nav.sim import SimDriver
    drv = SimDriver()
    shift = rec.xshift(Path(frames[0]).parent)
    imgs = [rec.unshift(cv2.imread(str(p)), shift) for p in frames]
    seq = (imgs + imgs[::-1]) * reps
    ticks, lie_ms, t = [], [], 0.0
    for i, img in enumerate(seq):
        t += 0.06
        t0 = time.perf_counter()
        obs = per.observe(img, t)
        drv.keys(t)
        s = me.update(t, obs.me_map, obs.map_pos, drv.want)
        brain.step(t, obs, s, drv)
        if i >= bench.WARMUP:
            ticks.append(1000 * (time.perf_counter() - t0))
            lie_ms.append((per.parts or {}).get("lie", 0.0))
    if rig.lie.pool is not None:
        rig.lie.pool.shutdown(wait=True)
    return ticks, lie_ms


def start_watch(every: float, gpu: bool, seconds: float, out: Path):
    cmd = [sys.executable, "-m", "maplebrain", "watch", str(out), "--seconds", str(seconds), "--every", str(every)]
    if gpu:
        cmd.append("--gpu")
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:                            # ready = its "watching for the Lie Detector" line
        if "watching for" in line:
            return p
        if "not found" in line:
            raise RuntimeError(line)
    raise RuntimeError("watch ended before it started looking")


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * (len(v) - 1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cycles", type=int, default=2)
    a = ap.parse_args()
    import bench
    from maplebrain.procperf import prefer_performance
    print(prefer_performance())
    frames = bench.fixture_frames()
    tmp = Path(tempfile.mkdtemp(prefix="ld_speed_"))
    rows = {name: ([], []) for name, _, _ in SETTINGS}
    for c in range(a.cycles):
        for name, lie_gpu, w in SETTINGS:
            p = start_watch(w[0], w[1], 40, tmp / "watch") if w else None
            try:
                time.sleep(2.0)                      # its first looks (GPU: the cuFFT plan) out of the way
                ticks, lie = run_ticks(lie_gpu, frames, a.reps)
            finally:
                if p is not None:
                    p.wait()                         # ends by itself (--seconds 40)
            rows[name][0].extend(ticks)
            rows[name][1].extend(lie)
            print(f"cycle {c + 1} {name:36s} tick p50 {statistics.median(ticks):5.1f} p90 {pct(ticks, 0.9):5.1f} "
                  f"p99 {pct(ticks, 0.99):5.1f} | lie part p50 {statistics.median(lie):.2f} max {max(lie):.1f}",
                  flush=True)
    print("\nall cycles pooled:")
    for name, (ticks, lie) in rows.items():
        print(f"  {name:36s} n {len(ticks):4d} tick p50 {statistics.median(ticks):5.1f} p90 {pct(ticks, 0.9):5.1f} "
              f"p99 {pct(ticks, 0.99):5.1f} | lie part max {max(lie):.1f} ms")


if __name__ == "__main__":
    main()
