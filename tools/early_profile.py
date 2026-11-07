"""Behaviour in the first N seconds of runs (what preceded the Lie Detectors). usage: early_profile.py N RUN..."""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # run as a plain script too
from maplebot.config import Keys

SWING_KEYS = Keys().swing_keys
N = float(sys.argv[1])
print(f"{'run':14s} {'Z':>4s} {'Zmax5s':>6s} {'bursts':>6s} {'turns':>5s} {'walk>2s':>7s} {'farEng':>6s} {'swingS':>6s} {'stepbk':>6s} {'stand%':>6s} {'kills':>5s} {'map':>4s}")
for run in sys.argv[2:]:
    T = [json.loads(l) for l in open(Path("runs") / run / "ticks.jsonl", encoding="utf-8")]
    T = [k for k in T if k["obs"]["t"] <= N]
    t0 = T[0]["obs"]["t"]
    zs, holds, turns, last_dir, walk_start, long_walks, swing, stand = [], [], 0, None, None, 0, 0.0, 0.0
    held = None
    for a, b in zip(T, T[1:]):
        dt = b["obs"]["t"] - a["obs"]["t"]
        for act in a["actions"]:
            if act.startswith("Tap(z"):
                zs.append(a["obs"]["t"])
            if act.startswith("Hold("):
                k = act[5:-1]
                if k in ("left", "right") and k != last_dir:
                    if last_dir is not None:
                        turns += 1
                    last_dir = k
                held = k
            if act == "Release()":
                held = None
        if held in ("left", "right"):
            walk_start = walk_start if walk_start is not None else a["obs"]["t"]
        else:
            if walk_start is not None and a["obs"]["t"] - walk_start > 2.0:
                long_walks += 1
            walk_start = None
        swing += dt if held in SWING_KEYS else 0
        stand += dt if held is None else 0
    dur = T[-1]["obs"]["t"] - t0
    zmax = max((sum(1 for z in zs if s <= z < s + 5) for s in zs), default=0)
    bursts = sum(1 for i, z in enumerate(zs) if i == 0 or z - zs[i - 1] > 0.5)
    log = open(Path("runs") / run / "log.txt", encoding="utf-8").read()
    early = [l for l in log.splitlines() if (m := re.match(r"\s*([\d.]+)s", l)) and float(m.group(1)) <= N]
    far = sum(1 for l in early if (m := re.search(r"SEEK -> ENGAGE.*dx ([+-]\d+)", l)) and abs(int(m.group(1))) > 300)
    kills = sum("kill confirmed" in l for l in early)
    mp = re.search(r"map (\d+):", log)
    print(f"{run:14s} {len(zs):4d} {zmax:6d} {bursts:6d} {turns:5d} {long_walks:7d} {far:6d} {swing/dur:6.0%} {sum('step back' in l for l in early):6d} {stand/dur:6.0%} {kills:5d} {mp.group(1) if mp else '-':>4s}")
