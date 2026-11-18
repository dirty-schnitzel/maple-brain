"""PLAN-loot.md S9 cost gate: the live Perceiver's tick with drops off vs on, A/B alternating in one process and state
(pinned to the performance cores as the bot is; the game running, nothing else of ours).

    python tools/loot/bench_drops.py [--clips busy,steam,line1,ant4fix] [--rounds 3] [--n 150]

Per clip: its frames read into memory once; per round one pass with perception.drops off and one on (the order
swaps every round), each pass a fresh Perceiver on the same rig (map kit, fit, the ONE DropFinder) over the same
frames; the first WARM frames of a pass not counted. -> perceive ms p50 / p90 per mode, on - off, and the parts.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "perc"))
sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
CLIPS = {"busy": ("runs/v2/20261117_094333_1", 100, 140),       # section 9's busiest stretch (12 drops a frame)
         "steam": ("runs/play/20261116_084844_2", 0, 60),
         "line1": ("runs/play/20261116_085108_3", 0, 60),
         "ant4": ("runs/play/20261116_154819_1", 0, 60)}
WARM = 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", default="busy,steam,line1,ant4")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--n", type=int, default=150)
    a = ap.parse_args()
    from maplebrain.procperf import prefer_performance
    print(prefer_performance())
    import frames as rec
    from run import bench_module, from_log, saved_frames
    from maplebrain.perception.perceiver import Perceiver
    bench = bench_module()
    P = lambda v, q: float(np.percentile(v, q)) if len(v) else float("nan")  # noqa: E731
    for name in a.clips.split(","):
        run, t0, t1 = CLIPS[name]
        run = ROOT / run
        mid = from_log(run)[0]
        fr = saved_frames(run, t0, t1)
        fr = fr[:a.n]                                   # consecutive saved frames: the tag / camera / minimap hold
        imgs = [(rec.read(run, f), t) for _, f, t in fr]
        per0, _, _, rig = bench.build(mid)
        cfg = per0.cfg
        res = {False: [], True: []}
        parts = {False: {}, True: {}}
        n_drops = []
        for r in range(a.rounds):
            for on in ((False, True) if r % 2 == 0 else (True, False)):
                cfg.perception.drops = on
                per = Perceiver(cfg, rig.self_tag, rig.kit, lie_detector=rig.lie, locator=rig.locator)
                for i, (img, t) in enumerate(imgs):
                    s = time.perf_counter()
                    per.observe(img, t)
                    ms = (time.perf_counter() - s) * 1000
                    if i < WARM:
                        continue
                    res[on].append(ms)
                    for k, v in (per.parts or {}).items():
                        parts[on].setdefault(k, []).append(v)
                    if on and per.facts.drops is not None:
                        n_drops.append(len(per.facts.drops))
                        for k in ("launch", "fetch", "pick"):
                            parts[on].setdefault("drops." + k, []).append(per.facts.drops_ms[k])
        d50, d90 = P(res[True], 50) - P(res[False], 50), P(res[True], 90) - P(res[False], 90)
        print(f"{name} ({run.name} t {t0}-{t1}, {len(imgs)} frames x {a.rounds} rounds, sightings a frame p50 "
              f"{P(n_drops, 50):.0f} p90 {P(n_drops, 90):.0f}): perceive off p50 {P(res[False], 50):.2f} p90 "
              f"{P(res[False], 90):.2f} | on p50 {P(res[True], 50):.2f} p90 {P(res[True], 90):.2f} | on - off p50 "
              f"{d50:+.2f} p90 {d90:+.2f} ms (gate p90 <= +1.0)")
        for on in (False, True):
            print(f"   parts {'on ' if on else 'off'}: " + ", ".join(
                f"{k} {P(v, 50):.2f}/{P(v, 90):.2f}" for k, v in sorted(parts[on].items(), key=lambda kv: -np.median(kv[1]))
                if P(v, 90) >= 0.05))
        del per, per0, rig


if __name__ == "__main__":
    main()
