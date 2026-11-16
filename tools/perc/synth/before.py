"""Today's detector + tracker on a synthetic set (step 3.0b's "before"): the live Perceiver (tools/perf/bench.build,
as tools/perc/replay/run.py) over every synthetic frame on its own - a fresh tracker per frame, the scene camera
started at the frame's known camera, a dying / hit frame's "prime" (the mob alive) shown first, the frame shown `--ticks` times 0.05 s apart (one sighting >= 0.75 or two
confirm a track) -> the tracks of the last tick.

    python tools/perc/synth/before.py OUT [--mob-score 0.70] [--ticks 2] [--name before]
    python tools/perc/label_eval.py OUT --labels synth.json --tracks before.jsonl --synth
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "perc" / "replay"))
import run as replay  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--mob-score", type=float, default=0.70)
    ap.add_argument("--ticks", type=int, default=2)
    ap.add_argument("--name", default="before")
    a = ap.parse_args()
    meta = json.loads((a.out / "synth.json").read_text())
    per, _, _, rig = replay.bench_module().build(meta["map"], a.mob_score)
    from maplebrain.perception.world import World
    ctx = rig.sprites.track_ctx
    t, t0 = 0.0, time.perf_counter()
    with open(a.out / f"{a.name}.jsonl", "w", encoding="utf-8") as f:
        for n, fr in meta["frames"].items():
            img = cv2.imread(str(a.out / "frames" / fr["frame"]))
            per.world = World(*ctx)
            sc = per.scene_cam
            sc.C, sc.step, sc.share, sc.found, sc.misses = tuple(fr["C"]), (0, 0), None, True, 0
            per.scene_next_t = -1e9
            t += 10.0
            if fr.get("prime"):                              # dying / hit: the mob alive first
                per.observe(cv2.imread(str(a.out / "frames" / fr["prime"])), t)
                t += 0.1
            for k in range(a.ticks):
                obs = per.observe(img, t + 0.05 * k)
            f.write(json.dumps({"n": int(n), "frame": fr["frame"], "scene_cam": getattr(obs, "scene_cam", None),
                                "mobs": obs.mobs}) + "\n")
    print(f"{len(meta['frames'])} frames in {time.perf_counter() - t0:.0f} s -> {a.out / (a.name + '.jsonl')}")


if __name__ == "__main__":
    main()
