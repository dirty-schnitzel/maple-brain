"""Behaviour profile of a recorded hunt: input rates, repetition, idle time - what a bot detector could see.
Usage: python tools/session_profile.py runs/manual/<hunt>"""
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))          # run as a plain script too
from maplebrain.config import Keys

SWING_KEYS = Keys().swing_keys

d = sys.argv[1]
ts = [json.loads(l) for l in open(f"{d}/ticks.jsonl", encoding="utf-8")]
T = ts[-1]["obs"]["t"] - ts[0]["obs"]["t"]
mins = T / 60
held, presses, holds = None, Counter(), Counter()
idle, walking, attacking = 0.0, 0.0, 0.0
taps_dur = Counter()
for a, b in zip(ts, ts[1:]):
    dt = b["obs"]["t"] - a["obs"]["t"]
    for act in a["actions"]:
        m = re.match(r"(\w+)\((.*)\)", act)
        k, arg = (m.group(1), m.group(2)) if m else (act, "")
        if k == "Hold":
            if held != arg:
                holds[arg] += 1
            held = arg
        elif k == "Release":
            held = None
        elif k == "Tap":
            key, secs = arg.split(",")
            presses[key] += 1
            taps_dur[(key, secs)] += 1
            if key in ("left", "right"):
                held = None
    if held in ("left", "right"):
        walking += dt
    elif held in SWING_KEYS:
        attacking += dt
    elif held is None:
        idle += dt
log = open(f"{d}/log.txt", encoding="utf-8").read().splitlines()
ev = Counter(re.sub(r"[-+]?\d+(\.\d+)?", "#", l.split("s ", 1)[1])[:60] for l in log if re.match(r"\s*\d", l) and "s " in l)
kills = [float(l.split("s")[0]) for l in log if "kill confirmed" in l]
gaps = [b - a for a, b in zip(kills, kills[1:])]
print(f"{d}: {T/60:.1f} min, {len(ts)} ticks")
print(f"time walking {walking/T:.0%}, attacking {attacking/T:.0%}, nothing held {idle/T:.0%}")
print("new holds / min:", {k: round(v / mins, 1) for k, v in holds.items()})
print("taps / min:", {k: round(v / mins, 1) for k, v in presses.items()})
print("tap kinds (key, secs):", taps_dur.most_common(8))
print(f"kills {len(kills)} = {len(kills)/mins:.1f}/min; gap median {st.median(gaps):.1f}s, CV {st.pstdev(gaps)/st.mean(gaps):.2f}")
print("top events:")
for k, v in ev.most_common(18):
    print(f"  {v:5d}  {k}")
