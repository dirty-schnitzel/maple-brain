"""Bot speed benchmark: the live brain-v2 tick (capture resize -> perceive -> self state -> brain) replayed on recorded
frames, timed per part. The regression test (tests/test_perf.py) runs it on tests/fixtures/perf_ant4 and compares
with tests/perf_baseline.json; every pytest run ends with a one-line report (tests/conftest.py).

    python tools/perf/bench.py                       # the fixture, print the numbers
    python tools/perf/bench.py --baseline            # ... and write them as this machine's baseline
    python tools/perf/bench.py --frames runs/v2/press1/frames --map 10005063 [--n 200]   # any recorded run

What's NOT in it: the capture itself (dxcam hands over a ready frame; its copy is in `resize`), the key driver thread,
ticks.jsonl / frame writing. The game competes for the GPU live: live ticks run a little slower than this.
Live reference (runs/v2/press1, 2026-11-08): tick median 58 ms = 16.2 fps; gpu 15, world 10, self 7, camshift 6.
"""
import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / "tests" / "fixtures" / "perf_ant4"
BASELINE = ROOT / "tests" / "perf_baseline.json"
ANT4 = 10005063                       # Dungeon / Ant Tunnel IV (the fixture's map)
SCREEN = (2560, 1440)                 # the user's capture size: `resize` times capture.normalize from it
WARMUP = 5                            # frames not counted (first CUDA calls, tracker start)


def machine() -> str:
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no cuda"
    except ImportError:
        gpu = "no torch"
    return f"{platform.node()} | {gpu}"


def build(map_id: int):
    """The live rig for `map_id` (runner._load_map with --gpu --tracker), a Perceiver, SelfTracker and BrainV2."""
    from maplebrain.brain.brain_v2 import BrainV2
    from maplebrain.config import Config
    from maplebrain.humanize import Humanizer
    from maplebrain.nav.selfstate import SelfTracker
    from maplebrain.perception.liedetector import LieDetector
    from maplebrain.perception.perceiver import Perceiver
    from maplebrain.runtime.runner import ASSETS, Rig, _load_map
    cfg = Config()
    cfg.perception.gpu = cfg.perception.tracker = True
    cfg.perception.sprite_score = 0.70
    cfg.brain = "v2"
    hz = Humanizer(cfg.humanize.jitter, 1)
    rig = Rig(cfg, hz, None, None, None, LieDetector.load(ASSETS), np.load(ASSETS / "self_tag_gray.npy"))
    if not _load_map(rig, map_id, lambda msg: None):
        raise RuntimeError(f"map {map_id} not in assets")
    per = Perceiver(cfg, rig.self_tag, rig.sprites, lie_detector=rig.lie, locator=rig.locator)
    nav = rig.locator.navmap
    return per, SelfTracker(nav, cfg.nav), BrainV2(cfg, nav, hz), rig


def bench(frames: list, map_id: int = ANT4) -> dict:
    """Median / p90 ms per part over `frames` (paths, in order), and the tick total -> fps."""
    from maplebrain.capture import normalize
    from maplebrain.nav.sim import SimDriver
    per, me, brain, rig = build(map_id)
    drv = SimDriver()
    imgs = [cv2.imread(str(p)) for p in frames]
    big = cv2.resize(imgs[0], SCREEN)                              # what dxcam hands over on the user's screen
    rows = []
    t = 0.0
    for i, img in enumerate(imgs):
        t += 0.06
        t0 = time.perf_counter()
        normalize(big)
        t1 = time.perf_counter()
        obs = per.observe(img, t)
        t2 = time.perf_counter()
        drv.keys(t)
        s = me.update(t, obs.me_map, obs.map_pos, drv.want)
        brain.step(t, obs, s, drv)
        t3 = time.perf_counter()
        if i >= WARMUP:
            rows.append({"resize": 1000 * (t1 - t0), "perceive": 1000 * (t2 - t1), "brain": 1000 * (t3 - t2),
                         "tick": 1000 * (t3 - t0), **{f"p.{k}": v for k, v in (per.parts or {}).items()}})
    keys = sorted({k for r in rows for k in r})
    out = {}
    for k in keys:
        v = sorted(r.get(k, 0.0) for r in rows)
        out[k] = {"p50": round(statistics.median(v), 1), "p90": round(v[int(0.9 * (len(v) - 1))], 1)}
    out["fps"] = round(1000 / out["tick"]["p50"], 1)
    out["frames"] = len(rows)
    out["machine"] = machine()
    return out


def fixture_frames() -> list:
    return sorted(FIXTURE.glob("*.jpg"))


def report(r: dict, base: dict | None = None) -> str:
    parts = sorted(((k[2:], v["p50"]) for k, v in r.items() if k.startswith("p.")), key=lambda kv: -kv[1])
    line = (f"bot speed (replay, {r['frames']} frames): {r['fps']} fps, tick {r['tick']['p50']} ms "
            f"(p90 {r['tick']['p90']}) = resize {r['resize']['p50']} + perceive {r['perceive']['p50']} "
            f"[{', '.join(f'{k} {v}' for k, v in parts)}] + brain {r['brain']['p50']}")
    if base:
        line += f" | baseline {base['fps']} fps, tick {base['tick']['p50']} ms ({base.get('date', '?')})"
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=Path, default=None)
    ap.add_argument("--map", type=int, default=ANT4)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--baseline", action="store_true", help="write the result as this machine's baseline")
    ap.add_argument("--json", action="store_true", help="print only the result as JSON (tests/test_perf.py)")
    a = ap.parse_args()
    frames = sorted(a.frames.glob("*.jpg"))[:a.n] if a.frames else fixture_frames()
    r = bench(frames, a.map)
    if a.json:
        print(json.dumps(r))
        return
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    print(report(r, base))
    if a.baseline:
        r["date"] = time.strftime("%Y-%m-%d")
        BASELINE.write_text(json.dumps(r, indent=1))
        print(f"baseline written: {BASELINE}")


if __name__ == "__main__":
    main()
